#!/usr/bin/env python3
# ============================================================================
# touchstone/calibrate.py  ——  校准（设计 §4.3 record_calibration）
# ----------------------------------------------------------------------------
# 用人审真实裁决当免费 标准答案，衡量 touchstone 准不准。
# 不另建数据库——直接从 GitHub API 重建：
#   • touchstone 发现/风险：从其评论里的 <!-- touchstone-result: ... --> marker 解析
#   • 人审裁决：从 PR 的 review 状态(APPROVED/CHANGES_REQUESTED)与是否合入
# 最小可算的是【PR 级代理】吻合度（finding 级"人是否采纳某条"需线程解决状态=GraphQL，留作细化）：
#   • 风险等级 vs 人审决定（high 档应更多 CHANGES_REQUESTED = 校准良好）
#   • 某 agent/rule 命中的 PR 中，人最终要求改动的比例（命中多但该比例低 = 噪声专才）
# 北极星：touchstone 标了问题、人也确实想改 的吻合比例。
# ============================================================================

import json
import os
import re
import sys

import ghclient            # GitHub HTTP 客户端(requests + 退避)
import requests

WINDOW = int(os.environ.get("CALIBRATE_WINDOW", "50"))   # 取最近 N 个已关闭 PR
NOISY_MIN_FIRES = 5          # agent/rule 命中达到此数才判定噪声
NOISY_CR_RATE = 0.2          # 命中 PR 的"人要求改动"比例低于此 → 噪声
NOISY_ADOPT_RATE = 0.2       # finding 级：命中条数多但被采纳(线程 resolved)比例低于此 → 噪声
_RESULT = re.compile(r"<!--\s*touchstone-result:\s*(\{.*?\})\s*-->", re.DOTALL)
_FINDING = re.compile(r"<!--\s*touchstone-finding:\s*(\{.*?\})\s*-->", re.DOTALL)


# --- GitHub REST（requests，见 ghclient；保持串行：二级限流惩罚并发）------------
def gh(path, token):
    base = os.environ.get("GITHUB_API_URL", "https://api.github.com")
    return ghclient.request("GET", base + path, token)


# --- GitHub GraphQL：取 PR 评论线程的 isResolved（REST 不暴露线程解决状态）------
_GQL_THREADS = """
query($owner:String!,$repo:String!,$num:Int!){
  repository(owner:$owner,name:$repo){
    pullRequest(number:$num){
      reviewThreads(first:100){
        nodes{ isResolved comments(first:20){ nodes{ author{login} body } } }
      }
    }
  }
}"""


def gql(query, variables, token):
    base = os.environ.get("GITHUB_GRAPHQL_URL", "https://api.github.com/graphql")
    return ghclient.request("POST", base, token,
                            data={"query": query, "variables": variables})


def parse_review_threads(data):
    """GraphQL 响应 → [{isResolved, comments:[{author, body}]}]。纯函数。"""
    pr = (((data or {}).get("data") or {}).get("repository") or {}).get("pullRequest") or {}
    nodes = ((pr.get("reviewThreads") or {}).get("nodes")) or []
    out = []
    for t in nodes:
        comments = [{"author": ((c.get("author") or {}).get("login") or ""),
                     "body": c.get("body") or ""}
                    for c in (((t.get("comments") or {}).get("nodes")) or [])]
        out.append({"isResolved": bool(t.get("isResolved")), "comments": comments})
    return out


def thread_findings(threads, bot_login=None):
    """把每条评论线程对回某条 touchstone 发现：线程内带 touchstone-finding 标记的评论
    → {rule_id, agent, resolved=线程 isResolved}。线程被 resolved 视作该条被采纳(proxy)。"""
    out = []
    for t in threads:
        for c in t.get("comments", []):
            m = _FINDING.search(c.get("body") or "")
            if not m:
                continue
            try:
                meta = json.loads(m.group(1))
            except json.JSONDecodeError:
                continue
            out.append({"rule_id": meta.get("rule_id"), "agent": meta.get("agent"),
                        "resolved": bool(t.get("isResolved"))})
            break                      # 一个线程只对一条发现
    return out


def fetch_review_threads(owner, repo, number, token):
    data = gql(_GQL_THREADS, {"owner": owner, "repo": repo, "num": number}, token)
    return parse_review_threads(data)


def _parse_result(comment_bodies, bot_login):
    """取最近一条 touchstone-result marker（touchstone 每轮都会贴）。"""
    for body in reversed(comment_bodies):
        m = _RESULT.search(body or "")
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                continue
    return None


def _human_verdict(reviews, bot_login):
    """人审最终裁决：取最后一条非 bot 的决定性 review 状态。"""
    state = None
    for rv in reviews:
        login = (rv.get("user") or {}).get("login", "")
        if login == bot_login or login.endswith("[bot]"):
            continue
        s = rv.get("state")
        if s in ("APPROVED", "CHANGES_REQUESTED"):
            state = s
    return state


