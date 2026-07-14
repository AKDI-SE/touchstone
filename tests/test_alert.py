"""告警钩子测试。全部离线：投递通过注入的假 gh_call / http_post，不触网。"""
from touchstone import alert


_HEALTHY = {"pr": 1, "sha": "abc", "engine_status": "ok", "review_reliable": True,
            "ai_raw_count": 3, "unverified_claims": 0}


# ---- 判定（纯函数）---------------------------------------------------------
def test_evaluate_silent_failure():
    rec = {**_HEALTHY, "review_reliable": False, "ai_raw_count": 0}
    kinds = [a["kind"] for a in alert.evaluate(rec)]
    assert "silent_failure" in kinds


def test_evaluate_engine_degraded():
    rec = {**_HEALTHY, "engine_status": "no_engine"}
    kinds = [a["kind"] for a in alert.evaluate(rec)]
    assert "engine_degraded" in kinds


def test_evaluate_unverified_claims():
    rec = {**_HEALTHY, "unverified_claims": 2}
    kinds = [a["kind"] for a in alert.evaluate(rec)]
    assert "unverified_claims" in kinds


def test_evaluate_healthy_no_alerts():
    assert alert.evaluate(_HEALTHY) == []


def test_evaluate_aggregate_reliable_low():
    agg = {"rounds": 10, "review_reliable_rate": 0.5, "silent_failure_rounds": 0,
           "engine_status_dist": {"ok": 5, "llm_failed": 5}}
    kinds = [a["kind"] for a in alert.evaluate(_HEALTHY, agg, reliable_min=0.8)]
    assert "reliable_rate_low" in kinds


def test_evaluate_aggregate_silent_trend():
    agg = {"rounds": 5, "review_reliable_rate": 1.0, "silent_failure_rounds": 2}
    kinds = [a["kind"] for a in alert.evaluate(_HEALTHY, agg, silent_max=0)]
    assert "silent_failure_trend" in kinds


def test_evaluate_scope_split():
    # 单轮告警 scope=pr；聚合告警 scope=repo
    rec = {**_HEALTHY, "engine_status": "no_engine"}
    agg = {"rounds": 5, "review_reliable_rate": 0.2, "silent_failure_rounds": 0}
    scopes = {a["kind"]: a["scope"] for a in alert.evaluate(rec, agg)}
    assert scopes["engine_degraded"] == "pr" and scopes["reliable_rate_low"] == "repo"


# ---- 通道选择 ---------------------------------------------------------------
def test_channels_disabled_by_default():
    assert alert.channels_from_env({}) == []                    # 总开关不开 → 不外呼


def test_channels_enabled_defaults_to_github():
    ch = alert.channels_from_env({"TOUCHSTONE_ALERT_ENABLED": "true"})
    assert "github-issue" in ch and "github-pr-comment" in ch


def test_channels_webhook_autoadded():
    ch = alert.channels_from_env({"TOUCHSTONE_ALERT_ENABLED": "true",
                                  "TOUCHSTONE_ALERT_CHANNELS": "github-pr-comment",
                                  "TOUCHSTONE_ALERT_WEBHOOK": "https://hook"})
    assert "webhook" in ch


# ---- 投递（注入假通道）-----------------------------------------------------
def _fake_gh(calls):
    def gh(method, path, token, data=None):
        calls.append((method, path, data))
        if method == "GET":                       # 找已开 Issue：返回空 → 走新建分支
            return []
        return {"number": 99}
    return gh


def test_deliver_pr_comment():
    calls = []
    al = {"severity": "high", "kind": "silent_failure", "title": "t", "body": "b", "scope": "pr"}
    res = alert.deliver([al], channels=["github-pr-comment"],
                        ctx={"owner": "o", "repo": "r", "number": 7, "token": "t"},
                        gh_call=_fake_gh(calls))
    assert ("github-pr-comment", "silent_failure", "ok") in res
    assert any("/issues/7/comments" in c[1] for c in calls)


def test_deliver_issue_create_when_none_open():
    calls = []
    al = {"severity": "high", "kind": "reliable_rate_low", "title": "t", "body": "b", "scope": "repo"}
    alert.deliver([al], channels=["github-issue"],
                  ctx={"owner": "o", "repo": "r", "token": "t"}, gh_call=_fake_gh(calls))
    # 先 GET 找已开 Issue，未命中 → POST 新建 /issues
    assert any(c[0] == "GET" for c in calls)
    assert any(c[0] == "POST" and c[1].endswith("/issues") for c in calls)


def test_deliver_issue_update_when_marker_matches():
    def gh(method, path, token, data=None):
        if method == "GET":
            return [{"number": 42, "body": "<!-- touchstone-alert:reliable_rate_low -->"}]
        gh.posted = path
        return {}
    al = {"severity": "high", "kind": "reliable_rate_low", "title": "t", "body": "b", "scope": "repo"}
    alert.deliver([al], channels=["github-issue"],
                  ctx={"owner": "o", "repo": "r", "token": "t"}, gh_call=gh)
    assert gh.posted.endswith("/issues/42/comments")            # 命中已开 Issue → 追评论而非新建


def test_deliver_webhook():
    posts = []
    al = {"severity": "high", "kind": "silent_failure", "title": "t", "body": "b", "scope": "pr"}
    alert.deliver([al], channels=["webhook"], ctx={"owner": "o", "repo": "r", "number": 1},
                  webhook_url="https://hook", http_post=lambda u, p: posts.append((u, p)))
    assert posts and posts[0][0] == "https://hook" and posts[0][1]["kind"] == "silent_failure"


def test_default_http_post_rejects_non_http_scheme():
    # SSRF 防护：webhook URL 来自 env，sink 上挡非 http(s) scheme——file/ftp/gopher 一律拒。
    import pytest
    for bad in ("file:///etc/passwd", "ftp://x/y", "gopher://x", "/etc/passwd", "x://y"):
        with pytest.raises(ValueError):
            alert._default_http_post(bad, {"k": "v"})


def test_deliver_failure_never_raises():
    def boom(*a, **k):
        raise RuntimeError("channel down")
    al = {"severity": "high", "kind": "silent_failure", "title": "t", "body": "b", "scope": "pr"}
    res = alert.deliver([al], channels=["github-pr-comment"],
                        ctx={"owner": "o", "repo": "r", "number": 1, "token": "t"}, gh_call=boom)
    # 记录失败但不抛；且带具体消息（可观测性子系统的本分是让故障可见、可定位）。
    assert res[0][2].startswith("failed:")
    assert "channel down" in res[0][2]


# ---- 编排 ------------------------------------------------------------------
def test_run_disabled_is_noop():
    rec = {**_HEALTHY, "review_reliable": False, "ai_raw_count": 0}
    assert alert.run(rec, None, {}, {"owner": "o", "repo": "r", "number": 1, "token": "t"}) == []


def test_run_enabled_delivers(monkeypatch):
    sent = []
    monkeypatch.setattr(alert, "_default_gh",
                        lambda m, p, t, data=None: sent.append(p) or {})
    rec = {**_HEALTHY, "review_reliable": False, "ai_raw_count": 0}
    env = {"TOUCHSTONE_ALERT_ENABLED": "true", "TOUCHSTONE_ALERT_CHANNELS": "github-pr-comment"}
    res = alert.run(rec, None, env, {"owner": "o", "repo": "r", "number": 5, "token": "t"})
    assert res and any("/issues/5/comments" in p for p in sent)
