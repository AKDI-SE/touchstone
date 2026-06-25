#!/usr/bin/env python3
# ============================================================================
# touchstone/learning_loop.py  ——  自进化评审学习回路（Phase 2）
#   设计：docs/learning-loop-design.html
#
# 一条【无训练、无权重、离线周期】的回路：把"人最终采纳/忽略了什么"蒸馏成自然语言
# 经验，回注 PR-Agent 的 extra_instructions —— 让评审随真实使用自我改进。
#
#   奖励来源 = calibrate.aggregate(records)  （复用；by_rule/by_agent 的 fires/adoption_rate）
#   经验进化 = 计数式蒸馏（distill_candidates，无需大模型）；或 TF-GRPO 语义优势蒸馏
#              （_distill_via_llm，已实现；取自 arXiv 2510.08191，生产需一个参数冻结的旗舰模型端点）
#   蒸馏器可插拔 = distill(ctx, name) 按名分发；register_distiller 注册自有实现（不必改本文件）；
#                  _distill_via_llm 的 rollout/score/distill_advantage 三步亦可注入替换。
#   门控/退役 = graduate（shadow A/B 达标）+ retire（govern 式，前提不再成立即退役）
#   注入     = render_injection(active 经验) → PR-Agent extra_instructions
#
# 两条铁律（来自设计中对坑的应对）：
#   ① 评审与学习解耦：评审路径只【读】经验库；学习是离线 cron，挂了不影响评审（用上一版经验）。
#   ② 经验只调"建议"、绝不进"合入闸"：只对 PR-Agent 源的发现(PRA-*/pr-agent:*)产经验；
#      确定性 contract_check 不受经验影响、永不进经验库（作固定基准，坑 2b）。
#   ③ 新经验默认不注入：先入 candidate 池，经 shadow A/B 达标才转 active（坑 3）。
# ============================================================================

import json
import os
import re
import time

# --- 阈值（保守：宁可慢些演进，不轻易注入/退役）---------------------------------
DISTILL_MIN_FIRES   = 8      # 命中样本下限，才考虑蒸馏成候选经验
SUPPRESS_ADOPT_MAX  = 0.20   # 采纳率低于此 → "别挑"（suppress）候选
EMPHASIZE_ADOPT_MIN = 0.80   # 采纳率高于此 → "该挑"（emphasize）候选
GRADUATE_MIN_SAMPLES = 20     # shadow A/B 两臂各需的样本下限
GRADUATE_MIN_LIFT   = 0.10   # 注入臂采纳率 - 不注入臂 ≥ 此 → 候选达标转 active
RETIRE_ADOPT_MAX    = 0.15   # active 经验对应类型采纳率跌破此（且复发）→ 退役（govern 式）

STORE_PATH = os.environ.get("TOUCHSTONE_EXPERIENCE", ".touchstone/experience.json")


# --- 经验库（JSON 产物，非服务）-------------------------------------------------
# experience: {id, repo, stack, finding_type, kind(suppress/emphasize),
#              text, evidence{fires,adoption}, status(candidate/active/retired),
#              source(human/tfgrpo/counting), locked(bool: 人锁定→回路不得改写/退役),
#              source_prs[], created_at, updated_at}
def load_store(path=None):
    path = path or STORE_PATH            # 调用时取，env/monkeypatch 在 import 后改也能生效
    try:
        return json.load(open(path, encoding="utf-8"))
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


def _exp_id(finding_type, kind):
    return f"{kind}:{finding_type}"


def _protected_types():
    """人立的红线：这些 finding_type 永不许被学习回路 suppress（哪怕历史上人总忽略）。
    来自 env TOUCHSTONE_PROTECTED_TYPES（逗号分隔），如 PRA-SECURITY,PRA-POSSIBLE_BUG。"""
    return {t.strip() for t in os.environ.get("TOUCHSTONE_PROTECTED_TYPES", "").split(",") if t.strip()}