# --- 纯聚合（可测）-----------------------------------------------------------
def _norm_record(r):
    """归一化两种 CalibrationRecord 形状：main() 经 record_calibration 构造的（touchstone_band/
    touchstone_findings/human_verdict）与历史 inline 形状（risk_band/findings/human_state）。"""
    return {
        "pr": r.get("pr"),
        "risk_band": r.get("risk_band", r.get("touchstone_band")),
        "findings": r.get("findings", r.get("touchstone_findings", [])),
        "human_state": r.get("human_state", r.get("human_verdict")),
        "finding_adoption": r.get("finding_adoption", []),
        "merged": r.get("merged"),
        "merge_commit_sha": r.get("merge_commit_sha"),
        "auto_handled": r.get("auto_handled"),
    }


def record_calibration(pr, touchstone_output, human_verdict):
    """§4.3（薄封装）：把【单个 PR】的 touchstone 输出与人审裁决组装成一条 CalibrationRecord
    （成员见设计 §3.5：touchstone_findings / touchstone_band / human_verdict / human_flagged / agreement）。
    批量校准不另建库，而是从 GitHub API 重建多条 record 后交 aggregate()（见 main()）。"""
    if isinstance(touchstone_output, dict):
        findings = touchstone_output.get("findings", []) or []
        band = (touchstone_output.get("risk") or {}).get("risk_band")
    else:
        findings, band = (touchstone_output or []), None
    if isinstance(human_verdict, dict):
        hv = human_verdict.get("state") or human_verdict.get("verdict")
        flagged = human_verdict.get("flagged", []) or []
    else:
        hv, flagged = human_verdict, []
    touchstone_flagged = bool(findings) or band in ("mid", "high")
    human_changes = str(hv).upper() in ("CHANGES_REQUESTED", "CHANGES")
    return {"pr": pr, "touchstone_findings": findings, "touchstone_band": band,
            "human_verdict": hv, "human_flagged": flagged,
            "agreement": touchstone_flagged == human_changes}


def aggregate(records):
    """records: [{risk_band, findings:[{rule_id,agent}], human_state, merged}]（经 _norm_record
    也接受 record_calibration 的 touchstone_* / human_verdict 形状）。"""
    records = [_norm_record(r) for r in records]
    def cr(rs):                       # 人"要求改动"比例（CHANGES_REQUESTED）
        n = [r for r in rs if r.get("human_state")]
        return (sum(r["human_state"] == "CHANGES_REQUESTED" for r in n) / len(n)) if n else None

    out = {"total": len(records), "by_risk": {}, "by_agent": {}, "by_rule": {}, "noisy": []}
    with_find = [r for r in records if r.get("findings")]
    out["prs_with_findings"] = len(with_find)
    out["overall_changes_requested_rate"] = cr(records)
    # 风险等级校准
    for band in ("high", "mid", "low"):
        rs = [r for r in records if r.get("risk_band") == band]
        out["by_risk"][band] = {"count": len(rs), "changes_requested_rate": cr(rs)}
    # 按 agent / rule：命中计数 + 命中 PR 的人改动比例
    def by_key(keyfn):
        acc = {}
        for r in records:
            seen = set()
            for f in r.get("findings", []):
                k = keyfn(f)
                if k and k not in seen:
                    seen.add(k)
                    acc.setdefault(k, []).append(r)
        return {k: {"fires": len(rs), "changes_requested_rate": cr(rs)} for k, rs in acc.items()}

    out["by_agent"] = by_key(lambda f: f.get("agent"))
    out["by_rule"] = by_key(lambda f: f.get("rule_id"))
    # 噪声判定：命中多但人改动比例低
    for kind, d in (("agent", out["by_agent"]), ("rule", out["by_rule"])):
        for k, v in d.items():
            rate = v["changes_requested_rate"]
            if v["fires"] >= NOISY_MIN_FIRES and rate is not None and rate < NOISY_CR_RATE:
                out["noisy"].append({"kind": kind, "key": k, "fires": v["fires"],
                                     "changes_requested_rate": round(rate, 2)})
    # finding 级采纳率（GraphQL 线程 isResolved）——比 PR 级更细，直接供固化/噪声判定使用
    def fa_by(keyfn):
        acc = {}
        for r in records:
            for fa in r.get("finding_adoption", []):
                k = keyfn(fa)
                if not k:
                    continue
                a = acc.setdefault(k, {"seen": 0, "adopted": 0})
                a["seen"] += 1
                a["adopted"] += 1 if fa.get("resolved") else 0
        return acc

    for kind, d, acc in (("agent", out["by_agent"], fa_by(lambda f: f.get("agent"))),
                         ("rule", out["by_rule"], fa_by(lambda f: f.get("rule_id")))):
        for k, a in acc.items():
            slot = d.setdefault(k, {"fires": 0, "changes_requested_rate": None})
            slot["findings_seen"] = a["seen"]
            slot["adopted"] = a["adopted"]
            slot["adoption_rate"] = round(a["adopted"] / a["seen"], 2) if a["seen"] else None
            if a["seen"] >= NOISY_MIN_FIRES and slot["adoption_rate"] is not None \
                    and slot["adoption_rate"] < NOISY_ADOPT_RATE:
                out["noisy"].append({"kind": kind, "key": k, "level": "finding",
                                     "findings_seen": a["seen"], "adoption_rate": slot["adoption_rate"]})
    return out


