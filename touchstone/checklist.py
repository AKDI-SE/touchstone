#!/usr/bin/env python3
# ============================================================================
# touchstone/checklist.py  ——  收敛清单 ConvergenceChecklist（修订设计 §4.3，评审意见 1、3）
# ----------------------------------------------------------------------------
# 双 agent 交互从「评论里聊天」改为「围绕一份逐项销项的清单收敛」：
#   - 评审方每条发现即一条清单项（方向 + 依据 + 达成判据）；
#   - author 改完逐项申报（done / waived:理由 / split:链接）；
#     ⚠ 销项分级（销项判据加固）：done 经机器复检（签名不再命中）方受理；waived/split 是
#       author 自证、机器不可核实——受理仅作展示销项与"待人核准"，绝不进 VERIFIED、
#       不触发收敛与自动放行（否则 author 一句 "waived:随便写" 即可不改代码闭环任意意见）。
#   - 评审方按达成判据复核后销项——勾选只是输入信号，复核后的状态才是权威（authority）。
# 收敛指标 = 销项率；「无推进」= 连续两轮销项率为零且无 waived/split 申报。
#
# 载体（双份同步）：
#   - 置顶评论：task list（人可读）+ 隐藏 JSON marker（机器可读、权威状态）；
#     防篡改沿用 loop.trusted_bodies 只信机器人评论的机制。
#   - 写入文件：每轮快照 checklist-round-N.json（供可视化页面与校准回放）。
#
# author 申报协议（ack）：author（agent 或人）在 PR 评论里发一个 fenced 块：
#   ```touchstone-ack
#   OE-001:src/a.py:12: done
#   SEC-001:src/b.py:3: waived: 测试夹具，非真实凭据
#   DUP-001:(diff):0: split: https://github.com/o/r/pull/99
#   ```
# 复核规则（authority）：
#   done   → 仅当该项签名在本轮发现中【不再出现】才落为 done（deterministic 判据即规则复检；
#            review 判据即评审模型定向复核后不再报）。仍出现 → 保持 open，note 记「复核未通过」。
#   waived → 必须带理由，否则不受理；受理后记 waived 并在报告中标给人核准（advisory 定位下
#            waived 计入销项，人对合入有最终决定权）。
#   split  → 必须带链接/编号，受理后记 split，计入销项。
# ============================================================================

import json
import re

_OPEN = "<!-- touchstone-checklist: "
_CLOSE = "-->"

_ACK_BLOCK = re.compile(r"```touchstone-ack\s*\n(.*?)```", re.S)
# 行格式：<sig>: <verb>[: <note>]，sig 本身含冒号（rule:file:line），故从右侧解析动词。
_ACK_LINE = re.compile(r"^(?P<sig>\S.*?):\s*(?P<verb>done|waived|split)\s*(?::\s*(?P<note>.+))?$")

# 销项分两级——销项判据加固（2026-07-09）：
#   VERIFIED = 机器可验证的销项：done（签名本轮复检不再命中，touchstone 侧确认，非 author 说了算）。
#   CLAIMED  = author 自证、机器无法核实的销项：waived（宣称误报/可接受）、split（宣称拆走）。
#     author 完全掌控 note 内容，真伪不可判——只作"输入信号"，不可单独构成收敛依据，
#     更不可触发自动放行（否则 author 一句 "waived: 无所谓" 即可闭环任意意见）。
# RESOLVED 仍是三者之并（供 resolved_rate 展示与 no_progress 判定），但 all_resolved /
# 收敛 / autonomy 放行改看 VERIFIED，见 all_verified / has_unverified_claims。
VERIFIED = {"done"}
CLAIMED = {"waived", "split"}
RESOLVED = VERIFIED | CLAIMED


def sig_of(finding):
    """清单项签名——与 loop._sig 同构（rule_id:file:line），保证两处对同一发现的指认一致。"""
    return f"{finding.get('rule_id')}:{finding.get('file')}:{finding.get('line')}"


def from_findings(findings, round_no=1):
    """由本轮发现生成初始清单（全部 open）。每项带方向、依据、达成判据——author 拿到的
    不是一段聊天，而是逐条可销项的待办（评审意见 3），且每条知道改到什么状态算过关（评审意见 1）。"""
    items = []
    seen = set()
    for f in findings or []:
        s = sig_of(f)
        if s in seen:
            continue
        seen.add(s)
        items.append({
            "sig": s,
            "direction": f.get("fix_direction") or f.get("suggested_fix") or "",
            "reasoning": f.get("fix_reasoning") or "",
            "done_criteria": (lambda dc: dc if isinstance(dc, dict) and dc.get("kind") in ("deterministic", "review")
                             else {"kind": "review", "spec": {"question": "该问题是否已解决？"}})(
                                 f.get("done_criteria")),
            "status": "open",
            "note": "",
        })
    return {"round": round_no, "items": items, "resolved_rate": _rate(items)}


def _rate(items):
    if not items:
        return 1.0
    return round(sum(1 for i in items if i["status"] in RESOLVED) / len(items), 4)


