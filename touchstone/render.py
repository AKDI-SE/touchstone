#!/usr/bin/env python3
# ============================================================================
# touchstone/render.py —— 评审报告渲染层（七段版面填充）
# ----------------------------------------------------------------------------
# 从 orchestrator 拆出（模块职责单一化）：orchestrator 编排链路，本模块只负责把
# 结构化结果填进版面。版面由 templates/review_report.md 唯一定义——模板是设计资产，
# 代码只填充、不定义版面（修订设计 §3 意见 4）。
# 拆分同时根治一处运行期地雷：原 render_findings 函数内的 `from llm_budget import`
# 平铺导入在移除 sys.path hack 后必然 ModuleNotFoundError，且因该分支缺测试覆盖 +
# 个别测试文件污染 sys.path 而在全量测试中被掩盖（单跑文件才炸）。现改为顶层包导入。
# ============================================================================

import os
import re
import sys

from touchstone.llm_budget import MAX_FINDINGS_IN_SUMMARY

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


def render_unreliable_callout(engine_status, ai_raw_count=0, added_lines=0, engine_detail=""):
    """本轮评审不可信时的置顶告警——[!CAUTION] 红框置顶，替代常规溯源/降级横幅。精简到两行：
    点明【失败环节】+ 后果 + 指向。具体可靠的原始错误详列在「验证与日志」段（本框不塞原始
    dump）。判定层（销项/收敛/放行）已由 review_reliable 挡住；本函数把同一信号接到呈现层。"""
    _WHERE = {
        "no_engine": "评审引擎未启动",
        "provider_failed": "取 PR 失败",
        "llm_failed": "LLM 调用失败",
        "skipped_large_diff": "diff 超预算被跳过",
    }
    where = _WHERE.get(engine_status) or f"疑似空收敛（约 {added_lines} 行改动却 {ai_raw_count} 建议）"
    tail = "；原始错误见下方「验证与日志」" if (engine_status != "ok" and engine_detail) else ""
    return "\n".join([
        "> [!CAUTION]",
        f"> **本轮 AI 评审不可信**：{where}。",
        f"> 请人工评审{tail}。",
    ])


def _finding_entry(i, f):
    """单条发现的渲染（规则命中与 AI 建议共用）：位置 — 问题 + 修复方向/依据/达成判据 + 行尾元数据。"""
    direction = f.get("fix_direction") or f.get("suggested_fix") or ""
    reasoning = f.get("fix_reasoning") or ""
    dc = f.get("done_criteria") or {}
    _spec = dc.get("spec") or {}
    if dc.get("kind") == "deterministic":
        dc_line = f"规则 `{_spec.get('recheck', '?')}` 复检不再命中"
    elif dc.get("kind") == "review":
        q = _spec.get("question", "")
        dc_line = f"需人工复核：{q}" if q else "定向复核通过"
    else:
        dc_line = ""
    e = (f"{i}. **`{f.get('file','?')}:{f.get('line','?')}`** — {f.get('rationale','')}\n"
         f"   - 修复方向：{direction}")
    if reasoning and reasoning != f.get("rationale"):
        e += f"\n   - 依据：{reasoning}"
    if dc_line:
        e += f"\n   - 达成判据：{dc_line}"
    e += (f"\n   - <sub>`{f['rule_id']}` · {f.get('severity','')} · "
          f"置信 {f['confidence']:.2f} · 来源 {f['agent']}</sub>")
    return e


def render_facts(scope_facts, gate_line="", lineage=None, rule_findings=None):
    """③ 静态检查区：不经 LLM 的确定性输出——修改范围 + 敏感路径命中 + 门禁 + 同源提示，
    以及确定性【规则命中的逐条发现】（contract/stack/size，可复现）。与「AI 评审」段并列同级
    H3，构成「确定性 vs LLM」两层视图。"""
    if not scope_facts and not rule_findings:
        return ""
    lines = ["### 静态检查", ""]
    if scope_facts and not scope_facts.get("parse_ok", True):
        lines.append(f"- ⚠️ {scope_facts.get('parse_warning', 'diff 解析失败：范围事实未生效')}")
        scope_facts = None      # 解析失败：跳过范围行，但仍渲染下方规则命中
    if scope_facts:
        t = scope_facts.get("totals", {})
        lines.append(f"- 修改范围：{t.get('files', 0)} 个文件（+{t.get('added', 0)} / −{t.get('deleted', 0)} 行）")
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
            entries = [e for e in lineage.get("lineage", []) if isinstance(e, dict) and "number" in e]
            if entries:
                hist = "、".join(f"#{e['number']}" for e in entries)
                lines.append(f"- ⚠️ 同源提示：与已关闭的 {hist} 内容同源，历史已消耗 "
                         f"{lineage.get('rounds_spent', 0)} 轮、继承未销项 "
                         f"{len(lineage.get('inherited_open_items', []))} 条，剩余轮次 "
                         f"{lineage.get('rounds_left', '?')}（重置需 `rounds-reset` label）")
    if rule_findings:
        shown = rule_findings[:MAX_FINDINGS_IN_SUMMARY]
        lines.append("")
        lines.append("#### 规则命中（可复现）")
        lines.append("")
        for i, f in enumerate(shown, 1):
            lines.append(_finding_entry(i, f))
        if len(rule_findings) > MAX_FINDINGS_IN_SUMMARY:
            lines.append("")
            lines.append(f"……另有 {len(rule_findings) - MAX_FINDINGS_IN_SUMMARY} 条（确定性核对已覆盖全文，见 check 标题/总闸）。")
    return "\n".join(lines)


