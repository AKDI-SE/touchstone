#!/usr/bin/env python3
# ============================================================================
# touchstone/ghclient.py  ——  GitHub HTTP 客户端（统一入口，消除 4 处重复 wrapper）
# ----------------------------------------------------------------------------
# requests + urllib3.Retry：连接池、指数退避、Retry-After、5xx/429 重试均由库处理。
# 【保持串行】——GitHub 二级限流惩罚并发，不做并发(这条与库无关，是 GitHub 策略)。
# 二级限流 403 带 Retry-After 时额外尊重一次；权限类 403(无 Retry-After) 由
# raise_for_status 立即抛出，不空转。
#
# 本模块是所有 GitHub REST/GraphQL 调用的唯一入口——此前 orchestrator/calibrate/
# checks/learning_loop 各自写了一个 `gh()` wrapper（拼 base_url + 传 token），
# 现在统一为 client() 工厂 + get/post/paginate/paginate_check_runs 方法。
# ============================================================================

import os
import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# 坏值（空串/非数字/负数）→ 默认 5，绝不在 import 时崩整链（对齐 loop.py MAX_ROUNDS 的兜底风格）。
try:
    GH_RETRY_MAX = max(0, int((os.environ.get("GH_RETRY_MAX") or "").strip() or "5"))
except (TypeError, ValueError):
    GH_RETRY_MAX = 5


def _base_url():
    return os.environ.get("GITHUB_API_URL", "https://api.github.com")


def make_session():
    # 只重试幂等的 GET：POST 评论/check-run/issue 并非幂等——5xx 后重放会造成重复副作用
    # （重复评审评论、重复 check-run、重复看板 issue）。POST 的 5xx 直接抛给调用方处理，
    # 由调用方决定重试语义（如"评论发失败可整轮重跑"）。审计 #1。
    retry = Retry(
        total=GH_RETRY_MAX, connect=GH_RETRY_MAX, read=GH_RETRY_MAX,
        backoff_factor=1.0,
        status_forcelist=(429, 500, 502, 503, 504),
        respect_retry_after_header=True,
        allowed_methods=frozenset(["GET"]),
    )
    s = requests.Session()
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    return s


_SESSION = None


def _session():
    global _SESSION
    if _SESSION is None:
        _SESSION = make_session()
    return _SESSION


def _retry_after_seconds(value, cap=120.0):
    """Retry-After 头 → 秒数（上限 cap）。审计 #3。

    RFC 7231 允许两种格式：延迟秒数（"120"）或 HTTP-date（"Fri, 28 Aug 2026 08:00:00 GMT"）。
    旧实现 ``float(value)`` 对 HTTP-date 直接 ValueError 打穿调用链；且无上限——服务端发
    大值（如 3600）会让进程静默挂到 job 超时。现：HTTP-date 换算剩余秒、非数字回落 60s、
    一律夹到 [0, cap]。纯函数。"""
    import email.utils
    try:
        secs = float(str(value).strip())
    except (TypeError, ValueError):
        try:  # HTTP-date 形式：剩余时间 = 目标时刻 - 现在
            target = email.utils.parsedate_to_datetime(str(value).strip())
            import datetime
            now = datetime.datetime.now(datetime.timezone.utc)
            if target.tzinfo is None:
                target = target.replace(tzinfo=datetime.timezone.utc)
            secs = (target - now).total_seconds()
        except (TypeError, ValueError, OverflowError):
            secs = 60.0          # 解析不出（含缺头）→ 保守 60s，绝不崩
    return max(0.0, min(secs, cap))


# ---- 统一客户端（替代各模块的 gh()/_gh_get()/_gh() wrapper）-------------------