def parse_acks(bodies):
    """从（不限来源的）评论正文里解析 author 申报。申报只是输入信号，不改权威状态——
    权威状态由 reconcile 按达成判据复核后写入 marker，故不需要对 ack 做来源过滤。
    返回 {sig: {verb, note}}，同一 sig 后到的申报覆盖先到的。"""
    acks = {}
    for body in bodies or []:
        for block in _ACK_BLOCK.findall(body or ""):
            for line in block.splitlines():
                line = line.strip()
                if not line:
                    continue
                m = _ACK_LINE.match(line)
                if not m:
                    continue
                acks[m.group("sig")] = {"verb": m.group("verb"),
                                        "note": (m.group("note") or "").strip()}
    return acks


def reconcile(prev, acks, current_findings, round_no=None, review_reliable=True):
    """按达成判据复核申报、吸收本轮新增发现，产出新一轮权威清单。

    - done：签名在本轮发现中不再出现才受理（deterministic=规则复检通过；review=定向复核未再报）；
            仍出现 → 保持 open，note 记复核未通过。
    - waived：必须带理由；受理后计入销项，报告中标给人核准。
    - split：必须带链接/编号；受理后计入销项。
    - 未申报但本轮发现中已消失的 open 项：同样销为 done（评审方复检即权威，申报缺席不阻塞）。
    - 本轮新增发现：追加为 open 项（清单跨轮累积，历史欠账不清零——供台账继承）。
    - review_reliable=False（本轮 LLM 评审不可信：引擎降级/可疑空收敛）时抑制依赖复检的销项：
      "签名本轮未再出现"此时不可靠（可能 diff 被裁空/LLM 随机性，非代码已改）。done 申报与
      自动销项均不触发，保持 open 待可靠轮复核；waived/split 仍受理（人判断不依赖 LLM）。
    """
    prev = prev or {"round": 0, "items": []}
    acks = acks or {}
    cur_sigs = {sig_of(f) for f in (current_findings or [])}
    items = [dict(i) for i in prev.get("items", [])]
    known = {i["sig"] for i in items}

    for it in items:
        if it["status"] in RESOLVED:
            continue
        ack = acks.get(it["sig"])
        still_firing = it["sig"] in cur_sigs
        if ack:
            verb, note = ack["verb"], ack["note"]
            if verb == "done":
                if still_firing:
                    it["note"] = "复核未通过：本轮仍命中，保持 open"
                elif not review_reliable:
                    it["note"] = "done 申报待可靠轮复核：本轮 LLM 评审不可信（引擎降级/可疑空收敛），暂不销项"
                else:
                    it["status"], it["note"] = "done", "申报并经复核销项"
            elif verb == "waived":
                if note:
                    # author 自证：受理为 waived（计入展示销项率），但标记待人核准——
                    # all_verified/收敛/放行不认它，机器不代人对"这是误报"拍板。
                    it["status"] = "waived"
                    it["note"] = f"author 宣称可豁免（待人核准，机器未验证）：{note}"
                else:
                    it["note"] = "waived 申报未带理由，不受理"
            elif verb == "split":
                if note:
                    it["status"] = "split"
                    it["note"] = f"author 宣称已拆出（待人核准，机器未验证）：{note}"
                else:
                    it["note"] = "split 申报未带链接/编号，不受理"
        elif not still_firing and review_reliable:
            it["status"], it["note"] = "done", "复检未再命中，销项"
        elif not still_firing and not review_reliable:
            it["note"] = "本轮 LLM 评审不可信（引擎降级/可疑空收敛），不予自动销项，待可靠轮复核"

    # 本轮新增发现 → 追加 open 项
    new_cl = from_findings(current_findings)
    for ni in new_cl["items"]:
        if ni["sig"] not in known:
            items.append(ni)

    rnd = round_no if round_no is not None else prev.get("round", 0) + 1
    return {"round": rnd, "items": items, "resolved_rate": _rate(items)}


def all_resolved(checklist):
    """所有项处于任一销项态（done/waived/split）——供展示与向后兼容。
    注意：不足以判定收敛或放行，那两处必须用 all_verified（waived/split 是 author 自证）。"""
    return all(i["status"] in RESOLVED for i in (checklist or {}).get("items", []))


def all_verified(checklist):
    """所有项均【机器可验证】销项（done）——收敛与自动放行的唯一合法依据。
    存在 waived/split（author 自证）时返回 False：这些项需人核准，机器不得代人闭环。"""
    return all(i["status"] in VERIFIED for i in (checklist or {}).get("items", []))


def unverified_claims(checklist):
    """返回 author 自证但未经机器核实的销项项（waived/split）——供收敛门与报告点名。"""
    return [i for i in (checklist or {}).get("items", [])
            if i.get("status") in CLAIMED]


def has_unverified_claims(checklist):
    return bool(unverified_claims(checklist))


