"""反馈循环 + 治理(固化/熔断) + 校准聚合。"""
import calibrate
import govern
import loop


# ---------------- loop ----------------
def _f(rid, file="f", line=1, fix="改这里"):
    return {"rule_id": rid, "file": file, "line": line, "suggested_fix": fix}


def test_loop_converged_when_no_actionable(rule_index):
    dec, _, st = loop.loop_step([], rule_index, loop.LoopState())
    assert dec == "converged" and st.round == 1


def test_loop_continue_with_actionable(rule_index):
    dec, _, st = loop.loop_step([_f("OE-001")], rule_index, loop.LoopState())
    assert dec == "continue" and st.round == 1


def test_loop_correctness_not_author_actionable(rule_index):
    # COR-001 class=correctness → 不交自改，交 verify/人 → converged
    dec, _, _ = loop.loop_step([_f("COR-001")], rule_index, loop.LoopState())
    assert dec == "converged"


def test_loop_excludes_pra_correctness_findings(rule_index):
    # PR-Agent "critical bug" → rule_id PRA-CRITICAL_BUG（不在 rule_index），category=correctness
    # 修复前：单靠 rule_index[rid].class 查不到 → 漏网判可自改；修复后：按 category 排除。
    pra = {"rule_id": "PRA-CRITICAL_BUG", "file": "f", "line": 1,
           "category": "correctness", "suggested_fix": "修这个 bug"}
    assert loop.author_actionable([pra], rule_index) == []
    conv = {"rule_id": "PRA-CONVENTION", "file": "f", "line": 1,
            "category": "convention", "suggested_fix": "改名"}
    assert loop.author_actionable([conv], rule_index) == [conv]


def test_loop_escalate_on_oscillation(rule_index):
    st = loop.LoopState(round=1, history=[["OE-001:f:1"]])
    dec, reason, _ = loop.loop_step([_f("OE-001", line=1)], rule_index, st)
    assert dec == "escalate" and "震荡" in reason


def test_loop_escalate_on_max_rounds(rule_index):
    st = loop.LoopState(round=3, history=[["OE-001:f:1"]])
    dec, reason, _ = loop.loop_step([_f("OE-001", line=2)], rule_index, st)   # 新签名,有推进
    assert dec == "escalate" and "轮次" in reason


def test_loop_marker_roundtrip():
    st = loop.LoopState(round=2, history=[["OE-001:f:1"], ["OE-001:f:2"]])
    body = loop.render_marker(st)
    back = loop.parse_latest_state([body])
    assert back.round == 2 and back.history == st.history


# ---------------- govern.promote_to_gate / apply ----------------
def test_promote_candidate_machine_checkable_recurring_high_adoption(rule_index):
    agg = {"by_rule": {"CTR-001": {"fires": 6, "changes_requested_rate": 0.6}}}
    cands = govern.promote_to_gate(agg, rule_index)
    assert any(c["rule_id"] == "CTR-001" for c in cands)


def test_promote_skips_non_machine_checkable(rule_index):
    agg = {"by_rule": {"OE-001": {"fires": 9, "changes_requested_rate": 0.9}}}  # OE-001 mc=False
    assert govern.promote_to_gate(agg, rule_index) == []


def test_promote_skips_low_adoption(rule_index):
    agg = {"by_rule": {"CTR-001": {"fires": 9, "changes_requested_rate": 0.2}}}  # 高命中低采纳=噪声
    assert govern.promote_to_gate(agg, rule_index) == []


def test_apply_promotions_sets_enforced_without_mutating_original():
    standards = {"rules": [{"id": "CTR-001"}, {"id": "OE-001"}]}
    new = govern.apply_promotions(standards, [{"rule_id": "CTR-001"}])
    assert {r["id"]: r.get("enforced") for r in new["rules"]} == {"CTR-001": True, "OE-001": None}
    assert "enforced" not in standards["rules"][0]   # 原对象未被改


