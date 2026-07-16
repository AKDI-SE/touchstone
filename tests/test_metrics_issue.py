"""评审健康度看板（metrics_issue）测试。全部离线：GitHub 调用经注入的 _FakeGH，
不触网。_FakeGH 模拟一个仓的 issue 存储（按 label/marker 去重、PATCH 改 body、POST 评论），
使跨轮 roundtrip / FIFO / comment 触发等行为可被真实地验证。"""
import pytest

from touchstone import metrics as M
from touchstone import metrics_issue as MI


# ---- 夹具 -------------------------------------------------------------------
def _env(**over):
    e = {"TOUCHSTONE_METRICS_ISSUE": "true"}
    e.update(over)
    return e


def _ctx(**over):
    c = {"owner": "o", "repo": "r", "number": 7, "token": "t", "run_url": "https://run/1"}
    c.update(over)
    return c


def _rec(reliable=True, engine="ok", ai=2, decision="continue", claims=0,
         pr=42, sha="deadbeef1234", round_no=1):
    risk = {"risk_band": "high"}
    findings = ([{"agent": "contract"}] + [{"agent": "pr-agent"}] * ai) if ai else [{"agent": "contract"}]
    return M.build(pr, sha, risk, findings, engine_status=engine, review_reliable=reliable,
                   ai_raw_count=ai, loop_decision=decision, gate="2/3", unverified_claims=claims,
                   change_class="code", added_lines=100, round_no=round_no)


class _FakeGH:
    """模拟仓级 issue 存储：GET 按 label 列、POST 建/评论、PATCH 改 body。记录全部调用。"""
    def __init__(self):
        self.calls = []                 # [(method, path, data)]
        self.issues = {}                # number(int) -> {title, labels, body, comments}
        self._next = 100

    def __call__(self, method, path, token, data=None):
        self.calls.append((method, path, data))
        if method == "GET":
            label = path.split("labels=", 1)[-1] if "labels=" in path else ""
            return [{"number": n, "body": i["body"]}
                    for n, i in self.issues.items() if label in i.get("labels", [])]
        if method == "POST":
            if path.endswith("/comments"):                      # /repos/o/r/issues/{n}/comments
                num = int(path.rstrip("/").split("/")[-2])
                self.issues.setdefault(num, {}).setdefault("comments", []).append((data or {}).get("body"))
                return {"id": 1}
            n = self._next
            self._next += 1
            self.issues[n] = {"title": (data or {}).get("title"),
                              "labels": (data or {}).get("labels", []),
                              "body": (data or {}).get("body"), "comments": []}
            return {"number": n}
        if method == "PATCH":                                   # /repos/o/r/issues/{n}
            num = int(path.rstrip("/").split("/")[-1])
            if num in self.issues and (data or {}).get("body") is not None:
                self.issues[num]["body"] = data["body"]
            return {}
        raise ValueError(f"_FakeGH 未实现 {method}")


def _one_body(gh):
    return gh.issues[list(gh.issues)[0]]["body"]


# ---- 编排：开关 / 创建 / 更新 ------------------------------------------------
def test_run_disabled_when_env_off():
    gh = _FakeGH()
    assert MI.run(_rec(), {}, _ctx(), gh_call=gh) == "disabled"
    assert gh.calls == []                                       # 不外呼


def test_creates_issue_when_none():
    gh = _FakeGH()
    assert MI.run(_rec(), _env(), _ctx(), gh_call=gh) == "ok"
    assert any(c[0] == "GET" for c in gh.calls)                # 先按 label 找
    posts = [c for c in gh.calls if c[0] == "POST" and c[1].endswith("/issues")]
    assert posts and posts[0][2]["labels"] == [MI.ISSUE_LABEL]
    assert MI._OPEN in posts[0][2]["body"]                     # 新建 body 带看板 + marker
    assert len(gh.issues) == 1


def test_updates_body_when_issue_exists_uses_patch():
    gh = _FakeGH()
    MI.run(_rec(pr=1), _env(), _ctx(), gh_call=gh)             # 首轮：创建
    num = list(gh.issues)[0]
    body1 = gh.issues[num]["body"]
    n_before = len(gh.calls)
    MI.run(_rec(pr=2), _env(), _ctx(), gh_call=gh)             # 二轮：应 PATCH、不新建
    patches = [c for c in gh.calls[n_before:] if c[0] == "PATCH"]
    assert patches and patches[0][1].endswith(f"/issues/{num}")
    assert not any(c[0] == "POST" and c[1].endswith("/issues") for c in gh.calls[n_before:])
    assert len(gh.issues) == 1                                 # 同一个 issue
    assert gh.issues[num]["body"] != body1                     # body 被重写


# ---- 跨轮 marker roundtrip / FIFO ------------------------------------------
def test_marker_roundtrip_accumulates():
    gh = _FakeGH()
    MI.run(_rec(reliable=True, pr=1), _env(), _ctx(), gh_call=gh)
    MI.run(_rec(reliable=False, engine="ok", ai=0, pr=2), _env(), _ctx(), gh_call=gh)
    history = MI._parse_marker(_one_body(gh))
    assert len(history) == 2                                   # 两轮都进了 marker
    assert {h["pr"] for h in history} == {1, 2}


