"""自动放行达标路径（可选，默认关）：判据各闸 + 经验层。纯函数,离线。
准入只看总闸(gate=='success')；质量门禁/可信绿规则已下沉到 verify 插件(见 test_checks)。"""
from touchstone import autonomy as A


# ---------------- 变更分类 ----------------
def test_file_profile():
    assert A.file_profile(["docs/x.md", "a/y.md"]) == "docs_only"
    assert A.file_profile(["src/test/java/FooTest.java"]) == "test_only"
    assert A.file_profile(["src/main/Foo.java"]) == "code"
    assert A.file_profile(["src/main/Foo.java", "docs/x.md"]) == "mixed"


def test_change_class_signature(rule_index):
    risk = {"risk_band": "low", "blast_radius": []}
    cls = A.change_class(risk, [{"category": "convention"}], ["a.py"], rule_index)
    assert cls == "low|code|convention|none"
    cls2 = A.change_class({"risk_band": "high", "blast_radius": ["security_surface"]},
                          [{"rule_id": "SEC-001"}], ["docs/x.md"], rule_index)
    assert cls2 == "high|docs_only|security|security_surface"


# ---------------- 经验层 ----------------
def test_build_experience_counts_only_eligible():
    recs = [
        {"change_class": "low|code|none|none", "auto_eligible": True, "reverted": False},
        {"change_class": "low|code|none|none", "auto_eligible": True, "reverted": True},
        {"change_class": "low|code|none|none", "auto_eligible": False, "reverted": True},  # 不计
    ]
    exp = A.build_experience(recs)
    c = exp["low|code|none|none"]
    assert c["samples"] == 2 and c["bad"] == 1 and c["bad_rate"] == 0.5


def test_graduate_classes_thresholds():
    exp = {
        "A": {"samples": 25, "bad": 0, "bad_rate": 0.0},
        "B": {"samples": 25, "bad": 5, "bad_rate": 0.2},     # 坏率超阈
        "C": {"samples": 5, "bad": 0, "bad_rate": 0.0},      # 样本不足
    }
    grad = A.graduate_classes(exp, min_samples=20, max_bad_rate=0.05)
    assert grad == {"A"}


# ---------------- 判据各闸（准入只看总闸 gate）----------------
def _ok_inputs():
    risk = {"risk_band": "low", "blast_radius": []}
    return dict(risk=risk, findings=[], loop_decision="converged", gate="success",
                autonomy_state={"tripped": False},
                graduated_classes={"low|code|none|none"}, cls="low|code|none|none")


def test_decide_disabled_by_default():
    d = A.decide_auto_merge(**_ok_inputs(), enabled=False)
    assert d["merge"] is False and d["mode"] == "disabled"


def test_decide_all_gates_pass_live():
    d = A.decide_auto_merge(**_ok_inputs(), enabled=True, shadow=False)
    assert d["merge"] is True and d["mode"] == "live" and d["failed"] == []


def test_decide_blocks_when_not_graduated():
    inp = _ok_inputs()
    inp["graduated_classes"] = set()
    d = A.decide_auto_merge(**inp, enabled=True)
    assert d["merge"] is False and "class_graduated" in d["failed"]


def test_decide_blocking_veto_high_band():
    inp = _ok_inputs()
    inp["risk"] = {**inp["risk"], "risk_band": "high"}
    d = A.decide_auto_merge(**inp, enabled=True)
    assert d["merge"] is False and "no_blocking_veto" in d["failed"]


def test_decide_blocking_veto_block_candidate():
    inp = _ok_inputs()
    inp["findings"] = [{"rule_id": "CTR-001", "severity": "block_candidate"}]
    d = A.decide_auto_merge(**inp, enabled=True)
    assert d["merge"] is False and "no_blocking_veto" in d["failed"]


def test_decide_blocks_when_tripped():
    inp = _ok_inputs()
    inp["autonomy_state"] = {"tripped": True}
    d = A.decide_auto_merge(**inp, enabled=True)
    assert d["merge"] is False and "not_tripped" in d["failed"]


def test_decide_blocks_when_gate_not_success():
    # 总闸非 success（契约/规则/可选 verify 任一未过都会让总闸 failure）→ 不放行
    inp = _ok_inputs()
    inp["gate"] = "failure"
    d = A.decide_auto_merge(**inp, enabled=True)
    assert d["merge"] is False and "quality_gate" in d["failed"]


def test_decide_blocks_when_gate_missing():
    inp = _ok_inputs()
    inp["gate"] = None      # touchstone 未产出总闸（无 checks 配置等）→ 不放行
    d = A.decide_auto_merge(**inp, enabled=True)
    assert d["merge"] is False and "quality_gate" in d["failed"]


