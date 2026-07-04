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
import re
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
import checklist as checklist_mod   # 收敛清单（修订设计 §4.3，评审意见 1、3）
import lineage               # 轮次台账与同源检测（修订设计 §4.4，评审意见 10）

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
_TEMPLATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "templates", "review_report.md")


def _load_template():
    """读七段版面模板（修订设计 §3 意见 4）。模板是设计资产：代码只填充，不定义版面。
    读取失败退回极简版面（防模板缺失把评审主链打断），并在 stderr 留痕。"""
    try:
        with open(_TEMPLATE_PATH, encoding="utf-8") as f:
            return f.read()
    except OSError as e:
        print(f"[warn] 版面模板读取失败（{e}），使用内置极简版面", file=sys.stderr)
        return "{{banner}}\n\n{{summary_line}}\n\n{{facts}}\n\n{{findings}}\n\n{{checklist}}\n\n{{verification}}\n\n{{markers}}"


def render_facts(scope_facts, gate_line="", lineage=None):
    """③ 确定性事实区：范围事实摘要（机器实测的修改范围，给人第一眼）+ 门禁状态 + 同源提示。
    与 author 的提交契约声明并排对照——声明是索引，这里是事实。"""
    if not scope_facts:
        return ""
    lines = ["**确定性事实**（机器实测，不经模型）："]
    if not scope_facts.get("parse_ok", True):
        lines.append(f"- ⚠️ {scope_facts.get('parse_warning', 'diff 解析失败：范围事实未生效')}")
        return "\n".join(lines)
    t = scope_facts.get("totals", {})
    lines.append(f"- 修改范围：{t.get('files', 0)} 个文件 · +{t.get('added', 0)} / -{t.get('deleted', 0)} 行")
    hits = scope_facts.get("sensitive_hits", [])
    if hits:
        by_rule = {}
        for h in hits:
            by_rule.setdefault(h["rule"], []).append(h["path"])
        for rule, paths in sorted(by_rule.items()):
            shown = ", ".join(f"`{p}`" for p in paths[:5]) + ("…" if len(paths) > 5 else "")
            lines.append(f"- 敏感路径命中（{rule}）：{shown}")
    else:
        lines.append("- 敏感路径命中：无")
    if gate_line:
        lines.append(f"- 门禁状态：{gate_line}")
    if lineage and lineage.get("lineage"):
        hist = "、".join(f"#{e['number']}" for e in lineage["lineage"])
        lines.append(f"- ⚠️ 同源提示：与已关闭的 {hist} 内容同源，历史已消耗 "
                     f"{lineage.get('rounds_spent', 0)} 轮、继承未销项 "
                     f"{len(lineage.get('inherited_open_items', []))} 条，剩余轮次 "
                     f"{lineage.get('rounds_left')}（重置需 `rounds-reset` label）")
    return "\n".join(lines)


