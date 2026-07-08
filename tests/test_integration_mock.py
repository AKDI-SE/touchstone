"""Mock 集成测试：打桩 GitHub HTTP / 网络 / 子进程 / LLM，真覆盖 main() 与 I/O 编排分支。
这些是离线无法真连的集成代码（GitHub API、子进程、LLM、CLI），用替身驱动其逻辑分支。"""
import json
import os
import sys
import types

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)            # 使 `from touchstone import ...` 可解析（仅仓库根；
# 不再把 touchstone/、verify/ 子目录也插进 path——那会让"函数内平铺导入"这类地雷
# 在全量测试里被静默掩盖、单跑文件才炸，见 CHANGELOG 工程化加固第二轮）

from touchstone import ghclient as G          # noqa: E402
from touchstone import preflight as P         # noqa: E402
from touchstone import pr_agent_runner as R   # noqa: E402


# ============================ ghclient ============================
class _Resp:
    def __init__(self, status=200, text='{"ok":1}', headers=None, jsonv=None):
        self.status_code = status
        self.text = text
        self.headers = headers or {}
        self._j = {"ok": 1} if jsonv is None else jsonv

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests_error(self.status_code)

    def json(self):
        return self._j


def requests_error(code):
    import requests
    return requests.HTTPError(str(code))


class _Sess:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, **kw):
        self.calls.append((method, url, kw))
        return self.responses.pop(0)


def test_ghclient_make_session():
    assert G.make_session() is not None       # 构造 requests.Session（无网络）


def test_ghclient_request_json_and_diff():
    s = _Sess([_Resp(jsonv={"a": 1})])
    assert G.request("GET", "https://x", "tok", session=s) == {"a": 1}
    s = _Sess([_Resp(text="DIFFTEXT")])
    assert G.request("GET", "https://x", "tok",
                     accept="application/vnd.github.diff", session=s) == "DIFFTEXT"


def test_ghclient_403_retry_after(monkeypatch):
    monkeypatch.setattr(G.time, "sleep", lambda *_: None)
    s = _Sess([_Resp(status=403, headers={"Retry-After": "0"}), _Resp(jsonv={"ok": 2})])
    assert G.request("GET", "https://x", "tok", session=s) == {"ok": 2}
    assert len(s.calls) == 2                   # 二级限流 → 额外重试一次


# ============================ preflight ============================
def test_preflight_check_config_branches():
    env = {"GITHUB_TOKEN": "t", "LLM_BASE_URL": "u", "LLM_API_KEY": "k",
           "LLM_MODEL": "m", "LLM_TEST_MODEL": "m", "HTTPS_PROXY": "http://p"}
    names = {n for n, _, _ in P.check_config(env)}
    assert "model-diversity" in names         # LLM_MODEL == LLM_TEST_MODEL → 告警
    assert "proxy" in names
    rows2 = P.check_config({})
    assert any(n == "GITHUB_TOKEN" and not ok for n, ok, _ in rows2)   # 缺必需


def test_preflight_check_network(monkeypatch):
    monkeypatch.setattr(P, "_ping", lambda *a, **k: (True, "HTTP 200"))
    rows = P.check_network({"GITHUB_TOKEN": "t", "LLM_BASE_URL": "https://llm",
                            "LLM_MODEL": "m", "LLM_API_KEY": "k"})
    assert len(rows) == 3 and all(ok for _, ok, _ in rows)


def test_preflight_main_no_net(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["preflight", "--no-net"])
    for k in ("GITHUB_TOKEN", "LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL"):
        monkeypatch.setenv(k, "x")
    monkeypatch.setenv("TOUCHSTONE_STANDARDS", os.path.join(ROOT, ".touchstone", "standards.yaml"))
    P.main()                                   # 必需项就绪 + --no-net → 不 hard_fail
    assert "预检" in capsys.readouterr().out


