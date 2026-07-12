#!/usr/bin/env python3
# ============================================================================
# touchstone/review_provider.py
#   "Touchstone on PR-Agent" 集成设计（docs/touchstone-on-pr-agent.html）的
#   评审路径骨架：把评审/聚合复用开源 PR-Agent，本系统只做归一 + 裁决映射。
#
#   评审提供器 fetch(pr_ctx) -> [ReviewItem]   —— 封装 PR-Agent 调用（CLI/API、公网或自托管端点）
#   发现归一 normalize(items, nmap) -> [Finding] —— PR-Agent 输出映射成本系统 Finding
#   裁决映射 map_verdict(findings) -> (findings, risk) —— 出三类判定/风险等级（不做共识）
#
# 实现状态（诚实标注）：orchestrator.py 已直连本模块（自研委员会已退役）——评审主链走
#   review_provider.fetch → normalize → map_verdict。PR-Agent 的真实端点调用需在你的部署环境
#   实现 PRAgentProvider._invoke_endpoint（CLI 子进程或 HTTP）；本文件可离线测：parse / normalize
#   / map_verdict 全是纯函数；fetch 支持把 PR-Agent 原始输出经 pr_ctx['pr_agent_output'] 注入。
#   REVIEW_PROVIDER 目前仅支持 "pr-agent"（默认）；端点未配置时 orchestrator 降级为只跑确定性核对。
# ============================================================================

import re
import json
import os
import shlex
import subprocess
import sys
import tempfile

import yaml

# ---- PR-Agent label → 本系统 category 的默认映射（可被 .touchstone/pr-agent.yaml 覆盖）----
# PR-Agent improve 工具的 label 取值见其 $PRCodeSuggestions schema。
_DEFAULT_NMAP = {
    "label_to_category": {
        "security": "security",
        "critical bug": "correctness",
        "possible bug": "correctness",
        "possible issue": "correctness_suspect",   # 弱信号：值得看一眼但不当已知缺陷
        "performance": "convention",
        "enhancement": "convention",
        "best practice": "convention",
        "maintainability": "convention",
        "typo": "convention",
        "general": "convention",
        "Organization best practice": "convention",   # 违反我们注入的 standards
    },
    "default_category": "convention",
    "default_severity": "warn",          # 顾问式：PR-Agent 建议一律 advisory，不产 block_candidate
    "default_confidence": 0.7,
    "discard_labels": [],
    "conf_min": 0.5,
    "high_categories": ["security", "correctness"],   # 命中才升 high；correctness_suspect 不在内→落 mid
}


class ReviewEngineDegraded(RuntimeError):
    """PR-Agent 评审引擎降级信号（防静默故障）。

    `degraded` ∈ {"no_engine", "llm_failed"}，由 `pr_agent_runner.run` 经 `_degraded` 字段上报、
    `_invoke_endpoint` 抛出；orchestrator 捕获后把对应说明写进贴到 PR 的人可见评审内容，
    而不是静默降级成"0 条发现"。子类 RuntimeError 以兼容既有宽泛捕获。"""
    def __init__(self, degraded, reason=""):
        super().__init__(f"{degraded}: {reason}")
        self.degraded = degraded
        self.reason = reason


# 可疑空收敛阈值（改动新增行 >= 此值 且 LLM 0 原始建议 -> 评审不可信）。
# 与 orchestrator._clean_review_trace 的 suspicious 判据同源；经 env 可调（如超大 PR 调参）。
_SUSPICIOUS_EMPTY_LINES = int(os.environ.get("TOUCHSTONE_SUSPICIOUS_EMPTY_LINES", "20") or 20)


