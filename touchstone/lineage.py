#!/usr/bin/env python3
# ============================================================================
# touchstone/lineage.py  ——  轮次台账 RoundLedger 与同源检测（修订设计 §4.4，评审意见 10）
# ----------------------------------------------------------------------------
# 漏洞：轮次以 PR 号记账时，关旧 PR、原样开新 PR 即重置轮次并让评审方失去历史记忆。
# 修法：记账主体从 PR 号改为【内容指纹】（由范围事实 ScopeFacts 派生）。
#
# 设计要点：
#   - 不新增存储：台账从已关闭 PR 的评论（loop marker + 收敛清单 marker）【重建】——
#     与既有「状态存于评论 marker」机制同构，无双源一致性负担。
#   - 命中处理是记录+提示，不是拦截：继承轮次余额与未销项清单，报告横幅明示；
#     正当的关旧开新（rebase 损坏、换分支）不受阻，只是历史欠账原样跟随。
#   - 人工重置口：PR 打 rounds-reset label（需仓库写权限）→ 全新台账并记录授权人。
#   - 指纹不用全文哈希（改一个空格即绕过）：文件集 Jaccard + hunk 结构相似度双阈值。
#   - 行为信号：同源重提本身记入台账 lineage，供学习回路作提交方行为层面的负样本素材。
#
# 控制变量（进锚定矩阵）：JACCARD_MIN=0.8、SHAPE_MIN=0.6、LOOKBACK_DAYS=30、rounds-reset label。
# ============================================================================

import datetime
import sys

from touchstone import loop
from touchstone import checklist as _checklist

JACCARD_MIN = 0.8        # 文件集 Jaccard 相似阈值
SHAPE_MIN = 0.6          # hunk 结构（每文件增删行数）相似阈值
LOOKBACK_DAYS = 30       # 只比对近 N 天关闭的 PR
RESET_LABEL = "rounds-reset"


def fresh_ledger(fingerprint, max_rounds=None, reset_by=None):
    mr = max_rounds if max_rounds is not None else loop.MAX_ROUNDS
    return {"fingerprint": fingerprint or {}, "lineage": [], "rounds_spent": 0,
            "rounds_left": mr, "inherited_open_items": [], "reset_by": reset_by}


def fileset_jaccard(a, b):
    """文件集 Jaccard 相似度。空对空视为不相似（空 diff 不构成同源证据）。"""
    sa, sb = set(a or []), set(b or [])
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def shape_similarity(shape_a, shape_b):
    """hunk 结构相似度：对共同文件的 (added, deleted) 计数做归一化 L1 差。
    只比共同文件——文件集差异已由 Jaccard 度量，此处度量「同一批文件里改动形状像不像」。"""
    a, b = shape_a or {}, shape_b or {}
    common = set(a) & set(b)
    if not common:
        return 0.0
    sims = []
    for p in common:
        aa, ad = (a[p] + [0, 0])[:2]
        ba, bd = (b[p] + [0, 0])[:2]
        denom = max(aa + ad, ba + bd, 1)
        sims.append(1.0 - (abs(aa - ba) + abs(ad - bd)) / (2.0 * denom))
    return sum(sims) / len(sims)


def same_origin(fp_a, fp_b, jaccard_min=JACCARD_MIN, shape_min=SHAPE_MIN):
    """同源判定：文件集 Jaccard ≥ 阈值 且 hunk 结构相似度 ≥ 阈值（双条件，缺一不可）。
    残余风险（有意接受）：刻意大幅改名+重排 hunk 可绕过——绕过成本已高于收益，
    且此类行为会被 lineage 行为信号记录；语义级比对的代价与 advisory 定位不符。"""
    j = fileset_jaccard((fp_a or {}).get("fileset"), (fp_b or {}).get("fileset"))
    s = shape_similarity((fp_a or {}).get("shape"), (fp_b or {}).get("shape"))
    return (j >= jaccard_min and s >= shape_min), j, s