def test_history_bounded_fifo():
    gh = _FakeGH()
    env = _env(TOUCHSTONE_METRICS_ISSUE_WINDOW="3")
    for i in range(5):                                         # 5 轮，window=3
        MI.run(_rec(pr=i, round_no=i), env, _ctx(), gh_call=gh)
    history = MI._parse_marker(_one_body(gh))
    assert len(history) == 3                                   # 只留最近 3 轮
    assert [h["pr"] for h in history] == [2, 3, 4]             # FIFO：丢最早的


def test_trend_uses_metrics_summarize():
    gh = _FakeGH()
    for r in [_rec(reliable=True, pr=1),
              _rec(reliable=False, engine="ok", ai=0, pr=2),
              _rec(reliable=True, pr=3)]:
        MI.run(r, _env(), _ctx(), gh_call=gh)
    history = MI._parse_marker(_one_body(gh))
    expected = M.summarize(history)                            # 看板 trend 即此聚合
    body = _one_body(gh)
    assert f"{expected['review_reliable_rate']:.0%}" in body   # 2/3 可信 → 67%
    assert str(expected["silent_failure_rounds"]) in body


# ---- 显著事件评论 -----------------------------------------------------------
def test_comment_on_degraded_but_not_on_healthy():
    gh = _FakeGH()
    MI.run(_rec(engine="llm_failed", reliable=False), _env(), _ctx(), gh_call=gh)   # 降级 → 评论
    assert any(c[0] == "POST" and c[1].endswith("/comments") for c in gh.calls)
    n_before = len(gh.calls)
    MI.run(_rec(engine="ok", reliable=True, decision="continue"),                    # 健康 → 不评
           _env(), _ctx(), gh_call=gh)
    assert not any(c[0] == "POST" and c[1].endswith("/comments")
                   for c in gh.calls[n_before:])


def test_comment_on_converged():
    gh = _FakeGH()
    MI.run(_rec(decision="converged"), _env(), _ctx(), gh_call=gh)
    assert any(c[0] == "POST" and c[1].endswith("/comments") for c in gh.calls)


def test_notable_events_pure():
    ev = {"converged", "degraded"}
    assert MI._notable_events({"loop_decision": "converged"}, ev)
    assert MI._notable_events({"engine_status": "no_engine"}, ev)
    assert MI._notable_events({"loop_decision": "continue", "engine_status": "ok"}, ev) == []


# ---- 失败绝不冒泡 / 数据最小化 ----------------------------------------------
def test_failure_never_bubbles():
    def boom(*a, **k):
        raise RuntimeError("issue API down")
    res = MI.run(_rec(), _env(), _ctx(), gh_call=boom)
    assert res.startswith("failed:")
    assert "issue API down" in res                             # 带消息可定位


def test_no_diff_no_secrets_in_body():
    gh = _FakeGH()
    MI.run(_rec(), _env(), _ctx(token="ghs_SUPERSECRET123"), gh_call=gh)
    body = _one_body(gh)
    assert "diff" not in body.lower()                         # 不含 diff/代码
    assert "ghs_SUPERSECRET123" not in body                   # token 不泄漏进 body
    assert "SUPERSECRET" not in body


# ---- marker 读写单元 --------------------------------------------------------
def test_marker_stamp_parse_roundtrip():
    h = [{"pr": 1, "review_reliable": True}, {"pr": 2, "review_reliable": False}]
    assert MI._parse_marker(MI._stamp_marker(h)) == h
    assert MI._parse_marker("no marker here") == []
    assert MI._parse_marker("") == []
    assert MI._parse_marker(MI._OPEN + " 损坏的 json " + MI._CLOSE) == []   # 损坏 → []


# ---- _default_gh 路由（生产默认实现，走公开 client()）-----------------------
def test_default_gh_routes_through_public_client(monkeypatch):
    calls = []

    class FakeClient:
        def get(self, path):
            calls.append(("GET", path, None)); return {"got": path}

        def post(self, path, data):
            calls.append(("POST", path, data)); return {"posted": path}

        def patch(self, path, data):
            calls.append(("PATCH", path, data)); return {"patched": path}

    import touchstone.ghclient as ghclient_mod
    monkeypatch.setattr(ghclient_mod, "client", lambda token: FakeClient())

    assert MI._default_gh("GET", "/repos/o/r/issues/9", "tok") == {"got": "/repos/o/r/issues/9"}
    assert MI._default_gh("POST", "/repos/o/r/issues", "tok", {"title": "x"}) == {"posted": "/repos/o/r/issues"}
    assert MI._default_gh("PATCH", "/repos/o/r/issues/9", "tok", {"body": "b"}) == {"patched": "/repos/o/r/issues/9"}
    assert calls == [("GET", "/repos/o/r/issues/9", None),
                     ("POST", "/repos/o/r/issues", {"title": "x"}),
                     ("PATCH", "/repos/o/r/issues/9", {"body": "b"})]
    # data=None 的 POST/PATCH 不崩（收到 {}）；非白名单 method 立即抛——不静默当 POST
    MI._default_gh("PATCH", "/x", "tok")
    for bad in ("PUT", "DELETE"):
        with pytest.raises(ValueError, match="GET/POST/PATCH"):
            MI._default_gh(bad, "/x", "tok")
