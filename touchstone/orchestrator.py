#!/usr/bin/env python3
# ============================================================================
# touchstone/orchestrator.py  ——  Touchstone 主编排（评审复用 PR-Agent）
# ----------------------------------------------------------------------------
# 形态：advisory。只产出评分与发现、回贴到 PR，**绝不拦截合入**，与人工审核并行。
# 链路：load_standards/contract → get_pr_diff → review_provider.fetch(PR-Agent) → normalize
#        → map_verdict(按 category 定风险等级，不做共识) + contract_check(确定性契约一致性)
#        → 回贴(摘要 + 尽力内联 + 中性 check run) → 写 touchstone-findings.json
# 评审引擎复用开源 PR-Agent（见 docs/touchstone-on-pr-agent.html）；自研委员会已退役。
# touchstone 不再直接调 LLM——PR-Agent 自带端点配置；touchstone 只做归一/裁决/门禁/回贴。
# 依赖：GitHub 走 requests(ghclient)、diff 解析用 unidiff、配置 pyyaml。
#   GITHUB_API_URL  缺省 https://api.github.com；用 GitHub Enterprise 在此改。
# ============================================================================

import json
import os
import sys
import urllib.request
import urllib.error

import requests

import yaml

# 同目录模块：兼容"脚本运行(python touchstone/orchestrator.py)"与"包导入(touchstone.orchestrator)"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ghclient             # GitHub HTTP 客户端(requests)
import checks                # 可插拔检查框架 + 总闸
import loop                  # 反馈循环控制器
import contract_check        # 提交契约一致性核对（确定性）
import review_provider       # 评审提供器(复用 PR-Agent) + 发现归一 + 裁决映射
import autonomy              # 变更分类计算（供自治经验层/auto_merge 重建）
import stack_rules           # §4.1 栈专项确定性规则（machine_checkable 的 SPR/JAVA/CTR）

# --- 配置 ---------------------------------------------------------------------
STANDARDS_PATH = os.environ.get("TOUCHSTONE_STANDARDS", ".touchstone/standards.yaml")
CONTRACT_PATH  = os.environ.get("TOUCHSTONE_CONTRACT",  ".touchstone/pr.yaml")
DIFF_BUDGET    = 60000   # diff 截断字符预算

# --- GitHub API（stdlib） -----------------------------------------------------
def gh(method, path, token, data=None, accept="application/vnd.github+json"):
    base = os.environ.get("GITHUB_API_URL", "https://api.github.com")
    return ghclient.request(method, base + path, token, data=data, accept=accept)


