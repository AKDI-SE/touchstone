# ============================================================================
# tests/test_checklist.py —— checklist 快照的原子写与旁路语义（商用审计 P2-3）
# ============================================================================
def test_snapshot_atomic_and_failure_returns_none(tmp_path, monkeypatch):
    # P2-3：快照走 atomicio（半文件毁校准回放）；失败仍返回 None（旁路不阻塞主链）
    import json as _json
    import touchstone.checklist as CL
    p = tmp_path / "checklist-round-1.json"
    cl = {"round": 1, "items": []}
    assert CL.snapshot(cl, str(p)) == str(p)
    assert _json.loads(p.read_text(encoding="utf-8")) == cl      # 落盘完整可解析
    def _boom(path, obj):
        raise OSError("disk full")
    monkeypatch.setattr(CL, "atomic_write_json", _boom)
    assert CL.snapshot(cl, str(tmp_path / "x.json")) is None
