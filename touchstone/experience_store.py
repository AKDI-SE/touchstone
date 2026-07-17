#!/usr/bin/env python3
# ============================================================================
# touchstone/experience_store.py —— 经验库（存取 + 生命周期 + 注入渲染）
# ----------------------------------------------------------------------------
# 从 learning_loop 拆出（模块职责单一化，第三轮工程化加固）。本模块只管经验的
# 【状态】：JSON 存取（含从受信 ref 读取防投毒）、seed/merge 入池、
# graduate（shadow A/B 达标 candidate→active）、retire/disable（前提不再成立即退役）、
# render_injection（active 经验 → PR-Agent extra_instructions）。
# 经验怎么【产生】在 distill.py；学习信号从哪【来】在 ground_truth.py；
# learning_loop.py 保留 CLI/main 编排并再导出全部名字（既有引用路径兼容）。
# 铁律不变：经验只调"建议"、绝不进"合入闸"；确定性 contract 类型永不进经验库。
# ============================================================================

import json
import os
import time

# --- 阈值（保守：宁可慢些演进，不轻易注入/退役）---------------------------------
SUPPRESS_ADOPT_MAX  = 0.20   # 采纳率低于此 → "别挑"（suppress）；蒸馏入池与退役镜像判据共用
EMPHASIZE_ADOPT_MIN = 0.80   # 采纳率高于此 → "该挑"（emphasize）；蒸馏入池与退役镜像判据共用
GRADUATE_MIN_SAMPLES = 20     # shadow A/B 两臂各需的样本下限
GRADUATE_MIN_LIFT   = 0.10   # 注入臂采纳率 - 不注入臂 ≥ 此 → 候选达标转 active
RETIRE_ADOPT_MAX    = 0.15   # active 经验对应类型采纳率跌破此（且复发）→ 退役（govern 式）
RETIRE_MIN_FIRES    = 8      # 退役判据的样本下限（与 distill.DISTILL_MIN_FIRES 同值同理：
                             # 样本不足不轻举妄动——蒸馏侧不入池，退役侧不退役）

STORE_PATH = (os.environ.get("TOUCHSTONE_STORE_PATH")
             or os.environ.get("TOUCHSTONE_EXPERIENCE") or ".touchstone/experience.json")

# --- 经验库（JSON 产物，非服务）-------------------------------------------------
# experience: {id, repo, stack, finding_type, kind(suppress/emphasize),
#              text, evidence{fires,adoption}, status(candidate/active/retired),
#              source(human/tfgrpo/counting), locked(bool: 人锁定→回路不得改写/退役),
#              source_prs[], created_at, updated_at}
def _read_store_text(path):
    ref = os.environ.get("TOUCHSTONE_EXPERIENCE_REF")
    if ref:
        import subprocess
        r = subprocess.run(["git", "show", f"{ref}:{path}"], capture_output=True, text=True, timeout=30)
        return r.stdout if r.returncode == 0 else None
    with open(path, encoding="utf-8") as f:
        return f.read()


def load_store(path=None):
    path = path or STORE_PATH
    try:
        text = _read_store_text(path)
        if not text:
            return {"experiences": []}
        store = json.loads(text)
        # 防静默故障（A3-F3）：经验库唯一合法顶层结构是 dict 且 experiences 为 list。存档若是合法
        # JSON 但形状不对（顶层 list/标量，或 experiences 非 list——旧格式/损坏/手改），json.loads 照样
        # 成功并原样返回，下游 render_injection / seed_experience 的 store.get(...) 与迭代会
        # AttributeError/TypeError 崩整个学习回路注入。在唯一加载边界 fail-safe：形状不对即视为损坏、
        # 回落安全默认，不抛、不崩、不把坏数据静默传下去。
        if not isinstance(store, dict) or not isinstance(store.get("experiences"), list):
            return {"experiences": []}
        return store
    except (OSError, json.JSONDecodeError):
        return {"experiences": []}


