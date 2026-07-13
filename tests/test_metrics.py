# ============================================================================
# tests/test_metrics.py —— 运行指标（运维可观测性，商用化 P0-3.2）
# ============================================================================
import json

from touchstone import metrics as M


def _rec(reliable=True, engine="ok", ai=2, decision="continue", claims=0):
    risk = {"risk_band": "high"}
    findings = ([{"agent": "contract"}] + [{"agent": "pr-agent"}] * ai) if ai else []
    return M.build(42, "deadbeef1234", risk, findings,
                   engine_status=engine, review_reliable=reliable, ai_raw_count=ai,
                   loop_decision=decision, gate="2/3", unverified_claims=claims,
                   change_class="code", added_lines=100)


def test_build_flat_serializable():
    r = _rec()
    json.dumps(r)                                    # 必须可序列化
    assert r["review_reliable"] is True and r["engine_status"] == "ok"
    assert r["findings_rule_based"] == 1 and r["findings_ai"] == 2
    assert r["sha"] == "deadbeef1234" and "version" in r


def test_emit_and_load_roundtrip(tmp_path):
    p = tmp_path / "m.json"
    assert M.emit(_rec(), path=str(p)) and M.emit(_rec(reliable=False), path=str(p))
    recs = M.load(str(p))
    assert len(recs) == 2


def test_load_skips_corrupt_lines(tmp_path):
    p = tmp_path / "m.json"
    p.write_text('{"ok":1}\n{bad json\n{"ok":2}\n', encoding="utf-8")
    assert len(M.load(str(p))) == 2                  # 坏行跳过，不拖垮聚合


def test_summarize_rates():
    recs = [_rec(reliable=True, decision="converged"),         # 收敛轮（engine ok）
            _rec(reliable=False, engine="ok", ai=0),           # 静默故障：engine 报 ok 却不可信
            _rec(reliable=True, claims=1)]                     # 被自证闸拦（engine ok）
    s = M.summarize(recs)
    assert s["rounds"] == 3
    assert s["review_reliable_rate"] == round(2 / 3, 3)
    assert s["silent_failure_rounds"] == 1
    assert s["blocked_by_unverified_claims"] == 1
    assert s["engine_status_dist"] == {"ok": 3}


def test_summarize_detected_failure_is_not_silent():
    """llm_failed / provider_failed 是引擎【已检测到】的故障，不算静默——只有
    engine_status=='ok' 却 review_reliable=False 才算（false-convergence 守则抓的）。
    锁死 silent 计数不把这些大声报错的状态计入，避免虚高静默指标误导运维。"""
    recs = [_rec(reliable=False, engine="llm_failed", ai=0),
            _rec(reliable=False, engine="provider_failed", ai=0)]
    s = M.summarize(recs)
    assert s["silent_failure_rounds"] == 0
    assert s["review_reliable_rate"] == 0.0
    assert s["engine_status_dist"]["llm_failed"] == 1
    assert s["engine_status_dist"]["provider_failed"] == 1


def test_summarize_empty():
    """空记录也必须返回完整 schema（零值默认）——下游监控/告警直接 index rate 字段，
    若空时只回 {"rounds":0} 会 KeyError。"""
    s = M.summarize([])
    assert s["rounds"] == 0
    assert s["review_reliable_rate"] == 0.0
    assert s["silent_failure_rounds"] == 0
    assert s["converged_rate"] == 0.0
    assert s["blocked_by_unverified_claims"] == 0
    assert s["engine_status_dist"] == {}


def test_build_carries_round_no():
    """round_no 必须透传到 record['round']。orchestrator 曾因 `round_no=(loop_info and None)`
    笔误（loop_info 是 tuple、恒返回 None）致该字段恒为 null，可观测性失真——此测试锁死
    build 不丢 round_no（修复见 orchestrator.py metrics.emit 调用处）。"""
    r = M.build(42, "deadbeef1234", {"risk_band": "high"}, [],
                engine_status="ok", review_reliable=True, ai_raw_count=0,
                loop_decision="converged", gate="2/3", unverified_claims=0,
                change_class="code", added_lines=10, round_no=7)
    assert r["round"] == 7