def review_reliable(engine_status, ai_raw_count, added_lines, engaged=False):
    """本轮 LLM 评审是否可作为 checklist 销项 / loop 收敛 / autonomy 自动放行的可靠证据。

    不可靠（返回 False）的情形--都意味着"本轮 0 建议不代表代码没问题"：
      1. 引擎降级：engine_status != "ok"（no_engine/provider_failed/llm_failed/skipped_large_diff）。
         pr-agent 没真跑或 LLM 调用失败 -> 0 建议是缺审，非审完无问题。
      2. 可疑空收敛：added_lines >= SUSPICIOUS_EMPTY_LINES 且 ai_raw_count == 0 且【未 engaged】。
         引擎虽 ok 但改动不小却 0 原始建议且 glm 没给出实质性评审结构--如 pr-agent 把 diff 裁空
         （PR #44 真根因：custom_model_max_tokens 语义用反致 4096 当窗口裁空 diff）：diff 空 →
         glm 无米下锅 → review 段近乎空（not engaged）。pr-agent 正常返回、engine_status="ok"，
         唯有此判据能抓住。

    engaged 逃生口（PR #51 排查）：engine_status="ok"、改动不小、0 key_issues/suggestions、
    但 glm 给出了实质性多段评审（effort/security/relevant_tests 等 ≥2 段非空）= 【审完无问题】，
    非"没审"。runner 在 review 段写 _engaged（见 _extract_engaged）。engaged 只放宽"可疑空收敛"，
    不救引擎降级（情形 1 仍优先）。engaged 默认 False → 老调用/老产物保持原行为（向后兼容）。

    返回 False 时：checklist 不予"复检未再命中"自动销项、loop 不收敛、autonomy 不自动放行
    --回落到人（ADVISORY 不拦人工合入）。是 PR #45 引擎根因修复之上的 defense-in-depth：
    引擎再坏或超大 PR 超 pr-agent token 预算被裁空时，不再假收敛放行未评审代码。"""
    if engine_status != "ok":
        return False
    if ai_raw_count > 0:
        return True                       # 有原始建议 → 引擎确审
    if added_lines < _SUSPICIOUS_EMPTY_LINES:
        return True                       # 小改动 0 建议合理
    return bool(engaged)                  # 改动不小却 0 建议：engaged=审完无问题；否则可疑（裁空/吞没）


# pr-agent 把 LLM 预测失败吞成 0 建议时，stderr 留下的可靠信号串。
# 见 retry_with_fallback_models（algo/pr_processing.py:326）的第一次吞 + run()（pr_code_suggestions.py:188）
# 的第二次吞：LLM 返回空 content -> 预测解析抛异常 -> WARNING "Failed to generate prediction" ->
# ERROR "Failed to generate prediction with any model" -> 退出码 0、JSON 无 _degraded、findings 全空。
# LLM 失败在 pr-agent 里因【工具而异】地出现在不同层，日志串不同（对 0.37 源码核实）：
#   improve：YAML 解析在 _get_prediction 内、位于 retry_with_fallback_models 圈内 ->
#            空 content 的解析失败会重抛，stderr 必含 "Failed to generate prediction"。
#   review ：retry 只包 _prepare_prediction（取原始文本）；解析在其后的 _prepare_pr_review
#            （retry 圈外）-> 空 content 走 load_yaml 失败路径，stderr 是
#            "Failed to parse AI prediction after fallbacks" / "Failed to parse review data"，
#            或 data=None 时 run() 顶层的 "Failed to review PR:"——【不含】generate prediction 串。
# 只认单一串会漏检"review 空响应 + improve 恰好 0 建议（小 PR 合法情形）"：SIG 缺席、
# engine_status 误判 ok，只剩 added_lines>=20 启发式兜底，小 PR 兜不住。故用信号集合。
_PRED_FAILURE_SIGS = (
    "Failed to generate prediction",              # improve/任何 retry 圈内失败（含超时/APIError）
    "Failed to parse AI prediction after fallbacks",   # review 解析层：修复兜底后仍无数据
    "Failed to parse review data",                # review 解析层：YAML 无 'review' 键
    "Failed to review PR:",                       # review run() 顶层吞没（如 data=None 的 TypeError）
    # runner 外化的工具级标记（run() 全吞使子进程异常通道失效，只能靠标记，见 pr_agent_runner）：
    "[runner] improve produced no data",
    "[runner] review produced empty prediction",
    "[runner] review prediction malformed",       # 形变输出：有原文但 review 段缺失/非 dict（旧盲区）
)

# 工具专属的【顶层】失败串——用于部分降级归因（哪个工具挂了）。与 _PRED_FAILURE_SIGS 的
# 区别：SIGS 判"整轮是否吞没"（需两侧都空），这里判"单侧失败而另一侧仍有产出"。
_IMPROVE_FAIL_SIGS = ("Failed to generate code suggestions for PR",
                      "[runner] improve produced no data")
_REVIEW_FAIL_SIGS = ("Failed to review PR:", "Failed to parse review data",
                     "Failed to parse AI prediction after fallbacks",
                     "[runner] review produced empty prediction",
                     "[runner] review prediction malformed")
_REPAIRED_PARSE_SIG = "Initial failure to parse AI prediction"   # 截断/畸形被 try_fix_yaml 修复的弱信号