# --- 蒸馏：calibrate 奖励 → 候选经验（训练-free 计数式）--------------------------
def distill_candidates(calib_agg, repo="", stack=""):
    """从 calibrate.aggregate 的 by_rule 统计蒸馏候选经验（无 LLM、无权重）。
    低采纳→suppress（别挑）、高采纳→emphasize（该挑）。只对 PR-Agent 源类型；确定性 contract 类型被跳过。
    更丰富的 TF-GRPO 语义优势蒸馏见 _distill_via_llm（已实现，需旗舰模型端点）。"""
    now = int(time.time())
    protected = _protected_types()
    out = []
    for ftype, v in (calib_agg.get("by_rule") or {}).items():
        if not _is_review_type(ftype):
            continue                      # 确定性 contract 类型不进经验（固定基准）
        fires = v.get("fires", 0)
        adopt = v.get("adoption_rate")
        if adopt is None:
            adopt = v.get("changes_requested_rate")
        if fires < DISTILL_MIN_FIRES or adopt is None:
            continue
        if adopt <= SUPPRESS_ADOPT_MAX:
            if ftype in protected:
                continue                      # 红线：受保护类型永不 suppress
            kind, text = "suppress", (f"Deprioritize {ftype}-type suggestions in this repo; "
                                      f"historically dismissed (adoption {adopt:.0%} over {fires}).")
        elif adopt >= EMPHASIZE_ADOPT_MIN:
            kind, text = "emphasize", (f"Emphasize {ftype}-type suggestions in this repo; "
                                       f"historically valued (adoption {adopt:.0%} over {fires}).")
        else:
            continue
        out.append({"id": _exp_id(ftype, kind), "repo": repo, "stack": stack,
                    "finding_type": ftype, "kind": kind, "text": text,
                    "evidence": {"fires": fires, "adoption": round(adopt, 2)},
                    "status": "candidate", "source": "counting", "locked": False,
                    "source_prs": [], "created_at": now, "updated_at": now})
    return out


# --- TF-GRPO：分组 rollout + 组内语义优势 → 候选经验 -----------------------------
#   取自 Training-Free GRPO（arXiv 2510.08191）：策略（PR-Agent 旗舰模型）冻结不动，
#   用“组内相对语义优势”取代数值优势/梯度，把经验积累成注入提示词的 token prior。
#   落到 PR 评审：对历史已合 PR（带人审裁决的最小真值集）分组生成评审、离线打分、
#   旗舰模型内省高分 vs 低分 → 候选经验。无梯度、无权重。
TFGRPO_GROUP_SIZE = int(os.environ.get("TOUCHSTONE_TFGRPO_G", "4"))
_W_NOISE = float(os.environ.get("TOUCHSTONE_W_NOISE", "0.5"))   # 噪声（人忽略却挑了）扣分权重，人可调
_W_MISS  = float(os.environ.get("TOUCHSTONE_W_MISS", "0.25"))   # 漏报（人采纳却没挑）扣分权重，人可调


def _finding_types(review):
    return {(f.get("finding_type") or f.get("rule_id")) for f in (review or [])
            if (f.get("finding_type") or f.get("rule_id"))}


def score_review(review, human_adopted, *, w_noise=None, w_miss=None):
    """② 按人审真值给一份评审离线打分（纯函数、不需大模型，复用 calibrate 的命中/噪声口径）。
    review: 一次 rollout 的发现列表（每个含 finding_type）；human_adopted: 人最终采纳的发现类型集合。
    奖励 = 命中(真阳) − w_noise·噪声(假阳) − w_miss·漏报。权重缺省取 _W_NOISE/_W_MISS（env 可配、人可调）。"""
    w_noise = _W_NOISE if w_noise is None else w_noise
    w_miss = _W_MISS if w_miss is None else w_miss
    adopted = set(human_adopted or [])
    seen = _finding_types(review)
    hits = len(seen & adopted)
    noise = len(seen - adopted)
    miss = len(adopted - seen)
    return hits - w_noise * noise - w_miss * miss


def _extract_json(text, default):
    """从 LLM 文本里抽取 JSON（容忍 ```json``` 包裹与前后说明）；失败返回 default。"""
    if not text:
        return default
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    raw = m.group(1) if m else text
    for opener, closer in (("[", "]"), ("{", "}")):
        i, j = raw.find(opener), raw.rfind(closer)
        if 0 <= i < j:
            try:
                return json.loads(raw[i:j + 1])
            except json.JSONDecodeError:
                pass
    return default


