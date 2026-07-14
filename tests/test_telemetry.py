"""使用遥测测试。重点验护栏：默认关、数据最小化（不外发 diff/代码/凭据）、匿名、失败不冒泡。全离线。"""
from touchstone import telemetry


_REC = {"ts": 1, "version": "1.0.0", "pr": 7, "sha": "abcdef", "engine_status": "ok",
        "review_reliable": True, "ai_raw_count": 3, "risk_band": "mid",
        "loop_decision": "converged", "gate": "pass", "unverified_claims": 0,
        # 下面这些【绝不该外发】——白名单会挡掉
        "diff": "SECRET DIFF", "token": "ghp_xxx", "raw_excerpt": "code here", "title": "PR 正文"}


# ---- 默认关 ----------------------------------------------------------------
def test_disabled_by_default():
    assert telemetry.enabled({}) is False
    assert telemetry.forward([_REC], {}) == "disabled"          # 不配端点 → 不外发


def test_enabled_when_endpoint_set():
    assert telemetry.enabled({"TOUCHSTONE_TELEMETRY_ENDPOINT": "https://c"}) is True


# ---- 数据最小化：只发白名单，绝不外发 diff/代码/凭据/正文 ---------------------
def test_envelope_only_whitelisted_fields():
    env = telemetry.build_envelope([_REC], deployment_id="site-A", version="1.0.0")
    rec = env["records"][0]
    assert "engine_status" in rec and "risk_band" in rec
    for banned in ("diff", "token", "raw_excerpt", "title"):
        assert banned not in rec                                # 敏感/大字段一律不外发


def test_envelope_metadata():
    env = telemetry.build_envelope([_REC], deployment_id="site-A", version="1.0.0")
    assert env["schema"] == telemetry.SCHEMA
    assert env["deployment_id"] == "site-A" and env["version"] == "1.0.0"


def test_deployment_id_defaults_unset():
    env = telemetry.build_envelope([_REC], deployment_id=None, version="1.0.0")
    assert env["deployment_id"] == "unset"


# ---- 匿名：抹掉 pr/sha 标识 -------------------------------------------------
def test_anonymize_strips_identifiers():
    plain = telemetry.build_envelope([_REC], deployment_id="s", version="1.0.0", anonymize=False)
    anon = telemetry.build_envelope([_REC], deployment_id="s", version="1.0.0", anonymize=True)
    assert "pr" in plain["records"][0] and "sha" in plain["records"][0]
    assert "pr" not in anon["records"][0] and "sha" not in anon["records"][0]
    assert anon["anonymized"] is True
    # 匿名后健康数值仍在（只抹标识，不抹信号）
    assert anon["records"][0]["engine_status"] == "ok"


# ---- 上报（注入假 http，零网络）+ token 透传 --------------------------------
def test_forward_posts_envelope():
    sent = {}
    def fake_post(url, payload, token=None, timeout=15):
        sent["url"], sent["payload"], sent["token"] = url, payload, token
        return 200
    env = {"TOUCHSTONE_TELEMETRY_ENDPOINT": "https://collector", "TOUCHSTONE_TELEMETRY_TOKEN": "T",
           "TOUCHSTONE_TELEMETRY_DEPLOYMENT_ID": "site-A"}
    assert telemetry.forward([_REC], env, version="1.0.0", http_post=fake_post) == "ok"
    assert sent["url"] == "https://collector" and sent["token"] == "T"
    assert sent["payload"]["deployment_id"] == "site-A"
    assert "diff" not in sent["payload"]["records"][0]          # 端到端也不外发 diff


def test_forward_anonymize_end_to_end():
    sent = {}
    env = {"TOUCHSTONE_TELEMETRY_ENDPOINT": "https://c", "TOUCHSTONE_TELEMETRY_ANONYMIZE": "true"}
    telemetry.forward([_REC], env, http_post=lambda u, p, token=None, timeout=15: sent.update(p=p))
    assert "pr" not in sent["p"]["records"][0]


# ---- 失败绝不冒泡 -----------------------------------------------------------
def test_forward_failure_never_raises():
    def boom(*a, **k):
        raise RuntimeError("collector down")
    env = {"TOUCHSTONE_TELEMETRY_ENDPOINT": "https://c"}
    assert telemetry.forward([_REC], env, http_post=boom).startswith("failed:")


def test_forward_empty_records_noop():
    env = {"TOUCHSTONE_TELEMETRY_ENDPOINT": "https://c"}
    assert telemetry.forward([], env) == "disabled"


# ---- SSRF 防护（与 alert.py 同构：scheme 白名单 + 不跟随重定向）-------------
def test_default_http_post_rejects_non_http_scheme():
    # 端点来自 env，sink 上挡非 http(s) scheme——file/ftp/gopher 一律拒。
    import pytest
    for bad in ("file:///etc/passwd", "ftp://x/y", "gopher://x", "/etc/passwd", "x://y"):
        with pytest.raises(ValueError):
            telemetry._default_http_post(bad, {"k": "v"})


def test_default_http_post_rejects_redirect():
    # opener 不许跟随重定向——合法 http 端点也可能 302 到内网（如云元数据）。
    import pytest
    with pytest.raises(Exception):
        telemetry._NoRedirectHandler().redirect_request(
            None, None, 302, "Found", {"Location": "http://169.254.169.254/"},
            "http://169.254.169.254/")