def partial_tool_failure(data, stderr):
    """部分降级归因：一个工具失败而另一个仍有真实产出。整轮不判不可信
    （prediction_swallowed_failure 按设计放行——评审仍有效），但必须可见：
    improve 连挂数日而 review 正常时，建议侧信号长期缺失却无人察觉（本次排查盲区 S1）。
    返回 "improve" / "review" / None。纯函数，便于离线测试。"""
    err = stderr or ""
    cs = (data.get("code_suggestions") if isinstance(data, dict) else None) or []
    ki = (((data.get("review") or {}).get("key_issues_to_review"))
          if isinstance(data, dict) else None) or []
    if not cs and ki and any(sig in err for sig in _IMPROVE_FAIL_SIGS):
        return "improve"
    if not ki and cs and any(sig in err for sig in _REVIEW_FAIL_SIGS):
        return "review"
    return None


def prediction_swallowed_failure(data, stderr):
    """检测 pr-agent 把 LLM 预测失败静默吞成"0 建议成功"的情形（防假收敛的可靠主判据）。

    glm-5.2 间歇性返回空 content（choices 存在但 content 为空串）-> 预测解析抛异常 -> pr-agent
    retry 吞 + run() 再吞，返回空 data、退出码 0、无 _degraded 字段。此时 _invoke_endpoint 的
    _degraded 检查（仅查字段）漏过，engine_status 被当 "ok"，0 建议被当"审完无问题"-> 假收敛。

    stderr 里 pr-agent 记的失败串（_PRED_FAILURE_SIGS，按工具/层各异，见其定义处注释）是可靠
    信号。但 improve 工具失败而 review 工具成功给了意见时，stderr 仍含失败串（improve 失败）、
    本轮却有 key_issues -> 不算吞没（仍拿到真实评审）。
    故判据：任一失败串存在 且 本轮原始建议全空（code_suggestions 与 key_issues 都 0）。返回 True ->
    _invoke_endpoint 抛 ReviewEngineDegraded("llm_failed")，engine_status=llm_failed，
    review_reliable 主分支（engine_status!="ok"）触发，不再依赖"大改动+0建议"的启发式近似。

    data：pr-agent 返回的 JSON dict（{"code_suggestions":[...], "review":{"key_issues_to_review":[...]}}）。
    stderr：适配子进程的完整 stderr。纯函数，便于离线测试。"""
    if not any(sig in (stderr or "") for sig in _PRED_FAILURE_SIGS):
        return False
    cs = data.get("code_suggestions") if isinstance(data, dict) else None
    ki = ((data.get("review") or {}).get("key_issues_to_review")
          if isinstance(data, dict) else None)
    return not cs and not ki


# 哨兵常量须与 pr_agent_runner._JSON_BEGIN/_JSON_END 字面一致（plumbing 协议）。
_JSON_BEGIN = "\n<<<TOUCHSTONE_JSON_BEGIN>>>\n"
_JSON_END = "\n<<<TOUCHSTONE_JSON_END>>>\n"


def _extract_json(stdout):
    """从 runner 子进程 stdout 提取结构化 JSON，容忍第三方库（litellm/pr-agent）延迟 print 的噪音。

    runner（pr_agent_runner._emit_json）用 _JSON_BEGIN/_JSON_END 哨兵包裹 JSON，本函数按哨兵精确提取；
    无哨兵（老协议/哨兵缺失）时退化为 raw_decode 取首个 JSON 对象，容忍前后噪音。都失败则抛
    json.JSONDecodeError（_invoke_endpoint 据此判 no_engine——纯噪音无 JSON 仍正确降级）。

    背景：litellm 1.84 async 成功回调会延迟把 "Logging Details LiteLLM-Async Success Call" 打到 stdout
    （晚于 runner 的 fd 级 dup2 重定向恢复），曾致 json.loads "Extra data" → 误判 no_engine（PR #49）。"""
    m = re.search(re.escape(_JSON_BEGIN) + r"(.*?)" + re.escape(_JSON_END), stdout or "", re.S)
    if m:
        return json.loads(m.group(1))
    obj, _end = json.JSONDecoder().raw_decode((stdout or "").lstrip())
    return obj


def _extract_engaged(data):
    """runner 在 review 段写 _engaged（glm 是否给出实质性多段评审结构，见 pr_agent_runner）。
    离线注入 / 老协议 / 非 dict → False（保守：无 engagement 信号时维持可疑空收敛判据）。"""
    if not isinstance(data, dict):
        return False
    return bool(((data.get("review") or {}).get("_engaged")))