def render_report(agg):
    L = [f"# 校准报告（最近 {agg['total']} 个已关闭 PR）", ""]
    cr = agg["overall_changes_requested_rate"]
    L.append(f"含发现的 PR：{agg['prs_with_findings']}/{agg['total']}　"
             f"整体人要求改动比例：{cr if cr is None else round(cr,2)}")
    L.append("\n## 风险等级校准（high 应明显高于 low）")
    for b in ("high", "mid", "low"):
        v = agg["by_risk"][b]
        L.append(f"- {b}: n={v['count']} 人改动比例={v['changes_requested_rate']}")
    L.append("\n## 按 agent（命中数 · 人改动比例 · finding 级采纳率）")
    for k, v in sorted(agg["by_agent"].items(), key=lambda x: -x[1]["fires"]):
        L.append(f"- {k}: fires={v['fires']} cr={v['changes_requested_rate']} "
                 f"adopt={v.get('adoption_rate')}({v.get('adopted','-')}/{v.get('findings_seen','-')})")
    L.append("\n## 按 rule（命中数 · 人改动比例 · finding 级采纳率）")
    for k, v in sorted(agg["by_rule"].items(), key=lambda x: -x[1]["fires"]):
        L.append(f"- {k}: fires={v['fires']} cr={v['changes_requested_rate']} "
                 f"adopt={v.get('adoption_rate')}({v.get('adopted','-')}/{v.get('findings_seen','-')})")
    if agg["noisy"]:
        L.append("\n## ⚠ 疑似噪声（命中多但很少被采纳 → 考虑收紧/退役）")
        for n in agg["noisy"]:
            if n.get("level") == "finding":
                L.append(f"- [{n['kind']}·finding] {n['key']}: seen={n['findings_seen']} "
                         f"adopt={n['adoption_rate']}")
            else:
                L.append(f"- [{n['kind']}] {n['key']}: fires={n['fires']} cr={n['changes_requested_rate']}")
    else:
        L.append("\n（未发现达阈值的噪声 agent/rule）")
    return "\n".join(L)


def main():
    token = os.environ["GITHUB_TOKEN"]
    owner, repo = os.environ["GITHUB_REPOSITORY"].split("/", 1)
    bot = os.environ.get("TOUCHSTONE_BOT_LOGIN", "github-actions[bot]")
    prs = gh(f"/repos/{owner}/{repo}/pulls?state=closed&sort=updated&direction=desc"
             f"&per_page={WINDOW}", token)
    records = []
    for pr in prs:
        n = pr["number"]
        comments = gh(f"/repos/{owner}/{repo}/issues/{n}/comments?per_page=100", token)
        result = _parse_result([c.get("body", "") for c in comments], bot)
        if not result:
            continue                      # 该 PR 没经过 touchstone，跳过
        # 真实自动放行标记（autonomy.execute_auto_merge 发布的隐藏 marker）；熔断据此归因
        auto_handled = any("touchstone:auto_handled" in (c.get("body") or "") for c in comments)
        reviews = gh(f"/repos/{owner}/{repo}/pulls/{n}/reviews?per_page=100", token)
        try:
            fa = thread_findings(fetch_review_threads(owner, repo, n, token), bot)
        except (requests.exceptions.RequestException, KeyError, ValueError) as e:
            print(f"[warn] PR #{n} 线程采纳取用失败: {e}", file=sys.stderr)
            fa = []
        # 经 record_calibration 构造（设计 §3.5 的 CalibrationRecord 形状），再追加重建期才有的字段。
        # aggregate 经 _norm_record 同时消费此形状与历史 inline 形状。
        hv = _human_verdict(reviews, bot)
        rec = record_calibration(n, {"findings": result.get("findings", []),
                                     "risk": {"risk_band": result.get("risk_band")}}, hv)
        rec.update({"finding_adoption": fa, "merged": bool(pr.get("merged_at")),
                    "merge_commit_sha": pr.get("merge_commit_sha"), "auto_handled": auto_handled})
        records.append(rec)
    agg = aggregate(records)
    report = render_report(agg)
    print(report)
    with open("calibration-report.md", "w", encoding="utf-8") as f:
        f.write(report)
    with open("calibration.json", "w", encoding="utf-8") as f:
        json.dump({"aggregate": agg, "records": records}, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