def _llm_json(llm, messages, default):
    """调用注入的 llm(messages)->str 并抽 JSON；任何失败都回退 default（鲁棒，离线可注入假 llm）。"""
    try:
        return _extract_json(llm(messages), default)
    except Exception:
        return default


def rollout_reviews(pr, experience_text, llm, group_size=TFGRPO_GROUP_SIZE):
    """① 在当前经验库 E（experience_text）下，让冻结旗舰模型对一个历史 PR 生成 group_size 份评审。
    每份是发现列表 [{finding_type, file?, note?}]。llm(messages)->str 由调用方注入
    （生产=参数冻结的旗舰模型端点；测试=确定性假 llm）；变体序号入提示以促组内多样性。"""
    sys_p = ("You are a senior code reviewer. Given a PR and the repo's learned review experience, "
             "list the review findings you would raise. Respond ONLY as a JSON array of objects "
             '{"finding_type": "PRA-...", "file": "...", "note": "..."}.')
    out = []
    for variant in range(group_size):
        user = (f"# Repo experience (advisory)\n{experience_text or '(none)'}\n\n"
                f"# PR\nid={pr.get('pr_id')} repo={pr.get('repo')} stack={pr.get('stack')}\n"
                f"{pr.get('summary', '')}\n\n# Diff\n{pr.get('diff', '')}\n\n"
                f"(variant {variant}: explore a distinct angle)")
        rv = _llm_json(llm, [{"role": "system", "content": sys_p},
                             {"role": "user", "content": user}], default=[])
        out.append(rv if isinstance(rv, list) else [])
    return out


def distill_semantic_advantage(pr, group, llm, repo="", stack=""):
    """③ 组内相对语义优势：把一组带分数的评审交旗舰模型内省——高分挑对了什么、低分挑偏/漏了什么——
    按 仓·栈·发现类型 提炼候选经验。返回与 distill_candidates 同 schema 的 Experience(candidate)；
    只保留 PR-Agent 源类型（确定性 contract 类型永不进经验，坑 2b）。"""
    ranked = sorted(zip(group["outputs"], group["rewards"]), key=lambda x: -x[1])
    payload = {"pr_id": pr.get("pr_id"),
               "high_reward_reviews": [r for r, _ in ranked[:2]],
               "low_reward_reviews": [r for r, _ in ranked[-2:]],
               "rewards": [round(x, 2) for x in group["rewards"]]}
    sys_p = ("Compare the higher-reward reviews against the lower-reward ones for this PR and "
             "distill repo-specific review experience: which finding_type to EMPHASIZE (humans "
             "act on) and which to SUPPRESS (humans dismiss). Respond ONLY as a JSON array of "
             '{"finding_type": "PRA-...", "kind": "emphasize|suppress", "text": "<one imperative sentence>"}.')
    user = f"# PR\n{pr.get('summary', '')}\n\n# Group\n{json.dumps(payload, ensure_ascii=False)}"
    items = _llm_json(llm, [{"role": "system", "content": sys_p},
                            {"role": "user", "content": user}], default=[])
    now, out = int(time.time()), []
    protected = _protected_types()
    for it in items if isinstance(items, list) else []:
        ftype = (it or {}).get("finding_type", "")
        kind = (it or {}).get("kind")
        text = (it or {}).get("text")
        if not ftype or kind not in ("emphasize", "suppress") or not text:
            continue
        if not _is_review_type(ftype):
            continue                          # 确定性类型不进经验（固定基准，坑 2b）
        if kind == "suppress" and ftype in protected:
            continue                          # 红线：受保护类型永不 suppress
        out.append({"id": _exp_id(ftype, kind), "repo": repo, "stack": stack,
                    "finding_type": ftype, "kind": kind, "text": text.strip(),
                    "evidence": {"tfgrpo": True, "group_rewards": payload["rewards"],
                                 "pr": pr.get("pr_id")},
                    "status": "candidate", "source": "tfgrpo", "locked": False,
                    "source_prs": [pr.get("pr_id")] if pr.get("pr_id") else [],
                    "created_at": now, "updated_at": now})
    return out


