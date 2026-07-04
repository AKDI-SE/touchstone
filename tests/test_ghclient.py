"""ghclient.py 的离线测试：mock session.request，覆盖 request/paginate/client/retry。"""
import json as _json

from touchstone import ghclient


class _Resp:
    def __init__(self, status=200, body="", headers=None):
        self.status_code = status
        self._body = body
        self.headers = headers or {}
        self.text = body if isinstance(body, str) else _json.dumps(body)
    def json(self):
        return self._body if not isinstance(self._body, str) else _json.loads(self._body)
    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.exceptions.HTTPError(f"{self.status_code}")


class _FakeSession:
    """按预设队列/函数返回响应。"""
    def __init__(self, responses):
        self._responses = list(responses) if not callable(responses) else responses
        self.calls = []
    def request(self, method, url, headers=None, json=None, timeout=None):
        self.calls.append({"method": method, "url": url, "headers": headers, "json": json})
        if callable(self._responses):
            return self._responses(method, url, json)
        return self._responses.pop(0)


def _mock_session(monkeypatch, responses):
    sess = _FakeSession(responses)
    monkeypatch.setattr(ghclient, "_session", lambda: sess)
    monkeypatch.setattr(ghclient.time, "sleep", lambda *_: None)
    return sess


# ---------------- request ----------------
def test_request_returns_json(monkeypatch):
    s = _mock_session(monkeypatch, [_Resp(200, {"ok": True})])
    assert ghclient.request("GET", "https://x/api", "tok") == {"ok": True}
    assert s.calls[0]["headers"]["Authorization"] == "Bearer tok"


def test_request_diff_returns_text(monkeypatch):
    _mock_session(monkeypatch, [_Resp(200, "--- a\n+++ a\n")])
    out = ghclient.request("GET", "u", "t", accept="application/vnd.github.diff")
    assert out.startswith("--- a")


def test_request_empty_body_returns_empty_dict(monkeypatch):
    _mock_session(monkeypatch, [_Resp(200, "")])
    assert ghclient.request("GET", "u", "t") == {}


def test_request_post_sends_json(monkeypatch):
    s = _mock_session(monkeypatch, [_Resp(201, {"id": 1})])
    ghclient.request("POST", "u", "t", data={"a": 1})
    assert s.calls[0]["json"] == {"a": 1}
    assert s.calls[0]["headers"]["Content-Type"] == "application/json"


def test_request_retries_after_header(monkeypatch):
    # 第一次 403 + Retry-After → 重试一次成功
    s = _mock_session(monkeypatch,
                      [_Resp(403, "", {"Retry-After": "0"}), _Resp(200, {"ok": 1})])
    assert ghclient.request("GET", "u", "t") == {"ok": 1}
    assert len(s.calls) == 2


def test_request_raises_on_http_error(monkeypatch):
    import pytest, requests
    _mock_session(monkeypatch, [_Resp(404, "")])
    with pytest.raises(requests.exceptions.HTTPError):
        ghclient.request("GET", "u", "t")


# ---------------- paginate ----------------
def test_paginate_multi_page(monkeypatch):
    pages = [_Resp(200, [{"i": i} for i in range(100)]), _Resp(200, [{"i": 99}])]
    s = _mock_session(monkeypatch, pages)
    out = ghclient.paginate("https://x/p", "t", max_pages=5)
    assert len(out) == 101                       # 100 + 1（第二页 <per_page → 停）


def test_paginate_stops_on_non_list(monkeypatch):
    _mock_session(monkeypatch, [_Resp(200, {"not": "a list"})])
    assert ghclient.paginate("u", "t") == []


def test_paginate_check_runs(monkeypatch):
    pages = [_Resp(200, {"check_runs": [{"id": 1}] * 100}),
             _Resp(200, {"check_runs": [{"id": 2}]})]
    _mock_session(monkeypatch, pages)
    out = ghclient.paginate_check_runs("u", "t", max_pages=5)
    assert out["total_count"] == 101 and len(out["check_runs"]) == 101


# ---------------- client() ----------------
def test_client_get_post(monkeypatch):
    s = _mock_session(monkeypatch, [_Resp(200, {"g": 1}), _Resp(201, {"p": 2})])
    c = ghclient.client("tok")
    assert c.get("/repos/x") == {"g": 1}
    assert c.post("/repos/x", {"k": 1}) == {"p": 2}
    assert s.calls[0]["url"].endswith("/repos/x")
    assert s.calls[1]["json"] == {"k": 1}


def test_client_paginate_and_check_runs(monkeypatch):
    pages = [_Resp(200, [{"a": 1}] * 100), _Resp(200, [{"a": 2}])]
    cr = [_Resp(200, {"check_runs": [{"id": 9}] * 100}), _Resp(200, {"check_runs": [{"id": 1}]})]
    _mock_session(monkeypatch, pages)
    c = ghclient.client("tok")
    assert c.paginate("/p", max_pages=3) == [{"a": 1}] * 100 + [{"a": 2}]
    _mock_session(monkeypatch, cr)
    assert c.paginate_check_runs("/cr", max_pages=3)["total_count"] == 101


def test_client_base_url_env(monkeypatch):
    monkeypatch.setenv("GITHUB_API_URL", "https://gh.enterprise/api")
    monkeypatch.setattr(ghclient, "_session", lambda: _FakeSession([_Resp(200, {})]))
    c = ghclient.client("t")
    assert c.base_url == "https://gh.enterprise/api"
    c.get("/x")                                  # 触发 _req（url 拼接 base）


# ---------------- session 单例 ----------------
def test_session_singleton(monkeypatch):
    from touchstone import ghclient as g
    g._SESSION = None
    s1 = g._session()
    s2 = g._session()
    assert s1 is s2
    g._SESSION = None                            # 清理，避免污染其它测试


def test_make_session_mounts_adapters():
    s = ghclient.make_session()
    assert "https://" in s.adapters