# --- 输入加载 -----------------------------------------------------------------
def load_yaml(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_pr_diff(owner, repo, number, token):
    diff = gh("GET", f"/repos/{owner}/{repo}/pulls/{number}", token,
              accept="application/vnd.github.v3.diff")
    if len(diff) > DIFF_BUDGET:
        diff = diff[:DIFF_BUDGET] + "\n... [diff 已截断]"
    return diff


# --- 回贴 ---------------------------------------------------------------------
def render_summary(risk, findings):
    label = {"high": "HIGH · 建议人细看/仲裁", "mid": "MID · 建议人过目",
             "low": "LOW · 可跳过"}[risk["risk_band"]]
    lines = [
        "**Touchstone · ADVISORY**（不拦截合入，与人工审核并行）",
        "",
        f"风险等级：**{label}**　建议动作：`{risk['human_action']}`　"
        f"验证建议：`{risk['verification_decision']}`",
    ]
    if risk["blast_radius"]:
        lines.append("影响面：" + ", ".join(risk["blast_radius"]))
    lines.append("")
    if not findings:
        lines.append("本次未发现规则范围内的问题。")
    else:
        lines.append(f"发现 {len(findings)} 条（按置信降序）：")
        for f in findings:
            lines.append(
                f"- `{f['rule_id']}` [{f.get('severity','')}] "
                f"conf={f['confidence']:.2f} · {f['agent']} · "
                f"`{f.get('file','?')}:{f.get('line','?')}`\n"
                f"  - {f.get('rationale','')}\n"
                f"  - 建议：{f.get('suggested_fix','')}"
            )
    return "\n".join(lines)


def anchor_inline(findings, diff):
    """把发现锚到 PR diff 的可评论行(RIGHT 侧新增行)。
    - 行恰在新增行上 → 直接锚。
    - 行不在新增行上(如指向被删代码/上下文外) → 就近锚到同文件最近新增行，注明原行。
    - 该文件无任何新增行(纯删除/重命名) → 不内联(靠摘要覆盖)。
    GitHub 要求内联评论落在 diff 内的可评论行，否则整条 review 被拒。"""
    _, added = contract_check.parse_diff(diff or "")

    def _fm(f):
        return ("<!-- touchstone-finding: "
                + json.dumps({"rule_id": f.get("rule_id"), "agent": f.get("agent")},
                             ensure_ascii=False) + " -->")
    out = []
    for f in findings:
        path, line = f.get("file"), f.get("line")
        if not path or not line:
            continue
        addl = sorted(n for n, _ in added.get(path, []))
        if not addl:                       # 文件无新增行 → 降级，只进摘要
            continue
        if line in addl:
            anchored, note = line, ""
        else:                              # 就近锚定，并注明原始行号
            anchored = min(addl, key=lambda n: abs(n - line))
            note = f"（原指 :{line}）"
        out.append({"path": path, "line": anchored, "side": "RIGHT",
                    "body": f"`{f['rule_id']}`{note} {f.get('rationale', '')}"
                            f"\n建议：{f.get('suggested_fix', '')}\n{_fm(f)}"})
    return out


def ci_verdict(owner, repo, head_sha, token):
    """读 head 的 check-runs 总判定，供反馈循环判断 CI/verify 是否红。
    排除 touchstone 自身的 check（neutral·advisory，不参与）。
    返回 True=全绿/中性、False=有失败、None=仍有未完成或无数据（未知不强制 author 继续）。"""
    try:
        data = gh("GET", f"/repos/{owner}/{repo}/commits/{head_sha}/check-runs", token)
    except (urllib.error.HTTPError, requests.exceptions.RequestException):
        return None
    runs = [r for r in (data.get("check_runs") or [])
            if not str(r.get("name", "")).startswith("touchstone")]
    if not runs:
        return None
    if any(r.get("status") != "completed" for r in runs):
        return None                      # 还有未跑完 → 未知
    bad = {"failure", "timed_out", "cancelled", "action_required", "stale"}
    if any(r.get("conclusion") in bad for r in runs):
        return False
    return True


def post_results(owner, repo, number, head_sha, token, risk, findings, loop_info=None,
                 change_class=None, diff=None, injected_types=None):
    # (1) 摘要评论——总是成功；顶部附反馈循环状态，底部附隐藏 state marker
    body = render_summary(risk, findings)
    if loop_info:
        decision, reason, marker = loop_info
        head = {"continue": "🔁 继续", "converged": "✅ 收敛",
                "escalate": "⬆️ 升级到人"}[decision]
        body = f"**反馈循环：{head}** — {reason}\n\n{body}\n\n{marker}"
    # 机读 result marker（隐藏）——校准/自治经验从 API 重建数据的入口
    result_marker = "<!-- touchstone-result: " + json.dumps({
        "risk_band": risk["risk_band"],
        "verification_decision": risk["verification_decision"],
        "change_class": change_class,
        "loop_decision": (loop_info[0] if loop_info else None),
        "injected_types": injected_types,          # 本轮注入的经验类型（供未来 shadow A/B 分臂采集）
        "findings": [{"rule_id": f.get("rule_id"), "agent": f.get("agent"),
                      "severity": f.get("severity")} for f in findings],
    }, ensure_ascii=False) + " -->"
    body = body + "\n\n" + result_marker
    try:
        gh("POST", f"/repos/{owner}/{repo}/issues/{number}/comments", token, {"body": body})
    except (urllib.error.HTTPError, requests.exceptions.RequestException) as e:
        print(f"[warn] 摘要评论失败: {e}", file=sys.stderr)
    # (2) 尽力内联评论（event=COMMENT，绝不 REQUEST_CHANGES）
    #     锚定到 diff 可评论行（删除行/超界行就近锚或降级）；每条附自识别隐藏标记
    if diff is not None:
        inline = anchor_inline(findings, diff)
    else:
        def _finding_marker(f):
            return ("<!-- touchstone-finding: "
                    + json.dumps({"rule_id": f.get("rule_id"), "agent": f.get("agent")},
                                 ensure_ascii=False) + " -->")
        inline = [{"path": f["file"], "line": f["line"], "side": "RIGHT",
                   "body": f"`{f['rule_id']}` {f.get('rationale','')}\n建议：{f.get('suggested_fix','')}"
                           f"\n{_finding_marker(f)}"}
                  for f in findings if f.get("file") and f.get("line")]
    if inline:
        try:
            gh("POST", f"/repos/{owner}/{repo}/pulls/{number}/reviews", token,
               {"event": "COMMENT", "comments": inline})
        except (urllib.error.HTTPError, requests.exceptions.RequestException) as e:
            print(f"[info] 内联评论降级(行不在 diff 内属正常): {e}", file=sys.stderr)
    # (3) 中性 check run（advisory，永不 failure）
    if head_sha:
        try:
            gh("POST", f"/repos/{owner}/{repo}/check-runs", token, {
                "name": "touchstone", "head_sha": head_sha, "status": "completed",
                "conclusion": "neutral",
                "output": {"title": f"风险等级 {risk['risk_band']} · {len(findings)} 条发现",
                           "summary": body[:600]},
            })
        except (urllib.error.HTTPError, requests.exceptions.RequestException) as e:
            print(f"[info] check run 跳过: {e}", file=sys.stderr)


# --- main ---------------------------------------------------------------------
def review_pr(pr, contract, standards, provider=None):
    """§4.1 主入口：复用 PR-Agent 评审 → 发现归一 → 提交契约核对 + 栈专项确定性规则 → 裁决映射。
    等价于 map_verdict( normalize(fetch(pr)) + check_contract_consistency(...) + check_stack_rules(...) )。
    pr：上下文 dict（owner/repo/number/sha/token/diff/standards 等）；返回 {findings, risk}。
    评审层只产建议与风险分流，不产准入（准入只由质量门禁/总闸决定）。"""
    nmap = review_provider.load_nmap(os.environ.get("REPO_DIR", "."))
    rules = standards.get("rules", []) if isinstance(standards, dict) else (standards or [])
    rule_index = {r["id"]: r for r in rules}
    diff = pr.get("diff", "")
    try:
        review_findings = review_provider.normalize(review_provider.fetch(pr, provider), nmap)
    except RuntimeError as e:
        print(f"[review_pr] PR-Agent 端点未配置或不可用，跳过评审、仅跑确定性核对：{e}", file=sys.stderr)
        review_findings = []
    contract_findings = contract_check.check_contract_consistency(diff, contract or {}, rule_index)
    stack_findings = stack_rules.check_stack_rules(diff, rule_index)
    findings, risk = review_provider.map_verdict(
        review_findings + contract_findings + stack_findings, nmap)
    return {"findings": findings, "risk": risk}


def main():
    token = os.environ["GITHUB_TOKEN"]

    event = load_yaml(os.environ["GITHUB_EVENT_PATH"]) or {}
    pr = event.get("pull_request", {})
    number = pr.get("number")
    head_sha = pr.get("head", {}).get("sha")
    owner, repo = os.environ["GITHUB_REPOSITORY"].split("/", 1)
    if not number:
        sys.exit("非 PR 事件，跳过。")

    standards = load_yaml(STANDARDS_PATH)
    if not standards:
        sys.exit(f"未找到规范 {STANDARDS_PATH}")
    contract = load_yaml(CONTRACT_PATH)
    rule_index = {r["id"]: r for r in standards.get("rules", [])}

    diff = get_pr_diff(owner, repo, number, token)
    changed_files, _ = contract_check.parse_diff(diff)

    # 评审主链（§4.1）：PR-Agent 评审归一 + 契约核对 + 栈专项确定性规则 → 裁决映射
    pr_ctx_review = {"owner": owner, "repo": repo, "number": number, "sha": head_sha,
                     "token": token, "diff": diff, "standards": standards}
    _out = review_pr(pr_ctx_review, contract, standards)
    findings, risk = _out["findings"], _out["risk"]

    # 反馈循环：从历史评论 marker 取状态 → 决策 → 回贴附状态与新 marker（author 无法篡改轮次）
    try:
        comments = gh("GET", f"/repos/{owner}/{repo}/issues/{number}/comments", token)
        bodies = [c.get("body", "") for c in comments] if isinstance(comments, list) else []
    except (urllib.error.HTTPError, requests.exceptions.RequestException):
        bodies = []
    state = loop.parse_latest_state(bodies)
    ci_pass = ci_verdict(owner, repo, head_sha, token)   # 供闭环：CI/verify 红则不收敛
    decision, reason, new_state = loop.loop_step(findings, rule_index, state, ci_passed=ci_pass)
    loop_info = (decision, reason, loop.render_marker(new_state))

    # 变更分类（供自治经验层/auto_merge）：touchstone 侧此时已知 risk/findings/changed_files
    cls = autonomy.change_class(risk, findings, sorted(changed_files), rule_index)
    contract_clean = not any(f.get("agent") == "contract-check" for f in findings)

    # 本轮注入的经验类型（学习回路 active 经验）——写入 result marker，供未来 shadow A/B 分臂采集。
    # 与 review_provider._experience_injection 同源（只读经验库、失败即空）。
    injected_types = []
    try:
        import learning_loop as _ll
        injected_types = _ll.active_types(_ll.load_store())
    except Exception:
        injected_types = []

    post_results(owner, repo, number, head_sha, token, risk, findings, loop_info, cls, diff,
                 injected_types=injected_types)

    # 可插拔检查 → 对外发【一个】总闸状态（策略全在 .touchstone/checks.yaml）。
    # CI 中由独立 gate job 在(可选)verify 之后聚合并发布，此处置 TOUCHSTONE_SKIP_GATE 跳过自发、
    # 避免重复发；本地/dry-run（未设该环境变量）则就地计算并发布，行为不变。
    gate = None
    if os.environ.get("TOUCHSTONE_SKIP_GATE", "").lower() not in ("1", "true", "yes", "on"):
        try:
            chk_cfg = checks.load_config(os.environ.get("REPO_DIR", "."))
            # 确定性发现 = contract-check（scope/test/dup/untested/sec）+ touchstone-rules（CTR/SPR/JAVA）。
            # 注意：之前这里误引了未定义的 contract_findings（NameError，仅因 gate 路径少被走到而隐藏）。
            det_findings = [f for f in findings
                            if f.get("agent") in ("contract-check", "touchstone-rules")]
            pr_ctx = {"owner": owner, "repo": repo, "sha": head_sha, "token": token,
                      "files": sorted(changed_files), "contract_findings": det_findings}
            gate, _ = checks.post_gate(pr_ctx, chk_cfg, checks.run_checks(chk_cfg, pr_ctx))
        except (urllib.error.HTTPError, requests.exceptions.RequestException) as e:
            print(f"[info] 总闸跳过: {e}", file=sys.stderr)

    # 升级到人：打标签（best-effort）
    if decision == "escalate":
        try:
            gh("POST", f"/repos/{owner}/{repo}/issues/{number}/labels", token,
               {"labels": ["touchstone:needs-human"]})
        except (urllib.error.HTTPError, requests.exceptions.RequestException):
            pass

    # 校准 + 自治决策入口：落盘供下游 join / auto_merge 组装
    with open("touchstone-findings.json", "w", encoding="utf-8") as f:
        json.dump({"pr": number, "sha": head_sha, "risk": risk, "findings": findings,
                   "changed_files": sorted(changed_files), "loop_decision": decision,
                   "contract_clean": contract_clean, "change_class": cls,
                   "gate": gate},
                  f, ensure_ascii=False, indent=2)

    # 风险分流的 job 输出：供下游 verify job 决定是否触发验证
    gho = os.environ.get("GITHUB_OUTPUT")
    if gho:
        with open(gho, "a", encoding="utf-8") as f:
            f.write(f"verification_decision={risk['verification_decision']}\n")
            f.write(f"risk_band={risk['risk_band']}\n")
            f.write(f"loop_decision={decision}\n")

    print(f"[touchstone] 风险={risk['risk_band']} 发现={len(findings)} 条")


if __name__ == "__main__":
    main()