def client(token):
    """返回一个绑定 token 的 GitHub 客户端，提供 get/post/paginate/paginate_check_runs。
    替代此前 4 个模块各自写的 `gh()` wrapper（拼 base_url + 传 token 的重复代码）。"""
    base = _base_url()

    def _req(method, path, data=None, accept="application/vnd.github+json", timeout=60):
        url = base + path if path.startswith("/") else path
        sess = _session()
        headers = {"Authorization": "Bearer " + token, "Accept": accept,
                   "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "touchstone"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        r = None
        for attempt in range(2):
            r = sess.request(method, url, headers=headers,
                             json=data if data is not None else None, timeout=timeout)
            # pr-agent 评审（第三轮）：手动 403+Retry-After 分支与 urllib3 Retry 层同律（审计 #1）——
            # 仅幂等 GET 重试。POST 的 403 可能发生在服务端【已处理】之后（限流在落库后触发），
            # 重放 = 重复评论/重复 check-run/重复看板 issue；直接抛给调用方决定重试语义。
            if (r.status_code == 403 and r.headers.get("Retry-After") and attempt == 0
                    and method.upper() == "GET"):
                time.sleep(_retry_after_seconds(r.headers["Retry-After"]))
                continue
            break
        r.raise_for_status()
        if accept.endswith("diff"):
            return r.text
        return r.json() if r.text else {}

    def get(path, accept="application/vnd.github+json"):
        return _req("GET", path, accept=accept)

    def post(path, data):
        return _req("POST", path, data=data)

    def patch(path, data):
        # 对称于 get/post：编辑既有资源（如 PATCH /repos/.../issues/{n} 改 body）。
        # make_session 的 allowed_methods 只含 GET/POST——PATCH 非幂等、不自动重试（issue
        # 编辑语义本就不该重放），但 sess.request 仍正常发送 PATCH（allowed_methods 仅约束
        # 【重试】，不约束可发 method）；403+Retry-After 的二级限流兜底在 _req 内仍生效。
        return _req("PATCH", path, data=data)

    def paginate(path, per_page=100, max_pages=20):
        # 分隔符按【原 path】一次性判定且不再变更（审计 #2）：旧实现翻到第 2 页时无条件
        # sep="&"，对不带 "?" 的 path 产出 `path&page=2` 这类无查询串起点的畸形 URL → 404
        # → raise_for_status 抛 HTTPError 打穿调用链（>100 条记录的列表必然触发）。
        q = "&" if "?" in path else "?"
        out = []
        for page in range(1, max_pages + 1):
            data = _req("GET", f"{path}{q}page={page}&per_page={per_page}")
            if not isinstance(data, list):
                break
            out.extend(data)
            if len(data) < per_page:
                break
        return out

    def paginate_check_runs(path, per_page=100, max_pages=20):
        q = "&" if "?" in path else "?"   # 同 paginate：sep 恒定（审计 #2）
        all_runs = []
        for page in range(1, max_pages + 1):
            data = _req("GET", f"{path}{q}page={page}&per_page={per_page}")
            runs = (data or {}).get("check_runs") or []
            all_runs.extend(runs)
            if len(runs) < per_page:
                break
        return {"check_runs": all_runs, "total_count": len(all_runs)}

    return type("GHClient", (), {
        "get": staticmethod(get), "post": staticmethod(post), "patch": staticmethod(patch),
        "paginate": staticmethod(paginate), "paginate_check_runs": staticmethod(paginate_check_runs),
        "_req": staticmethod(_req),
        "base_url": base, "token": token,
    })()


# ---- 旧接口（向后兼容，逐步迁移到 client()）---------------------------------

def request(method, url, token, data=None, accept="application/vnd.github+json",
            session=None, timeout=60):
    """串行请求 GitHub REST/GraphQL。accept 以 'diff' 结尾返回文本，否则返回 JSON。"""
    sess = session or _session()
    headers = {"Authorization": "Bearer " + token, "Accept": accept,
               "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "touchstone"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    r = None
    for attempt in range(2):
        r = sess.request(method, url, headers=headers,
                         json=data if data is not None else None, timeout=timeout)
        # pr-agent 评审（第三轮）：与 client._req 的手动 403 分支同律（审计 #1）——仅幂等 GET
        # 重试；POST 403 重放会重复评论/check-run/issue，直接抛给调用方。
        if (r.status_code == 403 and r.headers.get("Retry-After") and attempt == 0
                and method.upper() == "GET"):
            time.sleep(_retry_after_seconds(r.headers["Retry-After"]))
            continue
        break
    r.raise_for_status()
    if accept.endswith("diff"):
        return r.text
    return r.json() if r.text else {}


def paginate(url, token, *, per_page=100, max_pages=20, accept="application/vnd.github+json"):
    """GitHub 列表翻页（旧接口，逐步迁移到 client(token).paginate）。

    分隔符按原 url 一次判定、全程不变（审计 #2）：旧实现第 2 页起无条件用 "&"，
    对无 "?" 的 url 产出 `url&page=2` 畸形 URL → 404 → HTTPError 未捕获打穿调用链。"""
    q = "&" if "?" in url else "?"
    out = []
    for page in range(1, max_pages + 1):
        data = request("GET", f"{url}{q}page={page}&per_page={per_page}", token, accept=accept)
        if not isinstance(data, list):
            break
        out.extend(data)
        if len(data) < per_page:
            break
    return out


def paginate_check_runs(url, token, *, per_page=100, max_pages=20):
    """check-runs 专用翻页（旧接口，逐步迁移到 client(token).paginate_check_runs）。"""
    q = "&" if "?" in url else "?"   # 同 paginate：sep 恒定（审计 #2）
    all_runs = []
    for page in range(1, max_pages + 1):
        data = request("GET", f"{url}{q}page={page}&per_page={per_page}", token)
        runs = (data or {}).get("check_runs") or []
        all_runs.extend(runs)
        if len(runs) < per_page:
            break
    return {"check_runs": all_runs, "total_count": len(all_runs)}
