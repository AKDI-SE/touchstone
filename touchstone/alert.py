#!/usr/bin/env python3
# ============================================================================
# touchstone/alert.py  ——  告警钩子（把 metrics 信号投递到已配通道）
# ----------------------------------------------------------------------------
# metrics 把每轮健康信号落成事件流；alert 在其之上做两件事：
#   1) 判定（evaluate）：哪些 metrics 条件值得告警——纯函数、无 IO、可测。
#   2) 投递（deliver）：把告警发到【客户自己配置】的通道——GitHub 原生 / webhook。
#
# 设计约束（见 module-design；与 SECURITY/DEPLOYMENT 一致）：
#   · 投递目标是【配置】（secret/env），不是代码；告警进客户自己的渠道，绝不回传给我方，
#     也没有任何硬编码的外部 URL。
#   · 总开关 TOUCHSTONE_ALERT_ENABLED 不为 true → 不外呼，只保留 metrics artifact（默认行为）。
#   · 投递失败【绝不冒泡】：告警是可观测性，不是门禁——它挂掉不许拖垮评审 job。
#   · 内网/断网客户公网 webhook 连不通 → 走 GitHub 原生（复用同一 GITHUB_TOKEN，不出外网）。
#
# 通道（TOUCHSTONE_ALERT_CHANNELS，默认 github-issue,github-pr-comment）：
#   github-pr-comment  单轮即时告警 → 贴到对应 PR（天然按轮去重）
#   github-issue       滚动聚合告警 → 开/更新一个带 label 的跟踪 Issue（去重，防刷屏）
#   webhook            POST 告警 JSON 到 TOUCHSTONE_ALERT_WEBHOOK（企业微信/钉钉/自建）
#
# 概念：
#   · 告警判定（alert rule）：一组 metrics 条件 → 一条 Alert。
#   · Alert：{severity, kind, title, body, scope}；scope ∈ {"pr","repo"} 决定投递通道。
# ============================================================================

import json
import urllib.parse
import urllib.request

ISSUE_LABEL = "touchstone-alert"


# ---- 判定：metrics record(+聚合) → [Alert] --------------------------------
def _alert(severity, kind, title, record, scope, extra=""):
    ctx = (f"PR #{record.get('pr')} · sha {record.get('sha')} · "
           f"engine={record.get('engine_status')} · reliable={record.get('review_reliable')}")
    body = f"**[{severity.upper()}] {title}**\n\n{ctx}\n{extra}".rstrip()
    return {"severity": severity, "kind": kind, "title": title, "body": body, "scope": scope}


def evaluate(record, agg=None, *, reliable_min=0.8, silent_max=0):
    """从一条 metrics record（+可选聚合 agg=metrics.summarize(...)）判定要发哪些告警。
    纯函数、无 IO。返回 [Alert]。阈值可由调用方（env）覆盖。"""
    alerts = []
    # —— 单轮即时（scope=pr）——
    if (record.get("review_reliable") is False
            and record.get("engine_status") == "ok"
            and (record.get("ai_raw_count") or 0) == 0):
        # 静默故障 =「看着正常其实没审」——仅 engine_status=='ok' 才算（与 metrics.summarize 的
        # silent_failure_rounds 口径一致：那里 :108-110 同样只数 ok）。
        # llm_failed/no_engine/provider_failed 是【已被检测且大声上报】的降级，不是静默——
        # 它们由下面 engine_degraded 告警负责；把 llm_failed 也算静默会与 metrics 定义打架、
        # 且对同一事件双发（high 静默 + warn 降级），污染客户告警渠道。
        alerts.append(_alert("high", "silent_failure",
                             "LLM 静默故障：本轮评审不可信且 0 建议（不该被当绿灯）", record, "pr",
                             "排障见 docs/incident-runbook.md §1。"))
    if record.get("engine_status") in ("no_engine", "provider_failed", "llm_failed"):
        alerts.append(_alert("warn", "engine_degraded",
                             f"评审引擎降级：{record.get('engine_status')}", record, "pr",
                             "确定性核对仍有效（有横幅，非静默）；见 runbook §5。"))
    if (record.get("unverified_claims") or 0) > 0:
        alerts.append(_alert("warn", "unverified_claims",
                             f"{record['unverified_claims']} 条 author 自证（waived/split）待人核准",
                             record, "pr", "未核准前不触发自动放行；见 SECURITY 边界 1。"))
    # —— 滚动聚合（scope=repo）——
    if agg:
        rr = agg.get("review_reliable_rate")
        if rr is not None and agg.get("rounds", 0) and rr < reliable_min:
            alerts.append(_alert("high", "reliable_rate_low",
                                 f"评审可信率 {rr:.0%} 低于阈值 {reliable_min:.0%}", record, "repo",
                                 f"近 {agg.get('rounds')} 轮；引擎分布 {agg.get('engine_status_dist')}。"))
        if (agg.get("silent_failure_rounds") or 0) > silent_max:
            alerts.append(_alert("high", "silent_failure_trend",
                                 f"近 {agg.get('rounds')} 轮有 {agg['silent_failure_rounds']} 轮静默故障",
                                 record, "repo", "持续静默故障——查 LLM 端点/超时；见 runbook §1。"))
    return alerts


