#!/usr/bin/env python3
# ============================================================================
# touchstone/govern.py  ——  治理：建议→拦截桥 + 熔断（设计 §4.4）
# ----------------------------------------------------------------------------
# promote_to_gate：把 machine_checkable + 复发 + 高采纳(强归因证实有害)的规则
#   提升为确定性闸(rule.enforced=true)。改单一事实源须以【提案】交人确认,不静默改。
# update_autonomy：用真实结果(git revert 强归因 + merge_commit_sha 匹配)算 revert 率，
#   越阈值则 tripped=收回自主、回落到人；touchstone 低风险比例突升 → 告警(疑似放水/被钻)。
# 两者均为周期性治理,消费 calibrate 产出的 calibration.json + git 历史。
# ============================================================================

import copy
import json
import os
import re
import subprocess
import sys

PROMOTE_MIN_FIRES = int(os.environ.get("PROMOTE_MIN_FIRES", "5"))
PROMOTE_MIN_ADOPTION = float(os.environ.get("PROMOTE_MIN_ADOPTION", "0.5"))
REVERT_THRESH = float(os.environ.get("REVERT_THRESH", "0.10"))
APPROVAL_SPIKE = float(os.environ.get("APPROVAL_SPIKE", "0.20"))


# --- 建议→拦截桥（纯）--------------------------------------------------------
def promote_to_gate(calibration_agg, rule_index,
                    min_fires=PROMOTE_MIN_FIRES, min_adoption=PROMOTE_MIN_ADOPTION):
    """候选 = machine_checkable AND 复发(fires≥N) AND 高采纳(人改动比例≥阈值)。
    高采纳是"证实有害"的强归因代理——与噪声检测(高命中低采纳)正好相反。"""
    out = []
    for rid, v in (calibration_agg.get("by_rule") or {}).items():
        rule = rule_index.get(rid, {})
        if not rule.get("machine_checkable") or rule.get("enforced"):
            continue
        adoption = v.get("adoption_rate")           # finding 级(更直接)；缺则回落 PR 级
        if adoption is None:
            adoption = v.get("changes_requested_rate")
        if v.get("fires", 0) >= min_fires and adoption is not None and adoption >= min_adoption:
            out.append({"rule_id": rid, "fires": v["fires"], "adoption": round(adoption, 2),
                        "severity": rule.get("severity"),
                        "reason": "machine_checkable + 复发 + 高采纳（强归因证实有害）"})
    return out


def apply_promotions(standards, candidates):
    """返回置了 enforced=true 的新 standards（深拷贝，不改原对象；供提案）。"""
    ids = {c["rule_id"] for c in candidates}
    new = copy.deepcopy(standards)
    for r in new.get("rules", []):
        if r.get("id") in ids:
            r["enforced"] = True
    return new


# --- 熔断（纯）---------------------------------------------------------------
def update_autonomy(merge_records, prior_approval_rate=None,
                    revert_thresh=REVERT_THRESH, spike=APPROVAL_SPIKE):
    """merge_records: [{auto_handled, reverted, hotfixed, touchstone_approved}]"""
    auto = [m for m in merge_records if m.get("auto_handled")]
    bad = sum(1 for m in auto if m.get("reverted") or m.get("hotfixed"))
    revert_rate = (bad / len(auto)) if auto else 0.0
    approved = sum(1 for m in merge_records if m.get("touchstone_approved"))
    approval_rate = (approved / len(merge_records)) if merge_records else 0.0
    drift = (approval_rate - prior_approval_rate) if prior_approval_rate is not None else None

    reasons, tripped = [], False
    if auto and revert_rate > revert_thresh:
        tripped = True
        reasons.append(f"自动处理 PR 的 revert/hotfix 率 {revert_rate:.2f} > {revert_thresh}")
    if drift is not None and drift > spike:
        reasons.append(f"touchstone 低风险(批准)比例突升 {drift:+.2f}（疑似放水/被钻，告警）")
    return {
        "tripped": tripped,
        "revert_rate": round(revert_rate, 2),
        "approval_rate": round(approval_rate, 2),
        "approval_drift": (None if drift is None else round(drift, 2)),
        "reasons": reasons,
        "recommended_action": ("收回自主：恢复人工把关 / 关闭低风险自动放行 / 取消 verify 的"
                               " required 自动放行" if tripped else "维持"),
    }


