#!/usr/bin/env python3
# ============================================================================
# touchstone/ghclient.py  ——  GitHub HTTP 客户端（成熟库，替代手写 urllib + 退避）
# ----------------------------------------------------------------------------
# requests + urllib3.Retry：连接池、指数退避、Retry-After、5xx/429 重试均由库处理。
# 【保持串行】——GitHub 二级限流惩罚并发，不做并发(这条与库无关，是 GitHub 策略)。
# 二级限流 403 带 Retry-After 时额外尊重一次；权限类 403(无 Retry-After) 由
# raise_for_status 立即抛出，不空转。
# ============================================================================

import os
import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

GH_RETRY_MAX = int(os.environ.get("GH_RETRY_MAX", "5"))


def make_session():
    retry = Retry(
        total=GH_RETRY_MAX, connect=GH_RETRY_MAX, read=GH_RETRY_MAX,
        backoff_factor=1.0,
        status_forcelist=(429, 500, 502, 503, 504),   # 限流/服务端错误才重试
        respect_retry_after_header=True,               # 尊重 Retry-After
        allowed_methods=frozenset(["GET", "POST"]),
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


def request(method, url, token, data=None, accept="application/vnd.github+json",
            session=None, timeout=60):
    """串行请求 GitHub REST/GraphQL。accept 以 'diff' 结尾返回文本，否则返回 JSON。"""
    sess = session or _session()
    headers = {"Authorization": "Bearer " + token, "Accept": accept,
               "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "touchstone"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    r = None
    for attempt in range(2):     # 二级限流 403 带 Retry-After → 额外尊重一次
        r = sess.request(method, url, headers=headers,
                         json=data if data is not None else None, timeout=timeout)
        if r.status_code == 403 and r.headers.get("Retry-After") and attempt == 0:
            time.sleep(float(r.headers["Retry-After"]))
            continue
        break
    r.raise_for_status()
    if accept.endswith("diff"):
        return r.text
    return r.json() if r.text else {}


def paginate(url, token, *, per_page=100, max_pages=20, accept="application/vnd.github+json"):
    """GitHub 列表翻页：自动加 &page=N&per_page=M 直到 <per_page 或 max_pages 页。
    防单页 per_page=100 截断 >100 条数据（评论/评审/check-runs 等）。"""
    sep = "&" if "?" in url else "?"
    out = []
    for page in range(1, max_pages + 1):
        data = request("GET", f"{url}{sep}page={page}&per_page={per_page}", token, accept=accept)
        if not isinstance(data, list):
            break
        out.extend(data)
        if len(data) < per_page:
            break
        sep = "&"
    return out


def paginate_check_runs(url, token, *, per_page=100, max_pages=20):
    """check-runs 专用翻页：API 返回 {check_runs:[...]} 而非纯 list。"""
    sep = "&" if "?" in url else "?"
    all_runs = []
    for page in range(1, max_pages + 1):
        data = request("GET", f"{url}{sep}page={page}&per_page={per_page}", token)
        runs = (data or {}).get("check_runs") or []
        all_runs.extend(runs)
        if len(runs) < per_page:
            break
        sep = "&"
    return {"check_runs": all_runs, "total_count": len(all_runs)}