def test_preflight_main_hardfail(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["preflight", "--no-net"])
    for k in ("GITHUB_TOKEN", "LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(SystemExit):           # 缺必需 → 退出码 1
        P.main()


# ============================ pr_agent_runner ============================
def test_pr_agent_read(tmp_path):
    assert R._read(None) is None
    p = tmp_path / "e.txt"
    p.write_text("hi", encoding="utf-8")
    assert R._read(str(p)) == "hi"


def test_pr_agent_run_import_missing(monkeypatch):
    monkeypatch.setitem(sys.modules, "pr_agent", None)   # 不可导入 → 上报 no_engine（不抛、不非零退出）
    out = R.run("https://pr", "improve")
    assert out["_degraded"] == "no_engine"
    assert "pr-agent" in out["reason"]


def test_pr_agent_run_llm_failed(monkeypatch):
    # pr-agent 装了，但工具调用抛错（LLM 端点/鉴权/超时类）→ 上报 llm_failed（防静默故障）
    _install_fake_pr_agent(monkeypatch)
    _stub_llm(monkeypatch)
    import pr_agent.tools.pr_code_suggestions as cs_mod

    class CrashingCS:
        def __init__(self, url):
            self.data = {}

        async def run(self):
            raise RuntimeError("LLM 401 unauthorized")
    cs_mod.PRCodeSuggestions = CrashingCS
    out = R.run("https://pr", "improve")
    assert out["_degraded"] == "llm_failed"
    assert "401" in out["reason"]


def test_pr_agent_run_llm_preflight_fails(monkeypatch):
    # LLM 预检 ping 失败（端点不可达/鉴权坏）→ 立即 llm_failed 带真实错误，不进 pr-agent
    _install_fake_pr_agent(monkeypatch)
    monkeypatch.setenv("LLM_BASE_URL", "http://x")
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("LLM_MODEL", "m")

    def _boom(*a):
        raise RuntimeError("401 unauthorized")
    monkeypatch.setattr(R, "_ping_llm", _boom)
    out = R.run("https://pr", "improve")
    assert out["_degraded"] == "llm_failed"
    assert "探测失败" in out["reason"] and "401" in out["reason"]


def test_pr_agent_run_llm_config_incomplete(monkeypatch):
    # LLM 配置缺项（如没设 LLM_MODEL）→ llm_failed，明确告知缺哪个
    _install_fake_pr_agent(monkeypatch)
    monkeypatch.setenv("LLM_BASE_URL", "http://x")
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.delenv("LLM_MODEL", raising=False)
    out = R.run("https://pr", "improve")
    assert out["_degraded"] == "llm_failed"
    assert "配置不全" in out["reason"]


def test_pr_agent_run_provider_failed(monkeypatch):
    # pr-agent 装了，但构造时取 PR/git provider 失败（pre-LLM）→ 上报 provider_failed，与 llm_failed 区分
    _install_fake_pr_agent(monkeypatch)
    _stub_llm(monkeypatch)
    import pr_agent.tools.pr_code_suggestions as cs_mod

    class NoProviderCS:
        def __init__(self, url):
            raise ValueError("Failed to get git provider for " + url)
    cs_mod.PRCodeSuggestions = NoProviderCS
    out = R.run("https://github.com/o/r/pull/1", "improve")
    assert out["_degraded"] == "provider_failed"
    assert "git provider" in out["reason"]


def test_pr_agent_run_maps_github_token(monkeypatch):
    # GITHUB_TOKEN → pr-agent settings.github.user_token；git_provider 显式 github
    settings = _install_fake_pr_agent(monkeypatch)
    _stub_llm(monkeypatch)
    monkeypatch.setenv("GITHUB_TOKEN", "ghs_test_token")
    import pr_agent.tools.pr_code_suggestions as cs_mod

    class CS:
        def __init__(self, url):
            self.data = {"code_suggestions": []}

        async def run(self):
            return None
    cs_mod.PRCodeSuggestions = CS
    R.run("https://pr", "improve")
    assert settings.github.user_token == "ghs_test_token"
    assert settings.config.git_provider == "github"


def _install_fake_pr_agent(monkeypatch):
    algo_utils = types.ModuleType("pr_agent.algo.utils")
    algo_utils.load_yaml = lambda s, **k: {"review": {"key_issues_to_review": [{"x": 1}]}}
    cfg = types.ModuleType("pr_agent.config_loader")
    settings = types.SimpleNamespace(
        config=types.SimpleNamespace(publish_output=True, publish_output_progress=True),
        github=types.SimpleNamespace(user_token=""),
        pr_code_suggestions=types.SimpleNamespace(extra_instructions=""),
        pr_reviewer=types.SimpleNamespace(extra_instructions=""))
    cfg.get_settings = lambda: settings
    cs_mod = types.ModuleType("pr_agent.tools.pr_code_suggestions")

    class PRCodeSuggestions:
        def __init__(self, url):
            self.data = {"code_suggestions": [{"s": 1}]}

        async def run(self):
            return None
    cs_mod.PRCodeSuggestions = PRCodeSuggestions
    rv_mod = types.ModuleType("pr_agent.tools.pr_reviewer")

    class PRReviewer:
        def __init__(self, url):
            self.prediction = "review:\n  key_issues_to_review: []"

        async def run(self):
            return None
    rv_mod.PRReviewer = PRReviewer
    for name, mod in (("pr_agent", types.ModuleType("pr_agent")),
                      ("pr_agent.algo", types.ModuleType("pr_agent.algo")),
                      ("pr_agent.algo.utils", algo_utils),
                      ("pr_agent.config_loader", cfg),
                      ("pr_agent.tools", types.ModuleType("pr_agent.tools")),
                      ("pr_agent.tools.pr_code_suggestions", cs_mod),
                      ("pr_agent.tools.pr_reviewer", rv_mod)):
        monkeypatch.setitem(sys.modules, name, mod)
    return settings


def _stub_llm(monkeypatch):
    """让 runner 的 LLM 预检 ping 在离线测试里直接通过（设 LLM_* env + 打桩 _ping_llm 不真发请求）。"""
    monkeypatch.setenv("LLM_BASE_URL", "http://x")
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("LLM_MODEL", "m")
    monkeypatch.setattr(R, "_ping_llm", lambda *a: None)


def test_pr_agent_run_happy(monkeypatch):
    settings = _install_fake_pr_agent(monkeypatch)
    _stub_llm(monkeypatch)
    out = R.run("https://pr", "improve+review", extra_instructions="be strict")
    assert out["code_suggestions"] == [{"s": 1}]
    assert out["review"]["key_issues_to_review"] == [{"x": 1}]
    assert out.get("_degraded") is None                     # 正常：无降级标记
    assert settings.config.publish_output is False          # 关键：不往 PR 发评论
    assert settings.pr_reviewer.extra_instructions == "be strict"


def test_pr_agent_main(monkeypatch, capsys):
    _install_fake_pr_agent(monkeypatch)
    _stub_llm(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["pr_agent_runner", "--pr-url", "https://pr", "--mode", "improve"])
    R.main()
    assert "code_suggestions" in capsys.readouterr().out


def test_interaction_log_written_and_redacts_key(monkeypatch, tmp_path):
    # 完整 LLM 交互日志写入 artifact 文件，含 pr-agent 原始输出 + 配置轨迹；api_key 脱敏
    _install_fake_pr_agent(monkeypatch)
    _stub_llm(monkeypatch)
    logpath = tmp_path / "ix.log"
    monkeypatch.setenv("TOUCHSTONE_INTERACTION_LOG", str(logpath))
    out = R.run("https://pr", "improve+review", extra_instructions="x")
    R._write_interaction_log(out)
    txt = logpath.read_text(encoding="utf-8")
    assert "完整交互日志" in txt
    assert "code_suggestions" in txt          # 完整 pr-agent 输出
    assert "LLM 配置" in txt and "ping: 成功" in txt   # 交互轨迹
    assert "k" != txt  # 不写真实 api_key（_stub_llm 用了占位，但配置行只写'已设'）
    # 不设 env → 不写
    monkeypatch.delenv("TOUCHSTONE_INTERACTION_LOG", raising=False)
    R._write_interaction_log(out)   # 不抛、不写文件


# ============================ run.py（独立运行入口）============================
def _prep_repo_dir(tmp_path):
    import shutil
    (tmp_path / ".touchstone").mkdir()
    shutil.copy(os.path.join(ROOT, ".touchstone", "standards.yaml"),
                tmp_path / ".touchstone" / "standards.yaml")
    return tmp_path


_FAKE_REVIEW = {"findings": [{"rule_id": "R1", "confidence": 0.9, "file": "x.py",
                              "line": 1, "rationale": "r"}],
                "risk": {"risk_band": "low", "human_action": "skip",
                         "verification_decision": "cheap_only", "blast_radius": []}}


def test_run_main_dryrun(monkeypatch, tmp_path, capsys):
    from touchstone import run as RUN
    td = _prep_repo_dir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["run", "--repo", "o/r", "--pr", "5", "--repo-dir", str(td)])
    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    monkeypatch.setattr(RUN.C, "gh", lambda *a, **k: {"head": {"sha": "abcdef123"}, "title": "T"})
    monkeypatch.setattr(RUN.C, "get_pr_diff", lambda *a, **k: "--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n+x\n")
    monkeypatch.setattr(RUN.C, "review_pr", lambda *a, **k: dict(_FAKE_REVIEW))
    RUN.main()
    assert "DRY-RUN" in capsys.readouterr().out