def render_findings(risk, findings):
    """①横幅要素 + ④逐条发现。每条按「定位 · 方向 · 依据 · 达成判据」四要素呈现
    （修订设计 §3 意见 2、4）——不再输出补丁/精确指令。"""
    _RISK_LABELS = {"high": "HIGH · 建议人细看/仲裁", "mid": "MID · 建议人过目",
                    "low": "LOW · 可跳过"}
    label = _RISK_LABELS.get(risk.get("risk_band"), "UNKNOWN · 待人工定性")
    head = [
        "**Touchstone · ADVISORY**（不拦截合入，与人工审核并行）",
        "",
        f"风险等级：**{label}**　建议动作：`{risk['human_action']}`　"
        f"验证建议：`{risk['verification_decision']}`",
    ]
    if risk["blast_radius"]:
        head.append("影响面：" + ", ".join(risk["blast_radius"]))
    body = []
    if not findings:
        body.append("本次未发现规则范围内的问题。")
    else:
        from llm_budget import MAX_FINDINGS_IN_SUMMARY
        shown = findings[:MAX_FINDINGS_IN_SUMMARY]
        body.append(f"发现 {len(findings)} 条（按置信降序，"
                    + (f"仅列前 {MAX_FINDINGS_IN_SUMMARY} 条）：" if len(findings) > MAX_FINDINGS_IN_SUMMARY
                       else "全部）："))
        for f in shown:
            direction = f.get("fix_direction") or f.get("suggested_fix") or ""
            reasoning = f.get("fix_reasoning") or ""
            dc = f.get("done_criteria") or {}
            _spec = dc.get("spec") or {}     # spec 可能为 None（评审意见 PRA 防空）
            if dc.get("kind") == "deterministic":
                dc_line = f"规则 `{_spec.get('recheck', '?')}` 复检不再命中"
            elif dc.get("kind") == "review":
                dc_line = _spec.get("question", "定向复核通过")
            else:
                dc_line = ""
            entry = (f"- `{f['rule_id']}` [{f.get('severity','')}] "
                     f"conf={f['confidence']:.2f} · {f['agent']} · "
                     f"`{f.get('file','?')}:{f.get('line','?')}`\n"
                     f"  - 问题：{f.get('rationale','')}\n"
                     f"  - 方向：{direction}")
            if reasoning and reasoning != f.get("rationale"):
                entry += f"\n  - 依据：{reasoning}"
            if dc_line:
                entry += f"\n  - 达成判据：{dc_line}"
            body.append(entry)
        if len(findings) > MAX_FINDINGS_IN_SUMMARY:
            body.append(f"- ……另有 {len(findings) - MAX_FINDINGS_IN_SUMMARY} 条（确定性核对已覆盖全文，见 check 标题/总闸）。")
    return "\n".join(head), "\n".join(body)


def render_report(risk, findings, banner="", scope_facts=None, checklist_md="",
                  verification_md="", markers="", gate_line="", lineage=None):
    """按七段版面模板填充评审报告（修订设计 §3 意见 4）。版面由模板唯一定义。"""
    head, findings_md = render_findings(risk, findings)
    summary_line = head          # ①横幅与②总结共用要素：风险与建议动作即一句话结论
    parts = {
        "banner": banner or "",
        "summary_line": summary_line,
        "facts": render_facts(scope_facts, gate_line, lineage) if scope_facts else "",
        "findings": findings_md,
        "checklist": checklist_md or "",
        "verification": verification_md or "",
        "markers": markers or "",
    }
    out = _load_template()
    for k, v in parts.items():
        out = out.replace("{{" + k + "}}", v)
    # 折叠空段落留下的多余空行；剥掉模板头部注释（HTML 注释会带进评论——只保留 marker 类注释）
    out = re.sub(r"<!-- =+\n.*?=+ -->\n?", "", out, flags=re.S)
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    return out


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
                            f"\n方向：{f.get('fix_direction') or f.get('suggested_fix', '')}\n{_fm(f)}"})
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


def _run_link():
    """构造本次 workflow run 的链接（Actions 自动注入的 env）。用于在评审评论里指向
    pr-agent-interaction artifact（完整 LLM 交互日志）。非 Actions 环境返回空。"""
    run_id = os.environ.get("GITHUB_RUN_ID")
    if not run_id:
        return ""
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not repo:
        return ""
    return f"{server}/{repo}/actions/runs/{run_id}"


def _engine_banner(engine_status):
    """评审引擎降级的人可见说明（防静默故障）。贴在评审评论顶部 + check-run 标题里。"""
    if engine_status == "no_engine":
        return ("⚠️ **AI 评审未运行**：PR-Agent 未安装或不可用，本次评审**只含确定性契约与栈规则核对**，"
                "不含 LLM 代码评审。请确认 workflow 安装了 pr-agent（见 README「GitHub 集成」）。")
    if engine_status == "provider_failed":
        return ("⚠️ **AI 评审取 PR 失败**：PR-Agent 已启动但无法获取该 PR（git provider/凭据/网络），"
                "本次**只含确定性核对**。请检查 pr-agent 的 GitHub token（`GITHUB_TOKEN`）与 "
                "`git_provider` 配置。")
    if engine_status == "llm_failed":
        return ("⚠️ **AI 评审的 LLM 调用失败**：PR-Agent 已运行但 LLM 端点未成功响应，本次**只含确定性核对**。"
                "请检查 `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` 配置与端点可达性。")
    return ""