def load_nmap(repo_dir="."):
    """读 .touchstone/pr-agent.yaml 的 normalization 段（缺省用内置默认）。env TOUCHSTONE_PRAGENT 可覆盖路径。"""
    path = os.environ.get("TOUCHSTONE_PRAGENT", os.path.join(repo_dir, ".touchstone", "pr-agent.yaml"))
    nmap = dict(_DEFAULT_NMAP)
    try:
        data = yaml.safe_load(open(path, encoding="utf-8")) or {}
        norm = data.get("normalization", {})
        # 浅合并：用户配置覆盖默认（label 映射整体替换以避免歧义）
        for k in ("default_category", "default_severity", "default_confidence", "conf_min", "high_categories"):
            if k in norm:
                nmap[k] = norm[k]
        if "label_to_category" in norm:
            nmap["label_to_category"] = norm["label_to_category"]
        if "discard_labels" in norm:
            nmap["discard_labels"] = norm["discard_labels"]
    except (OSError, yaml.YAMLError):
        pass
    return nmap


# ---- 解析 PR-Agent 原始输出 → ReviewItem -----------------------------------
# ReviewItem（dict）: {kind, file, line_start, line_end, summary, body, label, tool}
def parse_pr_agent(raw):
    """把 PR-Agent improve（code_suggestions）与 review（key_issues_to_review）输出解析为 ReviewItem 列表。
    raw 形如 {'code_suggestions': [...], 'review': {'key_issues_to_review': [...], ...}}。
    字段名按 PR-Agent improve/review schema；不同版本字段略有差异，对接时以你的 PR-Agent 实际版本为准。
    防御：raw 来自子进程 JSON，形状不可信——顶层非 dict、条目非 dict 一律跳过而非抛异常
    （属性测试 test_parse_pr_agent_never_raises 的不变式：任意输入不崩）。"""
    items = []
    if not isinstance(raw, dict):
        return items
    for s in raw.get("code_suggestions", []) or []:
        if not isinstance(s, dict):
            continue
        items.append({
            "kind": "suggestion",
            "file": s.get("relevant_file"),
            "line_start": s.get("relevant_lines_start"),
            "line_end": s.get("relevant_lines_end"),
            "summary": s.get("one_sentence_summary") or s.get("suggestion_content"),
            "body": s.get("improved_code") or s.get("suggestion_content"),
            # reason 与 body 分开：body 可能是 improved_code（补丁），按评审意见 2 不得进
            # 模型来源发现的建议字段；reason 保留文字说明供 fix_reasoning。
            "reason": s.get("suggestion_content"),
            "label": (s.get("label") or "").strip(),
            "tool": "improve",
        })
    review = raw.get("review", {})
    review = review if isinstance(review, dict) else {}
    for k in review.get("key_issues_to_review", []) or []:
        if not isinstance(k, dict):
            continue
        items.append({
            "kind": "review",
            "file": k.get("relevant_file"),
            "line_start": k.get("start_line"),
            "line_end": k.get("end_line"),
            "summary": k.get("issue_header"),
            "body": k.get("issue_content"),
            "reason": k.get("issue_content"),
            "label": (k.get("label") or "review").strip(),
            "tool": "review",
        })
    return items


# ---- 子进程集成的辅助 --------------------------------------------------------
def _build_pr_url(pr_ctx):
    o, r, n = pr_ctx.get("owner"), pr_ctx.get("repo"), pr_ctx.get("number")
    host = os.environ.get("GITHUB_HOST", "github.com")
    return f"https://{host}/{o}/{r}/pull/{n}" if (o and r and n) else ""


def _load_provider_cfg(repo_dir):
    try:
        d = yaml.safe_load(open(os.path.join(repo_dir, ".touchstone", "pr-agent.yaml"), encoding="utf-8")) or {}
        return d.get("provider") or {}
    except OSError:
        return {}


def _provider_mode(pr_ctx):
    return (pr_ctx.get("mode") or os.environ.get("TOUCHSTONE_PRAGENT_MODE")
            or _load_provider_cfg(pr_ctx.get("repo_dir", ".")).get("mode") or "improve+review")


