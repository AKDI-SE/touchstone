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
        entries = [e for e in lineage.get("lineage", []) if isinstance(e, dict) and "number" in e]
        if entries:
            hist = "、".join(f"#{e['number']}" for e in entries)
            lines.append(f"- ⚠️ 同源提示：与已关闭的 {hist} 内容同源，历史已消耗 "
                     f"{lineage.get('rounds_spent', 0)} 轮、继承未销项 "
                     f"{len(lineage.get('inherited_open_items', []))} 条，剩余轮次 "
                     f"{lineage.get('rounds_left', '?')}（重置需 `rounds-reset` label）")
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
        f"风险等级：**{label}**　建议动作：`{risk.get('human_action', '—')}`　"
        f"验证建议：`{risk.get('verification_decision', '—')}`",
    ]
    _blast = risk.get("blast_radius")
    if _blast:
        head.append("影响面：" + ", ".join(_blast))
    body = []
    if not findings:
        body.append("本次未发现规则范围内的问题。")
    else:
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