def _recent_enough(iso_ts, days=LOOKBACK_DAYS, now=None):
    try:
        t = datetime.datetime.fromisoformat((iso_ts or "").replace("Z", "+00:00"))
    except ValueError:
        return False
    # 健壮性：naive 时间戳（无 Z/偏移——非 GitHub 规范源/脏数据/手写 fixture）与 aware 的 now
    # 相减会抛 TypeError「can't subtract offset-naive and offset-aware datetimes」，把整个
    # detect_lineage 带崩（台账继承失败→上游回落）。无偏移即按 UTC 解释，与上方 Z→+00:00 同语义。
    if t.tzinfo is None:
        t = t.replace(tzinfo=datetime.timezone.utc)
    now = now or datetime.datetime.now(datetime.timezone.utc)
    # 对称守卫：调用方传入的 now 若为 naive（测试 fixture / 非规范源），与上方已 aware 的 t
    # 相减同样抛 TypeError。无偏移即按 UTC 解释——与 t 的处理同语义，避免「补了 t 漏 now」的半截修复。
    if now.tzinfo is None:
        now = now.replace(tzinfo=datetime.timezone.utc)
    return (now - t).days <= days


def detect_lineage(scope_fp, api, owner, repo, current_number, current_labels=None,
                   max_rounds=None, days=LOOKBACK_DAYS, now=None):
    """检索近 days 天已关闭 PR → 指纹比对 → 命中则从其评论重建台账。

    api：可注入的请求函数 api(method, path) -> 解析后的 JSON（生产用 orchestrator.gh 的闭包，
         测试注入假实现）。所有网络访问经此单点，失败即返回全新台账（台账是增强，不阻塞评审）。
    current_labels：本 PR 的 label 名列表——含 rounds-reset 即人工授权重置（记录授权人由调用方补）。
    返回 RoundLedger（修订设计 §4.4）。
    """
    mr = max_rounds if max_rounds is not None else loop.MAX_ROUNDS
    if RESET_LABEL in (current_labels or []):
        return fresh_ledger(scope_fp, mr, reset_by="label:rounds-reset")
    if not scope_fp or not scope_fp.get("fileset"):
        return fresh_ledger(scope_fp, mr)
    try:
        closed = api("GET", f"/repos/{owner}/{repo}/pulls?state=closed&sort=updated"
                            f"&direction=desc&per_page=30") or []
    except Exception as e:                                    # 台账是增强，不阻塞评审主链
        print(f"[lineage] 关闭 PR 检索失败，按全新台账处理：{e}", file=sys.stderr)
        return fresh_ledger(scope_fp, mr)

    ledger = fresh_ledger(scope_fp, mr)
    for pr in closed:
        num = pr.get("number")
        if not num or num == current_number:
            continue
        if pr.get("merged_at"):
            continue          # 已合入的 PR 不是「关旧开新刷轮次」，不入台账
        if not _recent_enough(pr.get("closed_at") or pr.get("updated_at"), days, now):
            continue
        try:
            # 文件集初筛（列表 API 便宜）：files 端点取变更文件名
            files = api("GET", f"/repos/{owner}/{repo}/pulls/{num}/files?per_page=100") or []
            fileset = [f.get("filename") for f in files if f.get("filename")]
            shape = {f.get("filename"): [int(f.get("additions", 0)), int(f.get("deletions", 0))]
                     for f in files if f.get("filename")}
        except Exception:
            continue
        hit, j, s = same_origin(scope_fp, {"fileset": fileset, "shape": shape})
        if not hit:
            continue
        # 命中：从该关闭 PR 的评论重建历史（只信机器人评论——沿用 trusted_bodies）
        rounds, open_items = _history_from_comments(api, owner, repo, num)
        ledger["lineage"].append({"number": num, "rounds": rounds,
                                  "jaccard": round(j, 3), "shape_sim": round(s, 3)})
        ledger["rounds_spent"] += rounds
        for it in open_items:
            if it["sig"] not in {x["sig"] for x in ledger["inherited_open_items"]}:
                ledger["inherited_open_items"].append(it)
    ledger["rounds_left"] = max(0, mr - ledger["rounds_spent"])
    return ledger


def _history_from_comments(api, owner, repo, number):
    """从关闭 PR 的评论重建：已消耗轮次（loop marker）+ 未销项清单项（checklist marker）。"""
    try:
        comments = api("GET", f"/repos/{owner}/{repo}/issues/{number}/comments?per_page=100")
        comments = comments if isinstance(comments, list) else []
    except Exception:
        return 0, []
    bodies = loop.trusted_bodies(comments, None)      # 按 [bot] 后缀过滤，防伪造历史
    state = loop.parse_latest_state(bodies)
    cl = _checklist.parse_latest(bodies)
    open_items = []
    for i in (cl or {}).get("items", []):
        if i.get("status") != "open":
            continue
        it = dict(i)
        it["sig"] = _checklist._norm_sig(it.get("sig", ""))   # 旧 marker 脏 sig 归一化，台账跨 PR 去重可比
        open_items.append(it)
    return state.round, open_items