# ---------------- govern.update_autonomy ----------------
def test_autonomy_trips_on_high_revert():
    recs = [{"auto_handled": True, "reverted": True}] * 2 + [{"auto_handled": True}] * 8
    out = govern.update_autonomy(recs)            # revert_rate 0.2 > 0.10
    assert out["tripped"] and out["revert_rate"] == 0.2


def test_autonomy_ok_when_clean():
    recs = [{"auto_handled": True}] * 10
    out = govern.update_autonomy(recs)
    assert not out["tripped"] and out["revert_rate"] == 0.0


def test_autonomy_drift_computed():
    recs = [{"touchstone_approved": True}] * 10
    out = govern.update_autonomy(recs, prior_approval_rate=0.0)
    assert out["approval_rate"] == 1.0 and out["approval_drift"] == 1.0


# ---------------- govern.build_merge_records（读真实 auto_handled marker）----------
def test_build_merge_records_uses_marker_not_low_risk():
    records = [
        {"pr": 1, "merged": True, "risk_band": "low", "merge_commit_sha": "aaa"},            # 低风险但无 marker
        {"pr": 2, "merged": True, "risk_band": "mid", "merge_commit_sha": "bbb",
         "auto_handled": True},                                                               # 真实自动放行
    ]
    recs = govern.build_merge_records(records, set())
    by_pr = {r["pr"]: r for r in recs}
    assert by_pr[1]["auto_handled"] is False      # 不再用 risk_band=='low' 代理
    assert by_pr[2]["auto_handled"] is True
    assert all(r["hotfixed"] is False for r in recs)   # hotfix 检测尚未接通（已知）


def test_aggregate_consumes_record_calibration_shape():
    # record_calibration 产 touchstone_*/human_verdict 形状；aggregate 经 _norm_record 应正确消费
    rec = calibrate.record_calibration(
        7, {"findings": [{"rule_id": "PRA-X", "agent": "pr-agent:suggestion"}],
            "risk": {"risk_band": "high"}}, "CHANGES_REQUESTED")
    agg = calibrate.aggregate([rec])
    assert agg["total"] == 1 and agg["prs_with_findings"] == 1
    assert agg["by_risk"]["high"]["count"] == 1
    assert agg["overall_changes_requested_rate"] == 1.0


# ---------------- calibrate.aggregate ----------------
def test_calibrate_aggregate_counts_and_rates():
    records = [
        {"risk_band": "high", "findings": [{"rule_id": "CTR-001", "agent": "安全"}],
         "human_state": "CHANGES_REQUESTED"},
        {"risk_band": "low", "findings": [], "human_state": "APPROVED"},
    ]
    agg = calibrate.aggregate(records)
    assert agg["total"] == 2 and agg["prs_with_findings"] == 1
    assert agg["by_rule"]["CTR-001"]["fires"] == 1
    assert agg["by_rule"]["CTR-001"]["changes_requested_rate"] == 1.0


def test_calibrate_flags_noisy_rule():
    n = calibrate.NOISY_MIN_FIRES + 1
    records = [{"risk_band": "low", "findings": [{"rule_id": "NRULE", "agent": "A"}],
                "human_state": "APPROVED"} for _ in range(n)]   # cr=0 < 噪声阈值
    agg = calibrate.aggregate(records)
    assert agg["by_rule"]["NRULE"]["fires"] == n
    assert any(x["key"] == "NRULE" for x in agg["noisy"])


# ---------------- finding 级人采纳（GraphQL 线程 resolved）----------------
def _gql(threads):
    return {"data": {"repository": {"pullRequest": {"reviewThreads": {"nodes": threads}}}}}


def _thread(resolved, login, body):
    return {"isResolved": resolved, "comments": {"nodes": [{"author": {"login": login}, "body": body}]}}


def _mk(rule_id, agent="A"):
    return ("`%s` 说明\n<!-- touchstone-finding: {\"rule_id\": \"%s\", \"agent\": \"%s\"} -->"
            % (rule_id, rule_id, agent))