def _clean_review_trace(engine_status, ai_raw_count, added_lines, n_changed):
    """0 条发现时的溯源（防静默故障）：让人区分"LLM 真审了没问题"与"pr-agent 没真审/被过滤光"。
    仅在引擎正常（ok）且无降级时输出；降级由 _engine_banner 负责。"""
    if engine_status != "ok":
        return ""
    suspicious = added_lines >= 20 and ai_raw_count == 0   # 改动不小却 0 原始建议
    head = "🟢 **AI 评审已端到端运行**（PR-Agent + LLM 已调用，非模板空回）。"
    detail = f"PR-Agent 返回 **{ai_raw_count} 条原始建议**（归一后 0 条进入评审）；确定性契约/栈核对 0 命中。"
    scope = f"改动：{n_changed} 文件 / 约 {added_lines} 新增行。"
    tail = ("**改动不小却 0 建议——建议人工扫一眼**（LLM 可能未实质产出）。" if suspicious
            else "改动规模小，0 建议合理。")
    return f"{head}　{detail}　{scope}　{tail}"


def post_results(owner, repo, number, head_sha, token, risk, findings, loop_info=None,
                 change_class=None, diff=None, injected_types=None, injected_experience_ids=None,
                 engine_status="ok", det_warning="", ai_raw_count=0, added_lines=0, n_changed=0,
                 scope_facts=None, checklist_md="", ledger=None):
    # (1) 摘要评论——总是成功；按七段版面模板组装（修订设计 §3 意见 4）：
    #     ①横幅(降级说明/0-发现溯源/循环状态) ②总结 ③确定性事实 ④逐条发现 ⑤收敛清单 ⑥验证 ⑦机器 marker
    banner = _engine_banner(engine_status)
    if det_warning:
        banner = (banner + "\n\n" if banner else "") + f"⚠️ **{det_warning}**"
    # 引擎正常但 0 发现时，附溯源——让人能区分"LLM 真审了没问题"与"没真审"（防静默故障）
    if not banner and not findings:
        banner = _clean_review_trace(engine_status, ai_raw_count, added_lines, n_changed)
    markers = []
    if loop_info:
        decision, reason, marker = loop_info
        head = {"continue": "🔁 继续", "converged": "✅ 收敛",
                "escalate": "⬆️ 升级到人"}[decision]
        banner = f"**反馈循环：{head}** — {reason}" + ("\n\n" + banner if banner else "")
        markers.append(marker)
    verification_md = ""
    run_link = _run_link()
    if run_link:
        verification_md = f"📄 **完整 LLM 交互日志**（pr-agent 原始输出 / LLM 配置 / ping）：{run_link}"
    body = render_report(risk, findings, banner=banner, scope_facts=scope_facts,
                         checklist_md=checklist_md, verification_md=verification_md,
                         markers="\n".join(markers), lineage=ledger)
    # 机读 result marker（隐藏）——校准/自治经验从 API 重建数据的入口
    result_marker = "<!-- touchstone-result: " + json.dumps({
        "risk_band": risk["risk_band"],
        "verification_decision": risk["verification_decision"],
        "change_class": change_class,
        "loop_decision": (loop_info[0] if loop_info else None),
        "injected_types": injected_types,          # 本轮注入的经验类型（供 shadow A/B 分臂采集）
        "injected_experience_ids": injected_experience_ids,   # 本轮注入的经验【id】（单条归因/回退，见数据采集设计 取舍2）
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
                   "body": f"`{f['rule_id']}` {f.get('rationale','')}\n方向：{f.get('fix_direction') or f.get('suggested_fix','')}"
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
        flag = "⚠️ 评审降级 · " if (engine_status != "ok" or det_warning) else ""
        try:
            gh("POST", f"/repos/{owner}/{repo}/check-runs", token, {
                "name": "touchstone", "head_sha": head_sha, "status": "completed",
                "conclusion": "neutral",
                "output": {"title": f"{flag}风险等级 {risk['risk_band']} · {len(findings)} 条发现",
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
    changed_files, added = contract_check.parse_diff(diff)
    added_lines = sum(len(v) for v in added.values())
    ai_raw_count = 0
    max_lines = int(os.environ.get("TOUCHSTONE_MAX_DIFF_LINES", "0") or 0)
    size_findings = []
    if max_lines > 0 and added_lines > max_lines:
        engine_status = "skipped_large_diff"
        size_findings = [{
            "rule_id": "SIZE-001", "file": "", "line": 0,
            "category": "contract", "severity": "block_candidate",
            "confidence": 1.0,
            "rationale": f"PR 改动约 {added_lines} 行，超过单 PR 上限 {max_lines} 行。",
            "fix_direction": "请拆分为多个 PR，每个聚焦一个变更。",
            "fix_reasoning": "一次性提交大量代码增加评审难度与出错风险。",
            "done_criteria": {"kind": "deterministic", "spec": {"recheck": "SIZE-001"}},
            "suggested_fix": "请拆分为多个 PR，每个聚焦一个变更。",
            "agent": "contract-check",
        }]
        review_findings = []
    else:
        engine_status = "ok"
        try:
            raw_items = review_provider.fetch(pr, provider)
            ai_raw_count = len(raw_items)
            review_findings = review_provider.normalize(raw_items, nmap)
        except review_provider.ReviewEngineDegraded as e:
            engine_status = e.degraded
            print(f"[review_pr] 评审引擎降级（{e.degraded}）：{e.reason}", file=sys.stderr)
            review_findings = []
        except RuntimeError as e:
            engine_status = "no_engine"
            print(f"[review_pr] PR-Agent 不可用：{e}", file=sys.stderr)
            review_findings = []
    contract_findings = contract_check.check_contract_consistency(diff, contract or {}, rule_index)
    stack_findings = stack_rules.check_stack_rules(diff, rule_index)
    det_warning = contract_check._PARSE_WARNING or ""
    # 范围事实（修订设计 §4.1，评审意见 7）：确定性修改范围 + 仓级路径规则命中 + 内容指纹
    sf = contract_check.scope_facts(
        diff, contract_check.load_scope_rules(os.environ.get("REPO_DIR", ".")))
    findings, risk = review_provider.map_verdict(
        size_findings + review_findings + contract_findings + stack_findings, nmap,
        changed_files=changed_files, scope_facts=sf)
    return {"findings": findings, "risk": risk, "engine_status": engine_status,
            "det_warning": det_warning, "ai_raw_count": ai_raw_count,
            "added_lines": added_lines, "changed_files": changed_files,
            "scope_facts": sf}


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
    engine_status = _out.get("engine_status", "ok")
    det_warning = _out.get("det_warning", "")
    ai_raw_count = _out.get("ai_raw_count", 0)
    added_lines = _out.get("added_lines", 0)
    n_changed = len(_out.get("changed_files") or [])

    # 反馈循环：从历史评论 marker 取状态 → 决策 → 回贴附状态与新 marker。
    # 只信机器人自己发的评论（按发帖人过滤）——否则 author 可自己发伪造 marker 洗掉抗博弈闸。
    all_bodies = []          # 全量评论正文（含 author）——只用于解析 ack 申报（申报是输入信号）
    try:
        comments = gh("GET", f"/repos/{owner}/{repo}/issues/{number}/comments", token)
        comments = comments if isinstance(comments, list) else []
        all_bodies = [c.get("body", "") for c in comments]
        try:
            bot_login = (gh("GET", "/user", token) or {}).get("login")
        except (urllib.error.HTTPError, requests.exceptions.RequestException):
            bot_login = None
        if not bot_login:
            # GET /user 未返回身份（默认 GITHUB_TOKEN 常见）——不降级：trusted_bodies 改按
            # [bot] 后缀过滤（github-actions[bot]），防伪造仍生效（人无法注册 [bot] 后缀）。
            print("[info] GET /user 未返回身份：loop marker 改按 [bot] 后缀过滤（防伪造仍生效）",
                  file=sys.stderr)
        bodies = loop.trusted_bodies(comments, bot_login)
    except (urllib.error.HTTPError, requests.exceptions.RequestException):
        bodies = []
    state = loop.parse_latest_state(bodies)

    # 轮次台账（修订设计 §4.4，评审意见 10）：同源检测 + 历史继承。台账是增强，失败不阻塞。
    scope_facts = _out.get("scope_facts") or {}
    pr_labels = [l.get("name") for l in (pr.get("labels") or []) if isinstance(l, dict)]
    ledger = lineage.detect_lineage(
        scope_facts.get("fingerprint"), lambda m, p: gh(m, p, token),
        owner, repo, number, current_labels=pr_labels)

    # 收敛清单（修订设计 §4.3，评审意见 1、3）：上一轮权威清单（受信 marker）+ author 申报（ack，
    # 全量评论）→ 按达成判据复核销项 → 新一轮权威清单。首轮并入台账继承的历史未销项。
    prev_cl = checklist_mod.parse_latest(bodies)
    if prev_cl is None and ledger.get("inherited_open_items"):
        prev_cl = {"round": 0, "items": ledger["inherited_open_items"]}
    acks = checklist_mod.parse_acks(all_bodies)
    cur_cl = checklist_mod.reconcile(prev_cl, acks, findings, round_no=state.round + 1)
    checklist_mod.snapshot(cur_cl)          # 本轮快照写入文件（供可视化与校准回放）

    ci_pass = ci_verdict(owner, repo, head_sha, token)   # 供闭环：CI/verify 红则不收敛
    decision, reason, new_state = loop.loop_step(
        findings, rule_index, state, ci_passed=ci_pass,
        checklist_pair=(prev_cl, cur_cl), ledger=ledger)
    loop_info = (decision, reason, loop.render_marker(new_state))
    checklist_md = checklist_mod.render(
        cur_cl, rounds_left=max(0, ledger.get("rounds_left", loop.MAX_ROUNDS) - 1),
        lineage=ledger)

    # 变更分类（供自治经验层/auto_merge）：touchstone 侧此时已知 risk/findings/changed_files
    cls = autonomy.change_class(risk, findings, sorted(changed_files), rule_index)
    contract_clean = not any(f.get("agent") == "contract-check" for f in findings)

    # 本轮注入的经验类型（学习回路 active 经验）——写入 result marker，供未来 shadow A/B 分臂采集。
    # 与 review_provider._experience_injection 同源（只读经验库、失败即空）。
    injected_types, injected_experience_ids = [], []
    try:
        import learning_loop as _ll
        _store = _ll.load_store()
        injected_types = _ll.active_types(_store)
        injected_experience_ids = _ll.active_ids(_store)
    except Exception:
        injected_types, injected_experience_ids = [], []

    rd_path = os.environ.get("TOUCHSTONE_RDJSON_PATH")
    if rd_path:                       # 可选 reviewdog 后端：导出 RDFormat，行内投递交 reviewdog
        try:
            with open(rd_path, "w", encoding="utf-8") as _rf:
                json.dump(review_provider.to_rdjson(findings), _rf, ensure_ascii=False)
        except OSError as e:
            print(f"[warn] RDJSON 写出失败: {e}", file=sys.stderr)

    post_results(owner, repo, number, head_sha, token, risk, findings, loop_info, cls, diff,
                 injected_types=injected_types, injected_experience_ids=injected_experience_ids,
                 engine_status=engine_status, det_warning=det_warning,
                 ai_raw_count=ai_raw_count, added_lines=added_lines, n_changed=n_changed,
                 scope_facts=scope_facts, checklist_md=checklist_md, ledger=ledger)

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
