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
    recs = [_rec(reliable=True, decision="converged"),
            _rec(reliable=False, engine="llm_failed", ai=0),   # 静默故障
            _rec(reliable=True, claims=1)]                     # 被自证闸拦
    s = M.summarize(recs)
    assert s["rounds"] == 3
    assert s["review_reliable_rate"] == round(2 / 3, 3)
    assert s["silent_failure_rounds"] == 1
    assert s["blocked_by_unverified_claims"] == 1
    assert s["engine_status_dist"]["llm_failed"] == 1


def test_summarize_empty():
    assert M.summarize([])["rounds"] == 0