def test_parse_review_threads():
    data = _gql([_thread(True, "bot", "x"), _thread(False, "y", "z")])
    th = calibrate.parse_review_threads(data)
    assert len(th) == 2 and th[0]["isResolved"] is True and th[1]["isResolved"] is False


def test_thread_findings_matches_marker_only():
    raw = [_thread(True, "github-actions[bot]", _mk("SPR-DI-001")),
           _thread(False, "github-actions[bot]", _mk("JAVA-EQ-001")),
           _thread(True, "alice", "纯人类讨论，无标记")]   # 无标记 → 不计
    fa = calibrate.thread_findings(calibrate.parse_review_threads(_gql(raw)))
    assert fa == [{"rule_id": "SPR-DI-001", "agent": "A", "resolved": True},
                  {"rule_id": "JAVA-EQ-001", "agent": "A", "resolved": False}]


def test_calibrate_finding_adoption_rate():
    fa = [{"rule_id": "R1", "agent": "A", "resolved": True},
          {"rule_id": "R1", "agent": "A", "resolved": False},
          {"rule_id": "R2", "agent": "A", "resolved": True}]
    records = [{"risk_band": "mid", "findings": [{"rule_id": "R1", "agent": "A"},
                                                 {"rule_id": "R2", "agent": "A"}],
                "human_state": "APPROVED", "finding_adoption": fa}]
    agg = calibrate.aggregate(records)
    assert agg["by_rule"]["R1"]["adoption_rate"] == 0.5
    assert agg["by_rule"]["R2"]["adoption_rate"] == 1.0
    assert agg["by_agent"]["A"]["adoption_rate"] == round(2 / 3, 2)


def test_calibrate_finding_level_noise():
    n = calibrate.NOISY_MIN_FIRES + 1
    fa = [{"rule_id": "NF", "agent": "A", "resolved": False} for _ in range(n)]  # 全未采纳
    records = [{"risk_band": "low", "findings": [{"rule_id": "NF", "agent": "A"}],
                "human_state": "APPROVED", "finding_adoption": fa}]
    agg = calibrate.aggregate(records)
    assert any(x.get("level") == "finding" and x["key"] == "NF" for x in agg["noisy"])


def test_calibrate_no_finding_adoption_is_safe():
    # 旧记录(无 finding_adoption)不应报错，也不加采纳字段
    records = [{"risk_band": "mid", "findings": [{"rule_id": "R1", "agent": "A"}],
                "human_state": "APPROVED"}]
    agg = calibrate.aggregate(records)
    assert "adoption_rate" not in agg["by_rule"]["R1"]


def test_promote_prefers_finding_adoption_rate(rule_index):
    # PR 级 cr 低(0.1)但 finding 级采纳高(0.8) → 仍应固化(用更细信号)
    agg = {"by_rule": {"CTR-001": {"fires": 6, "changes_requested_rate": 0.1, "adoption_rate": 0.8}}}
    assert any(c["rule_id"] == "CTR-001" for c in govern.promote_to_gate(agg, rule_index))



# ---------------- ③ ghclient：requests + urllib3.Retry 退避配置（串行）----------------
import ghclient


def test_ghclient_session_retry_config():
    s = ghclient.make_session()
    retry = s.get_adapter("https://api.github.com/").max_retries
    assert retry.total == ghclient.GH_RETRY_MAX
    # 限流/5xx 才重试；尊重 Retry-After；不含权限 403（避免空转重试权限错误）
    assert 429 in retry.status_forcelist and 503 in retry.status_forcelist
    assert 403 not in retry.status_forcelist
    assert retry.respect_retry_after_header is True
    assert {"GET", "POST"} <= set(retry.allowed_methods)


