"""doctor（健康度自检）与 review_provider 注入 seam 的测试。全部离线，不打网络。"""
import pytest

from touchstone import doctor, preflight, review_provider


# ---- 自检评审：合成 PR 在进程内跑通、产出合法裁决（零网络） --------------------
def test_smoke_review_produces_verdict_offline():
    ok, detail = doctor.smoke_review({})
    assert ok is True
    # 注入空观察源 → 确定性链跑通、不降级
    assert "engine_status=ok" in detail
    assert "risk_band=" in detail


def test_smoke_review_restores_repo_dir(monkeypatch):
    monkeypatch.setenv("REPO_DIR", "/some/original")
    doctor.smoke_review({})
    import os
    assert os.environ["REPO_DIR"] == "/some/original"   # 隔离用的临时 REPO_DIR 已还原


def test_smoke_review_reports_engine_exception(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("引擎炸了")
    monkeypatch.setattr("touchstone.orchestrator.review_pr", _boom)
    ok, detail = doctor.smoke_review({})
    assert ok is False and "引擎异常" in detail       # never silent：异常如实报，不吞


# ---- review_provider 注入 seam：callable provider 短路 PR-Agent ---------------
def test_fetch_callable_provider_short_circuits():
    sentinel = [{"id": "X"}]
    assert review_provider.fetch({"diff": ""}, provider=lambda _pr: sentinel) == sentinel


def test_fetch_callable_provider_none_yields_empty():
    assert review_provider.fetch({"diff": ""}, provider=lambda _pr: None) == []


# ---- 三态分类 ---------------------------------------------------------------
def test_state_classification():
    assert doctor._state("GITHUB_TOKEN", True) == "pass"
    assert doctor._state("GITHUB_TOKEN", False) == "fail"        # 必需项 → 阻断
    assert doctor._state(doctor.SMOKE_ROW, False) == "fail"      # 自检评审失败 → 阻断
    assert doctor._state("GitHub API", False) == "fail"          # 取 PR 前提 → 阻断
    assert doctor._state("LLM 上下文窗口", False) == "warn"       # 可降级 → 警告，不拦门


# ---- collect：no_net 时不含连通性阶段 ----------------------------------------
def test_collect_no_net_skips_network():
    stages = dict((s, rows) for s, rows in doctor.collect({}, no_net=True))
    assert "配置" in stages and "自检评审" in stages
    assert not any("连通" in s for s in stages)


def test_collect_with_net_includes_network(monkeypatch):
    monkeypatch.setattr(preflight, "check_network", lambda env: [("GitHub API", True, "stub")])
    names = [s for s, _ in doctor.collect({"GITHUB_TOKEN": "t"}, no_net=False)]
    assert any("连通" in s for s in names)


# ---- report / 退出码 --------------------------------------------------------
def test_report_blocks_on_missing_required():
    report = doctor._report(doctor.collect({}, no_net=True))   # 无 GITHUB_TOKEN
    assert report["ok"] is False and report["summary"]["fail"] >= 1


def test_report_ok_when_all_pass():
    env = {"GITHUB_TOKEN": "t", "TOUCHSTONE_LLM_CONTEXT_TOKENS": "32768"}
    report = doctor._report(doctor.collect(env, no_net=True))
    assert report["ok"] is True and report["summary"]["fail"] == 0
    assert report["version"]


def test_main_exit_1_on_block(monkeypatch, capsys):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    with pytest.raises(SystemExit) as e:
        doctor.main(["--no-net"])
    assert e.value.code == 1
    assert "阻断" in capsys.readouterr().out


def test_main_exit_0_when_healthy(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    monkeypatch.setenv("TOUCHSTONE_LLM_CONTEXT_TOKENS", "32768")
    with pytest.raises(SystemExit) as e:
        doctor.main(["--no-net"])
    assert e.value.code == 0


def test_main_json_output(monkeypatch, capsys):
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    with pytest.raises(SystemExit):
        doctor.main(["--no-net", "--json"])
    import json
    parsed = json.loads(capsys.readouterr().out)
    assert "stages" in parsed and "summary" in parsed


# ---- 子命令分派：touchstone doctor / preflight -------------------------------
def test_run_dispatches_doctor(monkeypatch):
    monkeypatch.setattr("sys.argv", ["touchstone", "doctor", "--no-net"])
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    monkeypatch.setenv("TOUCHSTONE_LLM_CONTEXT_TOKENS", "32768")
    from touchstone import run
    with pytest.raises(SystemExit) as e:
        run.main()
    assert e.value.code == 0        # 分派到 doctor 且健康 → 0
