# ============================================================================
# tests/test_cli_paths.py —— CLI 入口路径补测（第三轮覆盖率缺口收口）
# ----------------------------------------------------------------------------
# verify_change.main 此前是 __main__ 裸块（100+ 行零覆盖）；现为可测函数。
# 口径：0=通过/plan 完成；1=verify 不过；2=配置错/plan 产物缺失。
# ============================================================================
import json

import pytest

from verify import verify_change as V


@pytest.fixture
def cli_env(monkeypatch, tmp_path):
    """最小可运行 CLI 环境：refs + LLM env + 工作目录隔离（产物落 tmp）。"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BASE_REF", "base")
    monkeypatch.setenv("HEAD_REF", "head")
    monkeypatch.setenv("LLM_BASE_URL", "http://llm")
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("LLM_MODEL", "m")
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    # contract 文件与 git diff 都替换掉（不碰真实仓库/子进程）
    (tmp_path / ".touchstone").mkdir()
    (tmp_path / ".touchstone" / "pr.yaml").write_text("intent: test\n", encoding="utf-8")
    monkeypatch.setattr(V.subprocess, "run",
                        lambda *a, **k: V.subprocess.CompletedProcess(a[0], 0, stdout="a.py\n", stderr=""))
    return tmp_path


def test_main_phase_plan_writes_plan_and_exits_0(cli_env, monkeypatch):
    monkeypatch.setattr(V, "plan_verification",
                        lambda *a, **k: {"schema": 1, "mode": "targeted_tests", "route": "cheap_only"})
    assert V.main(["--phase", "plan"]) == 0
    plan = json.loads((cli_env / V.PLAN_PATH).read_text(encoding="utf-8"))
    assert plan["route"] == "cheap_only"


def test_main_phase_execute_reads_plan_writes_result(cli_env, monkeypatch):
    (cli_env / V.PLAN_PATH).write_text(
        json.dumps({"schema": 1, "mode": "targeted_tests", "route": "cheap_only"}), encoding="utf-8")
    rc = V.main(["--phase", "execute"])
    assert rc == 0
    result = json.loads((cli_env / "verify-result.json").read_text(encoding="utf-8"))
    assert result["passed"] is True and result["mode"] == "targeted_tests"


def test_main_phase_execute_missing_plan_exits_2(cli_env, capsys):
    assert V.main(["--phase", "execute"]) == 2
    assert V.PLAN_PATH in capsys.readouterr().err


def test_main_phase_all_failed_verify_exits_1(cli_env, monkeypatch):
    monkeypatch.setattr(V, "plan_verification",
                        lambda *a, **k: {"schema": 1, "mode": "targeted_tests", "route": "spec_blind",
                                         "tests": {"code": "x", "source": "spec_blind", "author_model": "m"}})
    monkeypatch.setattr(V, "execute_verification",
                        lambda *a, **k: V.VerificationResult(passed=False, mode="targeted_tests",
                                                             adequacy=V.AdequacyResult()))
    assert V.main([]) == 1                                   # 默认 phase=all


def test_main_posts_github_when_token_and_event(cli_env, monkeypatch, tmp_path):
    """有 GITHUB_TOKEN + 事件文件 → 回贴评论与 check-run（mock urlopen 记录调用）。"""
    ev = tmp_path / "event.json"
    ev.write_text(json.dumps({"pull_request": {"number": 7, "head": {"sha": "abc"}}}), encoding="utf-8")
    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(ev))
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
    monkeypatch.setattr(V, "plan_verification",
                        lambda *a, **k: {"schema": 1, "mode": "targeted_tests", "route": "cheap_only"})
    posted = []

    class _R:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b"{}"

    monkeypatch.setattr(V.urllib.request, "urlopen",
                        lambda req, timeout=60: (posted.append(req.full_url), _R())[1])
    assert V.main([]) == 0
    assert any("/issues/7/comments" in u for u in posted)
    assert any("/check-runs" in u for u in posted)


# ---------------- autonomy CLI ----------------
def test_autonomy_cli_graduate_writes_classes(monkeypatch, tmp_path):
    """--graduate：读 calibration.json → 重建达标类 → 写 graduated-classes.json。"""
    import sys
    from touchstone import autonomy as A
    monkeypatch.chdir(tmp_path)
    (tmp_path / "calibration.json").write_text(json.dumps({"records": []}), encoding="utf-8")
    monkeypatch.setattr(A, "graduate_from_calibration", lambda records: {"docs_only"})
    monkeypatch.setattr(sys, "argv", ["autonomy", "--graduate"])
    A.main()
    out = json.loads((tmp_path / "graduated-classes.json").read_text(encoding="utf-8"))
    assert out["graduated_classes"] == ["docs_only"]


def test_autonomy_cli_noop_without_findings(monkeypatch, tmp_path, capsys):
    """无 touchstone 产物 → no-op（默认不放行），不崩。"""
    import sys
    from touchstone import autonomy as A
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["autonomy"])
    A.main()
    assert "no-op" in capsys.readouterr().out