def test_decide_blocks_when_loop_escalated():
    inp = _ok_inputs()
    inp["loop_decision"] = "escalate"
    d = A.decide_auto_merge(**inp, enabled=True)
    assert d["merge"] is False and "loop_converged" in d["failed"]


def test_decide_shadow_would_merge_but_not():
    d = A.decide_auto_merge(**_ok_inputs(), enabled=True, shadow=True)
    assert d["merge"] is False and d["mode"] == "shadow" and d.get("would_merge") is True


# ---------------- Actions 闭环：输入组装 / 经验重建 / 达标发布 ----------------
def test_build_decision_inputs_from_touchstone_output():
    co = {"risk": {"risk_band": "low"}, "change_class": "low|code|none|none",
          "loop_decision": "converged", "gate": "success",
          "findings": [{"rule_id": "OE-001", "agent": "touchstone-rules"}]}
    d = A.build_decision_inputs(co, {"tripped": False}, ["low|code|none|none"])
    assert d["cls"] == "low|code|none|none" and d["loop_decision"] == "converged"
    assert d["gate"] == "success" and d["graduated_classes"] == ["low|code|none|none"]


def test_reconstruct_auto_eligible():
    clean = {"risk_band": "low", "loop_decision": "converged",
             "findings": [{"rule_id": "OE-001", "agent": "touchstone-rules", "severity": "warn"}]}
    assert A.reconstruct_auto_eligible(clean) is True
    # high 档 → 否决
    assert A.reconstruct_auto_eligible({**clean, "risk_band": "high"}) is False
    # block_candidate → 否决
    assert A.reconstruct_auto_eligible(
        {**clean, "findings": [{"severity": "block_candidate"}]}) is False
    # 未收敛 → 否
    assert A.reconstruct_auto_eligible({**clean, "loop_decision": "escalate"}) is False
    # 契约不净 → 否
    assert A.reconstruct_auto_eligible(
        {**clean, "findings": [{"agent": "contract-check"}]}) is False


def test_graduate_from_calibration():
    # 同一变更分类，足量人合并样本、均干净(未 revert) → 达标
    base = {"risk_band": "low", "loop_decision": "converged", "change_class": "low|code|none|none",
            "findings": [], "merged": True, "merge_commit_sha": None}
    records = [dict(base) for _ in range(A.GRAD_MIN_SAMPLES)]
    grad = A.graduate_from_calibration(records)
    assert "low|code|none|none" in grad
    # 若其中若干被 revert(坏率超阈) → 不达标
    bad = [dict(base, merge_commit_sha=f"sha{i}") for i in range(A.GRAD_MIN_SAMPLES)]
    grad2 = A.graduate_from_calibration(bad, reverted_shas={f"sha{i}" for i in range(A.GRAD_MIN_SAMPLES)})
    assert "low|code|none|none" not in grad2


# ---------------- 边界：file_profile / 毕业阈值 / 自动放行六道闸 ----------------
def test_file_profile_categories():
    assert A.file_profile([]) == "empty"
    assert A.file_profile(["README.md", "docs/x.html"]) == "docs_only"
    assert A.file_profile(["src/test/Foo.java", "tests/test_x.py"]) == "test_only"
    assert A.file_profile(["src/main/Foo.java"]) == "code"
    assert A.file_profile(["src/main/Foo.java", "README.md"]) == "mixed"


def test_graduate_classes_boundaries():
    exp = {"c1": {"samples": 20, "bad": 1, "bad_rate": 0.05},   # ==20 且 ==0.05 → 达标(含等号)
           "c2": {"samples": 19, "bad": 0, "bad_rate": 0.0},    # 样本差 1 → 不达标
           "c3": {"samples": 50, "bad": 3, "bad_rate": 0.06}}   # 坏率超 → 不达标
    assert A.graduate_classes(exp) == {"c1"}


def test_build_experience_only_eligible_and_bad_rate():
    recs = [{"change_class": "x", "auto_eligible": True, "reverted": True},
            {"change_class": "x", "auto_eligible": True, "hotfixed": True},
            {"change_class": "x", "auto_eligible": True},
            {"change_class": "x", "auto_eligible": False, "reverted": True}]  # 非 eligible 不计
    exp = A.build_experience(recs)
    assert exp["x"]["samples"] == 3 and exp["x"]["bad"] == 2
    assert exp["x"]["bad_rate"] == round(2 / 3, 3)


_CLS = "low|code|none|none"
def _ok(**kw):
    base = dict(risk={"risk_band": "low"}, findings=[], loop_decision="converged",
                gate="success", autonomy_state={"tripped": False},
                graduated_classes={_CLS}, cls=_CLS, enabled=True, shadow=False)
    base.update(kw); return base