def _experience_injection(repo_dir):
    """学习回路的 active 经验 → PR-Agent extra_instructions（只读、可空、失败即空）。
    符合"评审路径只读经验库"的边界；经验只调建议、不进闸。
    TOUCHSTONE_EXPERIENCE_ENABLED=false 时整体关闭注入（默认开）。"""
    if os.environ.get("TOUCHSTONE_EXPERIENCE_ENABLED", "true").lower() not in ("1", "true", "yes", "on"):
        return ""
    # 纵深防御：PR 事件下未配受信 ref（TOUCHSTONE_EXPERIENCE_REF）则跳过注入——
    # 否则经验库会从可被本 PR 篡改的工作树读（投毒/提示注入）。工作流已配 ref 时无影响。
    if (os.environ.get("GITHUB_EVENT_NAME") == "pull_request"
            and not os.environ.get("TOUCHSTONE_EXPERIENCE_REF")):
        import sys as _sys
        print("[warn] PR 评审未配置 TOUCHSTONE_EXPERIENCE_REF → 跳过经验注入（防经验库投毒）",
              file=_sys.stderr)
        return ""
    try:
        from touchstone import learning_loop
        return learning_loop.render_injection(learning_loop.load_store()) or ""
    except Exception:
        return ""


# ---- 评审提供器：封装 PR-Agent 调用（子进程集成）----------------------------
class PRAgentProvider:
    """把 PR-Agent 抽象成一个可替换的"评审观察来源"。对上层只暴露 fetch(pr_ctx) -> [ReviewItem]。"""

    def fetch(self, pr_ctx):
        return parse_pr_agent(self._invoke(pr_ctx))

    def _invoke(self, pr_ctx):
        # 注入点：测试/离线下经 pr_ctx['pr_agent_output'] 直接传入原始输出
        if "pr_agent_output" in (pr_ctx or {}):
            return pr_ctx["pr_agent_output"]
        return self._invoke_endpoint(pr_ctx)

    def _invoke_endpoint(self, pr_ctx):
        """真集成（子进程）：起适配子进程 `python -m touchstone.pr_agent_runner`（可由 env
        TOUCHSTONE_PRAGENT_CMD 覆盖），它在装了 pr-agent 的环境里调 PR-Agent（不发评论）、打印 JSON。
        PR-Agent 是 pip 包、不是要部署的服务；真调只需子进程环境有 LLM key + GitHub token
        （任何 AI 评审器固有，经 env 透传）。沙箱无凭据 → 子进程会缺 key 失败，故此处只能离线测 plumbing。"""
        pr_url = pr_ctx.get("pr_url") or _build_pr_url(pr_ctx)
        if not pr_url:
            raise RuntimeError("无法确定 PR URL：pr_ctx 需含 pr_url 或 owner/repo/number")
        cmd = shlex.split(os.environ.get("TOUCHSTONE_PRAGENT_CMD", "python -m touchstone.pr_agent_runner"))
        args = cmd + ["--pr-url", pr_url, "--mode", _provider_mode(pr_ctx)]
        repo_dir = pr_ctx.get("repo_dir", ".")
        # best_practices.md 不经此传：pr-agent 的本地 best_practices 是文件式——放到被审仓库根即可。
        extra = pr_ctx.get("extra_instructions")
        if extra is None:
            extra = _experience_injection(repo_dir)   # 学习回路 active 经验 → extra_instructions（只读、可空）
        tmp = None
        try:
            if extra:
                tmp = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8")
                tmp.write(extra)
                tmp.close()
                args += ["--extra-instructions-file", tmp.name]
            try:
                proc = subprocess.run(args, capture_output=True, text=True,
                                      timeout=int(os.environ.get("TOUCHSTONE_PRAGENT_TIMEOUT", "600")))
            except subprocess.TimeoutExpired as e:
                raise ReviewEngineDegraded(
                    "llm_failed",
                    f"PR-Agent 子进程超时（{e.timeout}s）—— 大 PR 或 LLM 端点慢。"
                    f"可调 TOUCHSTONE_PRAGENT_TIMEOUT，或拆分 PR。") from e
            except FileNotFoundError as e:
                raise ReviewEngineDegraded(
                    "no_engine",
                    f"找不到 PR-Agent 适配命令 {cmd!r}：请 `pip install pr-agent` 并确保 "
                    f"touchstone.pr_agent_runner 可运行，或用 TOUCHSTONE_PRAGENT_CMD 指定。原始：{e}") from e
            if proc.returncode != 0:
                # 适配器本应总退出 0 并用 _degraded 上报；走到这里说明它自身崩了（venv 缺失/bug）
                raise ReviewEngineDegraded(
                    "no_engine",
                    f"PR-Agent 适配子进程非零退出（{proc.returncode}）。stderr 末尾：\n"
                    f"{(proc.stderr or '').strip()[-600:]}")
            try:
                data = _extract_json(proc.stdout)
            except json.JSONDecodeError as e:
                raise ReviewEngineDegraded(
                    "no_engine",
                    f"PR-Agent 适配输出非合法 JSON：{e}；stdout 末尾：\n"
                    f"{(proc.stdout or '').strip()[-300:]}") from e
            # 适配器的结构化降级上报（pr-agent 没装 / LLM 调用失败）——转成异常供 orchestrator 显式标注
            if isinstance(data, dict) and data.get("_degraded"):
                raise ReviewEngineDegraded(data["_degraded"], data.get("reason", ""))
            # 诊断（防"0 建议但不知真假"的静默故障）：把 pr-agent 原始返回的计数 + 完整 stderr 打到
            # job 日志与交互日志 artifact，让人能区分"LLM 真没建议"与"返回了内容但 parse 没解析出来"，
            # 并定位 pr-agent 调 LLM 时的真实错误。开 TOUCHSTONE_LITELLM_VERBOSE 时 stderr 含 litellm 请求轨迹。
            try:
                _cs = len((data.get("code_suggestions") or []))
                _ki = len(((data.get("review") or {}).get("key_issues_to_review") or []))
                _err_full = (proc.stderr or "").strip()
                print(f"[pr-agent] 原始返回：code_suggestions={_cs} key_issues={_ki} "
                      f"(stdout {len(proc.stdout or '')}B, stderr {len(proc.stderr or '')}B)", file=sys.stderr)
                if _err_full:
                    print(f"[pr-agent] stderr 完整：\n{_err_full[-6000:]}", file=sys.stderr)
                # 把完整 stderr 追加进交互日志 artifact（litellm 轨迹/真实 HTTP 错误）
                _ixlog = os.environ.get("TOUCHSTONE_INTERACTION_LOG")
                if _ixlog and _err_full:
                    with open(_ixlog, "a", encoding="utf-8") as _f:
                        _f.write("\n\n---- pr-agent 子进程 stderr（litellm 轨迹 / 真实错误）----\n")
                        _f.write(_err_full)
            except Exception:
                pass
            # pr-agent 把 LLM 预测失败（返回空 content -> 解析抛异常）吞成 0 建议的第二道兜底：
            # 退出码 0、无 _degraded 字段时，_degraded 检查漏过。stderr 的失败串 + 本轮 0 原始建议
            # 是可靠判据（见 prediction_swallowed_failure）。命中 -> 判 llm_failed 降级，engine_status
            # 置 llm_failed -> review_reliable 主分支触发，不再依赖"大改动+0建议"启发式近似。
            # 这正是 PR #44 round-3 / PR #46 "0 建议假收敛"的真根因（glm-5.2 间歇空 content 被吞）。
            if prediction_swallowed_failure(data, proc.stderr):
                raise ReviewEngineDegraded(
                    "llm_failed",
                    "PR-Agent 把 LLM 预测失败（stderr 含分层失败串，见 _PRED_FAILURE_SIGS）吞成 0 建议"
                    "（退出码 0、无 _degraded）--0 建议是 LLM 失败而非审完无问题。stderr 末尾：\n"
                    + (proc.stderr or "").strip()[-600:])
            # 非致命诊断元信息（部分降级/修复解析计数）——供 orchestrator 在报告中透明化：
            #   partial：单工具失败但另一侧仍有产出（整轮仍可信，不触发降级，但必须可见）；
            #   repaired：预测经 try_fix_yaml 修复解析的次数——输出截断（finish_reason=length）
            #             或轻度畸形的弱信号，条目可能被静默修丢（本次排查盲区 S3）。
            _LAST_META.update(
                partial_tool_failure=partial_tool_failure(data, proc.stderr),
                repaired_parses=(proc.stderr or "").count(_REPAIRED_PARSE_SIG),
                review_engaged=_extract_engaged(data))
            return data
        finally:
            if tmp:
                try:
                    os.unlink(tmp.name)
                except OSError:
                    pass


