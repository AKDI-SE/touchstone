#!/usr/bin/env python3
# ============================================================================
# touchstone/ground_truth.py —— 真值集采集（人审裁决 → TF-GRPO 学习信号）
# ----------------------------------------------------------------------------
# 从 learning_loop 拆出（模块职责单一化，第三轮工程化加固）。本模块只管学习信号
# 从哪【来】：取最近已关闭 PR，人 resolve 的发现线程 → human_adopted（正例），
# 忽略的 → human_ignored（噪声负例）；PR 级 APPROVED/CHANGES_REQUESTED + 是否合入
# 一并记录。复用 calibrate 的 marker 解析与 GraphQL 线程采纳口径，不另建库。
# ============================================================================

import os
import sys

GT_WINDOW = int(os.environ.get("TOUCHSTONE_GT_WINDOW", "30"))   # 重建真值集回看的最近已关闭 PR 数
GT_DIFF_BUDGET = 8000                                            # 单 PR diff 截断字符预算（喂 TF-GRPO 的上下文）

# --- 真值集采集：从 GitHub 人审裁决重建（喂 TF-GRPO 的学习信号）-----------------
#   「根据每次人工合入的好坏自己学习」的数据入口：取最近已关闭 PR，
#   把【人最终 resolve 了哪些发现线程】→ human_adopted（正例：该类发现值得挑）；
#   人忽略的 → human_ignored（噪声负例）。PR 级 APPROVED/CHANGES_REQUESTED + 是否合入
#   作为好坏信号一并记录。复用 calibrate 的 marker 解析与 GraphQL 线程采纳口径，不另建库。
def _gh_get(path, token, accept="application/vnd.github+json"):
    """GitHub REST GET（经 ghclient 连接池 + 退避）。accept 以 'diff' 结尾返回文本。"""
    from touchstone import ghclient
    base = os.environ.get("GITHUB_API_URL", "https://api.github.com")
    return ghclient.request("GET", base + path, token, accept=accept)


def _stack_of(filenames):
    """从改动文件后缀粗判技术栈（仅用于经验按栈归类；不确定 → 空串=通用）。"""
    exts = {os.path.splitext(f)[1].lower() for f in (filenames or []) if f}
    if exts & {".java"}:                       return "java"
    if exts & {".py"}:                         return "python"
    if exts & {".go"}:                         return "go"
    if exts & {".ts", ".tsx", ".js", ".jsx"}:  return "typescript"
    return ""


def make_gt_entry(pr_number, repo, stack, summary, diff, touchstone_findings,
                  resolved_types, human_state, merged):
    """纯函数：单个 PR → TF-GRPO 真值条目。
    human_adopted = 人 resolve 了线程的发现类型（正例：值得挑）；
    human_ignored = touchstone 挑了但人没采纳的（噪声负例）。
    与 _distill_via_llm 期望的 ground_truth schema 对齐（human_adopted 喂 score_review）。"""
    adopted = sorted({t for t in (resolved_types or []) if t})
    ts_types = {(f.get("rule_id") or f.get("finding_type")) for f in (touchstone_findings or [])}
    ts_types = {t for t in ts_types if t}
    return {"pr_id": str(pr_number), "repo": repo or "", "stack": stack or "",
            "summary": summary or "", "diff": diff or "",
            "human_adopted": adopted,
            "human_ignored": sorted(ts_types - set(adopted)),
            "human_state": human_state, "merged": bool(merged)}


def build_ground_truth(owner, repo, token, *, window=GT_WINDOW, bot_login=None,
                       diff_budget=GT_DIFF_BUDGET):
    """从 GitHub 重建 TF-GRPO 真值集（离线学习的数据入口，需 GITHUB_TOKEN）。
    复用 calibrate：touchstone 发现来自 <!-- touchstone-result: --> marker；
    人采纳来自该发现的评审线程被 resolved（GraphQL isResolved）；
    PR 级好坏来自人审 state(APPROVED/CHANGES_REQUESTED) + 是否合入。
    返回 [make_gt_entry ...]。任一 PR 取数失败仅跳过该 PR，不中断整体。"""
    from touchstone import calibrate as C
    bot_login = bot_login or os.environ.get("TOUCHSTONE_BOT_LOGIN", "github-actions[bot]")
    prs = _gh_get(f"/repos/{owner}/{repo}/pulls?state=closed&sort=updated&direction=desc"
                  f"&per_page={window}", token) or []
    out = []
    for pr in prs:
        n = pr.get("number")
        if not n:
            continue
        try:
            comments = _gh_get(f"/repos/{owner}/{repo}/issues/{n}/comments?per_page=100", token) or []
            result = C._parse_result([c.get("body", "") for c in comments], bot_login)
            if not result:
                continue                          # 未经过 touchstone 评审，无学习信号
            ts_findings = result.get("findings", []) or []
            try:
                threads = C.parse_review_threads(
                    C.gql(C._GQL_THREADS, {"owner": owner, "repo": repo, "num": n}, token))
                fa = C.thread_findings(threads, bot_login)
            except Exception as e:
                print(f"[learning_loop] PR#{n} 评审线程解析失败（按无采纳记录处理）: {e}",
                      file=sys.stderr)
                fa = []
            resolved_types = {f.get("rule_id") for f in fa if f.get("resolved")}
            reviews = _gh_get(f"/repos/{owner}/{repo}/pulls/{n}/reviews?per_page=100", token) or []
            human_state = C._human_verdict(reviews, bot_login)
            try:
                diff = _gh_get(f"/repos/{owner}/{repo}/pulls/{n}", token,
                               accept="application/vnd.github.v3.diff")
                if len(diff) > diff_budget:
                    diff = diff[:diff_budget] + "\n... [diff truncated]"
            except Exception as e:
                print(f"[learning_loop] PR#{n} diff 获取失败（以空 diff 继续）: {e}", file=sys.stderr)
                diff = ""
            files = [f.get("filename") for f in
                     (_gh_get(f"/repos/{owner}/{repo}/pulls/{n}/files?per_page=100", token) or [])]
            out.append(make_gt_entry(n, repo, _stack_of(files), pr.get("title", ""),
                                     diff, ts_findings, resolved_types, human_state,
                                     bool(pr.get("merged_at"))))
        except Exception as e:
            print(f"[learn] PR #{n} 取数失败，跳过：{e}", file=sys.stderr)
            continue
    return out