def test_run_main_post(monkeypatch, tmp_path):
    from touchstone import run as RUN
    td = _prep_repo_dir(tmp_path)
    monkeypatch.setattr(sys, "argv",
                        ["run", "--repo", "o/r", "--pr", "5", "--repo-dir", str(td), "--post"])
    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    monkeypatch.setattr(RUN.C, "gh", lambda *a, **k: {"head": {"sha": "abcdef123"}, "title": "T"})
    monkeypatch.setattr(RUN.C, "get_pr_diff", lambda *a, **k: "--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n+x\n")
    monkeypatch.setattr(RUN.C, "review_pr", lambda *a, **k: dict(_FAKE_REVIEW))
    posted = {}
    monkeypatch.setattr(RUN.C, "post_results", lambda *a, **k: posted.setdefault("ok", True))
    RUN.main()
    assert posted.get("ok")


def test_run_checkout_success_and_fail(monkeypatch, tmp_path):
    from touchstone import run as RUN
    import subprocess as sp
    monkeypatch.setattr(sp, "run", lambda *a, **k: types.SimpleNamespace(returncode=0))
    d, created = RUN._checkout("o/r", "sha", "tok")
    assert created
    import shutil
    shutil.rmtree(d, ignore_errors=True)

    def boom(*a, **k):
        raise sp.CalledProcessError(1, a[0], stderr=b"nope")
    monkeypatch.setattr(sp, "run", boom)
    with pytest.raises(SystemExit):
        RUN._checkout("o/r", "sha", "tok")