# 本次 invoke 的诊断元信息（部分降级/修复解析计数）。单次 CLI 进程内串行使用；
# fetch() 开头重置，_invoke_endpoint 填充，orchestrator 经 invoke_meta() 读取。
# 离线注入路径（pr_agent_output）不产生 stderr，保持默认值。
_LAST_META = {"partial_tool_failure": None, "repaired_parses": 0, "review_engaged": False}


def invoke_meta():
    """最近一次 fetch 的诊断元信息（拷贝）。"""
    return dict(_LAST_META)


def fetch(pr_ctx, provider=None):
    """按 provider 取评审观察（默认 pr-agent；目前仅此一种，未知 provider 抛错）。
    orchestrator.review_pr 已直连本函数；REVIEW_PROVIDER 留作未来接入其它评审来源的开关。"""
    _LAST_META.update(partial_tool_failure=None, repaired_parses=0, review_engaged=False)
    provider = provider or os.environ.get("REVIEW_PROVIDER", "pr-agent")
    if provider == "pr-agent":
        return PRAgentProvider().fetch(pr_ctx)
    raise ValueError(f"未知评审提供器: {provider}")


# ---- 发现归一：ReviewItem → 本系统 Finding ---------------------------------
def normalize(items, nmap=None):
    """把 PR-Agent 的 ReviewItem 按 nmap 映射成本系统 Finding（与 contract_check 同构，
    供下游裁决映射/总闸/校准直接复用）。agent 记来源（pr-agent:suggestion / pr-agent:review）。"""
    nmap = nmap or _DEFAULT_NMAP
    l2c = nmap.get("label_to_category", {})
    discard = set(nmap.get("discard_labels", []))
    findings = []
    for it in items or []:
        label = it.get("label", "")
        if label in discard:
            continue
        cat = l2c.get(label, nmap.get("default_category", "convention"))
        rid = "PRA-" + (label or it.get("kind", "review")).replace(" ", "_").upper()
        # 修订设计 §4.2（评审意见 2）：模型来源只给方向与依据，不给动手级指令。
        # suggestion 的 body 可能是 improved_code（补丁）——按设计降级为方向描述，不进任何建议字段；
        # deterministic_patch 仅确定性来源（confidence=1.0 规则命中）可填，模型来源禁填。
        direction = it.get("summary") or ""
        reasoning = it.get("reason") or ""
        if reasoning == direction:
            reasoning = ""            # 说明文字与方向重复时不复读
        findings.append({
            "rule_id": rid,
            "file": it.get("file"),
            "line": it.get("line_start"),
            "category": cat,
            "severity": nmap.get("default_severity", "warn"),
            "confidence": nmap.get("default_confidence", 0.7),
            "rationale": it.get("summary") or it.get("body"),
            "fix_direction": direction,
            "fix_reasoning": reasoning,
            # 复核判据（评审意见 1）：给不出确定性判据的模型来源发现，下一轮定向复核该问题。
            "done_criteria": {"kind": "review",
                              "spec": {"question": f"「{direction}」是否已按方向解决？"}},
            "suggested_fix": direction,   # 已废弃字段的过渡别名（=方向，不含补丁），供旧消费方
            "agent": "pr-agent:" + it.get("kind", "review"),
        })
    return findings