# ---------------- ④ 反馈循环联动 CI/verify 判定 ----------------
def test_loop_ci_red_with_no_findings_continues():
    dec, reason, ns = loop.loop_step([], {}, loop.LoopState(), ci_passed=False)
    assert dec == "continue" and "CI/verify 为红" in reason and ns.last_verdict is False


def test_loop_ci_green_no_findings_converges():
    dec, _, _ = loop.loop_step([], {}, loop.LoopState(), ci_passed=True)
    assert dec == "converged"


def test_loop_ci_unknown_no_findings_converges():
    dec, _, _ = loop.loop_step([], {}, loop.LoopState())
    assert dec == "converged"


def test_loop_ci_red_exhausts_rounds_escalates():
    st = loop.LoopState(round=loop.MAX_ROUNDS - 1, history=[])
    dec, reason, _ = loop.loop_step([], {}, st, ci_passed=False)
    assert dec == "escalate" and "轮次耗尽" in reason


def test_loop_marker_roundtrips_last_verdict():
    ns = loop.LoopState(round=2, history=[["X"]], last_verdict=False)
    back = loop.parse_latest_state([loop.render_marker(ns)])
    assert back.round == 2 and back.last_verdict is False


# ---------------- ci_verdict：读 check-runs，排除自身、未完成=未知 ----------------
def test_ci_verdict_excludes_self_and_detects_failure(monkeypatch):
    import orchestrator as C
    monkeypatch.setattr(C, "gh", lambda m, p, t: {"check_runs": [
        {"name": "touchstone", "status": "completed", "conclusion": "neutral"},
        {"name": "build", "status": "completed", "conclusion": "success"},
        {"name": "unit", "status": "completed", "conclusion": "failure"}]})
    assert C.ci_verdict("o", "r", "sha", "t") is False


def test_ci_verdict_all_green(monkeypatch):
    import orchestrator as C
    monkeypatch.setattr(C, "gh", lambda m, p, t: {"check_runs": [
        {"name": "build", "status": "completed", "conclusion": "success"}]})
    assert C.ci_verdict("o", "r", "sha", "t") is True


def test_ci_verdict_in_progress_is_unknown(monkeypatch):
    import orchestrator as C
    monkeypatch.setattr(C, "gh", lambda m, p, t: {"check_runs": [
        {"name": "build", "status": "in_progress", "conclusion": None}]})
    assert C.ci_verdict("o", "r", "sha", "t") is None
    monkeypatch.setattr(C, "gh", lambda m, p, t: {"check_runs": [
        {"name": "touchstone/verify", "status": "completed", "conclusion": "neutral"}]})
    assert C.ci_verdict("o", "r", "sha", "t") is None


# ---------------- 边界：calibrate.aggregate ----------------
def test_aggregate_empty_no_divzero():
    out = calibrate.aggregate([])
    assert out["total"] == 0
    assert out["overall_changes_requested_rate"] is None
    assert out["by_risk"]["high"]["changes_requested_rate"] is None
    assert out["noisy"] == []


def test_aggregate_dedup_and_noisy():
    recs = []
    for i in range(6):
        recs.append({"risk_band": "low",
                     "human_state": "CHANGES_REQUESTED" if i == 0 else "APPROVED",
                     "findings": [{"rule_id": "R1", "agent": "pr-agent:review"},
                                  {"rule_id": "R1", "agent": "pr-agent:review"}]})  # 同 PR 同 rule 去重
    out = calibrate.aggregate(recs)
    assert out["by_rule"]["R1"]["fires"] == 6                 # 每 PR 计一次
    assert any(n["key"] == "R1" for n in out["noisy"])        # 命中多、改动率低(1/6<0.2) → 噪声


def test_aggregate_cr_none_when_no_human_state():
    out = calibrate.aggregate([{"risk_band": "low", "findings": [{"rule_id": "R"}]}])
    assert out["by_rule"]["R"]["changes_requested_rate"] is None
    assert isinstance(calibrate.render_report(out), str)      # 报告渲染不报错