def test_run_main_missing_token(monkeypatch, tmp_path):
    from touchstone import run as RUN
    monkeypatch.setattr(sys, "argv", ["run", "--repo", "o/r", "--pr", "5", "--repo-dir", str(tmp_path)])
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    with pytest.raises(SystemExit):
        RUN.main()


# ============================ orchestrator ============================
from touchstone import orchestrator as ORC          # noqa: E402
from touchstone import review_provider as RP        # noqa: E402
from touchstone import govern as GOV                # noqa: E402

_RISK = {"risk_band": "low", "human_action": "skip",
         "verification_decision": "cheap_only", "blast_radius": []}


def test_render_summary_bands_and_findings():
    for band in ("high", "mid", "low"):
        r = dict(_RISK, risk_band=band, blast_radius=["schema"])
        assert "Touchstone" in ORC.render_summary(r, [])
    f = [{"rule_id": "R1", "confidence": 0.9, "agent": "pr-agent:review",
          "file": "x.py", "line": 3, "rationale": "r", "suggested_fix": "fix"}]
    assert "R1" in ORC.render_summary(_RISK, f)


def test_anchor_inline_in_diff_nearest_and_skip():
    diff = "--- a/x.py\n+++ b/x.py\n@@ -0,0 +1,3 @@\n+a\n+b\n+c\n"
    findings = [{"file": "x.py", "line": 2, "rule_id": "R", "rationale": "r"},   # 命中新增行 → 锚 2
                {"file": "x.py", "line": 99, "rule_id": "R2", "rationale": "r"}, # 越界 → 就近锚
                {"file": "y.py", "line": 1, "rule_id": "R3", "rationale": "r"}]  # 无新增行 → 跳过
    out = ORC.anchor_inline(findings, diff)
    lines = sorted(o["line"] for o in out)
    assert lines == [2, 3] and len(out) == 2


def test_ci_verdict_branches(monkeypatch):
    def mk(runs):
        return lambda *a, **k: {"check_runs": runs}
    monkeypatch.setattr(ORC, "gh", mk([{"name": "ci", "status": "completed", "conclusion": "success"}]))
    assert ORC.ci_verdict("o", "r", "s", "t") is True
    monkeypatch.setattr(ORC, "gh", mk([{"name": "ci", "status": "completed", "conclusion": "failure"}]))
    assert ORC.ci_verdict("o", "r", "s", "t") is False
    monkeypatch.setattr(ORC, "gh", mk([{"name": "ci", "status": "in_progress"}]))
    assert ORC.ci_verdict("o", "r", "s", "t") is None
    monkeypatch.setattr(ORC, "gh", mk([]))            # 仅 touchstone/无数据 → None
    assert ORC.ci_verdict("o", "r", "s", "t") is None


