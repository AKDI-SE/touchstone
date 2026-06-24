"""可插拔检查框架 checks.py 的离线测试（无网络：转达/发布用打桩）。"""
import os

import checks


# ---------------- 配置加载 ----------------
def test_load_config_defaults_when_missing(tmp_path):
    cfg = checks.load_config(str(tmp_path))
    assert cfg["gate"]["status_name"] == checks.DEFAULT_GATE
    assert cfg["checks"] == []


def test_load_config_reads_file(tmp_path, monkeypatch):
    p = tmp_path / "checks.yaml"
    p.write_text("gate:\n  status_name: x/gate\nchecks:\n  - name: a\n    required: true\n",
                 encoding="utf-8")
    monkeypatch.setenv("TOUCHSTONE_CHECKS", str(p))
    cfg = checks.load_config(str(tmp_path))
    assert cfg["gate"]["status_name"] == "x/gate" and cfg["checks"][0]["name"] == "a"


# ---------------- 总闸汇总 ----------------
def _r(name, passed, required):
    return checks.CheckResult(name, passed, "", required)


def test_aggregate_gate_all_required_pass():
    assert checks.aggregate_gate([_r("a", True, True), _r("b", True, True)]) == "success"


def test_aggregate_gate_required_fail():
    assert checks.aggregate_gate([_r("a", True, True), _r("b", False, True)]) == "failure"


def test_aggregate_gate_required_neutral_is_fail():
    assert checks.aggregate_gate([_r("a", None, True)]) == "failure"   # 未知不算通过


def test_aggregate_gate_optional_fail_ok():
    assert checks.aggregate_gate([_r("a", True, True), _r("b", False, False)]) == "success"


def test_aggregate_gate_empty_policy_passes():
    assert checks.aggregate_gate([_r("a", False, False)]) == "success"  # 无 required → 不挡


# ---------------- 内置：touchstone-rules ----------------
def test_touchstone_rules_blocks_on_block_candidate():
    pr = {"contract_findings": [{"rule_id": "CTR-001", "severity": "block_candidate"}]}
    passed, summary = checks._check_touchstone_rules(pr, {})
    assert passed is False and "CTR-001" in summary


def test_touchstone_rules_passes_when_clean():
    pr = {"contract_findings": [{"rule_id": "TEST-001", "severity": "warn", "category": "weak_test"}]}
    passed, _ = checks._check_touchstone_rules(pr, {})
    assert passed is True


# ---------------- verify 插件：折入结果 + 可信绿（author 自报规格不算通过）----------
def test_verify_plugin_missing_is_neutral(tmp_path):
    passed, summary = checks._check_verify({}, {"result_file": str(tmp_path / "nope.json")})
    assert passed is None and "未运行" in summary


def test_verify_plugin_rejects_author_proposed_spec(tmp_path):
    import json
    p = tmp_path / "verify-result.json"
    p.write_text(json.dumps({"passed": True, "spec_source": "author_proposed"}), encoding="utf-8")
    passed, _ = checks._check_verify({}, {"result_file": str(p)})
    assert passed is False        # author 自报规格的绿不构成正确性认证


def test_verify_plugin_accepts_human_curated_and_regression(tmp_path):
    import json
    for src in ("human_curated", None):
        p = tmp_path / "verify-result.json"
        p.write_text(json.dumps({"passed": True, "spec_source": src}), encoding="utf-8")
        assert checks._check_verify({}, {"result_file": str(p)})[0] is True
    p.write_text(json.dumps({"passed": False, "spec_source": "human_curated"}), encoding="utf-8")
    assert checks._check_verify({}, {"result_file": str(p)})[0] is False


# ---------------- 转达：读已有 check-run ----------------
def test_relay_reads_existing_check(monkeypatch):
    monkeypatch.setattr(checks.ghclient, "request",
                        lambda *a, **k: {"check_runs": [
                            {"name": "unit", "status": "completed", "conclusion": "success"}]})
    pr = {"owner": "o", "repo": "r", "sha": "s", "token": "t"}
    passed, summary = checks._run_relay(pr, {"source_check": "unit"})
    assert passed is True and "unit=success" in summary


