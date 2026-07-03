"""#7 性能/回归 + #8 schema/契约稳定性 + #9 并发（latest-wins）测试。"""
import json
import re
import time

import contract_check as cc
import loop
import review_provider as rp


# ============================ #7 性能（时间预算断言，防 O(n²) 悄悄进去）============
def test_parse_diff_large_diff_under_budget():
    # ~500 文件 × 小 hunk ≈ 大 diff；parse_diff 应线性、秒级
    parts = []
    for i in range(500):
        parts.append(f"diff --git a/m{i}.py b/m{i}.py\n--- a/m{i}.py\n+++ b/m{i}.py\n"
                     f"@@ -0,0 +1,2 @@\n+x{i}\n+y{i}\n")
    diff = "".join(parts)
    t0 = time.time()
    files, added = cc.parse_diff(diff)
    dt = time.time() - t0
    assert len(files) == 500 and dt < 3.0           # 线性、< 3s（留余量给慢 CI）


def test_map_verdict_many_findings_under_budget():
    findings = []
    for i in range(500):
        findings += rp.normalize([{"kind": "suggestion", "file": f"a{i}.py", "line_start": 1,
                                   "label": "typo", "summary": "x"}])
    t0 = time.time()
    _, risk = rp.map_verdict(findings)
    dt = time.time() - t0
    assert dt < 2.0 and risk["risk_band"] in ("low", "mid", "high")


# ============================ #8 schema/契约稳定性（marker 前后兼容）============
def test_loop_marker_roundtrip_preserves_state():
    st = loop.LoopState(round=3, history=[["A:f:1"], ["A:f:2", "B:g:3"]], last_verdict=None)
    body = loop.render_marker(st)
    back = loop.parse_latest_state([body])
    assert back.round == 3 and back.history == st.history


def test_loop_marker_tolerates_extra_fields_forward_compat():
    """marker 加字段（未来扩展）不得破坏旧解析——calibrate 反向解析依赖此稳定性。"""
    import json as _j
    st = loop.LoopState(2, [["A"]], True)
    base = _j.loads(re.search(r"<!-- touchstone-loop: (.*?) -->", loop.render_marker(st), re.S).group(1))
    base["future_field"] = "x"                       # 模拟未来追加字段
    body = f"<!-- touchstone-loop: {_j.dumps(base)} -->"
    back = loop.parse_latest_state([body])
    assert back.round == 2                            # 仍正确解析核心字段


def test_loop_marker_ignores_corrupt_marker():
    """损坏/手改的 marker 不得让解析崩——降级为空状态（fail-safe）。"""
    back = loop.parse_latest_state(["<!-- touchstone-loop: {not json} -->", "普通评论"])
    assert back.round in (0, 1)                       # 解析失败 → 默认态，不抛


# ============================ #9 并发：latest-wins（快速连续多 marker）============
def test_parse_latest_state_picks_latest_among_many():
    """多个 marker（如并发/快速连续回帖）→ 取最后一个有效 round（latest-wins）。"""
    bodies = [
        loop.render_marker(loop.LoopState(r, [[f"A:{r}"]], None))
        for r in (1, 2, 3, 4)
    ]
    back = loop.parse_latest_state(bodies)
    assert back.round == 4                            # 最新的 round=4 胜出


def test_experience_store_save_load_idempotent(tmp_path):
    """save→load→save 往返一致（不累积/不丢字段）——离线侧的"原子性"基线。"""
    import learning_loop as L
    import os
    p = str(tmp_path / "s.json")
    os.environ["TOUCHSTONE_STORE_PATH"] = p
    s1 = {"experiences": [{"id": "e:::T", "finding_type": "T", "kind": "emphasize",
                           "text": "x", "evidence": {}, "status": "active", "source": "human",
                           "locked": True, "repo": "", "stack": "", "source_prs": [],
                           "created_at": 1, "updated_at": 1}]}
    L.save_store(s1, p)
    loaded = L.load_store(p)
    L.save_store(loaded, p)
    again = L.load_store(p)
    assert again == s1                                # 二次往返逐位一致
