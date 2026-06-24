#!/usr/bin/env python3
# ============================================================================
# touchstone/autonomy.py  ——  自动放行达标路径（设计 §4.7）
# ----------------------------------------------------------------------------
# 可选路径（默认关）：开启后才替人点合并。第一原则：授权自动放行的【不是委员会的
# 意见，而是汇总状态检查（质量门禁）的通过】。多闸串联、默认全关、经验门控、熔断保障。
#   decide_auto_merge：质量门禁绿 + 委员会无拦截 + 反馈循环收敛 + 未熔断 + 类已达标 + 总开关
#   经验层：change_class 签名 + build_experience + graduate_classes（与 §4.4 固化同构）
#   安全自举：影子(shadow) → 毕业(graduate) → 实放(live)
#   execute_auto_merge：调 merge API 并打 auto_handled marker 供校准归因
# 默认 AUTONOMY_ENABLED 关 → 放行 0 个。
# ============================================================================

import json
import os
import urllib.request


def _envbool(k):
    return os.environ.get(k, "").lower() in ("1", "true", "yes", "on")


AUTONOMY_ENABLED = _envbool("AUTONOMY_ENABLED")       # 总开关，默认关
AUTONOMY_SHADOW = _envbool("AUTONOMY_SHADOW")         # 影子模式，默认关
GRAD_MIN_SAMPLES = int(os.environ.get("GRAD_MIN_SAMPLES", "20"))
GRAD_MAX_BAD_RATE = float(os.environ.get("GRAD_MAX_BAD_RATE", "0.05"))


# --- 变更分类签名（经验在此粒度累积/毕业）------------------------------------
def file_profile(changed_files):
    kinds = set()
    for f in changed_files or []:
        base = os.path.basename(f)
        if f.endswith(".md") or "/docs/" in f or f.startswith("docs/"):
            kinds.add("doc")
        elif "test" in base.lower() or "/test/" in f or "/tests/" in f or "src/test/" in f:
            kinds.add("test")
        else:
            kinds.add("code")
    if not kinds:
        return "empty"
    if kinds == {"doc"}:
        return "docs_only"
    if kinds == {"test"}:
        return "test_only"
    if kinds == {"code"}:
        return "code"
    return "mixed"


def change_class(risk, findings, changed_files, rule_index=None):
    rule_index = rule_index or {}
    cats = sorted({(f.get("category") or rule_index.get(f.get("rule_id"), {}).get("category"))
                   for f in (findings or [])} - {None})
    blast = ",".join(risk.get("blast_radius") or []) or "none"
    return f"{risk.get('risk_band')}|{file_profile(changed_files)}|{','.join(cats) or 'none'}|{blast}"


# --- 经验层：累积与毕业（与 §4.4 promote_to_gate 同构）----------------------
def build_experience(merge_records):
    """merge_records: [{change_class, auto_eligible, reverted, hotfixed, human_override}]
    仅 auto_eligible(本会被自动放行)的样本计入；坏结局=被 revert 或 hotfix。"""
    acc = {}
    for m in merge_records or []:
        if not m.get("auto_eligible"):
            continue
        c = acc.setdefault(m.get("change_class"), {"samples": 0, "bad": 0, "overrides": 0})
        c["samples"] += 1
        if m.get("reverted") or m.get("hotfixed"):
            c["bad"] += 1
        if m.get("human_override"):
            c["overrides"] += 1
    for v in acc.values():
        v["bad_rate"] = round(v["bad"] / v["samples"], 3) if v["samples"] else 0.0
    return acc


def graduate_classes(experience, min_samples=None, max_bad_rate=None):
    min_samples = GRAD_MIN_SAMPLES if min_samples is None else min_samples
    max_bad_rate = GRAD_MAX_BAD_RATE if max_bad_rate is None else max_bad_rate
    return {c for c, v in (experience or {}).items()
            if v["samples"] >= min_samples and v["bad_rate"] <= max_bad_rate}


# --- 自动放行判据（可选路径，默认关）------------------------------------------
def decide_auto_merge(risk, findings, loop_decision, gate,
                      autonomy_state, graduated_classes, cls,
                      enabled=None, shadow=None):
    enabled = AUTONOMY_ENABLED if enabled is None else enabled
    shadow = AUTONOMY_SHADOW if shadow is None else shadow
    # 阻断否决（不再是委员会）：high 风险档或任一幸存 block_candidate 发现 → 否决（能拦、不能批）
    veto = (risk.get("risk_band") == "high") or \
           any(f.get("severity") == "block_candidate" for f in (findings or []))
    checks = {
        # 准入只看总闸：契约/确定性规则/(可选)verify 都已折进汇总状态检查，autonomy 不再自行判定质量门禁
        "quality_gate": gate == "success",
        "no_blocking_veto": not veto,
        "loop_converged": loop_decision == "converged",
        "not_tripped": not (autonomy_state or {}).get("tripped"),
        "class_graduated": cls in (graduated_classes or set()),
    }
    base = {"checks": checks, "change_class": cls,
            "failed": [k for k, v in checks.items() if not v]}
    if not enabled:
        return {"merge": False, "mode": "disabled",
                "reason": "AUTONOMY_ENABLED 关（默认）→ 回落到人", **base}
    if base["failed"]:
        return {"merge": False, "mode": "shadow" if shadow else "live",
                "reason": "未过闸：" + ",".join(base["failed"]) + " → 回落到人", **base}
    if shadow:
        return {"merge": False, "mode": "shadow", "would_merge": True,
                "reason": "影子模式：各闸通过，本会自动放行（未执行，记证据）", **base}
    return {"merge": True, "mode": "live", "reason": "各闸通过 → 自动放行", **base}