# ---- 通道选择（env）--------------------------------------------------------
def channels_from_env(env):
    """总开关不开 → []（不外呼，只保留 metrics artifact）。开则取通道集；配了 webhook URL 自动加 webhook。"""
    if str(env.get("TOUCHSTONE_ALERT_ENABLED", "")).lower() != "true":
        return []
    raw = env.get("TOUCHSTONE_ALERT_CHANNELS", "github-issue,github-pr-comment")
    chans = [c.strip() for c in raw.split(",") if c.strip()]
    if env.get("TOUCHSTONE_ALERT_WEBHOOK") and "webhook" not in chans:
        chans.append("webhook")
    return chans


# ---- 投递（各通道独立 try/except，绝不冒泡）--------------------------------
class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    # SSRF 防护：webhook 端点不许跟随重定向——合法 http(s) 端点也可能 302 到内网
    # （如云元数据 169.254.169.254），scheme 白名单挡不住重定向后的目标。故用此 handler
    # 替换默认的 HTTPRedirectHandler：收到 3xx 直接抛，opener.open 不跟随。
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError(f"webhook 端点 {code} 重定向被拒（SSRF 防护，不跟随到 {newurl}）")


_WEBHOOK_OPENER = urllib.request.build_opener(_NoRedirectHandler)


def _default_gh(method, path, token, data=None):
    # 走 ghclient 公开 client()（内部已拼 base_url），不伸手进 ghclient 的私有 _base_url()。
    # ghclient.py 末段明示 client() 是各模块老 gh() wrapper（request()+_base_url() 拼装）的官方
    # 替代；这里即迁移到公开接口，消除私有方法耦合（alert 属 A 层、ghclient 属 B 层，本函数是
    # alert 的默认投递器，仅经公开 client() 调用，不跨层触碰 ghclient 内部）。注入式测试用
    # deliver(..., gh_call=...) 的 seam 直接替换本函数，故本默认实现的内部改造不影响测试。
    # alert 通道只用 GET/POST（_post_pr_comment / _open_or_update_issue 的评论 + 开 issue），
    # ghclient session 也只重试 GET/POST（make_session allowed_methods）。故 GET/POST 显式分发，
    # 其余 method 立即抛 ValueError——不静默当 POST，防调用方误传 PUT/PATCH/DELETE 被吞（PR#69 r1）。
    from touchstone import ghclient
    c = ghclient.client(token)
    if method == "GET":
        return c.get(path)
    if method == "POST":
        return c.post(path, data or {})
    raise ValueError(f"_default_gh 仅支持 GET/POST，不支持 {method!r}")


