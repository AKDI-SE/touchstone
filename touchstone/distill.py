#!/usr/bin/env python3
# ============================================================================
# touchstone/distill.py —— 经验蒸馏（计数式 + TF-GRPO 语义优势，可插拔分发）
# ----------------------------------------------------------------------------
# 从 learning_loop 拆出（模块职责单一化，第三轮工程化加固）。本模块只管经验怎么
# 【产生】：计数式蒸馏（distill_candidates，无需大模型）；TF-GRPO 语义优势蒸馏
# （_distill_via_llm，arXiv 2510.08191：分组 rollout → 组内奖励对比 → LLM 蒸馏差异，
#  需参数冻结的旗舰模型端点）；distill(ctx, name) 按名分发 + register_distiller 注册自有实现。
# 产出一律是 status=candidate 的候选——激活/退役等生命周期在 experience_store.py。
# ============================================================================

import json
import os
import re
import sys
import time

from touchstone.experience_store import (_exp_id, _is_review_type,           # noqa: F401
                                         _protected_types, render_injection,
                                         SUPPRESS_ADOPT_MAX, EMPHASIZE_ADOPT_MIN)
# 采纳率阈值的单一事实来源在 experience_store（入池与退役是同一对判据的镜像）；此处引用。

# --- 阈值 ---------------------------------------------------------------------
DISTILL_MIN_FIRES   = 8      # 命中样本下限，才考虑蒸馏成候选经验

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
        out.append({"id": _exp_id(ftype, kind, repo, stack), "repo": repo, "stack": stack,
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
                pass    # 静默豁免：候选切片解析失败 → 继续尝试下一策略，
                        # 回退链走完仍失败时由调用方统一报错。
    return default


def _llm_json(llm, messages, default):
    """调用注入的 llm(messages)->str 并抽 JSON；任何失败都回退 default（鲁棒，离线可注入假 llm）。"""
    try:
        return _extract_json(llm(messages), default)
    except Exception as e:
        # 回退 default 是刻意设计（离线可注入假 llm），但静默会让"LLM 全程没调通"不可见——留痕
        print(f"[learning_loop] LLM 调用失败，回退默认值: {e}", file=sys.stderr)
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
    rewards = group["rewards"]
    if len(rewards) < 2 or len({round(r, 6) for r in rewards}) < 2:
        return []                                  # 退化组：组内奖励无差异，对比无意义（I4）
    # strict=True：outputs 与 rewards 同长是 rollout 构造不变式，违反应显式暴露而非静默截断
    ranked = sorted(zip(group["outputs"], rewards, strict=True), key=lambda x: -x[1])
    payload = {"pr_id": pr.get("pr_id"),
               "reviews_by_reward": [{"reward": round(rw, 2), "review": rv} for rv, rw in ranked]}
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
        out.append({"id": _exp_id(ftype, kind, repo, stack), "repo": repo, "stack": stack,
                    "finding_type": ftype, "kind": kind, "text": text.strip(),
                    "evidence": {"tfgrpo": True, "group_rewards": [round(x, 2) for x in rewards],
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
    base_active = [e for e in (store or {}).get("experiences", []) if e.get("status") == "active"]
    acc = {}
    for _ in range(max(1, epochs)):
        # 每轮用「已有 active + 本轮已蒸出候选」重渲染 E，下一轮在更新后的 E 上 rollout（I2）
        cond = {"experiences": base_active + [dict(c, status="active") for c in acc.values()]}
        experience_text = render_injection(cond)
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


def _flagship_configured():
    """旗舰模型端点是否就绪（TF-GRPO 生成/内省用）。缺则自动回退计数式蒸馏。"""
    return bool(os.environ.get("LLM_BASE_URL") and os.environ.get("LLM_API_KEY")
                and (os.environ.get("TOUCHSTONE_FLAGSHIP_MODEL") or os.environ.get("LLM_MODEL")))