def test_post_results_calls_three_endpoints(monkeypatch):
    calls = []
    monkeypatch.setattr(ORC, "gh", lambda m, p, t, data=None, accept="": calls.append((m, p)) or {})
    diff = "--- a/x.py\n+++ b/x.py\n@@ -0,0 +1,1 @@\n+a\n"
    f = [{"rule_id": "R1", "confidence": 0.9, "agent": "pr-agent:review",
          "file": "x.py", "line": 1, "rationale": "r", "suggested_fix": "fix"}]
    ORC.post_results("o", "r", 5, "sha", "tok", _RISK, f,
                     loop_info=("converged", "ok", "<!-- m -->"), change_class="low|code|none|none", diff=diff)
    paths = " ".join(p for _, p in calls)
    assert "/issues/5/comments" in paths and "/pulls/5/reviews" in paths and "/check-runs" in paths


def test_orchestrator_main_end_to_end(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"pull_request": {"number": 7, "head": {"sha": "abc123"}}}),
                     encoding="utf-8")
    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    monkeypatch.setenv("TOUCHSTONE_SKIP_GATE", "1")        # 跳过总闸（checks 另测）
    monkeypatch.setenv("REPO_DIR", ROOT)
    monkeypatch.setattr(ORC, "STANDARDS_PATH", os.path.join(ROOT, ".touchstone", "standards.yaml"))
    monkeypatch.setattr(ORC, "CONTRACT_PATH", os.path.join(tmp_path, "nope.yaml"))

    def fake_gh(method, path, token, data=None, accept="application/vnd.github+json"):
        if accept.endswith("diff"):
            return "--- a/x.py\n+++ b/x.py\n@@ -0,0 +1,1 @@\n+x\n"
        if path.endswith("/comments") and method == "GET":
            return []
        if "check-runs" in path and method == "GET":
            return {"check_runs": []}
        return {}
    monkeypatch.setattr(ORC, "gh", fake_gh)

    def _no_endpoint(pr, provider=None):                  # 触发 review_pr 的降级分支
        raise RuntimeError("PR-Agent 端点未配置")
    monkeypatch.setattr(RP, "fetch", _no_endpoint)
    ORC.main()

    out = json.loads((tmp_path / "touchstone-findings.json").read_text(encoding="utf-8"))
    assert out["pr"] == 7 and "risk" in out and out["gate"] is None


def _setup_main(monkeypatch, tmp_path, fake_gh_fn):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "event.json").write_text(
        json.dumps({"pull_request": {"number": 8, "head": {"sha": "sha8"}}}), encoding="utf-8")
    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(tmp_path / "event.json"))
    monkeypatch.setenv("REPO_DIR", ROOT)
    monkeypatch.setenv("GITHUB_RUN_ID", "999")
    monkeypatch.setattr(ORC, "STANDARDS_PATH", os.path.join(ROOT, ".touchstone", "standards.yaml"))
    monkeypatch.setattr(ORC, "CONTRACT_PATH", str(tmp_path / "nope.yaml"))
    monkeypatch.setattr(ORC, "gh", fake_gh_fn)
    monkeypatch.setattr(RP, "fetch", lambda pr, provider=None: [])


def test_main_rdjson_and_output(monkeypatch, tmp_path):
    def fgh(method, path, token, data=None, accept="application/vnd.github+json"):
        if accept.endswith("diff"):
            return "--- a/x.py\n+++ b/x.py\n@@ -0,0 +1,1 @@\n+x\n"
        return [] if (path.endswith("/comments") and method == "GET") else {}
    _setup_main(monkeypatch, tmp_path, fgh)
    monkeypatch.setenv("TOUCHSTONE_SKIP_GATE", "1")
    monkeypatch.setenv("TOUCHSTONE_RDJSON_PATH", str(tmp_path / "out.rdjson"))
    gho = tmp_path / "gho.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(gho))
    ORC.main()
    assert (tmp_path / "out.rdjson").exists()
    assert "verification_decision=" in gho.read_text(encoding="utf-8")


def test_main_gate_path(monkeypatch, tmp_path):
    def fgh(method, path, token, data=None, accept="application/vnd.github+json"):
        if accept.endswith("diff"):
            return "--- a/x.py\n+++ b/x.py\n@@ -0,0 +1,1 @@\n+x\n"
        return [] if (path.endswith("/comments") and method == "GET") else {}
    _setup_main(monkeypatch, tmp_path, fgh)
    monkeypatch.delenv("TOUCHSTONE_SKIP_GATE", raising=False)   # 走 gate 路径
    monkeypatch.setattr(ORC.checks, "post_gate",
                        lambda pr, cfg, res: ("success", res))
    monkeypatch.setattr(ORC.checks, "run_checks", lambda cfg, pr: [])
    ORC.main()
    out = json.loads((tmp_path / "touchstone-findings.json").read_text(encoding="utf-8"))
    assert out["gate"] == "success"