def test_decide_auto_merge_disabled_and_live():
    assert A.decide_auto_merge(**_ok(enabled=False))["mode"] == "disabled"
    d = A.decide_auto_merge(**_ok())
    assert d["merge"] is True and not d["failed"]


def test_decide_auto_merge_each_gate_fails():
    assert "quality_gate" in A.decide_auto_merge(**_ok(gate="failure"))["failed"]
    assert "no_blocking_veto" in A.decide_auto_merge(**_ok(risk={"risk_band": "high"}))["failed"]
    assert "no_blocking_veto" in A.decide_auto_merge(
        **_ok(findings=[{"severity": "block_candidate"}]))["failed"]
    assert "loop_converged" in A.decide_auto_merge(**_ok(loop_decision="escalate"))["failed"]
    assert "not_tripped" in A.decide_auto_merge(**_ok(autonomy_state={"tripped": True}))["failed"]
    assert "class_graduated" in A.decide_auto_merge(**_ok(graduated_classes=set()))["failed"]


def test_decide_auto_merge_shadow_would_merge():
    d = A.decide_auto_merge(**_ok(shadow=True))
    assert d["merge"] is False and d.get("would_merge") is True and d["mode"] == "shadow"


def test_graduate_from_calibration_and_decision_inputs():
    recs = [{"merged": True, "change_class": "x", "loop_decision": "converged",
             "findings": [], "risk_band": "low", "merge_commit_sha": "aaa"} for _ in range(20)]
    assert "x" in A.graduate_from_calibration(recs, reverted_shas=set())
    # 含 contract-check 发现 → 非 auto_eligible
    assert not A.reconstruct_auto_eligible({"loop_decision": "converged", "risk_band": "low",
                                            "findings": [{"agent": "contract-check"}]})
    inp = A.build_decision_inputs({"risk": {"risk_band": "low"}, "gate": "success",
                                   "change_class": _CLS, "loop_decision": "converged"}, {}, {_CLS})
    assert inp["gate"] == "success" and inp["cls"] == _CLS


# ============ 第七道闸·基线新鲜度（merge skew 防护）回归 ============
def test_base_fresh_gate_blocks_stale_base():
    """基线过期（base_fresh=False）→ 即便其余闸全绿也拒绝自动放行；None（未评估）保持兼容不拦。"""
    from touchstone import autonomy as A
    kw = dict(risk={"risk_band": "low"}, findings=[], loop_decision="converged",
              gate="success", autonomy_state={}, graduated_classes={"low|code"},
              cls="low|code", enabled=True, shadow=False)
    assert A.decide_auto_merge(**kw, base_fresh=None)["merge"] is True     # 未评估：兼容旧行为
    dec = A.decide_auto_merge(**kw, base_fresh=False)
    assert dec["merge"] is False and "base_fresh" in dec["failed"]         # 过期：拒放行
    assert A.decide_auto_merge(**kw, base_fresh=True)["merge"] is True


def test_is_base_fresh_pure_compare():
    from touchstone import autonomy as A
    assert A.is_base_fresh({"base": {"sha": "abc"}}, "abc") is True
    assert A.is_base_fresh({"base": {"sha": "abc"}}, "def") is False       # main 已前进 → 过期
    assert A.is_base_fresh({}, "abc") is False                             # 数据缺失 → 不算新鲜


def test_enqueue_auto_merge_uses_graphql_queue(monkeypatch):
    """queue 模式：GraphQL 取 node id → enablePullRequestAutoMerge，排队/批测交给平台。"""
    from touchstone import autonomy as A
    calls = []
    def fake(url, headers, payload):
        calls.append(payload["query"][:30])
        if "enablePullRequestAutoMerge" in payload["query"]:
            assert payload["variables"]["id"] == "NODE1"
            return {"data": {"enablePullRequestAutoMerge": {}}}
        return {"data": {"repository": {"pullRequest": {"id": "NODE1"}}}}
    monkeypatch.setattr(A, "_gql_post", fake)
    A.enqueue_auto_merge("o/r", 7, "tok")
    assert len(calls) == 2 and "mutation" in calls[1]


# ---------------- 网络函数（mock ghclient.request，与实现同口径）----------------
def _mock_gh_request(monkeypatch, seq):
    """按调用顺序返回 seq 中的响应；元素为 Exception 则抛出（模拟网络/HTTP 错误）。"""
    it = iter(seq)
    def fake(method, url, token, data=None, accept="application/vnd.github+json",
             session=None, timeout=60):
        v = next(it)
        if isinstance(v, Exception):
            raise v
        return v
    monkeypatch.setattr(A.ghclient, "request", fake)


def test_check_base_fresh_fresh(monkeypatch):
    # PR base sha == base 分支 head sha → 新鲜
    _mock_gh_request(monkeypatch, [
        {"base": {"ref": "main", "sha": "abc"}, "head": {"sha": "abc"}},
        {"sha": "abc"},
    ])
    assert A.check_base_fresh("o/r", 7, "tok") is True