def _flagship_llm():
    """默认旗舰模型调用器 llm(messages)->str（openai SDK，参数冻结）。仅真实运行时构造；
    缺 env / 缺 openai 时清晰报错。测试一律注入假 llm，不走此处。"""
    base_url = os.environ.get("LLM_BASE_URL")
    api_key = os.environ.get("LLM_API_KEY")
    model = os.environ.get("TOUCHSTONE_FLAGSHIP_MODEL") or os.environ.get("LLM_MODEL")
    if not (base_url and api_key and model):
        raise RuntimeError("TF-GRPO 需要旗舰模型端点：设置 LLM_BASE_URL / LLM_API_KEY / TOUCHSTONE_FLAGSHIP_MODEL")
    import openai
    client = openai.OpenAI(base_url=base_url, api_key=api_key, timeout=120)

    def _call(messages):
        resp = client.chat.completions.create(model=model, messages=messages, temperature=0.7)
        return resp.choices[0].message.content or ""
    return _call


def _distill_via_llm(ground_truth, store, llm=None, *, group_size=TFGRPO_GROUP_SIZE,
                     epochs=1, repo="", stack="",
                     rollout=None, score=None, distill_advantage=None):
    """TF-GRPO 入口（实现）。机制设计见 docs/learning-loop-design.html §3。
    ground_truth: 最小真值集 [{pr_id, repo, stack, summary, diff, human_adopted:[finding_type]}]
                  —— 历史已合 PR + 人审裁决（生产由 calibrate 从 GitHub 重建）。
    store: 当前经验库（用其 active 经验 render 成 E 来 condition rollout）。
    llm:   注入的 llm(messages)->str；缺省用 _flagship_llm()（参数冻结的旗舰模型端点）。
    多轮(epochs)对每个 PR：① rollout G 份评审 → ② 按人审真值离线打分 → ③ 旗舰模型内省出组内语义优势
    → 候选经验。策略全程冻结、无梯度无权重。返回候选经验（caller 再 merge_candidates → graduate 门控）。
    可注入替换其中任一步（默认用内置）：
      rollout(pr, E_text, llm, group_size) -> [review]
      score(review, human_adopted) -> float
      distill_advantage(pr, group, llm, repo, stack) -> [Experience(candidate)]"""
    llm = llm or _flagship_llm()
    rollout = rollout or rollout_reviews
    score = score or score_review
    distill_advantage = distill_advantage or distill_semantic_advantage
    experience_text = render_injection(store or {"experiences": []})
    acc = {}
    for _ in range(max(1, epochs)):
        for pr in ground_truth or []:
            reviews = rollout(pr, experience_text, llm, group_size)
            rewards = [score(o, pr.get("human_adopted")) for o in reviews]
            group = {"outputs": reviews, "rewards": rewards}
            for c in distill_advantage(pr, group, llm,
                                                pr.get("repo", repo), pr.get("stack", stack)):
                prev = acc.get(c["id"])
                if prev:
                    prev["source_prs"] = sorted(set(prev["source_prs"]) | set(c["source_prs"]))
                    prev["updated_at"] = c["updated_at"]
                else:
                    acc[c["id"]] = c
    return list(acc.values())


# --- 蒸馏器分发：按名选实现 + 注册自定义（照搬 review_provider 的分发风格）---------------
#   蒸馏上下文 ctx（统一入参，各实现按需取用）：{calib_agg, ground_truth, store, llm, repo, stack}
def _counting_distiller(ctx):
    return distill_candidates(ctx.get("calib_agg") or {}, ctx.get("repo", ""), ctx.get("stack", ""))


def _tfgrpo_distiller(ctx):
    return _distill_via_llm(ctx.get("ground_truth") or [], ctx.get("store") or {"experiences": []},
                            ctx.get("llm"), repo=ctx.get("repo", ""), stack=ctx.get("stack", ""))


_DISTILLERS = {"counting": _counting_distiller, "tfgrpo": _tfgrpo_distiller}


def register_distiller(name, fn):
    """注册自定义蒸馏器 fn(ctx)->[Experience]。外部 `import learning_loop` 后调用即可，不必改本文件；
    随后用 env TOUCHSTONE_DISTILLER=name 或 distill(ctx, name) 选用。"""
    _DISTILLERS[name] = fn