# ---- 裁决映射：Finding → 三类判定/风险等级（不做共识，PR-Agent 已去重排序）----
_HUMAN = {"high": "read+arbitrate", "mid": "read", "low": "skip"}


# 影响面严重因子：高风险 + 命中其一 → 升到 full_suite（最强一档，多跑变异）。
_SEVERE_BLAST = {"cross_module_contract", "security_surface"}

# 确定性影响面：直接从改动文件【路径】判定，不依赖 PR-Agent 给的 category。
# 目的：即便评审侧误判了类别（把该 high 的改动判成 low），命中这些路径的改动仍会被
# 强制抬到 high → full_suite，并触发（可选的）自动合并否决。这是「风险分流的安全性不能
# 全押在会误判的判断层」的确定性兜底（对应主设计 §5 该遗留项的缓解，此处落地）。
_DET_BLAST_PATTERNS = {
    "cross_module_contract": [
        r"(^|/)migrations?/", r"\.sql$", r"\.proto$", r"\.graphql$", r"\.avsc$", r"\.thrift$",
        r"(^|/)schema[./]", r"schema\.\w+$", r"openapi", r"swagger",
    ],
    "security_surface": [
        r"(^|/)(auth|oauth|iam|security|crypto|secrets?|credentials?)([/_.]|$)",
        r"(password|keystore|private[_-]?key)",
    ],
}


