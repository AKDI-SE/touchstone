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


def render_findings(risk, findings):
    """②态势表 + ④逐条发现。
    态势表：风险/动作/验证/影响面收进一张表，一眼扫读（此前三要素全角空格挤一行）。
    逐条发现：人最关心的「位置 — 问题」前置；rule_id/severity/置信/来源是审计信息，
    降级为行尾 <sub> 小字。每条仍按「定位 · 方向 · 依据 · 达成判据」四要素呈现
    （修订设计 §3 意见 2、4）——不再输出补丁/精确指令。"""
    _RISK_LABELS = {"high": "HIGH · 建议人细看/仲裁", "mid": "MID · 建议人过目",
                    "low": "LOW · 可跳过"}
    label = _RISK_LABELS.get(risk.get("risk_band"), "UNKNOWN · 待人工定性")
    blast = ", ".join(risk.get("blast_radius") or []) or "—"
    head = [
        "| 风险等级 | 建议动作 | 验证建议 | 影响面 |",
        "| :-- | :-- | :-- | :-- |",
        f"| **{label}** | `{risk.get('human_action', '—')}` "
        f"| `{risk.get('verification_decision', '—')}` | {blast} |",
    ]
    body = []
    if not findings:
        body.append("### 评审发现")
        body.append("")
        body.append("本次未发现规则范围内的问题。")
    else:
        shown = findings[:MAX_FINDINGS_IN_SUMMARY]
        cap = (f"，仅列前 {MAX_FINDINGS_IN_SUMMARY} 条" if len(findings) > MAX_FINDINGS_IN_SUMMARY else "")
        body.append(f"### 评审发现（共 {len(findings)} 条，按置信降序{cap}）")
        body.append("")
        for i, f in enumerate(shown, 1):
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
            entry = (f"{i}. **`{f.get('file','?')}:{f.get('line','?')}`** — {f.get('rationale','')}\n"
                     f"   - 修复方向：{direction}")
            if reasoning and reasoning != f.get("rationale"):
                entry += f"\n   - 依据：{reasoning}"
            if dc_line:
                entry += f"\n   - 达成判据：{dc_line}"
            entry += (f"\n   - <sub>`{f['rule_id']}` · {f.get('severity','')} · "
                      f"置信 {f['confidence']:.2f} · 来源 {f['agent']}</sub>")
            body.append(entry)
        if len(findings) > MAX_FINDINGS_IN_SUMMARY:
            body.append(f"{len(shown) + 1}. ……另有 {len(findings) - MAX_FINDINGS_IN_SUMMARY} 条"
                        f"（确定性核对已覆盖全文，见 check 标题/总闸）。")
    return "\n".join(head), "\n".join(body)


def render_report(risk, findings, banner="", scope_facts=None, checklist_md="",
                  verification_md="", markers="", gate_line="", lineage=None):
    """按七段版面模板填充评审报告（修订设计 §3 意见 4）。版面由模板唯一定义。"""
    head, findings_md = render_findings(risk, findings)
    summary_line = head          # ② 态势表：风险与建议动作一眼扫读
    # ① 状态横幅（降级说明/循环状态/0-发现溯源）统一 blockquote——与正文视觉区隔
    if banner:
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