def save_store(store, path=None):
    path = path or STORE_PATH
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    json.dump(store, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return store


def _is_review_type(finding_type):
    """只有 PR-Agent 源的发现类型才进经验库；确定性 contract_check（SCOPE/TEST/DUP/CTR…）是固定基准，永不进。"""
    return finding_type.startswith("PRA-") or finding_type.startswith("pr-agent")


def _exp_id(finding_type, kind, repo="", stack=""):
    # 经验唯一键含 仓·栈：多仓部署下 A 仓与 B 仓的同类型经验不互相覆盖（I1）
    return f"{kind}:{repo}:{stack}:{finding_type}"


def _protected_types():
    """人立的红线：这些 finding_type 永不许被学习回路 suppress（哪怕历史上人总忽略）。
    来自 env TOUCHSTONE_PROTECTED_TYPES（逗号分隔），如 PRA-SECURITY,PRA-POSSIBLE_BUG。"""
    return {t.strip() for t in os.environ.get("TOUCHSTONE_PROTECTED_TYPES", "").split(",") if t.strip()}


def seed_experience(store, finding_type, kind, text, *, repo="", stack="",
                    status="active", locked=True):
    """人手写一条经验当种子（source=human）。默认直接 active 且 locked（人是权威，学习回路
    不得静默改写或退役）；传 locked=False 可交回路管理。用于冷启动、注入团队领域知识与红线。"""
    if kind not in ("emphasize", "suppress"):
        raise ValueError("kind 必须是 emphasize 或 suppress")
    now = int(time.time())
    exp = {"id": _exp_id(finding_type, kind, repo, stack), "repo": repo, "stack": stack,
           "finding_type": finding_type, "kind": kind, "text": text.strip(),
           "evidence": {"seeded": True}, "status": status, "source": "human",
           "locked": bool(locked), "source_prs": [], "created_at": now, "updated_at": now}
    idx = {e["id"]: e for e in store.get("experiences", [])}
    if exp["id"] in idx:
        idx[exp["id"]].update({k: exp[k] for k in ("text", "status", "source", "locked", "updated_at")})
        return idx[exp["id"]]
    store.setdefault("experiences", []).append(exp)
    return exp


def merge_candidates(store, candidates):
    """把候选并入经验库的 candidate 池：同 id 已存在则更新证据（不降级 active/retired 的状态）。"""
    idx = {e["id"]: e for e in store.get("experiences", [])}
    for c in candidates:
        if c["id"] in idx:
            e = idx[c["id"]]
            if e.get("locked") or e.get("source") == "human":
                continue                      # 人锁定/手写的经验，回路不得静默改写
            e["evidence"] = c["evidence"]
            e["text"] = c["text"]
            e["updated_at"] = c["updated_at"]
        else:
            store.setdefault("experiences", []).append(c)
            idx[c["id"]] = c
    return store


# --- 门控：candidate → active（shadow A/B 达标）---------------------------------
def graduate(store, ab_results):
    """shadow A/B：对最近 PR 比较"注入该经验 vs 不注入"的采纳率，lift 达标且样本足 → 转 active。
    ab_results: {finding_type: {with_seen, with_adopted, without_seen, without_adopted}}。
    A/B 的真实跑批（需真实 PR + PR-Agent）在你的环境做；本函数只做达标【判定】。"""
    graduated = []
    for e in store.get("experiences", []):
        if e["status"] != "candidate":
            continue
        ab = ab_results.get(e["finding_type"])
        if not ab:
            continue
        ws, wa = ab.get("with_seen", 0), ab.get("with_adopted", 0)
        os_, oa = ab.get("without_seen", 0), ab.get("without_adopted", 0)
        if ws < GRADUATE_MIN_SAMPLES or os_ < GRADUATE_MIN_SAMPLES:
            continue
        lift = (wa / ws) - (oa / os_)
        if lift >= GRADUATE_MIN_LIFT:
            e["status"] = "active"
            e["evidence"]["ab_lift"] = round(lift, 2)
            e["updated_at"] = int(time.time())
            graduated.append(e["id"])
    return graduated


# --- 退役：active → retired（govern 式，前提不再成立）---------------------------
def retire(store, calib_agg):
    """active 经验的前提若不再成立则退役（沿 govern 思路）：
      suppress（"这类是噪声"）—— 若该类型采纳率回升到 emphasize 阈值以上 → 前提不再成立，退役；
      emphasize（"这类有价值"）—— 若该类型采纳率跌破 RETIRE_ADOPT_MAX → 前提不再成立，退役。"""
    by_rule = calib_agg.get("by_rule") or {}
    retired = []
    for e in store.get("experiences", []):
        if e["status"] != "active":
            continue
        if e.get("locked"):
            continue                          # 人锁定的经验不自动退役
        v = by_rule.get(e["finding_type"])
        if not v or v.get("fires", 0) < RETIRE_MIN_FIRES:
            continue
        adopt = v.get("adoption_rate")
        if adopt is None:
            adopt = v.get("changes_requested_rate")
        if adopt is None:
            continue
        gone = (e["kind"] == "suppress" and adopt >= EMPHASIZE_ADOPT_MIN) or \
               (e["kind"] == "emphasize" and adopt <= RETIRE_ADOPT_MAX)
        if gone:
            e["status"] = "retired"
            e["updated_at"] = int(time.time())
            retired.append(e["id"])
    return retired


def disable(store, exp_id):
    """人工单条停用（→retired），可回退。每条经验留来源/证据，便于抽检与回退。"""
    for e in store.get("experiences", []):
        if e["id"] == exp_id:
            e["status"] = "retired"
            e["updated_at"] = int(time.time())
            return True
    return False


# --- 注入：active 经验 → PR-Agent extra_instructions（只建议、不进闸）-------------
def _resolve_conflicts(active):
    """同一 仓·栈·发现类型 不能既 emphasize 又 suppress：保留 updated_at 较新的一条（I3）。"""
    by = {}
    for e in active:
        k = (e.get("repo", ""), e.get("stack", ""), e.get("finding_type"))
        if k not in by or e.get("updated_at", 0) >= by[k].get("updated_at", 0):
            by[k] = e
    keep = {id(v) for v in by.values()}
    return [e for e in active if id(e) in keep]


def render_injection(store):
    """把 active 经验渲染成注入 PR-Agent 的 extra_instructions 文本。
    仅 active；candidate/retired 不注入。输出纯指令文本——只影响 PR-Agent 的建议，
    不触碰确定性 contract_check / 总闸（评审与合入闸的边界）。"""
    active = _resolve_conflicts([e for e in store.get("experiences", []) if e["status"] == "active"])
    if not active:
        return ""
    lines = ["# Learned review experience (repo-specific, advisory only — do not gate merges):"]
    for e in active:
        lines.append(f"- {e['text']}")
    return "\n".join(lines)


def active_types(store):
    """当前 active 经验的 finding_type 列表——即本轮评审会被注入（render_injection）的类型。
    供 orchestrator 写入 result marker，为未来 shadow A/B 采纳率分臂采集留接口。"""
    return [e.get("finding_type") for e in (store or {}).get("experiences", [])
            if e.get("status") == "active" and e.get("finding_type")]


def active_ids(store):
    """当前 active 经验的 id 列表——供 orchestrator 写入 result marker 的 injected_experience_ids，
    使坏经验可【单条】归因与回退（类型级的 active_types 只能归因到类型，见数据采集设计 取舍 2）。"""
    return [e.get("id") for e in (store or {}).get("experiences", [])
            if e.get("status") == "active" and e.get("id")]