def _default_http_post(url, payload):
    # SSRF 防护：webhook URL 来自 env，校验 scheme——只许 http/https，
    # 拒 file:///ftp:///gopher 等会被当成本地/其它协议读取的端点；
    # 并用不跟随重定向的 opener——合法 http 端点也可能 302 到内网。
    scheme = urllib.parse.urlparse(url).scheme.lower()
    if scheme not in ("http", "https"):
        raise ValueError(f"webhook URL scheme 不允许: {scheme!r}")
    req = urllib.request.Request(url, data=json.dumps(payload, ensure_ascii=False).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with _WEBHOOK_OPENER.open(req, timeout=15) as r:
        return r.status


def _post_pr_comment(al, ctx, gh_call):
    gh_call("POST", f"/repos/{ctx['owner']}/{ctx['repo']}/issues/{ctx['number']}/comments",
            ctx["token"], {"body": _with_link(al, ctx)})


def _open_or_update_issue(al, ctx, gh_call):
    """去重开/更新跟踪 Issue：按 label 找已开的同类 Issue，有则追评论，无则新建。防每轮刷屏。"""
    owner, repo, token = ctx["owner"], ctx["repo"], ctx["token"]
    found = gh_call("GET", f"/repos/{owner}/{repo}/issues?state=open&labels={ISSUE_LABEL}", token) or []
    marker = f"<!-- touchstone-alert:{al['kind']} -->"
    hit = next((i for i in found if marker in (i.get("body") or "")), None)
    if hit:
        gh_call("POST", f"/repos/{owner}/{repo}/issues/{hit['number']}/comments", token,
                {"body": _with_link(al, ctx)})
    else:
        gh_call("POST", f"/repos/{owner}/{repo}/issues", token,
                {"title": f"[touchstone] {al['title']}", "labels": [ISSUE_LABEL],
                 "body": marker + "\n\n" + _with_link(al, ctx)})


def _with_link(al, ctx):
    run = ctx.get("run_url")
    return al["body"] + (f"\n\n[查看本轮运行]({run})" if run else "")


def deliver(alerts, *, channels, ctx, gh_call=None, webhook_url=None, http_post=None):
    """把 alerts 投递到已配通道。返回 [(channel, kind, result)]。每次投递独立捕获异常——绝不冒泡。"""
    gh_call = gh_call or _default_gh
    http_post = http_post or _default_http_post
    results = []
    for al in alerts:
        for ch in channels:
            try:
                if ch == "github-pr-comment" and al["scope"] == "pr" and ctx.get("number"):
                    _post_pr_comment(al, ctx, gh_call)
                elif ch == "github-issue" and al["scope"] == "repo":
                    _open_or_update_issue(al, ctx, gh_call)
                elif ch == "webhook" and webhook_url:
                    http_post(webhook_url, {"kind": al["kind"], "severity": al["severity"],
                                            "title": al["title"], "body": al["body"],
                                            "pr": ctx.get("number"), "repo": f"{ctx.get('owner')}/{ctx.get('repo')}"})
                else:
                    continue
                results.append((ch, al["kind"], "ok"))
            except Exception as e:                       # noqa: BLE001 —— 告警失败绝不拖垮评审
                # 带上消息（截断）：可观测性子系统的本分就是让故障可见——
                # 只留 type 名（"failed: HTTPError"）没法定位，运维无从下手。
                msg = str(e).strip().replace("\n", " ")[:200]
                results.append((ch, al["kind"], f"failed: {type(e).__name__}: {msg}"))
    return results


def run(record, agg, env, ctx):
    """编排：按 env 选通道（不开→无操作），判定，投递。返回投递结果（空=未启用/无告警）。"""
    channels = channels_from_env(env)
    if not channels:
        return []
    alerts = evaluate(record, agg,
                      reliable_min=float(env.get("TOUCHSTONE_ALERT_RELIABLE_MIN", "0.8")),
                      silent_max=int(env.get("TOUCHSTONE_ALERT_SILENT_MAX", "0")))
    if not alerts:
        return []
    return deliver(alerts, channels=channels, ctx=ctx,
                   webhook_url=env.get("TOUCHSTONE_ALERT_WEBHOOK"))