def test_relay_failure_and_missing(monkeypatch):
    monkeypatch.setattr(checks.ghclient, "request",
                        lambda *a, **k: {"check_runs": [
                            {"name": "unit", "status": "completed", "conclusion": "failure"}]})
    pr = {"owner": "o", "repo": "r", "sha": "s", "token": "t"}
    assert checks._run_relay(pr, {"source_check": "unit"})[0] is False
    assert checks._run_relay(pr, {"source_check": "nope"})[0] is None    # 未找到 → 中性


# ---------------- 编排：禁用跳过 / 插件隔离 / 发总闸 ----------------
def test_run_checks_skips_disabled_and_isolates_failure(monkeypatch):
    @checks.builtin("boom")
    def _boom(pr, cfg):
        raise RuntimeError("x")

    cfg = {"checks": [
        {"name": "off", "type": "builtin", "plugin": "touchstone-rules", "enabled": False},
        {"name": "crash", "type": "builtin", "plugin": "boom", "required": True}]}
    pr = {"contract_findings": []}
    results = checks.run_checks(cfg, pr)
    assert len(results) == 1 and results[0].name == "crash" and results[0].passed is None
    assert checks.aggregate_gate(results) == "failure"   # 崩了的 required → 总闸 fail


def test_post_gate_posts_single_status(monkeypatch):
    captured = {}

    def fake(method, url, token, data=None):
        captured["method"] = method
        captured["data"] = data
        return {}
    monkeypatch.setattr(checks.ghclient, "request", fake)
    pr = {"owner": "o", "repo": "r", "sha": "abc", "token": "t"}
    cfg = {"gate": {"status_name": "touchstone/gate"}}
    results = [_r("touchstone-rules", True, True), _r("verify", None, False)]
    gate, _ = checks.post_gate(pr, cfg, results)
    assert gate == "success"
    assert captured["method"] == "POST"
    assert captured["data"]["name"] == "touchstone/gate"
    assert captured["data"]["conclusion"] == "success"
    assert captured["data"]["head_sha"] == "abc"


# ---------------- gate CLI：聚合并发总闸 + 写回 touchstone-findings.json ----------
def _gate_cli(tmp_path, monkeypatch, findings):
    import json
    posted = {}
    monkeypatch.setattr(checks.ghclient, "request",
                        lambda method, url, token, data=None, **k: posted.update(data or {}) or {})
    cy = tmp_path / "checks.yaml"
    cy.write_text("gate:\n  status_name: touchstone/gate\n"
                  "checks:\n  - {name: touchstone-rules, type: builtin, plugin: touchstone-rules, required: true}\n",
                  encoding="utf-8")
    monkeypatch.setenv("TOUCHSTONE_CHECKS", str(cy))
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    monkeypatch.chdir(tmp_path)
    (tmp_path / "touchstone-findings.json").write_text(
        json.dumps({"sha": "s", "changed_files": ["a.py"], "findings": findings, "gate": None}),
        encoding="utf-8")
    checks.main()
    co = json.load(open(tmp_path / "touchstone-findings.json", encoding="utf-8"))
    return co, posted


def test_gate_cli_clean_writes_success(tmp_path, monkeypatch):
    co, posted = _gate_cli(tmp_path, monkeypatch, [])
    assert co["gate"] == "success" and posted["conclusion"] == "success"


def test_gate_cli_contract_block_writes_failure(tmp_path, monkeypatch):
    co, posted = _gate_cli(tmp_path, monkeypatch,
                           [{"agent": "contract-check", "rule_id": "CTR-001", "severity": "block_candidate"}])
    assert co["gate"] == "failure" and posted["conclusion"] == "failure"