# --- 强归因 revert 检测（git）------------------------------------------------
def detect_revert_shas(repo_dir, base_ref, window=200):
    """从 base 分支日志里抓 'This reverts commit <sha>' 的被还原 sha 集合。"""
    try:
        out = subprocess.run(
            ["git", "-C", repo_dir, "log", f"-n{window}", "--grep=This reverts commit",
             "--pretty=%B", base_ref],
            capture_output=True, text=True, timeout=60).stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return set()
    return set(re.findall(r"This reverts commit ([0-9a-f]{7,40})", out))


def build_merge_records(calibration_records, revert_shas):
    """从 calibration 记录构造熔断输入。auto_handled/approved 取真实 marker（calibrate 从
    <!-- touchstone:auto_handled --> 重建），不再用 risk_band=='low' 代理——后者会把 autonomy
    关闭时的低风险人合 PR 误算成自动放行。hotfix 检测尚未接通（仅 git revert 是已接信号）。"""
    recs = []
    for r in calibration_records:
        if not r.get("merged"):
            continue
        auto = bool(r.get("auto_handled"))
        sha = (r.get("merge_commit_sha") or "")
        reverted = any(sha.startswith(s) or s.startswith(sha[:7]) for s in revert_shas if sha)
        recs.append({"pr": r.get("pr"), "auto_handled": auto, "touchstone_approved": auto,
                     "reverted": reverted, "hotfixed": False})
    return recs


# --- CLI ---------------------------------------------------------------------
def main():
    import yaml
    cal_path = os.environ.get("CALIBRATION_JSON", "calibration.json")
    std_path = os.environ.get("TOUCHSTONE_STANDARDS", ".touchstone/standards.yaml")
    if not os.path.exists(cal_path):
        sys.exit(f"未找到 {cal_path}（请先运行 calibrate.py）")
    cal = json.load(open(cal_path, encoding="utf-8"))
    standards = yaml.safe_load(open(std_path, encoding="utf-8"))
    rule_index = {r["id"]: r for r in standards.get("rules", [])}
    agg = cal.get("aggregate", {})
    records = cal.get("records", [])

    # 1) 建议→拦截桥：候选 + 提案（不静默改 SoT）
    cands = promote_to_gate(agg, rule_index)
    prop = ["# 固化提案（建议→拦截桥）", ""]
    if cands:
        prop.append("以下规则满足 machine_checkable + 复发 + 高采纳，建议固化为确定性闸"
                    "（enforced=true）。请人确认后合入 standards.yaml：")
        for c in cands:
            prop.append(f"- `{c['rule_id']}` fires={c['fires']} 采纳率={c['adoption']} — {c['reason']}")
        with open("standards.proposed.yaml", "w", encoding="utf-8") as f:
            yaml.safe_dump(apply_promotions(standards, cands), f, allow_unicode=True, sort_keys=False)
        prop.append("\n→ 已生成 standards.proposed.yaml（含 enforced=true），供 review。")
    else:
        prop.append("无达阈值的固化候选。")
    open("promotion-proposal.md", "w", encoding="utf-8").write("\n".join(prop))

    # 2) 熔断
    repo = os.environ.get("REPO_DIR", ".")
    base = os.environ.get("BASE_REF", "HEAD")
    reverts = detect_revert_shas(repo, base)
    merge_records = build_merge_records(records, reverts)
    prior = None
    if os.path.exists("autonomy-prev.json"):
        try:
            prior = json.load(open("autonomy-prev.json")).get("approval_rate")
        except (json.JSONDecodeError, KeyError):
            prior = None
    state = update_autonomy(merge_records, prior_approval_rate=prior)
    json.dump(state, open("autonomy-state.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    print("=== 固化提案 ===")
    print("\n".join(prop))
    print("\n=== 熔断状态 ===")
    print(json.dumps(state, ensure_ascii=False, indent=2))
    if state["tripped"]:
        print("\n⚠ 熔断触发 —— 建议收回自主权。", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