def distill(ctx, name=None):
    """按名分发到蒸馏器，返回候选经验（与 distill_candidates 同 schema，交 merge_candidates → graduate）。
    name 缺省取 env TOUCHSTONE_DISTILLER；再缺省：有真值集→tfgrpo，否则 counting。
    内置 counting / tfgrpo；自定义实现经 register_distiller 注册后即可按名选用。"""
    name = name or os.environ.get("TOUCHSTONE_DISTILLER") or ("tfgrpo" if ctx.get("ground_truth") else "counting")
    fn = _DISTILLERS.get(name)
    if not fn:
        raise ValueError(f"未知蒸馏器: {name!r}（已注册: {sorted(_DISTILLERS)}）")
    return fn(ctx)


def seed_experience(store, finding_type, kind, text, *, repo="", stack="",
                    status="active", locked=True):
    """人手写一条经验当种子（source=human）。默认直接 active 且 locked（人是权威，学习回路
    不得静默改写或退役）；传 locked=False 可交回路管理。用于冷启动、注入团队领域知识与红线。"""
    if kind not in ("emphasize", "suppress"):
        raise ValueError("kind 必须是 emphasize 或 suppress")
    now = int(time.time())
    exp = {"id": _exp_id(finding_type, kind), "repo": repo, "stack": stack,
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
        if not v or v.get("fires", 0) < DISTILL_MIN_FIRES:
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
def render_injection(store):
    """把 active 经验渲染成注入 PR-Agent 的 extra_instructions 文本。
    仅 active；candidate/retired 不注入。输出纯指令文本——只影响 PR-Agent 的建议，
    不触碰确定性 contract_check / 总闸（评审与合入闸的边界）。"""
    active = [e for e in store.get("experiences", []) if e["status"] == "active"]
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


def main():
    """离线 cron 入口：读经验库 →（外部已备好 calib_agg / ab_results）→ 蒸馏/达标/退役 → 落盘。
    真实编排（取 calibrate 记录、跑 A/B）在 CI/cron 脚本里组装；此处给最小可跑骨架。"""
    import sys
    store = load_store()
    agg_path = os.environ.get("TOUCHSTONE_CALIB_AGG")
    if not agg_path:
        sys.exit("设置 TOUCHSTONE_CALIB_AGG=calibrate 聚合结果(JSON) 路径")
    agg = json.load(open(agg_path, encoding="utf-8"))
    gt_path = os.environ.get("TOUCHSTONE_TFGRPO_GROUNDTRUTH")
    ctx = {"calib_agg": agg, "store": store, "repo": os.environ.get("REPO_DIR", ""),
           "ground_truth": json.load(open(gt_path, encoding="utf-8")) if gt_path else None}
    cands = distill(ctx)          # 按名分发：env TOUCHSTONE_DISTILLER；默认 有真值集→tfgrpo 否则 counting
    merge_candidates(store, cands)
    # candidate → active（shadow A/B 达标）。ab_results 由 env TOUCHSTONE_AB_RESULTS 指向的 JSON 提供
    # （calibrate 按 marker 的 injected_types 切臂后产出——该采集到位前，candidate 不自动激活，
    # 注入由人写 seed 驱动；这是「最小接通 + 诚实」：graduate 已在管线中，但不伪造数据）。
    ab_path = os.environ.get("TOUCHSTONE_AB_RESULTS")
    if ab_path and os.path.exists(ab_path):
        try:
            grad = graduate(store, json.load(open(ab_path, encoding="utf-8")))
            print(f"[learn] graduate 达标转 active：{len(grad)} 条 {grad}")
        except (OSError, json.JSONDecodeError) as e:
            print(f"[learn] graduate 跳过（A/B 数据无效：{e}）", file=sys.stderr)
    else:
        print("[learn] graduate 跳过（无 A/B 数据；当前注入由人写 seed 驱动，自动达标需积累样本）")
    retire(store, agg)
    save_store(store)
    print(f"[learn] 经验库：{sum(1 for e in store['experiences'] if e['status']=='active')} active / "
          f"{len(store['experiences'])} 总")


if __name__ == "__main__":
    main()