# --- 执行（merge API 集成点；打 auto_handled marker 供校准归因）----------------
def execute_auto_merge(repo, pr_number, sha, token, api_url=None, merge_method="squash"):
    api = (api_url or os.environ.get("GITHUB_API_URL", "https://api.github.com")).rstrip("/")
    hdr = {"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
           "Content-Type": "application/json"}

    def _req(method, path, payload):
        req = urllib.request.Request(api + path, data=json.dumps(payload).encode("utf-8"),
                                     method=method, headers=hdr)
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))

    merged = _req("PUT", f"/repos/{repo}/pulls/{pr_number}/merge",
                  {"sha": sha, "merge_method": merge_method})
    marker = json.dumps({"auto_handled": True, "sha": sha})
    _req("POST", f"/repos/{repo}/issues/{pr_number}/comments",
         {"body": f"<!-- touchstone:auto_handled {marker} -->\n"
                  "Touchstone 自动放行：质量门禁通过 + 变更分类已达标 + 各闸通过。"})
    return merged


# --- Actions 闭环：组装决策输入 / 从历史重建经验与达标类 ----------------------
def build_decision_inputs(touchstone_out, autonomy_state, graduated_classes):
    """把 touchstone-findings.json（含总闸结论 gate）+ 熔断态 + 达标类 → decide_auto_merge 入参。纯函数。"""
    return {
        "risk": touchstone_out.get("risk", {}),
        "findings": touchstone_out.get("findings", []),
        "loop_decision": touchstone_out.get("loop_decision"),
        "gate": touchstone_out.get("gate"),
        "autonomy_state": autonomy_state,
        "graduated_classes": list(graduated_classes or []),
        "cls": touchstone_out.get("change_class"),
    }


def reconstruct_auto_eligible(record):
    """从历史 marker/记录重建【委员会侧】放行资格（质量门禁/熔断在放行时另判）：
    非否决(非 high 档且无 block_candidate) ∧ 闭环收敛 ∧ 契约净。"""
    findings = record.get("findings", [])
    veto = (record.get("risk_band") == "high") or \
           any(f.get("severity") == "block_candidate" for f in findings)
    contract_clean = not any(f.get("agent") == "contract-check" for f in findings)
    return (not veto) and record.get("loop_decision") == "converged" and contract_clean


def experience_record(record, reverted=False, hotfixed=False):
    return {"change_class": record.get("change_class"),
            "auto_eligible": reconstruct_auto_eligible(record),
            "reverted": reverted, "hotfixed": hotfixed}


def graduate_from_calibration(records, reverted_shas=None):
    """校准记录(含 change_class/loop_decision/findings/merge_commit_sha) + revert 集
    → 经验库 → 达标变更分类集合。影子累积：只数 auto_eligible 的人合并样本。"""
    reverted_shas = set(reverted_shas or [])
    recs = [experience_record(r, reverted=(r.get("merge_commit_sha") in reverted_shas))
            for r in records if r.get("merged")]
    return graduate_classes(build_experience(recs))


def _load(path):
    try:
        return json.load(open(path, encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def main():
    import argparse
    ap = argparse.ArgumentParser(prog="touchstone.autonomy")
    ap.add_argument("--inputs", help="显式决策输入 JSON（测试/手动用）")
    ap.add_argument("--execute", action="store_true", help="merge=true 时真执行")
    ap.add_argument("--graduate", action="store_true",
                    help="从 calibration.json 重建经验、写 graduated-classes.json")
    args = ap.parse_args()

    # 模式一：发布达标变更分类（govern 定时任务用）
    if args.graduate:
        cal = _load("calibration.json") or {}
        grad = sorted(graduate_from_calibration(cal.get("records", [])))
        with open("graduated-classes.json", "w", encoding="utf-8") as f:
            json.dump({"graduated_classes": grad}, f, ensure_ascii=False, indent=2)
        print(f"[autonomy] 达标变更分类 {len(grad)}：{grad}")
        return

    # 模式二：决策（+ 可选执行）
    if args.inputs and os.path.exists(args.inputs):
        d = _load(args.inputs) or {}
        cls = d.get("cls") or change_class(d.get("risk", {}), d.get("findings", []),
                                           d.get("changed_files", []), d.get("rule_index", {}))
        repo, pr, sha = d.get("repo"), d.get("pr"), d.get("sha")
    else:
        co = _load("touchstone-findings.json")
        if not co:
            print("[autonomy] 无 touchstone 产物；no-op（默认不放行）")
            return
        d = build_decision_inputs(
            co,
            {"tripped": os.environ.get("AUTONOMY_TRIPPED") == "true"},
            (_load("graduated-classes.json") or {}).get("graduated_classes", []))
        cls = d["cls"]
        repo = os.environ.get("GITHUB_REPOSITORY")
        pr, sha = co.get("pr"), co.get("sha")

    dec = decide_auto_merge(d.get("risk", {}), d.get("findings", []), d.get("loop_decision"),
                            d.get("gate"), d.get("autonomy_state"),
                            set(d.get("graduated_classes", [])), cls)
    print(json.dumps(dec, ensure_ascii=False))
    if dec["merge"] and args.execute and repo and pr and sha:
        execute_auto_merge(repo, pr, sha, os.environ["GITHUB_TOKEN"])
        print("[autonomy] 已自动放行（auto_handled）")


if __name__ == "__main__":
    main()