def render_findings(risk, findings, review_reliable=True):
    """②态势区 + ④「AI 评审」（仅 LLM 发现）。
    态势区：「标签 + 人话」陈述行——风险等级（含"该怎么办"）与触发因子；verification_decision
      机器路由字段不入此区，降到「验证与日志」。
    AI 评审：仅 LLM（pr-agent）发现；确定性规则命中的逐条发现归「静态检查」段（render_facts）。
      `findings` 入参此处即为全部发现，函数内按来源过滤只渲染 LLM 部分。"""
    _RISK = {"high": "高", "mid": "中", "low": "低"}
    _ACTION = {"read+arbitrate": "需人工评审后合入", "read": "建议人工过目",
               "skip": "无需人工介入"}
    _BLAST = {"cross_module_contract": "跨模块契约变更", "security_surface": "涉及安全面"}
    band = _RISK.get(risk.get("risk_band"), "未定")
    action = _ACTION.get(risk.get("human_action"), "建议人工过目")
    factors = "、".join(_BLAST.get(b, b) for b in (risk.get("blast_radius") or []))
    if review_reliable:
        head = [f"> **风险等级：{band}** — {action}"]
    else:
        head = [f"> **风险等级：{band}** <sub>（仅确定性信号，LLM 评审不可信）</sub>"
                " — 需人工评审，原 AI 建议不采信"]
    if factors:                       # 无触发因子时不显「触发因子：无」——去冗余
        head.append(f"> **触发因子：** {factors}")

    ai_based = [f for f in (findings or []) if str(f.get("agent", "")).startswith("pr-agent")]
    total = len(ai_based)
    if not ai_based:
        return "\n".join(head), "### AI 评审\n\n本次 LLM 未提出建议。"
    cap = (f"，仅列前 {MAX_FINDINGS_IN_SUMMARY} 条" if total > MAX_FINDINGS_IN_SUMMARY else "")
    body = [f"### AI 评审（共 {total} 条{cap}）", ""]
    for i, f in enumerate(sorted(ai_based, key=lambda x: -x.get("confidence", 0))[:MAX_FINDINGS_IN_SUMMARY], 1):
        body.append(_finding_entry(i, f))
    if total > MAX_FINDINGS_IN_SUMMARY:
        body.append("")
        body.append(f"……另有 {total - MAX_FINDINGS_IN_SUMMARY} 条（超列表上限）。")
    return "\n".join(head), "\n".join(body)


def render_report(risk, findings, banner="", scope_facts=None, checklist_md="",
                  verification_md="", markers="", gate_line="", lineage=None,
                  review_reliable=True, engine_status="ok", ai_raw_count=0, added_lines=0,
                  engine_detail=""):
    """按七段版面模板填充评审报告（修订设计 §3 意见 4）。版面由模板唯一定义。"""
    head, findings_md = render_findings(risk, findings, review_reliable=review_reliable)
    summary_line = head          # ② 态势表：风险与建议动作一眼扫读
    rule_findings = [f for f in (findings or []) if not str(f.get("agent", "")).startswith("pr-agent")]
    # ① 状态横幅（降级说明/循环状态/0-发现溯源）统一 blockquote——与正文视觉区隔；
    #    评审不可信时 [!CAUTION] 告警置顶【替代】常规横幅的降级/溯源部分（原因已并入
    #    告警，避免同一信息两处重复），循环状态行仍保留在告警之后。
    if not review_reliable:
        # 不可信时 [!CAUTION] 告警置顶替代降级/溯源部分（原因已并入告警，避免重复）。
        # 但 banner 可能还载有与可信度无关的内容（det_warning/llm_notes/unverified_claims
        # 及循环状态行）--这些不能丢，作为 blockquote 追加在告警之后（pr-agent 评审意见：
        # 不可信时整块 banner 被丢弃会静默丢失重要通知）。
        kept = []
        if banner:
            for ln in banner.split("\n"):
                if not ln.strip():
                    continue
                kept.append(ln)
        banner = render_unreliable_callout(engine_status, ai_raw_count, added_lines, engine_detail)
        if kept:
            banner += "\n\n" + "\n".join(("> " + ln if not ln.startswith(">") else ln) for ln in kept)
    elif banner:
        banner = "\n".join(("> " + ln if ln.strip() else ">") for ln in banner.split("\n"))
    parts = {
        "banner": banner or "",
        "summary_line": summary_line,
        "facts": render_facts(scope_facts, gate_line, lineage, rule_findings=rule_findings) if (scope_facts or rule_findings) else "",
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
    label = {"high": "高", "mid": "中", "low": "低"}.get(risk["risk_band"], "未定")
    action = {"read+arbitrate": "需人工评审后合入", "read": "建议人工过目",
              "skip": "无需人工介入"}.get(risk["human_action"], "建议人工过目")
    lines = [
        "**Touchstone · ADVISORY**（不拦截合入，与人工审核并行）",
        "",
        f"风险等级：**{label}** — {action}",
    ]
    _blast = {"cross_module_contract": "跨模块契约变更", "security_surface": "涉及安全面"}
    if risk["blast_radius"]:
        lines.append("触发因子：" + "、".join(_blast.get(b, b) for b in risk["blast_radius"]))
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