def deterministic_blast(changed_files):
    """从改动文件路径确定性推断影响面因子（不依赖 LLM 类别）。命中即强证据。"""
    files = [str(f).lower() for f in (changed_files or [])]
    out = []
    for factor, pats in _DET_BLAST_PATTERNS.items():
        if any(any(re.search(p, f) for p in pats) for f in files):
            out.append(factor)
    return out


def route(risk):
    """§4.2 风险分流（真实实现）：按 risk_band（高风险时再看影响面）决定人看不看、跑哪一档验证。
    三档充分性阶梯（§6.2）：
      低/中            → cheap_only（仅廉价信号）
      高               → targeted_tests（生成针对性验收测试 + 覆盖/哨兵）
      高 且 影响面严重 → full_suite（在 targeted 基础上再跑变异测试——最强、最贵的一档）
    map_verdict 在定级后调用本函数，填入 human_action / verification_decision。

    注：契约/安全类违例（contract/security category）由【确定性门禁】以 block_candidate
    severity 拦截，不依赖此处的验证档——验证(verify)只管 correctness（spec-blind 验收测试）。
    故契约变更落到 mid/cheap_only 不构成漏洞：它的拦截发生在门禁，不在 verify。"""
    band = risk.get("risk_band")
    if band == "high":
        severe = bool(_SEVERE_BLAST & set(risk.get("blast_radius") or []))
        vd = "full_suite" if severe else "targeted_tests"
    else:
        vd = "cheap_only"
    return {"human_action": _HUMAN.get(band, "read"), "verification_decision": vd}


def map_verdict(findings, nmap=None, changed_files=None, scope_facts=None):
    """把归一后的 Finding 按 category 映射到风险等级与验证预算决策（风险路由）。
    取代自研 aggregate 的"评审侧定级"，但去掉去重/共识——那由 PR-Agent 完成。
    返回 (过滤后 findings, RiskAssessment)，结构与主文档 RiskAssessment 一致。
    scope_facts（修订设计 §4.1，评审意见 7）：范围事实的 sensitive_hits 按仓级路径规则
    （.touchstone/scope-rules.yaml）确定性点亮影响面——推导顺序为路径规则命中（确定性）∪
    发现类别推导（模型，补充），模型漏报不再导致影响面漏判。"""
    nmap = nmap or _DEFAULT_NMAP
    conf_min = nmap.get("conf_min", 0.5)
    kept = sorted((f for f in (findings or []) if f.get("confidence", 0) >= conf_min),
                  key=lambda x: -x.get("confidence", 0))
    cats = {f.get("category") for f in kept}
    blast = []
    if "security" in cats:
        blast.append("security_surface")
    if "contract" in cats:                 # 一般来自 contract_check，而非 PR-Agent
        blast.append("cross_module_contract")
    if scope_facts and changed_files is None:
        changed_files = [f["path"] for f in scope_facts.get("changed_files", [])]
    det = set(deterministic_blast(changed_files))  # 确定性影响面（按路径，不信 LLM 类别）
    if scope_facts:                                # 范围事实的仓级规则命中（可配置的确定性影响面）
        det |= {h["rule"] for h in scope_facts.get("sensitive_hits", [])}
    blast = sorted(set(blast) | det)
    # 命中高危类别，或【确定性】命中严重影响面 → high。后者保证：即便评审侧漏判类别，
    # 触及 migration/schema/proto/安全面的改动也会被抬到 full_suite、并被自动合并否决拦下。
    high = bool(set(nmap.get("high_categories", ["security", "correctness"])) & cats) \
        or bool(_SEVERE_BLAST & set(det))
    band = "high" if high else ("mid" if kept else "low")
    risk = {"risk_band": band, "blast_radius": blast}
    risk.update(route(risk))          # §4.2 风险分流：人看不看 / 跑哪档验证
    return kept, risk


def to_rdjson(findings, source_name="touchstone"):
    """把发现转成 Reviewdog Diagnostic Format(rdjson)——成熟行内评论后端的接缝：
    reviewdog 处理行锚定长尾（过滤模式/位置修正），本系统不必自研。纯函数，供导出。"""
    sev = {"block_candidate": "ERROR", "warn": "WARNING"}
    return {"source": {"name": source_name},
            "diagnostics": [{
                "message": (f.get("rationale") or f.get("rule_id") or ""),
                "code": {"value": f.get("rule_id") or ""},
                "location": {"path": f.get("file") or "",
                             "range": {"start": {"line": int(f.get("line") or 1)}}},
                "severity": sev.get(f.get("severity"), "INFO"),
            } for f in (findings or [])]}