def test_check_base_fresh_stale_triggers_update(monkeypatch, capsys):
    # base sha != base head → 过期，update_if_behind 调 update-branch → 返回 False
    _mock_gh_request(monkeypatch, [
        {"base": {"ref": "main", "sha": "old"}, "head": {"sha": "new"}},
        {"sha": "newest"},
        {"ok": True},                               # update-branch 响应
    ])
    assert A.check_base_fresh("o/r", 7, "tok") is False
    assert "update-branch" in capsys.readouterr().err


def test_check_base_fresh_stale_no_update(monkeypatch):
    _mock_gh_request(monkeypatch, [
        {"base": {"ref": "main", "sha": "old"}, "head": {"sha": "new"}},
        {"sha": "new"},
    ])
    assert A.check_base_fresh("o/r", 7, "tok", update_if_behind=False) is False


def test_check_base_fresh_api_error_returns_none(monkeypatch):
    import requests
    _mock_gh_request(monkeypatch, [requests.exceptions.ConnectionError("boom")])
    assert A.check_base_fresh("o/r", 7, "tok") is None


def test_check_base_fresh_update_branch_failure_still_false(monkeypatch, capsys):
    import requests
    _mock_gh_request(monkeypatch, [
        {"base": {"ref": "main", "sha": "old"}, "head": {"sha": "new"}},
        {"sha": "new"},
        requests.exceptions.HTTPError("500"),        # update-branch 失败
    ])
    assert A.check_base_fresh("o/r", 7, "tok") is False
    assert "update-branch 失败" in capsys.readouterr().err


def test_enqueue_auto_merge_success(monkeypatch):
    calls = []
    resps = [{"data": {"repository": {"pullRequest": {"id": "NODE_ID"}}}}, {}]
    def fake_post(url, token, payload):
        calls.append(payload)
        return resps.pop(0)                          # 第一次=query(node id)，第二次=mutation
    monkeypatch.setattr(A, "_gql_post", fake_post)
    assert A.enqueue_auto_merge("o/r", 7, "tok") == {}
    assert calls[1]["variables"]["id"] == "NODE_ID"


def test_enqueue_auto_merge_no_node_id_raises(monkeypatch):
    monkeypatch.setattr(A, "_gql_post", lambda *a: {"errors": ["no pr"]})
    import pytest
    with pytest.raises(RuntimeError, match="node id"):
        A.enqueue_auto_merge("o/r", 7, "tok")


def test_enqueue_auto_merge_mutation_error_raises(monkeypatch):
    seq = [{"data": {"repository": {"pullRequest": {"id": "N"}}}}, {"errors": ["denied"]}]
    monkeypatch.setattr(A, "_gql_post", lambda *a: seq.pop(0))
    import pytest
    with pytest.raises(RuntimeError, match="入队失败"):
        A.enqueue_auto_merge("o/r", 7, "tok")


# ---------------- review_reliable 闸：引擎不可信时不自动放行 ----------------
def test_decide_blocks_when_review_unreliable():
    # 各闸本全过，但本轮 LLM 评审不可信（引擎降级/可疑空收敛）-> 不自动放行，回落人
    d = A.decide_auto_merge(**_ok_inputs(), enabled=True, shadow=False, review_reliable=False)
    assert d["merge"] is False and "review_reliable" in d["failed"]


def test_decide_review_reliable_true_does_not_block():
    # review_reliable=True 不入 failed（默认值，保旧行为）
    d = A.decide_auto_merge(**_ok_inputs(), enabled=True, shadow=False, review_reliable=True)
    assert d["merge"] is True and "review_reliable" not in d["failed"]


def test_build_decision_inputs_reads_review_reliable():
    co = {"risk": {"risk_band": "low"}, "findings": [], "loop_decision": "converged",
          "gate": "success", "change_class": "low|code|none|none",
          "review_reliable": False, "engine_status": "ok", "ai_raw_count": 0, "added_lines": 25}
    d = A.build_decision_inputs(co, {"tripped": False}, ["low|code|none|none"])
    assert d["review_reliable"] is False


def test_build_decision_inputs_recomputes_when_field_absent():
    # 旧产物无 review_reliable 字段 -> 从 engine_status/ai_raw_count/added_lines 重算（向后兼容）
    co = {"risk": {"risk_band": "low"}, "findings": [], "loop_decision": "converged",
          "gate": "success", "change_class": "low|code|none|none",
          "engine_status": "llm_failed", "ai_raw_count": 0, "added_lines": 5}
    d = A.build_decision_inputs(co, {"tripped": False}, [])
    assert d["review_reliable"] is False  # llm_failed -> 不可靠
