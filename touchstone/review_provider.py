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

import json
import os
import shlex
import subprocess
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
    字段名按 PR-Agent improve/review schema；不同版本字段略有差异，对接时以你的 PR-Agent 实际版本为准。"""
    items = []
    for s in (raw or {}).get("code_suggestions", []) or []:
        items.append({
            "kind": "suggestion",
            "file": s.get("relevant_file"),
            "line_start": s.get("relevant_lines_start"),
            "line_end": s.get("relevant_lines_end"),
            "summary": s.get("one_sentence_summary") or s.get("suggestion_content"),
            "body": s.get("improved_code") or s.get("suggestion_content"),
            "label": (s.get("label") or "").strip(),
            "tool": "improve",
        })
    review = (raw or {}).get("review", {}) or {}
    for k in review.get("key_issues_to_review", []) or []:
        items.append({
            "kind": "review",
            "file": k.get("relevant_file"),
            "line_start": k.get("start_line"),
            "line_end": k.get("end_line"),
            "summary": k.get("issue_header"),
            "body": k.get("issue_content"),
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
    符合"评审路径只读经验库"的边界；经验只调建议、不进闸。"""
    try:
        import learning_loop
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
            except FileNotFoundError as e:
                raise RuntimeError(f"找不到 PR-Agent 适配命令 {cmd!r}：请 `pip install pr-agent` 并确保 "
                                   f"touchstone.pr_agent_runner 可运行，或用 TOUCHSTONE_PRAGENT_CMD 指定。原始：{e}")
            if proc.returncode != 0:
                raise RuntimeError(f"PR-Agent 适配子进程非零退出（{proc.returncode}）。stderr 末尾：\n"
                                   f"{(proc.stderr or '').strip()[-600:]}")
            try:
                return json.loads(proc.stdout)
            except json.JSONDecodeError as e:
                raise RuntimeError(f"PR-Agent 适配输出非合法 JSON：{e}；stdout 末尾：\n"
                                   f"{(proc.stdout or '').strip()[-300:]}")
        finally:
            if tmp:
                try:
                    os.unlink(tmp.name)
                except OSError:
                    pass


def fetch(pr_ctx, provider=None):
    """按 provider 取评审观察（默认 pr-agent；目前仅此一种，未知 provider 抛错）。
    orchestrator.review_pr 已直连本函数；REVIEW_PROVIDER 留作未来接入其它评审来源的开关。"""
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
        findings.append({
            "rule_id": rid,
            "file": it.get("file"),
            "line": it.get("line_start"),
            "category": cat,
            "severity": nmap.get("default_severity", "warn"),
            "confidence": nmap.get("default_confidence", 0.7),
            "rationale": it.get("summary") or it.get("body"),
            "suggested_fix": it.get("body"),
            "agent": "pr-agent:" + it.get("kind", "review"),
        })
    return findings


# ---- 裁决映射：Finding → 三类判定/风险等级（不做共识，PR-Agent 已去重排序）----
_HUMAN = {"high": "read+arbitrate", "mid": "read", "low": "skip"}


# 影响面严重因子：高风险 + 命中其一 → 升到 full_suite（最强一档，多跑变异）。
# 仅列 map_verdict 实际会产出（security_surface / cross_module_contract）的因子——
# 其余（如 touches_public_api / schema）当前无产出路径，不在此避免「看着有、其实空」。
_SEVERE_BLAST = {"cross_module_contract", "security_surface"}


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


def map_verdict(findings, nmap=None):
    """把归一后的 Finding 按 category 映射到风险等级与验证预算决策（风险路由）。
    取代自研 aggregate 的"评审侧定级"，但去掉去重/共识——那由 PR-Agent 完成。
    返回 (过滤后 findings, RiskAssessment)，结构与主文档 RiskAssessment 一致。"""
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
    high = bool(set(nmap.get("high_categories", ["security", "correctness"])) & cats)
    band = "high" if high else ("mid" if kept else "low")
    risk = {"risk_band": band, "blast_radius": blast}
    risk.update(route(risk))          # §4.2 风险分流：人看不看 / 跑哪档验证
    return kept, risk
