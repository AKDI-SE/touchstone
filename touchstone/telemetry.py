#!/usr/bin/env python3
# ============================================================================
# touchstone/telemetry.py  ——  使用遥测汇聚（可选，默认关）
# ----------------------------------------------------------------------------
# 预留一个【可插拔 sink】：把每轮 metrics 记录上报到一个【配置指定】的中心汇聚点
# （"touchstone 统一的地方"）——供跨部署观察 touchstone 表现（如 1→N 复制时的健康对比）。
#
# 这是 alert 的【镜像】：alert 把告警发到客户自己的渠道、绝不回传；telemetry 则【主动上报】。
# 因此它的护栏更严——对国企/政企/内网客户，安全门禁产品若默认偷偷 phone-home 是采购硬伤：
#
#   1) 默认关、显式 opt-in：不配 TOUCHSTONE_TELEMETRY_ENDPOINT → 一个字节都不外发（同现状）。
#   2) 端点是配置、无硬编码 URL：指向 AKDI 中心 collector【或客户自己的内网聚合点】皆可；
#      断网客户不配即禁用。
#   3) 数据最小化：只发 metrics 扁平记录（健康数值/engine_status/裁决），
#      【绝不发 diff、代码、PR 正文、凭据】。ANONYMIZE 可再抹掉 repo/pr 标识，
#      让客户"只共享健康趋势、不暴露在审什么"。
#   4) 失败绝不冒泡：上报挂了不拖垮评审 job（可观测性不当门禁）。
#
# 配置（env）：
#   TOUCHSTONE_TELEMETRY_ENDPOINT     汇聚点 URL（不配=禁用）
#   TOUCHSTONE_TELEMETRY_TOKEN        可选 bearer（collector 鉴权用）
#   TOUCHSTONE_TELEMETRY_DEPLOYMENT_ID 部署标识（站点/租户，供中心按部署分桶）
#   TOUCHSTONE_TELEMETRY_ANONYMIZE    "true" → 抹掉 pr/sha 等标识，只留健康数值
# ============================================================================

import json
import time
import urllib.parse
import urllib.request

SCHEMA = "touchstone.telemetry.v1"
# 允许外发的字段白名单（数据最小化：只发健康/裁决数值，不含代码/diff/正文/凭据）。
_ALLOWED = {
    "ts", "version", "round", "engine_status", "review_reliable", "ai_raw_count",
    "partial_tool_failure", "repaired_parses", "findings_total", "findings_rule_based",
    "findings_ai", "risk_band", "loop_decision", "gate", "unverified_claims",
    "change_class", "added_lines",
}
# 标识字段（可用 ANONYMIZE 抹掉）。注意：diff/代码/PR 正文本就不在 metrics 记录里，无需过滤。
_IDENTIFIERS = {"pr", "sha"}


def enabled(env):
    return bool(env.get("TOUCHSTONE_TELEMETRY_ENDPOINT"))


def _project(record, anonymize):
    """投影到白名单字段（数据最小化）；anonymize 时连标识字段一并去掉。"""
    keep = set(_ALLOWED)
    if not anonymize:
        keep |= _IDENTIFIERS
    return {k: v for k, v in record.items() if k in keep}


def build_envelope(records, *, deployment_id, version, anonymize=False):
    """把若干 metrics 记录包成一个上报信封（可 JSON 序列化）。只含白名单字段。"""
    return {
        "schema": SCHEMA,
        "deployment_id": deployment_id or "unset",
        "sent_at": int(time.time()),
        "version": version,
        "anonymized": bool(anonymize),
        "records": [_project(r, anonymize) for r in records],
    }


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    # SSRF 防护：汇聚点端点不许跟随重定向——合法 http(s) 端点也可能 302 到内网
    # （如云元数据 169.254.169.254），scheme 白名单挡不住重定向后的目标。
    # 与 alert.py 一致（镜像模块、同一威胁模型：env-sourced 出站 URL）。
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError(f"telemetry 端点 {code} 重定向被拒（SSRF 防护，不跟随到 {newurl}）")


_OPENER = urllib.request.build_opener(_NoRedirectHandler)


def _default_http_post(url, payload, token=None, timeout=15):
    # SSRF 防护：端点 URL 来自 env（操作员配置，可能误配/被污染），校验 scheme——只许 http/https，
    # 拒 file:///ftp:///gopher 等会被当本地/其它协议读取的端点；并用不跟随重定向的 opener。
    # 与 alert.py _default_http_post 同构（同一政企/内网客户、同一 egress 威胁面，cross-patch 一致）。
    scheme = urllib.parse.urlparse(url).scheme.lower()
    if scheme not in ("http", "https"):
        raise ValueError(f"telemetry URL scheme 不允许: {scheme!r}")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, data=json.dumps(payload, ensure_ascii=False).encode(),
                                 headers=headers, method="POST")
    with _OPENER.open(req, timeout=timeout) as r:
        return r.status


def forward(records, env, *, version="", http_post=None):
    """按 env 把 records 上报到汇聚点。未配端点 → 无操作。失败绝不冒泡，只返回状态串。"""
    endpoint = env.get("TOUCHSTONE_TELEMETRY_ENDPOINT")
    if not endpoint or not records:
        return "disabled"
    http_post = http_post or _default_http_post
    envelope = build_envelope(
        records,
        deployment_id=env.get("TOUCHSTONE_TELEMETRY_DEPLOYMENT_ID"),
        version=version,
        anonymize=str(env.get("TOUCHSTONE_TELEMETRY_ANONYMIZE", "")).lower() == "true")
    try:
        http_post(endpoint, envelope, token=env.get("TOUCHSTONE_TELEMETRY_TOKEN"))
        return "ok"
    except Exception as e:                        # noqa: BLE001 —— 遥测失败不许拖垮评审
        return f"failed: {type(e).__name__}"