def no_progress(prev, cur):
    """无推进判定（修订设计 §3 意见 3）：与上一轮相比销项数为零，且本轮无 waived/split 申报。
    覆盖「author 只发布评论不实际修改」的假修情形。prev 为空（首轮）不算无推进；
    prev.round==0（台账继承的种子清单——历史未销项并入，author 尚未获得本 PR 的修改机会）
    同样不算——该情形由真实数据回放发现：不加此闸，同源重提的第 1 轮会被误判无推进直接升级。"""
    if not prev or not prev.get("items") or prev.get("round", 0) == 0:
        return False
    def _n(cl):
        return sum(1 for i in cl.get("items", []) if i["status"] in RESOLVED)
    def _ws(cl):
        return sum(1 for i in cl.get("items", []) if i["status"] in ("waived", "split"))
    return _n(cur) <= _n(prev) and _ws(cur) <= _ws(prev)


_STATUS_MARK = {"open": "- [ ]", "done": "- [x]", "waived": "- [x]", "split": "- [x]"}
_STATUS_LABEL = {"open": "", "done": "✅ 已销项", "waived": "🟡 waived（待人核准）", "split": "🔀 已拆出"}


def render(checklist, rounds_left=None, lineage=None):
    """生成置顶评论正文：task list（人可读）+ 隐藏 JSON marker（权威状态，机器可读）。
    lineage：轮次台账的同源提示（评审意见 10），有则在头部明示历史欠账。"""
    cl = checklist or {"round": 0, "items": [], "resolved_rate": 1.0}
    # 版面铁律（易读性改版）：品牌名只在报告 H2 标题出现一次，本段与③④⑥并列用 H3；
    # 每轮重复的申报方式样板折叠进 <details>，不占屏。
    lines = [f"### 收敛清单（第 {cl['round']} 轮 · 销项率 "
             f"{int(cl['resolved_rate'] * 100)}%"
             + (f" · 剩余轮次 {rounds_left}" if rounds_left is not None else "") + "）"]
    if lineage and lineage.get("lineage"):
        hist = "、".join(f"#{e['number']}（{e['rounds']} 轮）" for e in lineage["lineage"])
        lines.append(f"> ⚠️ 与已关闭的 {hist} 内容同源：历史已消耗 {lineage.get('rounds_spent', 0)} 轮，"
                     f"未销项 {len(lineage.get('inherited_open_items', []))} 条已并入本清单，"
                     f"剩余轮次按台账计。人工重置请打 `rounds-reset` label。")
    lines.append("")
    for it in cl["items"]:
        mark = _STATUS_MARK.get(it["status"], "- [ ]")
        label = _STATUS_LABEL.get(it["status"], "")
        head = f"{mark} `{it['sig']}`" + (f" {label}" if label else "")
        lines.append(head)
        if it["direction"]:
            lines.append(f"  - 方向：{it['direction']}")
        if it["reasoning"] and it["reasoning"] != it["direction"]:
            lines.append(f"  - 依据：{it['reasoning']}")
        dc = it.get("done_criteria") or {}
        if dc.get("kind") == "deterministic":
            lines.append(f"  - 达成判据：规则 `{dc.get('spec', {}).get('recheck', '?')}` 复检不再命中")
        elif dc.get("kind") == "review":
            lines.append(f"  - 达成判据：{dc.get('spec', {}).get('question', '定向复核通过')}")
        if it["note"]:
            lines.append(f"  - 状态说明：{it['note']}")
    lines.append("")
    lines.append("<details><summary>如何申报销项</summary>")
    lines.append("")
    lines.append("发评论，内容为 ```touchstone-ack``` 代码块，每行 "
                 "`<签名>: done|waived: 理由|split: 链接`。勾选/申报是输入信号，"
                 "以评审方按达成判据复核后的本清单为准。")
    lines.append("")
    lines.append("</details>")
    lines.append("")
    lines.append(_OPEN + json.dumps(cl, ensure_ascii=False) + _CLOSE)
    return "\n".join(lines)


def parse_latest(bodies):
    """从（受信的）评论正文序列中取最新一份权威清单（marker 解析失败则跳过该条）。
    调用方须先用 loop.trusted_bodies 过滤——清单权威状态只信机器人自己发的评论。"""
    latest = None
    for body in bodies or []:
        start = 0
        while True:
            i = (body or "").find(_OPEN, start)
            if i < 0:
                break
            j = body.find(_CLOSE, i)
            if j < 0:
                break
            try:
                latest = json.loads(body[i + len(_OPEN):j].strip())
            except (json.JSONDecodeError, ValueError):
                pass
            start = j + len(_CLOSE)
    return latest


def snapshot(checklist, path=None):
    """本轮清单快照写入文件（checklist-round-N.json）——供可视化页面与校准回放。
    返回写入路径；失败返回 None（快照是旁路，不阻塞评审主链）。"""
    cl = checklist or {}
    path = path or f"checklist-round-{cl.get('round', 0)}.json"
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cl, f, ensure_ascii=False, indent=2)
        return path
    except OSError:
        return None
