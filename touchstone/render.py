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


def render_unreliable_callout(engine_status, ai_raw_count=0, added_lines=0):
    """本轮评审不可信时的置顶告警——版面铁律：不可信必须以 GitHub 原生 [!CAUTION]
    红色警示框置于标题正下方，替代（而非并存于）常规溯源/降级横幅。
    背景（PR #44/#46 实测教训）：旧版只在横幅里给一句加粗的"改动不小却 0 建议——
    建议人工扫一眼"，而态势表照常显示 LOW·可跳过/skip——评审失败反而呈现最低风险，
    是主动误导。判定层（销项/收敛/放行）已由 review_reliable 挡住，本函数把同一信号
    接到呈现层：0 发现 ≠ 审过没问题，必须让人一眼看到。"""
    _CAUSE = {
        "no_engine": "PR-Agent 未安装或不可用（引擎没跑）",
        "provider_failed": "PR-Agent 无法获取该 PR（git provider/凭据/网络）",
        "llm_failed": "LLM 端点未成功响应（含空响应被 pr-agent 吞没，退出码仍为 0 的情形）",
        "skipped_large_diff": "diff 超预算被跳过",
    }
    cause = _CAUSE.get(engine_status)
    if cause is None:      # engine ok 但可疑空收敛（唯启发式能抓：diff 被裁空/空响应漏检）
        cause = (f"引擎状态正常，但改动约 {added_lines} 新增行却 {ai_raw_count} 条原始建议"
                 "——疑似 diff 被裁空或 LLM 空响应未被检出")
    return "\n".join([
        "> [!CAUTION]",
        "> **本轮 AI 评审不可信 —— 0 发现 ≠ 审过没问题。**",
        f"> 原因：{cause}。",
        "> 本轮评审结果不作数：收敛清单不销项、反馈循环不收敛、自治不放行。",
        "> 请人工评审本 PR，或排除故障后重新触发评审（详见下方「验证与日志」）。",
    ])


def render_facts(scope_facts, gate_line="", lineage=None):
    """③ 确定性事实区：范围事实摘要（机器实测的修改范围，给人第一眼）+ 门禁状态 + 同源提示。
    与 author 的提交契约声明并排对照——声明是索引，这里是事实。
    易读性铁律：与④⑤⑥并列的段落用同级 H3（此前只有收敛清单是 H3，
    渲染后像整条评论的总标题，其余段落反像它的下级）。"""
    if not scope_facts:
        return ""
    lines = ["### 确定性事实（机器实测，不经模型）", ""]
    if not scope_facts.get("parse_ok", True):
        lines.append(f"- ⚠️ {scope_facts.get('parse_warning', 'diff 解析失败：范围事实未生效')}")
        return "\n".join(lines)
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
    return "\n".join(lines)


def render_findings(risk, findings, review_reliable=True):
    """②态势区 + ④逐条发现（2026-07-10 易读性改版·二）。
    态势区：放弃四列枚举表格，改「标签 + 人话」陈述行——只呈现人真正要关心的两件事，
      风险等级（含"该怎么办"）与触发因子；枚举值译成中文、英文原名括注。
      verification_decision 是机器路由信号（决定 CI 跑哪档验证，非给人的待办），
      已移出态势区、降级到「验证与日志」段（render_report 处理）。
    逐条发现：按来源分组——规则检查命中（rule-based，可复现）/ AI 评审建议（LLM，含置信度），
      呼应系统"确定性 vs 概率性"核心；「位置 — 问题」前置，审计元数据降 <sub> 行尾。"""
    _RISK = {"high": "高", "mid": "中", "low": "低"}
    _ACTION = {"read+arbitrate": "需人工评审后合入", "read": "建议人工过目",
               "skip": "无需人工介入"}
    _BLAST = {"cross_module_contract": "跨模块契约变更", "security_surface": "涉及安全面"}
    band = _RISK.get(risk.get("risk_band"), "未定")
    action = _ACTION.get(risk.get("human_action"), "建议人工过目")
    factors = "、".join(_BLAST.get(b, b) for b in (risk.get("blast_radius") or [])) or "无"
    if review_reliable:
        head = [f"> **风险等级：{band}** — {action}",
                f"> **触发因子：** {factors}"]
    else:
        head = [f"> **风险等级：{band}** <sub>（仅确定性信号，LLM 评审不可信）</sub>"
                " — 需人工评审，原 AI 建议不采信",
                f"> **触发因子：** {factors}"]

    body = []
    if not findings:
        body.append("### 评审发现")
        body.append("")
        body.append("本次未发现规则范围内的问题。")
        return "\n".join(head), "\n".join(body)

    rule_based = [f for f in findings if f.get("agent") != "pr-agent"]
    ai_based = [f for f in findings if f.get("agent") == "pr-agent"]

    def _entry(i, f):
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

    total = len(findings)
    cap = (f"，仅列前 {MAX_FINDINGS_IN_SUMMARY} 条" if total > MAX_FINDINGS_IN_SUMMARY else "")
    body.append(f"### 评审发现（共 {total} 条{cap}）")
    body.append("")
    n = 0
    budget = MAX_FINDINGS_IN_SUMMARY
    if rule_based:
        body.append("#### 规则检查命中（rule-based，可复现）")
        body.append("")
        for f in rule_based[:budget]:
            n += 1
            body.append(_entry(n, f))
        budget -= len(rule_based[:budget])
        body.append("")
    if ai_based and budget > 0:
        body.append("#### AI 评审建议（LLM，含置信度）")
        body.append("")
        for f in sorted(ai_based, key=lambda x: -x.get("confidence", 0))[:budget]:
            n += 1
            body.append(_entry(n, f))
    if total > MAX_FINDINGS_IN_SUMMARY:
        body.append("")
        body.append(f"……另有 {total - MAX_FINDINGS_IN_SUMMARY} 条（确定性核对已覆盖全文，见 check 标题/总闸）。")
    return "\n".join(head), "\n".join(body)


def render_report(risk, findings, banner="", scope_facts=None, checklist_md="",
                  verification_md="", markers="", gate_line="", lineage=None,
                  review_reliable=True, engine_status="ok", ai_raw_count=0, added_lines=0):
    """按七段版面模板填充评审报告（修订设计 §3 意见 4）。版面由模板唯一定义。"""
    head, findings_md = render_findings(risk, findings, review_reliable=review_reliable)
    summary_line = head          # ② 态势表：风险与建议动作一眼扫读
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
        banner = render_unreliable_callout(engine_status, ai_raw_count, added_lines)
        if kept:
            banner += "\n\n" + "\n".join(("> " + ln if not ln.startswith(">") else ln) for ln in kept)
    elif banner:
        banner = "\n".join(("> " + ln if ln.strip() else ">") for ln in banner.split("\n"))
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

