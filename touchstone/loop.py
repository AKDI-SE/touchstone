#!/usr/bin/env python3
# ============================================================================
# touchstone/loop.py  ——  反馈循环控制器 loop_step（设计 §4.3）
# ----------------------------------------------------------------------------
# 在 touchstone 侧(中立方,非 author)bound 住「author 改 → 重提 → 再审」的循环。
# 只管【可自改发现】(结构层 = 非正确性类 且 有 suggested_fix)；
#   正确性不在此解决——交 verify/人。
# converged ≠ correct：converged 仅表示无更多可自改发现，正确性由 verify job 正交把关。
# 状态持久化：存在 PR 评论的隐藏 marker 里，轮次由历史 marker 派生（author 无法篡改）。
# ============================================================================

import json
from dataclasses import dataclass, field
from typing import Optional

MAX_ROUNDS = 3
_OPEN = "<!-- touchstone-loop:"
_CLOSE = "-->"

# 正确性类 category（含 PR-Agent 源的 "correctness"）：不进自改循环，交 verify/人。
_CORRECTNESS_CATEGORIES = {"correctness", "correctness_suspect", "weak_test"}


@dataclass
class LoopState:
    round: int = 0
    history: list = field(default_factory=list)   # 每轮的可自改发现签名集（list[list[str]]）
    last_verdict: Optional[bool] = None           # 上轮 CI/verify 判定：True 绿 / False 红 / None 未知


def _sig(f):
    return f"{f.get('rule_id')}:{f.get('file')}:{f.get('line')}"


def author_actionable(findings, rule_index):
    """可由 author 自改的发现：非正确性类 且 有 suggested_fix。
    正确性判定双路：① 在册规则的 class==correctness；② 发现自带 category 落在正确性集合
    （覆盖 PR-Agent 源的 PRA-* 发现——其 rule_id 不在 standards rule_index，单靠 ① 会漏网）。"""
    out = []
    for f in findings:
        if rule_index.get(f.get("rule_id"), {}).get("class") == "correctness":
            continue                                   # 在册正确性规则
        if f.get("category") in _CORRECTNESS_CATEGORIES:
            continue                                   # PR-Agent 源 correctness（PRA-* 等）
        if not (f.get("suggested_fix") or "").strip():
            continue
        out.append(f)
    return out


def loop_step(findings, rule_index, state, max_rounds=MAX_ROUNDS, ci_passed=None):
    """返回 (decision, reason, new_state)。decision ∈ converged|continue|escalate。
    ci_passed：当前轮 CI/verify 判定（True 绿 / False 红 / None 未知）。
    发现清零但 CI 红时不收敛——发 continue 让 author 接着修构建/测试（仍受轮次上限约束）。
    安全性不依赖此项：converged 与否都不放行，自动合并另有独立的质量门禁（总闸）闸。"""
    acts = author_actionable(findings, rule_index)
    cur = sorted({_sig(f) for f in acts})
    prev_sets = [set(h) for h in state.history]
    nr = state.round + 1
    hist = (state.history + [cur])[-(max_rounds + 1):]   # 限长,避免 marker 膨胀

    # 收敛：无可自改发现。但若【已知 CI/verify 为红】则不算改完——提示 author 接着修。
    if not cur:
        if ci_passed is False:
            if nr >= max_rounds:
                return ("escalate",
                        f"发现已清但 CI/verify 持续为红，轮次耗尽（≥ {max_rounds}）→ 交人",
                        LoopState(nr, hist, ci_passed))
            return ("continue",
                    "委员会发现已清，但 CI/verify 为红：请修复构建/测试失败后再 push",
                    LoopState(nr, hist, ci_passed))
        return "converged", "无可自改发现（正确性另由 verify 把关）", LoopState(nr, hist, ci_passed)

    # 震荡：发现集与历史某轮完全重复（改了又冒出同一组）
    if set(cur) in prev_sets:
        return "escalate", "震荡：发现集重复出现，自改未推进", LoopState(nr, hist, ci_passed)

    # 无推进：相比上一轮既没减少、也没解决任何既有发现（含假修 / 协商降级）
    if prev_sets:
        last = prev_sets[-1]
        if len(cur) >= len(last) and not (last - set(cur)):
            return "escalate", "无推进：既未减少也未解决既有发现（含假修/协商降级）", LoopState(nr, hist, ci_passed)

    # 轮次耗尽
    if nr >= max_rounds:
        return "escalate", f"轮次耗尽（≥ {max_rounds}）仍有可自改发现", LoopState(nr, hist, ci_passed)

    return "continue", f"第 {nr} 轮，待 author 自改 {len(cur)} 项", LoopState(nr, hist, ci_passed)


# --- 状态持久化（PR 评论隐藏 marker）----------------------------------------
def render_marker(state):
    payload = json.dumps({"round": state.round, "history": state.history,
                          "last_verdict": state.last_verdict}, ensure_ascii=False)
    return f"{_OPEN} {payload} {_CLOSE}"


def parse_latest_state(comment_bodies):
    """从历史评论里取轮次最大的 loop marker；无则返回初始状态。"""
    latest = LoopState()
    for body in comment_bodies or []:
        i = body.rfind(_OPEN)
        if i == -1:
            continue
        j = body.find(_CLOSE, i)
        if j == -1:
            continue
        try:
            d = json.loads(body[i + len(_OPEN):j].strip())
            st = LoopState(int(d.get("round", 0)), list(d.get("history", [])),
                           d.get("last_verdict"))
            if st.round >= latest.round:
                latest = st
        except (json.JSONDecodeError, ValueError, TypeError):
            continue
    return latest