def test_main_post_results_fail_swallowed(monkeypatch, tmp_path):
    # 摘要评论/内联/check-run POST 失败 → 走 warn/info 分支，main 不崩
    import requests
    def fgh(method, path, token, data=None, accept="application/vnd.github+json"):
        if accept.endswith("diff"):
            return "--- a/x.py\n+++ b/x.py\n@@ -0,0 +1,1 @@\n+x\n"
        if path.endswith("/comments") and method == "GET":
            return []
        if "check-runs" in path and method == "GET":
            return {"check_runs": []}
        raise requests.exceptions.HTTPError(f"403 forbidden: {path}")
    _setup_main(monkeypatch, tmp_path, fgh)
    monkeypatch.setenv("TOUCHSTONE_SKIP_GATE", "1")
    ORC.main()                       # 各 POST 失败被吞，落盘仍完成
    assert (tmp_path / "touchstone-findings.json").exists()


# ============================ govern.main ============================
def test_govern_main(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    cal = {"aggregate": {"by_rule": {}}, "records": []}
    (tmp_path / "calibration.json").write_text(json.dumps(cal), encoding="utf-8")
    monkeypatch.setenv("CALIBRATION_JSON", str(tmp_path / "calibration.json"))
    monkeypatch.setenv("TOUCHSTONE_STANDARDS", os.path.join(ROOT, ".touchstone", "standards.yaml"))
    monkeypatch.setattr(GOV, "detect_revert_shas", lambda *a, **k: set())   # 不打 git
    GOV.main()
    assert (tmp_path / "promotion-proposal.md").exists()
    assert (tmp_path / "autonomy-state.json").exists()


# ============================ calibrate ============================
from touchstone import calibrate as CAL            # noqa: E402
from touchstone import autonomy as AUT             # noqa: E402

_FINDING_MARKER = '<!-- touchstone-finding: {"rule_id": "R", "agent": "pr-agent:review"} -->'
_RESULT_MARKER = ("<!-- touchstone-result: " +
                  json.dumps({"risk_band": "low", "verification_decision": "cheap_only",
                              "change_class": None, "loop_decision": None, "findings": []}) + " -->")


def test_calibrate_pure_parsers():
    data = {"data": {"repository": {"pullRequest": {"reviewThreads": {"nodes": [
        {"isResolved": True, "comments": {"nodes": [{"author": {"login": "github-actions[bot]"}, "body": _FINDING_MARKER}]}}]}}}}}
    threads = CAL.parse_review_threads(data)
    assert threads[0]["isResolved"] and threads[0]["comments"][0]["author"] == "github-actions[bot]"
    tf = CAL.thread_findings(threads)
    assert tf[0]["rule_id"] == "R" and tf[0]["resolved"] is True
    assert CAL._parse_result([_RESULT_MARKER], "bot")["risk_band"] == "low"
    assert CAL._human_verdict([{"user": {"login": "alice"}, "state": "APPROVED"},
                               {"user": {"login": "bot[bot]"}, "state": "CHANGES_REQUESTED"}], "bot") == "APPROVED"
    rec = CAL.record_calibration(5, {"findings": [{"rule_id": "R"}], "risk": {"risk_band": "high"}},
                                 {"state": "CHANGES_REQUESTED"})
    assert rec["agreement"] is True and rec["touchstone_band"] == "high"


def test_calibrate_gh_gql_and_fetch(monkeypatch):
    monkeypatch.setattr(CAL.ghclient, "request", lambda m, u, t, **k: {"m": m, "u": u})
    assert CAL.gh("/x", "tok")["m"] == "GET"
    assert CAL.gql("Q", {"v": 1}, "tok")["m"] == "POST"
    monkeypatch.setattr(CAL, "gql", lambda q, v, t: {"data": {"repository": {"pullRequest":
                        {"reviewThreads": {"nodes": []}}}}})
    assert CAL.fetch_review_threads("o", "r", 1, "t") == []


def test_calibrate_main(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")

    def fake_gh(path, token):
        if "/pulls?state=closed" in path:
            return [{"number": 1, "merged_at": "t", "merge_commit_sha": "sha"}]
        if "/issues/1/comments" in path:
            return [{"body": _RESULT_MARKER, "user": {"login": "github-actions[bot]"}}]
        if "/pulls/1/reviews" in path:
            return [{"user": {"login": "alice"}, "state": "APPROVED"}]
        return []
    monkeypatch.setattr(CAL, "gh", fake_gh)
    monkeypatch.setattr(CAL, "gh_paginate", fake_gh)
    monkeypatch.setattr(CAL, "fetch_review_threads", lambda *a: [])
    CAL.main()
    rep = json.loads((tmp_path / "calibration.json").read_text(encoding="utf-8"))
    assert rep["aggregate"]["total"] == 1 and (tmp_path / "calibration-report.md").exists()


# ============================ autonomy main / execute ============================
def test_autonomy_main_graduate(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    recs = [{"merged": True, "change_class": "x", "loop_decision": "converged",
             "findings": [], "risk_band": "low", "merge_commit_sha": "s"} for _ in range(20)]
    (tmp_path / "calibration.json").write_text(json.dumps({"records": recs}), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["autonomy", "--graduate"])
    AUT.main()
    grad = json.loads((tmp_path / "graduated-classes.json").read_text(encoding="utf-8"))
    assert "x" in grad["graduated_classes"]


def test_autonomy_main_decision_inputs(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    inp = {"risk": {"risk_band": "low"}, "findings": [], "loop_decision": "converged",
           "gate": "success", "autonomy_state": {"tripped": False},
           "graduated_classes": ["low|code|none|none"], "cls": "low|code|none|none"}
    (tmp_path / "in.json").write_text(json.dumps(inp), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["autonomy", "--inputs", str(tmp_path / "in.json")])
    AUT.main()
    assert "merge" in capsys.readouterr().out


def test_autonomy_main_noop(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["autonomy"])     # 无 touchstone-findings.json → no-op
    AUT.main()
    assert "no-op" in capsys.readouterr().out


class _UR:
    def __init__(self, payload):
        self._p = json.dumps(payload).encode()

    def read(self):
        return self._p

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_autonomy_execute_auto_merge(monkeypatch):
    seen = []

    def fake_req(method, url, token, data=None, **kw):
        seen.append(url)
        return {"merged": True}
    monkeypatch.setattr(AUT.ghclient, "request", fake_req)
    res = AUT.execute_auto_merge("o/r", 5, "sha", "tok")
    assert res == {"merged": True} and any("/merge" in u for u in seen)


def test_execute_auto_merge_posts_marker_comment(monkeypatch):
    """P0-5: execute_auto_merge 必须发 touchstone:auto_handled marker 评论
    （calibrate 据此重建自动放行归因；marker 丢了 → 熔断数据全错）。"""
    posts = []

    def fake_req(method, url, token, data=None, **kw):
        import json as _j
        posts.append((url, _j.dumps(data or {}, ensure_ascii=False)))
        return {"merged": True}
    monkeypatch.setattr(AUT.ghclient, "request", fake_req)
    AUT.execute_auto_merge("o/r", 5, "sha", "tok")
    comment_posts = [(u, b) for u, b in posts if "/issues/5/comments" in u]
    assert comment_posts, "未发 auto_handled marker 评论"
    assert "touchstone:auto_handled" in comment_posts[0][1]


# ============================ verify_change（mock LLM/runner，不碰子进程）========
from verify import verify_change as V          # noqa: E402


def test_verify_extract_code_and_interface(tmp_path):
    assert V._extract_code("```python\nx=1\n```") == "x=1"
    assert V._extract_code("bare code") == "bare code"
    (tmp_path / "m.py").write_text("def foo(a, b):\n    return a + b\n", encoding="utf-8")
    assert "foo" in str(V._extract_interface(str(tmp_path), ["m.py"]))


def test_verify_generate_spec_blind_tests(monkeypatch):
    monkeypatch.setattr(V, "_llm", lambda messages, **cfg: "```python\ndef test_x():\n    assert True is True\n```")
    cfg = {"base_url": "u", "api_key": "k", "model": "m"}
    ts = V.generate_spec_blind_tests(["adds two numbers"], "def add(a, b)", cfg)
    assert ts.source == "spec_blind" and "test_x" in ts.code and ts.author_model == "m"
    ts2 = V.generate_spec_blind_tests(["x"], "class Foo", cfg, framework="junit5")   # junit 分支
    assert ts2.code


def test_verify_select_runner_and_acceptance(monkeypatch, tmp_path):
    assert isinstance(V.select_runner(str(tmp_path), ["x.java"]), V.MavenRunner)
    assert isinstance(V.select_runner(str(tmp_path), ["x.py"]), V.PythonRunner)
    af = tmp_path / "acc.yaml"
    af.write_text("acceptance_criteria:\n  - does X\n", encoding="utf-8")
    monkeypatch.setenv("TOUCHSTONE_ACCEPTANCE", str(af))
    crit, src = V.resolve_acceptance_spec({}, str(tmp_path))
    assert src == "human_curated" and crit == ["does X"]
    monkeypatch.delenv("TOUCHSTONE_ACCEPTANCE", raising=False)
    crit2, src2 = V.resolve_acceptance_spec({"acceptance_criteria": ["a"]}, str(tmp_path / "none"))
    assert src2 == "author_proposed" and crit2 == ["a"]


def test_verify_regression_path_with_fake_runner(monkeypatch, tmp_path):
    class FakeRunner:
        lang = "python"

        def run_suite(self, d):
            return True, "ok"

        def changed_coverage(self, d, cf, ch):
            return 0.9

        def mutation(self, d, cf):
            return 0.8
    monkeypatch.setattr(V, "_worktree", lambda repo, ref: str(tmp_path))
    monkeypatch.setattr(V, "_rm_worktree", lambda *a, **k: None)
    monkeypatch.setattr(V, "_changed_lines", lambda repo, b, h: {"x.py": {1}})
    res = V._verify_regression(str(tmp_path), FakeRunner(), ["x.py"], "base", "head", "targeted_tests")
    assert res.passed and res.mode == "regression_only"


# ---------------- pr_agent_runner 健壮性：glm-5.2 修复不能静默回退 ----------------
def test_custom_max_tokens_uses_context_window_not_output(monkeypatch):
    # 【输入侧预算，非输出】custom_model_max_tokens 必须取 context_tokens（上下文窗口），
    # 不是 output_tokens。设 CONTEXT_TOKENS=200000、OUTPUT_TOKENS=4096 → 应取 200000。
    # 锁死此语义：若误用 output_tokens，会拿 4096 当窗口→diff 裁空→LLM 0 建议（PR #44 真根因）。
    settings = _install_fake_pr_agent(monkeypatch)
    _stub_llm(monkeypatch)
    monkeypatch.setenv("TOUCHSTONE_LLM_CONTEXT_TOKENS", "200000")
    monkeypatch.setenv("TOUCHSTONE_LLM_OUTPUT_TOKENS", "4096")
    import pr_agent.tools.pr_code_suggestions as cs_mod

    class CS:
        def __init__(self, url):
            self.data = {"code_suggestions": []}
        async def run(self):
            return None
    cs_mod.PRCodeSuggestions = CS
    R.run("https://pr", "improve")
    assert settings.config.custom_model_max_tokens == 200000   # 取上下文窗口，不是输出 4096


def test_custom_max_tokens_context_unset_falls_back_to_128k(monkeypatch):
    # CONTEXT_TOKENS 未声明（0）→ 回退 128000（现代模型典型窗口），绝不回退 4096。
    # 4096 当窗口 = 改动 diff 被裁空。此回退值是"宁可让 LLM 看全 diff"的安全默认。
    settings = _install_fake_pr_agent(monkeypatch)
    _stub_llm(monkeypatch)
    monkeypatch.delenv("TOUCHSTONE_LLM_CONTEXT_TOKENS", raising=False)
    import pr_agent.tools.pr_code_suggestions as cs_mod

    class CS:
        def __init__(self, url):
            self.data = {"code_suggestions": []}
        async def run(self):
            return None
    cs_mod.PRCodeSuggestions = CS
    R.run("https://pr", "improve")
    assert settings.config.custom_model_max_tokens == 128000   # 回退 128k，不是 4096


def test_custom_max_tokens_and_fallback_actually_set(monkeypatch):
    # 锁死：run 后 custom_model_max_tokens 已设（取 context_tokens）、fallback_models 已清空。
    # 这两项正是 glm-5.2 出真实意见的根因修复——若静默失败会回到"0 建议"。
    settings = _install_fake_pr_agent(monkeypatch)
    _stub_llm(monkeypatch)
    monkeypatch.setenv("TOUCHSTONE_LLM_CONTEXT_TOKENS", "3333")
    import pr_agent.tools.pr_code_suggestions as cs_mod

    class CS:
        def __init__(self, url):
            self.data = {"code_suggestions": []}
        async def run(self):
            return None
    cs_mod.PRCodeSuggestions = CS
    R.run("https://pr", "improve+review")
    assert settings.config.custom_model_max_tokens == 3333
    assert settings.config.fallback_models == []             # 清空，不再试不存在的 gpt-5.4-mini
    assert settings.config.model == "openai/m"               # provider 前缀就位
    assert settings.config.git_provider == "github"
