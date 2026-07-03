"""§4.1 栈专项确定性规则（stack_rules）+ §4.1/§4.2/§4.3 三个薄封装
（review_pr / route / record_calibration）的离线测试。全部不触网、不起子进程。"""
import copy

import orchestrator
import review_provider as rp
import calibrate
import stack_rules
from helpers import build_diff


# ---------------- stack_rules：按栈跑可机检规则 ----------------
def test_spr_di_field_injection(rule_index):
    diff = build_diff([("src/main/java/Foo.java",
                        ["@Autowired", "private UserService userService;"], True)])
    ids = {f["rule_id"] for f in stack_rules.check_stack_rules(diff, rule_index)}
    assert "SPR-DI-001" in ids


def test_spr_tx_on_nonpublic(rule_index):
    diff = build_diff([("src/main/java/Bar.java",
                        ["@Transactional", "private void doWork() {"], True)])
    ids = {f["rule_id"] for f in stack_rules.check_stack_rules(diff, rule_index)}
    assert "SPR-TX-001" in ids


def test_java_eq_string(rule_index):
    diff = build_diff([("src/main/java/Eq.java", ['if (name == "admin") {'], True)])
    ids = {f["rule_id"] for f in stack_rules.check_stack_rules(diff, rule_index)}
    assert "JAVA-EQ-001" in ids


def test_java_empty_catch(rule_index):
    diff = build_diff([("src/main/java/Exc.java",
                        ["try { run(); } catch (Exception e) {}"], True)])
    ids = {f["rule_id"] for f in stack_rules.check_stack_rules(diff, rule_index)}
    assert "JAVA-EXC-001" in ids


def test_java_log(rule_index):
    diff = build_diff([("src/main/java/Log.java", ["e.printStackTrace();"], True)])
    ids = {f["rule_id"] for f in stack_rules.check_stack_rules(diff, rule_index)}
    assert "JAVA-LOG-001" in ids


def test_ctr_contract_path(rule_index):
    diff = build_diff([("proto/user.proto", ["message User { int32 id = 1; }"], True)])
    ids = {f["rule_id"] for f in stack_rules.check_stack_rules(diff, rule_index)}
    assert "CTR-001" in ids


def test_non_java_no_stack_findings(rule_index):
    diff = build_diff([("README.md", ["hello world", "x == \"y\""], True)])
    # README 非 java、非契约路径 → 不触发任何栈规则
    assert stack_rules.check_stack_rules(diff, rule_index) == []


def test_findings_are_advisory_warn(rule_index):
    diff = build_diff([("src/main/java/Log.java", ["e.printStackTrace();"], True)])
    fs = stack_rules.check_stack_rules(diff, rule_index)
    assert fs and all(f["severity"] == "warn" and f["agent"] == "touchstone-rules" for f in fs)


def test_machine_checkable_false_not_run(rule_index):
    # 把 SPR-DI-001 标为 machine_checkable=false（应改归 best_practices）→ 确定性路径不再跑它
    ri = copy.deepcopy(rule_index)
    ri["SPR-DI-001"]["machine_checkable"] = False
    diff = build_diff([("src/main/java/Foo.java",
                        ["@Autowired", "private UserService userService;"], True)])
    ids = {f["rule_id"] for f in stack_rules.check_stack_rules(diff, ri)}
    assert "SPR-DI-001" not in ids


def test_rule_absent_not_run():
    # 规则不在 rule_index（未声明）→ 不跑
    diff = build_diff([("src/main/java/Log.java", ["e.printStackTrace();"], True)])
    assert stack_rules.check_stack_rules(diff, {}) == []


# ---------------- review_pr：§4.1 主入口薄封装 ----------------
def _standards():
    import yaml
    import os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return yaml.safe_load(open(os.path.join(root, ".touchstone", "standards.yaml"), encoding="utf-8"))


def test_review_pr_composes_stack_and_returns_risk(monkeypatch):
    # 打桩 PR-Agent 评审为空，避免起子进程；只验"栈规则进了主链、返回 {findings, risk}"
    monkeypatch.setattr(rp, "fetch", lambda ctx, provider=None: [])
    diff = build_diff([("src/main/java/Foo.java",
                        ["@Autowired", "private UserService svc;"], True)])
    pr = {"owner": "o", "repo": "r", "number": 1, "sha": "abc", "token": "t", "diff": diff}
    out = orchestrator.review_pr(pr, {}, _standards())
    assert set(out) == {"findings", "risk", "engine_status"}
    assert out["engine_status"] == "ok"                  # fetch 打桩成功 → 引擎正常
    assert "SPR-DI-001" in {f["rule_id"] for f in out["findings"]}
    assert out["risk"]["risk_band"] in ("low", "mid", "high")
    assert "human_action" in out["risk"] and "verification_decision" in out["risk"]


# ---------------- route：§4.2 风险分流薄封装 ----------------
def test_route_three_tiers():
    # 高 + 影响面严重 → full_suite（最强一档，多跑变异）
    assert rp.route({"risk_band": "high", "blast_radius": ["security_surface"]})["verification_decision"] == "full_suite"
    # 高 但影响面不严重 → targeted_tests
    assert rp.route({"risk_band": "high", "blast_radius": []})["verification_decision"] == "targeted_tests"
    # 低/中 → cheap_only
    assert rp.route({"risk_band": "low"}) == {"human_action": "skip", "verification_decision": "cheap_only"}
    assert rp.route({"risk_band": "mid", "blast_radius": []})["verification_decision"] == "cheap_only"


def test_map_verdict_uses_route():
    # security → 高 + security_surface → full_suite（变异因此可达）
    _, risk = rp.map_verdict([{"category": "security", "confidence": 0.9}])
    assert risk["risk_band"] == "high"
    assert risk["human_action"] == "read+arbitrate"
    assert risk["verification_decision"] == "full_suite"


def test_high_without_severe_blast_is_targeted():
    # correctness → 高，但 map_verdict 不为它加影响面 → targeted_tests（非 full_suite）
    _, risk = rp.map_verdict([{"category": "correctness", "confidence": 0.9}])
    assert risk["risk_band"] == "high" and risk["blast_radius"] == []
    assert risk["verification_decision"] == "targeted_tests"


# ---------------- record_calibration：§4.3 校准记录薄封装 ----------------
def test_record_calibration_agreement():
    co = {"findings": [{"rule_id": "X"}], "risk": {"risk_band": "high"}}
    rec = calibrate.record_calibration("o/r#1", co, {"state": "CHANGES_REQUESTED"})
    assert rec["touchstone_band"] == "high" and rec["human_verdict"] == "CHANGES_REQUESTED"
    assert rec["agreement"] is True          # touchstone 标了 + 人要求改 → 一致
    assert set(("touchstone_findings", "touchstone_band", "human_verdict",
                "human_flagged", "agreement")) <= set(rec)


def test_record_calibration_disagreement():
    co = {"findings": [{"rule_id": "X"}], "risk": {"risk_band": "high"}}
    rec = calibrate.record_calibration("o/r#1", co, "APPROVED")
    assert rec["agreement"] is False         # touchstone 标了 + 人放行 → 不一致（疑似误报）


def test_record_calibration_clean_approved():
    co = {"findings": [], "risk": {"risk_band": "low"}}
    rec = calibrate.record_calibration("o/r#2", co, "APPROVED")
    assert rec["agreement"] is True          # 都没标 → 一致


def test_stack_rules_empty_diff_no_crash(rule_index):
    """空 diff / None diff 不应崩，返回空列表（极端边界）。"""
    assert stack_rules.check_stack_rules("", rule_index) == []
    assert stack_rules.check_stack_rules(None, rule_index) == []
