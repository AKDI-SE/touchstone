"""自进化评审学习回路（Phase 2）：经验库 + 训练-free 蒸馏 + shadow达标 + 退役 + 注入。
全离线、纯函数；TF-GRPO 的 rollout/语义优势内省以注入的假 llm 离线覆盖，真实 A/B 跑批在你的环境做。"""
import json
import os

import pytest
from touchstone import learning_loop as L
from touchstone import ground_truth as GT


def _agg(by_rule):
    return {"by_rule": by_rule, "by_agent": {}}


# 一份贴近 calibrate.aggregate 的奖励：含 PR-Agent 类型与一个确定性锚(SCOPE-001)
_REWARD = _agg({
    "PRA-POSSIBLE_BUG": {"fires": 12, "adoption_rate": 0.90},   # 高采纳 → emphasize
    "PRA-MAINTAINABILITY": {"fires": 15, "adoption_rate": 0.10},  # 低采纳 → suppress
    "PRA-TYPO": {"fires": 3, "adoption_rate": 0.0},             # 样本不足 → 跳过
    "SCOPE-001": {"fires": 20, "adoption_rate": 0.05},          # 确定性锚 → 永不进经验
})


# ---------------- 库读写 ----------------
def test_store_roundtrip(tmp_path):
    p = str(tmp_path / "exp.json")
    L.save_store({"experiences": [{"id": "x", "status": "active"}]}, p)
    assert L.load_store(p)["experiences"][0]["id"] == "x"
    # 不存在 → 空库
    assert L.load_store(str(tmp_path / "none.json")) == {"experiences": []}


def test_load_store_non_dict_or_bad_experiences_falls_back_safe(tmp_path):
    """A3-F3：存档是合法 JSON 但顶层非 dict（list/标量）或 experiences 非 list（旧格式/损坏/手改），
    json.loads 照样成功并原样返回——下游 render_injection 的 store.get(...) 抛 AttributeError 崩整个
    学习回路注入。load_store 是唯一加载入口，应在边界 fail-safe：形状不对即回落 {'experiences': []}。"""
    p = tmp_path / "store.json"
    # 顶层 list（修复前：load_store 返 list → render_injection 崩 AttributeError: 'list' has no .get）
    p.write_text('[{"id":"x"}]', encoding="utf-8")
    store = L.load_store(str(p))
    assert store == {"experiences": []} and isinstance(store, dict)
    assert L.render_injection(store) == ""                       # 下游不再崩
    # 标量 JSON（json.loads("123") -> int）
    p.write_text("123", encoding="utf-8")
    assert L.load_store(str(p)) == {"experiences": []}
    # dict 但 experiences 非 list（迭代崩的姊妹情形，一并 fail-safe）
    p.write_text('{"experiences":"nope"}', encoding="utf-8")
    assert L.load_store(str(p)) == {"experiences": []}
    # 正常 dict 不受影响（回归）
    p.write_text('{"experiences":[{"id":"x","status":"active"}]}', encoding="utf-8")
    assert L.load_store(str(p))["experiences"][0]["id"] == "x"


# ---------------- 边界：确定性锚不进经验 ----------------
def test_is_review_type_excludes_contract_anchor():
    assert L._is_review_type("PRA-POSSIBLE_BUG")
    assert L._is_review_type("pr-agent:suggestion")
    assert not L._is_review_type("SCOPE-001")        # contract 锚
    assert not L._is_review_type("contract-check")
    assert not L._is_review_type("TEST-001")


# ---------------- 蒸馏（训练-free 计数）----------------
def test_distill_emphasize_and_suppress_skip_anchor_and_lowfire():
    cands = L.distill_candidates(_REWARD, repo="o/r")
    by = {c["finding_type"]: c for c in cands}
    assert by["PRA-POSSIBLE_BUG"]["kind"] == "emphasize"
    assert by["PRA-MAINTAINABILITY"]["kind"] == "suppress"
    assert "SCOPE-001" not in by          # 确定性锚被跳过（坑 2b）
    assert "PRA-TYPO" not in by           # fires<下限
    assert all(c["status"] == "candidate" for c in cands)   # 新经验默认 candidate（坑 3）


def test_distill_midrange_yields_nothing():
    cands = L.distill_candidates(_agg({"PRA-X": {"fires": 30, "adoption_rate": 0.5}}))
    assert cands == []


# ---------------- 并入候选池（去重） ----------------
def test_merge_candidates_dedup_updates_evidence():
    store = {"experiences": []}
    L.merge_candidates(store, L.distill_candidates(_REWARD))
    n1 = len(store["experiences"])
    # 再并一次（证据更新、不新增、不改状态）
    L.merge_candidates(store, L.distill_candidates(_REWARD))
    assert len(store["experiences"]) == n1
    assert all(e["status"] == "candidate" for e in store["experiences"])


# ---------------- 门控：shadow A/B 达标 candidate→active ----------------
def test_graduate_on_sufficient_lift_and_samples():
    store = {"experiences": []}
    L.merge_candidates(store, L.distill_candidates(_REWARD))
    ab = {"PRA-MAINTAINABILITY": {"with_seen": 25, "with_adopted": 20,    # 0.80
                                  "without_seen": 25, "without_adopted": 15},  # 0.60 → lift 0.20
          "PRA-POSSIBLE_BUG": {"with_seen": 8, "with_adopted": 8,         # 样本不足
                               "without_seen": 8, "without_adopted": 4}}
    grad = L.graduate(store, ab)
    st = {e["finding_type"]: e["status"] for e in store["experiences"]}
    assert "PRA-MAINTAINABILITY" in [s.split(":")[-1] for s in grad]
    assert st["PRA-MAINTAINABILITY"] == "active"
    assert st["PRA-POSSIBLE_BUG"] == "candidate"     # 样本不足 → 不达标


def test_graduate_low_lift_stays_candidate():
    store = {"experiences": [{"id": "suppress:PRA-A", "finding_type": "PRA-A", "kind": "suppress",
                              "status": "candidate", "evidence": {}}]}
    ab = {"PRA-A": {"with_seen": 30, "with_adopted": 16, "without_seen": 30, "without_adopted": 15}}  # lift~0.03
    assert L.graduate(store, ab) == []
    assert store["experiences"][0]["status"] == "candidate"


# ---------------- 退役：前提不再成立 ----------------
def test_retire_when_premise_no_longer_holds():
    store = {"experiences": [
        {"id": "emphasize:PRA-E", "finding_type": "PRA-E", "kind": "emphasize", "status": "active", "evidence": {}},
        {"id": "suppress:PRA-S", "finding_type": "PRA-S", "kind": "suppress", "status": "active", "evidence": {}},
    ]}
    agg = _agg({"PRA-E": {"fires": 10, "adoption_rate": 0.10},   # emphasize 但采纳跌破 → 退役
                "PRA-S": {"fires": 10, "adoption_rate": 0.85}})  # suppress 但采纳回升 → 退役
    retired = L.retire(store, agg)
    assert set(retired) == {"emphasize:PRA-E", "suppress:PRA-S"}
    assert all(e["status"] == "retired" for e in store["experiences"])


def test_disable_single_experience():
    store = {"experiences": [{"id": "emphasize:PRA-Z", "status": "active"}]}
    assert L.disable(store, "emphasize:PRA-Z") is True
    assert store["experiences"][0]["status"] == "retired"
    assert L.disable(store, "nope") is False


# ---------------- bootstrap seed（冷启动辅助路径 c：高采纳 type 直接 active）----------------
def test_bootstrap_enabled_reads_env(monkeypatch):
    """bootstrap 总开关 env 解析：默认关 / 真值开 / 假值关。"""
    monkeypatch.delenv("TOUCHSTONE_BOOTSTRAP_SEED", raising=False)
    assert L._bootstrap_enabled() is False
    for v in ("1", "true", "yes", "on"):
        monkeypatch.setenv("TOUCHSTONE_BOOTSTRAP_SEED", v)
        assert L._bootstrap_enabled() is True
    for v in ("0", "false", "no", "off", ""):
        monkeypatch.setenv("TOUCHSTONE_BOOTSTRAP_SEED", v)
        assert L._bootstrap_enabled() is False


def test_bootstrap_seeds_active_for_high_adoption(monkeypatch):
    """env 开 + 高采纳（fires>=15 且 adoption>=0.85）→ 产 active emphasize（source=bootstrap, locked=False）。"""
    monkeypatch.setenv("TOUCHSTONE_BOOTSTRAP_SEED", "1")
    agg = _agg({"PRA-HIGH": {"fires": 20, "adoption_rate": 0.90},       # 达标 → 产
                "PRA-LOW-ADOPT": {"fires": 20, "adoption_rate": 0.50},  # 采纳不足 → 跳
                "PRA-LOW-FIRES": {"fires": 10, "adoption_rate": 0.90},  # fires 不足 → 跳
                "SCOPE-001": {"fires": 30, "adoption_rate": 0.95}})     # 确定性锚 → 跳
    store = {"experiences": []}
    produced = L.bootstrap_from_calibrate(agg, store, repo="o/r", stack="python")
    assert produced == ["emphasize:o/r:python:PRA-HIGH"]
    e = store["experiences"][0]
    assert e["status"] == "active" and e["kind"] == "emphasize"
    assert e["source"] == "bootstrap" and e["locked"] is False
    assert len(store["experiences"]) == 1


def test_bootstrap_skips_protected_and_existing(monkeypatch):
    """protected_types 跳过（人立红线不碰）；已有 emphasize 经验的 type 跳过——不绕 graduate 把
    candidate 直接提成 active（坑 3 门控纪律）。"""
    monkeypatch.setenv("TOUCHSTONE_BOOTSTRAP_SEED", "1")
    monkeypatch.setenv("TOUCHSTONE_PROTECTED_TYPES", "PRA-PROTECTED")
    try:
        agg = _agg({"PRA-PROTECTED": {"fires": 20, "adoption_rate": 0.90},  # protected → 跳
                    "PRA-EXISTING": {"fires": 20, "adoption_rate": 0.90},   # 已有 candidate → 跳
                    "PRA-NEW": {"fires": 20, "adoption_rate": 0.90}})       # 全新 → 产
        store = {"experiences": [{"id": "emphasize:o/r:python:PRA-EXISTING",
                                  "finding_type": "PRA-EXISTING", "kind": "emphasize",
                                  "status": "candidate", "evidence": {}}]}
        produced = L.bootstrap_from_calibrate(agg, store, repo="o/r", stack="python")
        assert produced == ["emphasize:o/r:python:PRA-NEW"]
        existing = next(e for e in store["experiences"] if e["finding_type"] == "PRA-EXISTING")
        assert existing["status"] == "candidate"     # 没被提成 active（不绕 graduate）
        assert len(store["experiences"]) == 2         # 原 candidate + 1 新 active
    finally:
        monkeypatch.delenv("TOUCHSTONE_PROTECTED_TYPES", raising=False)


def test_bootstrap_disabled_by_default(monkeypatch):
    """env 默认关 → 无产出（零行为变化）。"""
    monkeypatch.delenv("TOUCHSTONE_BOOTSTRAP_SEED", raising=False)
    agg = _agg({"PRA-HIGH": {"fires": 20, "adoption_rate": 0.90}})
    assert L.bootstrap_from_calibrate(agg, {"experiences": []}) == []


def test_main_bootstraps_active_before_merge_when_enabled(tmp_path, monkeypatch):
    """main 在 merge_candidates【前】调 bootstrap（env 开时）：高采纳全新 type 直接 seed active，
    随后 distill 同 id candidate 经 merge 补 evidence 但不降级 active。env 关时 distill 只产 candidate 无 active。"""
    store_path = tmp_path / "exp.json"
    (tmp_path / "agg.json").write_text(json.dumps({"aggregate": {"by_rule": {
        "PRA-HIGH": {"fires": 20, "adoption_rate": 0.90}}}}), encoding="utf-8")
    monkeypatch.setattr(L, "STORE_PATH", str(store_path))
    monkeypatch.setenv("TOUCHSTONE_CALIB_AGG", str(tmp_path / "agg.json"))
    monkeypatch.setenv("TOUCHSTONE_DISTILLER", "counting")
    # env 关 → distill 产 candidate，无 active
    store_path.write_text('{"experiences": []}', encoding="utf-8")
    monkeypatch.delenv("TOUCHSTONE_BOOTSTRAP_SEED", raising=False)
    L.main()
    exps = L.load_store(str(store_path))["experiences"]
    assert all(e["status"] != "active" for e in exps)
    # env 开 → bootstrap 在 merge 前产 active（merge 后仍 active）
    store_path.write_text('{"experiences": []}', encoding="utf-8")
    monkeypatch.setenv("TOUCHSTONE_BOOTSTRAP_SEED", "1")
    report = L.main()
    exps = L.load_store(str(store_path))["experiences"]
    e = next(x for x in exps if x["finding_type"] == "PRA-HIGH")
    assert e["status"] == "active" and e["source"] == "bootstrap"
    assert any("bootstrap_from_calibrate" in s for s in report["steps"])


def test_seed_experience_rejects_unknown_source():
    """source 只许 human/bootstrap，防误用新取值绕过 source 语义。"""
    with pytest.raises(ValueError):
        L.seed_experience({"experiences": []}, "PRA-X", "emphasize", "t", source="bogus")


# ---------------- 注入：只 active、不进闸 ----------------
def test_render_injection_only_active_no_anchor():
    store = {"experiences": [
        {"id": "suppress:PRA-MAINTAINABILITY", "finding_type": "PRA-MAINTAINABILITY",
         "kind": "suppress", "status": "active", "text": "Deprioritize PRA-MAINTAINABILITY-type suggestions ..."},
        {"id": "emphasize:PRA-CAND", "finding_type": "PRA-CAND", "kind": "emphasize",
         "status": "candidate", "text": "should not appear"},
    ]}
    out = L.render_injection(store)
    assert "PRA-MAINTAINABILITY" in out
    assert "should not appear" not in out          # candidate 不注入
    assert "advisory only" in out                  # 明确只建议、不进闸
    assert "SCOPE-001" not in out and "TEST-001" not in out   # 确定性锚永不出现
    # 空库 → 空注入
    assert L.render_injection({"experiences": []}) == ""


# ---------------- TF-GRPO：分组 rollout + 组内语义优势（实现，离线假 llm）----------------
def _fake_llm(messages):
    """确定性假旗舰模型：rollout 请求→固定评审；内省请求→固定候选经验（含一个确定性锚，应被剔除）。"""
    sysp = messages[0]["content"]
    user = messages[1]["content"] if len(messages) > 1 else ""
    if "list the review findings" in sysp:
        if "variant 0" in user:      # 各 variant 产出不同 → 组内奖励有差异（配合 I4 守卫）
            return ('[{"finding_type":"PRA-POSSIBLE_BUG","file":"a.py","note":"npe"},'
                    '{"finding_type":"PRA-TYPO","file":"a.py","note":"typo"}]')
        if "variant 1" in user:
            return '[{"finding_type":"PRA-POSSIBLE_BUG","file":"a.py","note":"npe"}]'
        return "[]"
    if "distill repo-specific review experience" in sysp:
        return ('```json\n[{"finding_type":"PRA-POSSIBLE_BUG","kind":"emphasize",'
                '"text":"Emphasize possible-bug findings in this repo."},'
                '{"finding_type":"SCOPE-001","kind":"suppress","text":"anchor must be excluded"}]\n```')
    return "[]"


def test_score_review_hits_noise_miss():
    r = [{"finding_type": "PRA-A"}, {"finding_type": "PRA-B"}]
    assert abs(L.score_review(r, ["PRA-A", "PRA-C"]) - 0.25) < 1e-9   # 命中1 − 噪声0.5 − 漏报0.25
    assert L.score_review([], ["PRA-A"]) == -0.25                     # 全漏报
    assert L.score_review(r, ["PRA-A", "PRA-B"]) == 2                 # 全命中、无噪声


def test_extract_json_fenced_and_bare():
    assert L._extract_json('```json\n[{"a":1}]\n```', None) == [{"a": 1}]
    assert L._extract_json('noise {"k":2} tail', None) == {"k": 2}
    assert L._extract_json("not json", "DEF") == "DEF"


def test_rollout_reviews_group_with_fake_llm():
    pr = {"pr_id": "1", "repo": "o/r", "stack": "py", "summary": "s", "diff": "d"}
    reviews = L.rollout_reviews(pr, "", _fake_llm, group_size=3)
    assert len(reviews) == 3
    assert {f["finding_type"] for f in reviews[0]} == {"PRA-POSSIBLE_BUG", "PRA-TYPO"}


def test_distill_semantic_advantage_excludes_anchor():
    pr = {"pr_id": "1", "repo": "o/r", "stack": "py"}
    group = {"outputs": [[{"finding_type": "PRA-POSSIBLE_BUG"}], [{"finding_type": "PRA-TYPO"}]],
             "rewards": [1.0, -0.5]}
    cands = L.distill_semantic_advantage(pr, group, _fake_llm, "o/r", "py")
    by = {c["finding_type"]: c for c in cands}
    assert by["PRA-POSSIBLE_BUG"]["kind"] == "emphasize"
    assert "SCOPE-001" not in by                                # 确定性锚被剔除（坑 2b）
    assert all(c["status"] == "candidate" for c in cands)       # 默认 candidate（坑 3）
    assert by["PRA-POSSIBLE_BUG"]["source_prs"] == ["1"]


def test_distill_via_llm_end_to_end_then_graduate():
    gt = [{"pr_id": "1", "repo": "o/r", "stack": "py", "summary": "s", "diff": "d",
           "human_adopted": ["PRA-POSSIBLE_BUG"]}]
    cands = L._distill_via_llm(gt, {"experiences": []}, llm=_fake_llm, group_size=3)
    by = {c["finding_type"]: c for c in cands}
    assert "PRA-POSSIBLE_BUG" in by and "SCOPE-001" not in by
    assert all(c["status"] == "candidate" for c in cands)       # 不自动生效，仍需门控
    store = {"experiences": []}
    L.merge_candidates(store, cands)
    ab = {"PRA-POSSIBLE_BUG": {"with_seen": 25, "with_adopted": 22,
                               "without_seen": 25, "without_adopted": 15}}   # lift 0.28
    L.graduate(store, ab)
    got = [e for e in store["experiences"] if e["finding_type"] == "PRA-POSSIBLE_BUG"][0]
    assert got["status"] == "active"                            # 与计数式同一套 shadow A/B 门控


def test_distill_via_llm_requires_endpoint_without_llm(monkeypatch):
    import pytest
    for k in ("LLM_BASE_URL", "LLM_API_KEY", "TOUCHSTONE_FLAGSHIP_MODEL", "LLM_MODEL"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(RuntimeError):                            # 生产需配置旗舰端点
        L._distill_via_llm([{"pr_id": "1", "human_adopted": []}], {"experiences": []})


# ---------------- 蒸馏器分发 + 三步可注入（插件式）----------------
def test_distill_dispatch_default_selection(monkeypatch):
    monkeypatch.delenv("TOUCHSTONE_DISTILLER", raising=False)
    # 无真值集 → counting
    c1 = L.distill({"calib_agg": _REWARD, "repo": "o/r"})
    assert any(c["finding_type"] == "PRA-MAINTAINABILITY" for c in c1)
    # 有真值集 → tfgrpo（注入假 llm）
    c2 = L.distill({"ground_truth": [{"pr_id": "1", "human_adopted": ["PRA-POSSIBLE_BUG"],
                                      "repo": "o/r", "stack": "py", "summary": "s", "diff": "d"}],
                    "store": {"experiences": []}, "llm": _fake_llm})
    assert any(c["finding_type"] == "PRA-POSSIBLE_BUG" for c in c2)


def test_register_and_dispatch_custom_distiller():
    L.register_distiller("mine", lambda ctx: [{"id": "x", "status": "candidate"}])
    assert L.distill({}, name="mine")[0]["id"] == "x"          # 自有实现按名选用


def test_dispatch_unknown_raises():
    import pytest
    with pytest.raises(ValueError):
        L.distill({}, name="nope")


def test_distill_via_llm_injectable_steps():
    calls = {"rollout": 0, "score": 0, "distill": 0}

    def my_rollout(pr, E, llm, G):
        calls["rollout"] += 1
        return [[{"finding_type": "PRA-Z"}]]

    def my_score(review, adopted):
        calls["score"] += 1
        return 1.0

    def my_distill(pr, group, llm, repo, stack):
        calls["distill"] += 1
        return [{"id": "emphasize:PRA-Z", "finding_type": "PRA-Z", "kind": "emphasize",
                 "text": "x", "evidence": {}, "status": "candidate",
                 "source_prs": [pr.get("pr_id")], "repo": repo, "stack": stack,
                 "created_at": 0, "updated_at": 0}]

    gt = [{"pr_id": "1", "human_adopted": ["PRA-Z"], "repo": "o/r", "stack": "py"}]
    out = L._distill_via_llm(gt, {"experiences": []}, llm=lambda m: "[]",
                             rollout=my_rollout, score=my_score, distill_advantage=my_distill)
    assert calls == {"rollout": 1, "score": 1, "distill": 1}   # 三步均用注入实现
    assert out[0]["finding_type"] == "PRA-Z"


# ---------------- 人类输入：手写种子 / 红线 / 锁定 / 奖励权重 ----------------
def test_seed_experience_human_active_locked():
    store = {"experiences": []}
    e = L.seed_experience(store, "PRA-SECURITY", "emphasize", "Always flag auth changes.")
    assert e["source"] == "human" and e["locked"] is True and e["status"] == "active"
    assert store["experiences"][0]["id"] == "emphasize:::PRA-SECURITY"   # I1：id 含 repo/stack（此处空）
    assert "Always flag auth changes." in L.render_injection(store)   # 人写的 active 经验会被注入


def test_retire_skips_locked():
    store = {"experiences": [{"id": "emphasize:PRA-X", "finding_type": "PRA-X", "kind": "emphasize",
                              "status": "active", "locked": True, "evidence": {}, "text": "t"}]}
    L.retire(store, {"by_rule": {"PRA-X": {"fires": 30, "adoption_rate": 0.0}}})  # 本应触发退役
    assert store["experiences"][0]["status"] == "active"               # 锁定的不自动退役


def test_merge_candidates_skips_locked_human():
    store = {"experiences": [{"id": "suppress:PRA-Y", "finding_type": "PRA-Y", "kind": "suppress",
                              "status": "active", "locked": True, "source": "human",
                              "text": "human text", "evidence": {"seeded": True}}]}
    L.merge_candidates(store, [{"id": "suppress:PRA-Y", "finding_type": "PRA-Y", "kind": "suppress",
                                "status": "candidate", "text": "loop text",
                                "evidence": {"fires": 9}, "updated_at": 1}])
    assert store["experiences"][0]["text"] == "human text"             # 回路不得改写人锁定的经验


def test_protected_type_never_suppressed_counting(monkeypatch):
    monkeypatch.setenv("TOUCHSTONE_PROTECTED_TYPES", "PRA-SECURITY")
    cands = L.distill_candidates({"by_rule": {"PRA-SECURITY": {"fires": 20, "adoption_rate": 0.05}}})
    assert not any(c["kind"] == "suppress" for c in cands)             # 受保护，不生成 suppress


def test_protected_type_never_suppressed_tfgrpo(monkeypatch):
    monkeypatch.setenv("TOUCHSTONE_PROTECTED_TYPES", "PRA-SECURITY")
    fake = lambda m: ('[{"finding_type":"PRA-SECURITY","kind":"suppress","text":"drop sec"},'
                      '{"finding_type":"PRA-TYPO","kind":"suppress","text":"drop typo"}]')
    cands = L.distill_semantic_advantage({"pr_id": "1"},
                                         {"outputs": [[{"finding_type": "PRA-SECURITY"}],
                                                      [{"finding_type": "PRA-TYPO"}]],
                                          "rewards": [1.0, 0.0]},      # 非退化组
                                         fake, "o/r", "py")
    kinds = {(c["finding_type"], c["kind"]) for c in cands}
    assert ("PRA-SECURITY", "suppress") not in kinds                  # 红线挡住
    assert ("PRA-TYPO", "suppress") in kinds                          # 非保护类型照常


def test_score_review_weights_override():
    r = [{"finding_type": "PRA-A"}, {"finding_type": "PRA-B"}]         # adopted={A}: 命中1·噪声1·漏报0
    assert L.score_review(r, ["PRA-A"]) == 1 - 0.5                     # 默认权重
    assert L.score_review(r, ["PRA-A"], w_noise=1.0) == 0.0            # 人调高噪声惩罚
    assert L.score_review(r, ["PRA-A"], w_noise=0.0) == 1.0            # 人调低


# ---------------- 案例：examples/seed_experiences.py 的 10 条种子 ----------------
def test_example_seed_experiences():
    import importlib.util
    path = os.path.join(os.path.dirname(__file__), "..", "examples", "seed_experiences.py")
    spec = importlib.util.spec_from_file_location("seed_experiences", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    assert len(m.SEEDS) == 10
    ids = {f"{k}:{t}" for t, k, *_ in m.SEEDS}
    assert len(ids) == 10                              # 无 (动作,finding_type) 撞 id
    store = {"experiences": []}
    m.apply_seeds(store)
    exps = store["experiences"]
    assert len(exps) == 10
    assert all(e["source"] == "human" and e["locked"] and e["status"] == "active" for e in exps)
    assert sum(e["kind"] == "emphasize" for e in exps) == 8
    assert sum(e["kind"] == "suppress" for e in exps) == 2
    assert set(m.PROTECTED) <= {e["finding_type"] for e in exps}   # 红线类型都在种子里
    assert "Spring proxies" in m.L.render_injection(store)         # 种子会被注入评审


# ---------------- active_types + main() 接通 graduate（F8）----------------
def test_active_types_returns_only_active():
    store = {"experiences": [
        {"finding_type": "PRA-A", "status": "active"},
        {"finding_type": "PRA-B", "status": "candidate"},
        {"finding_type": "PRA-C", "status": "retired"},
        {"finding_type": "PRA-D", "status": "active"}]}
    assert sorted(L.active_types(store)) == ["PRA-A", "PRA-D"]
    assert L.active_types({"experiences": []}) == []


def _seed_candidate_store(path, ftype="PRA-X"):
    path.write_text(json.dumps({"experiences": [
        {"id": f"emphasize:{ftype}", "finding_type": ftype, "kind": "emphasize",
         "status": "candidate", "locked": False, "source_prs": [], "evidence": {}}]}),
        encoding="utf-8")
    return path


def test_main_graduates_candidate_when_ab_provided(tmp_path, monkeypatch):
    store_path = _seed_candidate_store(tmp_path / "exp.json")
    (tmp_path / "agg.json").write_text(json.dumps({}), encoding="utf-8")   # 无新候选
    (tmp_path / "ab.json").write_text(json.dumps({"PRA-X": {
        "with_seen": 25, "with_adopted": 20, "without_seen": 25, "without_adopted": 10}}),
        encoding="utf-8")                                                    # lift 0.4 ≥ 0.10
    monkeypatch.setattr(L, "STORE_PATH", str(store_path))
    monkeypatch.setenv("TOUCHSTONE_CALIB_AGG", str(tmp_path / "agg.json"))
    monkeypatch.setenv("TOUCHSTONE_AB_RESULTS", str(tmp_path / "ab.json"))
    monkeypatch.setenv("TOUCHSTONE_DISTILLER", "counting")
    L.main()
    e = next(x for x in L.load_store(str(store_path))["experiences"]
             if x["finding_type"] == "PRA-X")
    assert e["status"] == "active"                                          # graduate 已接通


def test_main_skips_graduate_without_ab(tmp_path, monkeypatch):
    store_path = _seed_candidate_store(tmp_path / "exp.json")
    (tmp_path / "agg.json").write_text(json.dumps({}), encoding="utf-8")
    monkeypatch.setattr(L, "STORE_PATH", str(store_path))
    monkeypatch.setenv("TOUCHSTONE_CALIB_AGG", str(tmp_path / "agg.json"))
    monkeypatch.delenv("TOUCHSTONE_AB_RESULTS", raising=False)
    monkeypatch.setenv("TOUCHSTONE_DISTILLER", "counting")
    L.main()
    e = next(x for x in L.load_store(str(store_path))["experiences"]
             if x["finding_type"] == "PRA-X")
    assert e["status"] == "candidate"                                       # 无 A/B 数据 → 不自动激活


# ---------------- 真值集采集：从人工合入裁决重建（build_ground_truth）----------------
def test_stack_of_infers():
    assert L._stack_of(["a.py", "b.py"]) == "python"
    assert L._stack_of(["A.java"]) == "java"
    assert L._stack_of(["main.go"]) == "go"
    assert L._stack_of(["x.ts"]) == "typescript"
    assert L._stack_of(["README.md"]) == ""                                # 不确定 → 通用


def test_make_gt_entry_splits_adopted_and_ignored():
    ts = [{"rule_id": "PRA-A"}, {"rule_id": "PRA-B"}, {"rule_id": "SCOPE-001"}]
    e = L.make_gt_entry(7, "o/r", "python", "title", "diff", ts,
                        {"PRA-A"}, "APPROVED", True)
    assert e["human_adopted"] == ["PRA-A"]                                 # 人 resolve 的 → 正例
    assert e["human_ignored"] == ["PRA-B", "SCOPE-001"]                    # 挑了但人没采纳 → 噪声负例
    assert e["pr_id"] == "7" and e["merged"] is True and e["human_state"] == "APPROVED"


def test_build_ground_truth_from_human_verdicts(tmp_path, monkeypatch):
    """离线模拟 GitHub 重建：PR#1 有 touchstone marker + 线程采纳信号；PR#2 无 marker → 跳过。"""
    from touchstone import calibrate as C
    marker = ("<!-- touchstone-result: " + json.dumps(
        {"findings": [{"rule_id": "PRA-POSSIBLE_BUG"}, {"rule_id": "PRA-TYPO"}]}) + " -->")
    threads_payload = {"data": {"repository": {"pullRequest": {"reviewThreads": {"nodes": [
        {"isResolved": True, "comments": {"nodes": [{"author": {"login": "github-actions[bot]"}, "body":
            "<!-- touchstone-finding: " + json.dumps({"rule_id": "PRA-POSSIBLE_BUG"}) + " -->"}]}},
        {"isResolved": False, "comments": {"nodes": [{"author": {"login": "github-actions[bot]"}, "body":
            "<!-- touchstone-finding: " + json.dumps({"rule_id": "PRA-TYPO"}) + " -->"}]}},
    ]}}}}}

    def fake_gh(path, token, accept="application/vnd.github+json"):
        if "state=closed" in path:
            return [{"number": 1, "title": "fix bug", "merged_at": "2026-01-01"},
                    {"number": 2, "title": "docs", "merged_at": None}]
        if "issues/1/comments" in path:
            return [{"body": marker}]
        if "issues/2/comments" in path:
            return []                                                       # 无 marker → 跳过
        if "pulls/1/reviews" in path:
            return [{"state": "APPROVED", "user": {"login": "alice"}}]
        if "pulls/1/files" in path:
            return [{"filename": "src/a.py"}]
        if path.endswith("/pulls/1") and accept.endswith("diff"):
            return "diff --git a.py"
        return []
    monkeypatch.setattr(GT, "_gh_get", fake_gh)
    monkeypatch.setattr(C, "gql", lambda q, v, t: threads_payload if v["num"] == 1 else {"data": {}})

    gt = L.build_ground_truth("o", "r", "tok")
    assert len(gt) == 1                                                     # PR#2 无 marker 被跳过
    entry = gt[0]
    assert entry["pr_id"] == "1" and entry["stack"] == "python"
    assert entry["human_adopted"] == ["PRA-POSSIBLE_BUG"]                   # 人 resolve 的 → 采纳
    assert entry["human_ignored"] == ["PRA-TYPO"]                           # 人没采纳 → 噪声
    assert entry["merged"] is True and entry["human_state"] == "APPROVED"


# ---------------- aggregate_ab + 自动 graduate（恢复 injected_types→A/B 分臂接线）----------------
def test_build_ground_truth_carries_injected_types_from_marker(tmp_path, monkeypatch):
    """result marker 的 injected_types 必须透传进真值条目——这是 graduate 自动分臂的数据来源，
    曾在 ground_truth 拆分时被丢（本 PR 恢复）。锁此透传链，防再次回归。"""
    from touchstone import calibrate as C
    marker = ("<!-- touchstone-result: " + json.dumps(
        {"findings": [{"rule_id": "PRA-X"}], "injected_types": ["PRA-SEED", "PRA-X"]}) + " -->")

    def fake_gh(path, token, accept="application/vnd.github+json"):
        if "state=closed" in path:
            return [{"number": 1, "title": "t", "merged_at": "2026-01-01"}]
        if "issues/1/comments" in path:
            return [{"body": marker}]
        if "pulls/1/reviews" in path:
            return [{"state": "APPROVED", "user": {"login": "alice"}}]
        if "pulls/1/files" in path:
            return [{"filename": "a.py"}]
        if path.endswith("/pulls/1") and accept.endswith("diff"):
            return "diff --git a.py"
        return []
    monkeypatch.setattr(GT, "_gh_get", fake_gh)
    monkeypatch.setattr(C, "gql", lambda q, v, t: {"data": {}})
    entry = L.build_ground_truth("o", "r", "tok")[0]
    assert entry["raised_types"] == ["PRA-X"]                  # touchstone 挑过的
    assert entry["injected_types"] == ["PRA-SEED", "PRA-X"]    # marker 的注入类型透传


def test_make_gt_entry_carries_injected_and_raised():
    ts = [{"rule_id": "PRA-A"}, {"rule_id": "PRA-B"}]
    e = L.make_gt_entry(1, "o/r", "python", "t", "d", ts, {"PRA-A"}, "APPROVED", True,
                        injected_types=["PRA-A", "PRA-C"])
    assert e["raised_types"] == ["PRA-A", "PRA-B"]
    assert e["injected_types"] == ["PRA-A", "PRA-C"]


# -------- shadow 注入采 A/B with 臂（冷启动破死锁 step2：aggregate_ab 拓宽 with 臂判据）--------
def test_aggregate_ab_shadow_counts_as_with_arm():
    """shadow_types 让 candidate 进 with 臂（破死锁数据侧）：同类型在 injected_types 或
    shadow_types 任一出现 → with 臂；都未出现 → without 臂。"""
    gt = [
        {"raised_types": ["PRA-X"], "injected_types": ["PRA-X"], "shadow_types": [], "human_adopted": ["PRA-X"]},
        {"raised_types": ["PRA-X"], "injected_types": [], "shadow_types": ["PRA-X"], "human_adopted": ["PRA-X"]},
        {"raised_types": ["PRA-X"], "injected_types": [], "shadow_types": [], "human_adopted": []},
    ]
    ab = L.aggregate_ab(gt)
    assert ab["PRA-X"] == {"with_seen": 2, "with_adopted": 2,        # active(PR1) + shadow(PR2) 都计入 with 臂
                           "without_seen": 1, "without_adopted": 0}  # PR3 都未注入 → without 臂


def test_aggregate_ab_shadow_absent_backward_compatible():
    """向后兼容：gt 条目无 shadow_types 键（旧 marker / step2 前）→ 等价 shadow_types=[]，
    with 臂判据退化为只看 injected_types（现有行为字节级不变）。"""
    gt = [
        {"raised_types": ["PRA-A"], "injected_types": ["PRA-A"], "human_adopted": ["PRA-A"]},
        {"raised_types": ["PRA-A"], "injected_types": [], "human_adopted": []},
    ]
    ab = L.aggregate_ab(gt)
    assert ab["PRA-A"] == {"with_seen": 1, "with_adopted": 1, "without_seen": 1, "without_adopted": 0}


def test_make_gt_entry_carries_shadow_types():
    """make_gt_entry 的 shadow_types 参数透传进真值条目（供 aggregate_ab 的 with 臂判据）。"""
    e = L.make_gt_entry(1, "o/r", "python", "t", "d", [{"rule_id": "PRA-A"}], {"PRA-A"},
                        "APPROVED", True, injected_types=["PRA-A"], shadow_types=["PRA-CAND"])
    assert e["shadow_types"] == ["PRA-CAND"]
    e2 = L.make_gt_entry(2, "o/r", "python", "t", "d", [], set(), "APPROVED", True)  # 默认 None → 空列表
    assert e2["shadow_types"] == []


def test_cold_start_candidate_graduates_via_shadow():
    """【冷启动破死锁验收锚点 · step5】candidate 仅靠 shadow 注入采 A/B with 臂 → graduate 达标转 active。

    死锁机制（step2 前）：candidate 从未被 active 注入 → 历史 marker 的 injected_types 不含其 type →
    aggregate_ab 对该 type 的 with 臂恒 0 → graduate 因 ws<GRADUATE_MIN_SAMPLES(20) 永远跳过 →
    candidate 永远卡池（唯一进 active 的是人手 seed，非自进化）。shadow_types 拓宽 with 臂判据
    （injected_types ∪ shadow_types）→ candidate 未达 active 也能采 with 臂样本 → 死锁破。

    先红后绿：step2 前 aggregate_ab 不看 shadow_types → with_seen 会是 0 → graduate 跳过 → 末尾 assert 红；
    step2 合入后 with_seen=20 → graduate 转 active → 绿。"""
    T = "PRA-DEADLOCK"
    # with 臂 20 条：仅 shadow 注入 T（injected_types 空——candidate 从未 active 注入），16 条人采纳（rate 0.8）
    gt = ([{"raised_types": [T], "injected_types": [], "shadow_types": [T],
             "human_adopted": [T] if i % 5 else []} for i in range(20)] +
          # without 臂 20 条：未注入 T，2 条人采纳（rate 0.1）
          [{"raised_types": [T], "injected_types": [], "shadow_types": [],
            "human_adopted": [T] if i % 10 == 0 else []} for i in range(20)])
    ab = L.aggregate_ab(gt)
    arm = ab[T]
    assert arm["with_seen"] == 20 and arm["with_adopted"] == 16     # shadow 拓宽 with 臂（否则恒 0=死锁）
    assert arm["without_seen"] == 20 and arm["without_adopted"] == 2
    # lift = 0.8 − 0.1 = 0.7 ≥ 0.10，两臂各 ≥ 20 → graduate 达标
    store = {"experiences": [{"id": "e:::T", "finding_type": T, "kind": "emphasize",
                              "text": "x", "status": "candidate", "updated_at": 1, "evidence": {}}]}
    assert L.graduate(store, ab) == ["e:::T"]
    assert store["experiences"][0]["status"] == "active"            # 死锁破：candidate 经 shadow graduate


def test_build_ground_truth_carries_shadow_types_from_marker(tmp_path, monkeypatch):
    """result marker 的 shadow_types 必须透传进真值条目——这是 shadow 注入采 with 臂的数据来源（step2 核心）。
    锁此透传链（对齐 injected_types 的 test_build_ground_truth_carries_injected_types_from_marker）。"""
    from touchstone import calibrate as C
    marker = ("<!-- touchstone-result: " + json.dumps(
        {"findings": [{"rule_id": "PRA-X"}],
         "injected_types": ["PRA-SEED"],
         "shadow_types": ["PRA-X", "PRA-CAND"]}) + " -->")

    def fake_gh(path, token, accept="application/vnd.github+json"):
        if "state=closed" in path:
            return [{"number": 1, "title": "t", "merged_at": "2026-01-01"}]
        if "issues/1/comments" in path:
            return [{"body": marker}]
        if "pulls/1/reviews" in path:
            return [{"state": "APPROVED", "user": {"login": "alice"}}]
        if "pulls/1/files" in path:
            return [{"filename": "a.py"}]
        if path.endswith("/pulls/1") and accept.endswith("diff"):
            return "diff --git a.py"
        return []
    monkeypatch.setattr(GT, "_gh_get", fake_gh)
    monkeypatch.setattr(C, "gql", lambda q, v, t: {"data": {}})
    entry = L.build_ground_truth("o", "r", "tok")[0]
    assert entry["raised_types"] == ["PRA-X"]
    assert entry["injected_types"] == ["PRA-SEED"]
    assert entry["shadow_types"] == ["PRA-CAND", "PRA-X"]          # marker shadow_types 透传进真值条目


def test_aggregate_ab_splits_by_injection():
    gt = [
        {"raised_types": ["PRA-A"], "injected_types": ["PRA-A"], "human_adopted": ["PRA-A"]},
        {"raised_types": ["PRA-A"], "injected_types": [], "human_adopted": []},
        {"raised_types": ["PRA-B"], "injected_types": [], "human_adopted": []},
    ]
    ab = L.aggregate_ab(gt)
    assert ab["PRA-A"] == {"with_seen": 1, "with_adopted": 1,
                           "without_seen": 1, "without_adopted": 0}
    assert ab["PRA-B"] == {"with_seen": 0, "with_adopted": 0,
                           "without_seen": 1, "without_adopted": 0}
    assert L.aggregate_ab([]) == {}


def test_main_auto_graduates_from_ground_truth(tmp_path, monkeypatch):
    """无 --ab-results 时，main 自动从 ground_truth 的 injected_types 算 A/B → graduate。"""
    store_path = tmp_path / "exp.json"
    store_path.write_text(json.dumps({"experiences": [
        {"id": "emphasize:PRA-X", "finding_type": "PRA-X", "kind": "emphasize",
         "status": "candidate", "locked": False, "source_prs": [], "evidence": {}}]}),
        encoding="utf-8")
    gt_path = tmp_path / "gt.json"
    gt = ([{"pr_id": str(i), "raised_types": ["PRA-X"], "injected_types": ["PRA-X"],
            "human_adopted": ["PRA-X"]} for i in range(25)] +                 # 注入臂：全采纳
          [{"pr_id": str(100 + i), "raised_types": ["PRA-X"], "injected_types": [],
            "human_adopted": []} for i in range(25)])                          # 对照臂：全未采纳
    gt_path.write_text(json.dumps(gt), encoding="utf-8")
    monkeypatch.delenv("TOUCHSTONE_DISTILLER", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    report = L.main(["--store", str(store_path), "--ground-truth", str(gt_path)])
    e = next(x for x in L.load_store(str(store_path))["experiences"] if x["finding_type"] == "PRA-X")
    assert e["status"] == "active"                                            # 自动 A/B → 达标激活
    assert any("aggregate_ab" in s for s in report["steps"])


# ---------------- main() 的 CLI 路径（learn.yml 走这里）----------------
def test_main_cli_path_counting_then_graduate(tmp_path, monkeypatch):
    store_path = tmp_path / "exp.json"
    store_path.write_text(json.dumps({"experiences": []}), encoding="utf-8")
    (tmp_path / "agg.json").write_text(json.dumps(
        {"by_rule": {"PRA-X": {"fires": 12, "adoption_rate": 0.9}}}), encoding="utf-8")   # 高采纳→emphasize 候选
    (tmp_path / "ab.json").write_text(json.dumps({"PRA-X": {
        "with_seen": 25, "with_adopted": 20, "without_seen": 25, "without_adopted": 10}}),
        encoding="utf-8")                                                    # lift 0.4 ≥ 0.10
    out_path = tmp_path / "report.json"
    gho = tmp_path / "gh.txt"
    monkeypatch.delenv("TOUCHSTONE_DISTILLER", raising=False)
    monkeypatch.setenv("GITHUB_OUTPUT", str(gho))
    report = L.main(["--store", str(store_path), "--calib-agg", str(tmp_path / "agg.json"),
                     "--ab-results", str(tmp_path / "ab.json"), "--output", str(out_path)])
    assert report["distiller"] == "counting"                                # 无旗舰端点/真值集 → 计数式
    assert report["candidates"] >= 1
    e = next(x for x in L.load_store(str(store_path))["experiences"]
             if x["finding_type"] == "PRA-X")
    assert e["status"] == "active"                                          # 达标转 active
    assert json.load(open(out_path, encoding="utf-8"))["candidates"] >= 1   # 学习报告落盘
    assert "changed=true" in gho.read_text(encoding="utf-8")                # 输出 changed 供 workflow 提交


def test_main_cli_build_ground_truth(tmp_path, monkeypatch):
    store_path = tmp_path / "exp.json"
    store_path.write_text(json.dumps({"experiences": []}), encoding="utf-8")
    gt_path = tmp_path / "gt.json"
    monkeypatch.setenv("GITHUB_TOKEN", "tk")
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
    monkeypatch.delenv("TOUCHSTONE_DISTILLER", raising=False)
    called = {}

    def fake_bgt(owner, repo, token, **kw):
        called["args"] = (owner, repo)
        return [{"pr_id": "1", "repo": "o/r", "stack": "python", "summary": "s",
                 "diff": "d", "human_adopted": ["PRA-A"]}]
    monkeypatch.setattr(L, "build_ground_truth", fake_bgt)
    report = L.main(["--store", str(store_path), "--build-ground-truth",
                     "--ground-truth", str(gt_path)])
    assert called["args"] == ("o", "r")                                     # 从 GITHUB_REPOSITORY 解析
    assert report["ground_truth"] == 1                                      # 真值集已采集
    assert gt_path.exists()                                                 # 并落盘供后续 TF-GRPO 复用


def test_main_cli_ground_truth_min_skips_tfgrpo(tmp_path, monkeypatch):
    """真值集不足下限时，即便有旗舰端点也回退计数式（不伪造 TF-GRPO 数据）。"""
    store_path = tmp_path / "exp.json"
    store_path.write_text(json.dumps({"experiences": []}), encoding="utf-8")
    gt_path = tmp_path / "gt.json"
    gt_path.write_text(json.dumps([{"pr_id": "1", "human_adopted": ["PRA-A"]}]), encoding="utf-8")
    monkeypatch.setenv("LLM_BASE_URL", "http://x"); monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("TOUCHSTONE_FLAGSHIP_MODEL", "m"); monkeypatch.setenv("TOUCHSTONE_GROUND_TRUTH_MIN", "10")
    monkeypatch.delenv("TOUCHSTONE_DISTILLER", raising=False)
    report = L.main(["--store", str(store_path), "--ground-truth", str(gt_path)])
    assert report["ground_truth"] == 0                                      # 不足下限 → 视作无真值集
    assert report["distiller"] == "counting"                                # 回退计数式


def test_active_ids_for_experience_provenance():
    """active_ids 给出 active 经验的 id 列表——供 marker 的 injected_experience_ids 做单条归因。"""
    from touchstone import learning_loop as L
    store = {"experiences": [
        {"id": "emphasize:::PRA-SECURITY", "finding_type": "PRA-SECURITY", "status": "active"},
        {"id": "suppress:::PRA-TYPO", "finding_type": "PRA-TYPO", "status": "candidate"},
    ]}
    ids = L.active_ids(store)
    assert ids == ["emphasize:::PRA-SECURITY"]           # 只列 active，candidate 不算
    assert L.active_ids({"experiences": []}) == []


# ==================== TF-GRPO 加固回归（I1/I2/I3/I4，重施于新基线）====================
def test_exp_id_scoped_no_multirepo_collision():
    fake = lambda m: '[{"finding_type":"PRA-X","kind":"emphasize","text":"x"}]'
    g = {"outputs": [[{"finding_type": "PRA-X"}], [{"finding_type": "PRA-Y"}]], "rewards": [1.0, 0.0]}
    a = L.distill_semantic_advantage({"pr_id": "1"}, g, fake, "acme/pay", "java")
    b = L.distill_semantic_advantage({"pr_id": "2"}, g, fake, "acme/risk", "py")
    store = {"experiences": []}
    L.merge_candidates(store, a); L.merge_candidates(store, b)
    assert a[0]["id"] != b[0]["id"] and len(store["experiences"]) == 2

def test_degenerate_group_skipped():
    fake = lambda m: '[{"finding_type":"PRA-X","kind":"emphasize","text":"x"}]'
    same = {"outputs": [[{"finding_type": "PRA-X"}]] * 2, "rewards": [0.5, 0.5]}
    assert L.distill_semantic_advantage({"pr_id": "1"}, same, fake, "o/r", "py") == []

def test_injection_conflict_resolved():
    store = {"experiences": [
        {"id": "e", "repo": "o/r", "stack": "py", "finding_type": "PRA-X", "kind": "emphasize",
         "text": "DO flag PRA-X", "status": "active", "updated_at": 100},
        {"id": "s", "repo": "o/r", "stack": "py", "finding_type": "PRA-X", "kind": "suppress",
         "text": "do NOT flag PRA-X", "status": "active", "updated_at": 200}]}
    out = L.render_injection(store)
    assert "do NOT flag PRA-X" in out and "DO flag PRA-X" not in out

def test_epochs_rerender_experience():
    seen = []
    rollout = lambda pr, E, llm, g: (seen.append(E) or
        [[{"finding_type": "PRA-X"}], [{"finding_type": "PRA-Y"}]])
    dist = lambda pr, g, llm, repo, stack: [{"id": L._exp_id("PRA-X", "emphasize", repo, stack),
        "repo": repo, "stack": stack, "finding_type": "PRA-X", "kind": "emphasize",
        "text": "E1-EXP", "status": "candidate", "source": "tfgrpo", "locked": False,
        "source_prs": ["1"], "created_at": 1, "updated_at": 1}]
    gt = [{"pr_id": "1", "repo": "o/r", "stack": "py", "summary": "s", "diff": "d",
           "human_adopted": ["PRA-X"]}]
    L._distill_via_llm(gt, {"experiences": []}, llm=lambda m: "[]", group_size=2, epochs=2,
                       rollout=rollout, score=lambda r, h: 1.0, distill_advantage=dist)
    assert len(seen) == 2 and seen[0] == "" and "E1-EXP" in seen[1]


def test_store_path_prefers_new_env(monkeypatch, tmp_path):
    """TOUCHSTONE_STORE_PATH 优先于旧名 TOUCHSTONE_EXPERIENCE。"""
    import importlib
    from touchstone import experience_store, learning_loop
    f = tmp_path / 's.json'; f.write_text('{"experiences": [{"id": "x", "status": "active", "finding_type": "T"}]}')
    monkeypatch.setenv('TOUCHSTONE_STORE_PATH', str(f))
    # STORE_PATH 的 env 求值在 experience_store 导入期——reload 它（learning_loop 门面随后同步）
    importlib.reload(experience_store)
    try:
        assert experience_store.load_store()['experiences'][0]['id'] == 'x'
    finally:
        monkeypatch.delenv('TOUCHSTONE_STORE_PATH', raising=False)
        importlib.reload(experience_store); importlib.reload(learning_loop)


# ---------------- 边角分支补测 ----------------
def test_read_store_text_from_ref(monkeypatch, tmp_path):
    import subprocess
    from touchstone import learning_loop as L
    monkeypatch.setenv("TOUCHSTONE_EXPERIENCE_REF", "origin/main")
    class _R:
        returncode = 0
        stdout = '{"experiences": []}'
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _R())
    assert L._read_store_text("data/x.json") == '{"experiences": []}'


def test_read_store_text_ref_failure_returns_none(monkeypatch):
    import subprocess
    from touchstone import learning_loop as L
    monkeypatch.setenv("TOUCHSTONE_EXPERIENCE_REF", "origin/main")
    class _R:
        returncode = 1
        stdout = ""
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _R())
    assert L._read_store_text("data/x.json") is None


def test_extract_json_none_and_no_json():
    from touchstone import learning_loop as L
    assert L._extract_json(None, "DEF") == "DEF"
    assert L._extract_json("no json here", "DEF") == "DEF"


def test_llm_json_exception_returns_default():
    from touchstone import learning_loop as L
    assert L._llm_json(lambda m: (_ for _ in ()).throw(RuntimeError("x")), [], "DEF") == "DEF"


def test_flagship_llm_success(monkeypatch):
    from touchstone import learning_loop as L
    monkeypatch.setenv("LLM_BASE_URL", "http://b")
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("TOUCHSTONE_FLAGSHIP_MODEL", "m")
    captured = {}
    class _Msg: content = "OK"
    class _Choice: message = _Msg()
    class _Resp: choices = [_Choice()]
    class _Client:
        def __init__(self, **kw): pass
        @property
        def chat(self): return self
        @property
        def completions(self): return self
        def create(self, **kw):
            captured.update(kw)
            return _Resp()
    import openai
    monkeypatch.setattr(openai, "OpenAI", _Client)
    fn = L._flagship_llm()
    assert fn([{"role": "user", "content": "hi"}]) == "OK"
    assert captured["model"] == "m" and captured["temperature"] == 0.7


def test_seed_experience_updates_existing():
    from touchstone import learning_loop as L
    store = {"experiences": [L.seed_experience({"experiences": []}, "PRA-X", "emphasize", "first")]}
    # 同 id 再 seed → 更新 text
    updated = L.seed_experience(store, "PRA-X", "emphasize", "second")
    assert updated["text"] == "second"
    assert len(store["experiences"]) == 1


def test_seed_experience_bad_kind_raises():
    import pytest
    from touchstone import learning_loop as L
    with pytest.raises(ValueError):
        L.seed_experience({"experiences": []}, "PRA-X", "wat", "x")


def test_graduate_skips_no_ab_and_low_samples():
    from touchstone import learning_loop as L
    store = {"experiences": [
        {"id": "e:::T1", "finding_type": "T1", "status": "candidate", "evidence": {}, "updated_at": 1},
        {"id": "e:::T2", "finding_type": "T2", "status": "candidate", "evidence": {}, "updated_at": 1},
    ]}
    # T1 无 ab → 跳；T2 样本不足 → 跳
    ab = {"T2": {"with_seen": 1, "with_adopted": 1, "without_seen": 1, "without_adopted": 0}}
    assert L.graduate(store, ab) == []


def test_gh_get_uses_ghclient(monkeypatch):
    from touchstone import ghclient, learning_loop as L
    monkeypatch.setattr(ghclient, "request",
                        lambda method, url, token, accept=None: {"ok": 1})
    assert L._gh_get("/repos/x", "tok") == {"ok": 1}


def test_build_ground_truth_skips_failed_pr(monkeypatch, tmp_path):
    from touchstone import learning_loop as L
    # _gh_get 对 pulls 返回数据、对其它失败 → 该 PR 跳过，不中断
    seq = [{"number": 1, "title": "t", "merged_at": "x", "base": {"ref": "main"}}]
    monkeypatch.setattr(GT, "_gh_get", lambda path, token, accept=None: (
        seq if "pulls?state" in path else ({"files": []} if "/files" in path else None)))
    out = L.build_ground_truth("o", "r", "tok", window=5)
    assert isinstance(out, list)


def test_ground_truth_written_atomically(monkeypatch, tmp_path):
    # P2-3：真值文件走 atomicio（半文件会让下轮校准读损坏 JSON）——锁死调用点防回退裸写
    import touchstone.learning_loop as LL
    calls = {}
    monkeypatch.setattr(LL, "atomic_write_json",
                        lambda path, obj: calls.update(path=path, obj=obj))
    monkeypatch.setattr(LL, "build_ground_truth", lambda *a, **k: [{"x": 1}])
    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
    # 经验库/输出都指向 tmp，避免污染仓库
    gt = tmp_path / "gt.json"
    LL.main(["--build-ground-truth", "--ground-truth", str(gt),
             "--store", str(tmp_path / "store.json"),
             "--output", str(tmp_path / "report.json")])
    assert calls.get("path") == str(gt) and calls.get("obj") == [{"x": 1}]


# ==================== shadow 注入：candidate 池 → A/B with 臂（冷启动破死锁，默认关）====================
# 详见 docs/tfgrpo-self-evolution-design.html §2。本组锁定 shadow_candidates 的确定性抽样 + 安全闸
# + render_injection(include_shadow) 的默认关/开启行为；graduate 零改动（candidate→active 仍走原 A/B 门控）。
def _candidate(ftype, kind="emphasize", source_prs=None, repo="", stack=""):
    """造一条 candidate 经验（shadow_candidates 的输入）。默认带 1 条 source_prs 过 min_evidence=1 初筛。"""
    return {"id": L._exp_id(ftype, kind, repo, stack), "repo": repo, "stack": stack,
            "finding_type": ftype, "kind": kind, "text": f"advise on {ftype}",
            "status": "candidate", "source_prs": source_prs if source_prs is not None else ["1"],
            "evidence": {}, "locked": False}


def test_shadow_candidates_deterministic_across_calls():
    """同一 store 多次调 shadow_candidates 返回同一批——hashlib 稳定哈希，不随 PYTHONHASHSEED 抖动
    （抖动会让同 PR 多轮评审注入不同 shadow 集，污染 A/B 归因）。"""
    store = {"experiences": [_candidate(f"PRA-C{i}") for i in range(6)]}
    a = L.shadow_candidates(store, ratio=1.0, max_per_review=10, min_evidence=1)
    b = L.shadow_candidates(store, ratio=1.0, max_per_review=10, min_evidence=1)
    assert [e["id"] for e in a] == [e["id"] for e in b]


def test_shadow_candidates_ratio_controls_selection():
    """ratio=1.0 全入选（受 max_per_review 截）；ratio=0.0 空集；中间值按 id 稳定哈希确定性筛选。"""
    store = {"experiences": [_candidate(f"PRA-C{i}") for i in range(4)]}
    assert len(L.shadow_candidates(store, ratio=1.0, max_per_review=10, min_evidence=1)) == 4
    assert L.shadow_candidates(store, ratio=0.0, max_per_review=10, min_evidence=1) == []
    # 中间值：用已知 _shadow_hash 设 ratio 精确包含/排除某条（确定性，非统计性断言）
    e = _candidate("PRA-MID")
    h = L._shadow_hash(e["id"])
    s = {"experiences": [e]}
    assert L.shadow_candidates(s, ratio=h + 1e-6, max_per_review=10, min_evidence=1) != []   # h < ratio → 入选
    assert L.shadow_candidates(s, ratio=h, max_per_review=10, min_evidence=1) == []          # h >= ratio → 排除


def test_shadow_candidates_min_evidence_filters():
    """source_prs 数 < min_evidence 的 candidate 不入选（初筛防孤证）。"""
    store = {"experiences": [
        _candidate("PRA-RICH", source_prs=["1", "2", "3"]),
        _candidate("PRA-POOR", source_prs=[])]}
    got = L.shadow_candidates(store, ratio=1.0, max_per_review=10, min_evidence=1)
    assert [e["finding_type"] for e in got] == ["PRA-RICH"]


def test_shadow_candidates_protected_suppress_excluded(monkeypatch):
    """protected_types 的 suppress 永不 shadow 注入（安全闸）；同类型 emphasize 不受此限（该挑的仍采数）。"""
    monkeypatch.setenv("TOUCHSTONE_PROTECTED_TYPES", "PRA-SEC")
    store = {"experiences": [
        _candidate("PRA-SEC", kind="suppress"),    # 红线 suppress → 挡
        _candidate("PRA-SEC", kind="emphasize"),   # 红线 emphasize → 放行
        _candidate("PRA-TYPO", kind="suppress")]}  # 非保护 suppress → 放行
    got = {(e["finding_type"], e["kind"]) for e in
           L.shadow_candidates(store, ratio=1.0, max_per_review=10, min_evidence=1)}
    assert ("PRA-SEC", "suppress") not in got
    assert ("PRA-SEC", "emphasize") in got
    assert ("PRA-TYPO", "suppress") in got


def test_shadow_candidates_max_per_review_caps():
    """ratio=1.0 全入选，但 max_per_review 截单轮爆炸面。"""
    store = {"experiences": [_candidate(f"PRA-C{i}") for i in range(5)]}
    got = L.shadow_candidates(store, ratio=1.0, max_per_review=2, min_evidence=1)
    assert len(got) == 2


def test_shadow_candidates_negative_max_clamped_to_zero():
    """max_per_review 负数 clamp 到 0（返空），不返 selected[:-N] 的尾部元素（语义 bug 防回归）。
    触发场景：env TOUCHSTONE_SHADOW_MAX_PER_REVIEW 误配负数——修复前 selected[:-1] 会返 N-1 条。"""
    store = {"experiences": [_candidate(f"PRA-C{i}") for i in range(4)]}
    assert L.shadow_candidates(store, ratio=1.0, max_per_review=-1, min_evidence=1) == []
    assert L.shadow_candidates(store, ratio=1.0, max_per_review=-5, min_evidence=1) == []


def test_shadow_hash_scale_guarantees_below_one():
    """除数必须严格大于最大可能分子（2**32-1）→ 商恒 < 1.0（半开区间 [0,1)），使 ratio=1.0 真正全选。
    防 off-by-one 回归：除以 (2**32-1) 会让 hash=0xFFFFFFFF 时商=1.0，被 `>=ratio` 错误排除。"""
    from touchstone import experience_store as ES
    assert ES._SHADOW_HASH_SCALE > (2**32 - 1)            # 除数 > 最大分子 → 商严格 < 1.0
    for eid in ["emphasize:::PRA-A", "suppress:o/r:PRA-B", "x", "PRA-" * 25]:
        h = L._shadow_hash(eid)
        assert 0.0 <= h < 1.0                             # 行为级：任意 id 落在 [0, 1)


def test_shadow_candidates_only_candidate_status():
    """非 candidate（active/retired）不入选 shadow。"""
    store = {"experiences": [
        _candidate("PRA-CAND"),
        {"id": "emphasize:PRA-ACT", "finding_type": "PRA-ACT", "kind": "emphasize",
         "status": "active", "source_prs": ["1"], "text": "x"},
        {"id": "emphasize:PRA-RET", "finding_type": "PRA-RET", "kind": "emphasize",
         "status": "retired", "source_prs": ["1"], "text": "x"}]}
    got = [e["finding_type"] for e in
           L.shadow_candidates(store, ratio=1.0, max_per_review=10, min_evidence=1)]
    assert got == ["PRA-CAND"]


def test_render_injection_shadow_off_by_default():
    """默认 include_shadow=False：输出不含 shadow 段（零行为变化，与改前等价）。"""
    store = {"experiences": [
        {"id": "emphasize:PRA-ACT", "finding_type": "PRA-ACT", "kind": "emphasize",
         "status": "active", "text": "flag PRA-ACT"},
        _candidate("PRA-CAND")]}
    out = L.render_injection(store)
    assert "PRA-CAND" not in out and "[shadow]" not in out
    assert "flag PRA-ACT" in out


def test_render_injection_includes_shadow_when_enabled(monkeypatch):
    """include_shadow=True：active 段后追加 shadow 段、每条前缀 [shadow]。"""
    monkeypatch.setenv("TOUCHSTONE_SHADOW_RATIO", "1.0")          # 全入选，免哈希偶然性
    monkeypatch.setenv("TOUCHSTONE_SHADOW_MAX_PER_REVIEW", "10")
    store = {"experiences": [
        {"id": "emphasize:PRA-ACT", "finding_type": "PRA-ACT", "kind": "emphasize",
         "status": "active", "text": "flag PRA-ACT"},
        _candidate("PRA-CAND")]}
    out = L.render_injection(store, include_shadow=True)
    assert "flag PRA-ACT" in out                      # active 段在
    assert "Shadow candidates" in out                 # shadow 段标题在
    assert "[shadow] advise on PRA-CAND" in out       # shadow 候选标灰注入
    assert out.index("flag PRA-ACT") < out.index("Shadow candidates")   # active 段在 shadow 段前


def test_render_injection_active_empty_shadow_only(monkeypatch):
    """active 空但 include_shadow=True 且有 candidate → 只输出 shadow 段（不因 active 空早返回空串）。"""
    monkeypatch.setenv("TOUCHSTONE_SHADOW_RATIO", "1.0")
    monkeypatch.setenv("TOUCHSTONE_SHADOW_MAX_PER_REVIEW", "10")
    store = {"experiences": [_candidate("PRA-CAND")]}
    out = L.render_injection(store, include_shadow=True)
    assert "Learned review experience" not in out     # 无 active 段
    assert "[shadow] advise on PRA-CAND" in out       # 仍有 shadow 段


def test_shadow_types_and_ids_mirror_candidates(monkeypatch):
    """shadow_types/shadow_ids 与 shadow_candidates 取同一批（env 同源）——marker 归因与渲染一致。"""
    monkeypatch.setenv("TOUCHSTONE_SHADOW_RATIO", "1.0")
    monkeypatch.setenv("TOUCHSTONE_SHADOW_MAX_PER_REVIEW", "5")
    monkeypatch.setenv("TOUCHSTONE_SHADOW_MIN_EVIDENCE", "1")
    store = {"experiences": [_candidate(f"PRA-C{i}") for i in range(3)]}
    cands = L.shadow_candidates(store, ratio=1.0, max_per_review=5, min_evidence=1)
    assert sorted(L.shadow_types(store)) == sorted(e["finding_type"] for e in cands)
    assert sorted(L.shadow_ids(store)) == sorted(e["id"] for e in cands)


def test_shadow_injection_enabled_reads_env(monkeypatch):
    """shadow 注入总开关：默认关（字节级零行为变化）、真值开、假值关。orchestrator 与
    review_provider 必须读同一本开关（marker 归因与实际渲染一致的前提）。"""
    monkeypatch.delenv("TOUCHSTONE_SHADOW_INJECTION", raising=False)
    assert L._shadow_injection_enabled() is False                  # 默认关
    for v in ("1", "true", "yes", "on", "TRUE", "Yes"):
        monkeypatch.setenv("TOUCHSTONE_SHADOW_INJECTION", v)
        assert L._shadow_injection_enabled() is True
    for v in ("0", "false", "no", "off", "", "garbage"):
        monkeypatch.setenv("TOUCHSTONE_SHADOW_INJECTION", v)
        assert L._shadow_injection_enabled() is False


def test_orchestrator_review_pr_writes_shadow_to_marker_when_enabled(monkeypatch):
    """post_results 把 shadow_types/shadow_experience_ids 写进 result marker（step3 marker 透传）。
    review_pr 的取值（env 开→shadow_types(store)）由 _shadow_injection_enabled + shadow_types
    单测覆盖；本测锁 marker 字段透传 + 向后兼容（不传→空列表=现状字节级）。用 review_pr 产完整
    risk/findings（0-finding 路径），再单独调 post_results 传 shadow_* 验透传（同 test_e2e_replay 模式）。"""
    from touchstone import orchestrator as orc
    import re
    posted = {}
    monkeypatch.setattr(orc, "gh", lambda m, p, t, data=None, **k:
                        posted.update(body=data["body"]) if (m == "POST" and p.endswith("/comments")) else {})
    monkeypatch.setenv("TOUCHSTONE_SKIP_GATE", "1")            # 跳 gate（聚焦 marker，不测闸）
    pr = {"owner": "o", "repo": "r", "number": 1, "sha": "s", "token": "t",
          "diff": "diff --git a/x b/x\n--- a/x\n+++ b/x\n@@ -1 +1 @@\n-a\n+b\n",
          "pr_agent_output": {"code_suggestions": [], "review": {"key_issues_to_review": []}}}
    out = orc.review_pr(pr, {}, {})                            # 产完整 risk/findings
    posted.clear()
    orc.post_results("o", "r", 1, "s", "t", out["risk"], out["findings"],
                     change_class="low|code|none|none",
                     shadow_types=["PRA-CAND"], shadow_experience_ids=["emphasize:::PRA-CAND"])
    result = json.loads(re.search(r"<!-- touchstone-result: (.*?) -->", posted["body"], re.S).group(1))
    assert result["shadow_types"] == ["PRA-CAND"]
    assert result["shadow_experience_ids"] == ["emphasize:::PRA-CAND"]
    # 向后兼容：不传 shadow_* → 空列表（现状字节级）
    posted.clear()
    orc.post_results("o", "r", 2, "s", "t", out["risk"], out["findings"], change_class="low|code|none|none")
    result2 = json.loads(re.search(r"<!-- touchstone-result: (.*?) -->", posted["body"], re.S).group(1))
    assert result2["shadow_types"] == [] and result2["shadow_experience_ids"] == []


def test_shadow_failure_does_not_wipe_active_injection(monkeypatch):
    """shadow 取值抛异常不能 wipe 已成功取到的 active injection（pr-agent review #117：生产路径
    vs 实验路径失败隔离）。直接测 _collect_injection——shadow_types 抛异常时返回的 injected_types
    仍保留 active 结果、shadow 为空。"""
    from touchstone import orchestrator as orc
    monkeypatch.setattr(L, "load_store", lambda: {"experiences": []})
    monkeypatch.setattr(L, "active_types", lambda s: ["PRA-ACTIVE"])
    monkeypatch.setattr(L, "active_ids", lambda s: ["emphasize:::PRA-ACTIVE"])
    def _boom(s):
        raise RuntimeError("shadow path bug")
    monkeypatch.setattr(L, "shadow_types", _boom)
    monkeypatch.setattr(L, "shadow_ids", lambda s: ["s"])
    monkeypatch.setenv("TOUCHSTONE_SHADOW_INJECTION", "true")
    it, iid, st, sid = orc._collect_injection()
    assert it == ["PRA-ACTIVE"]                                # active 保留（未被 shadow 失败 wipe）
    assert iid == ["emphasize:::PRA-ACTIVE"]
    assert st == [] and sid == []                              # shadow 失败丢弃


# ==================== 盲区2 坏真值检测（B/C/D 信号 → trust_weight；env 默认关 = 零行为变化）====================
# 详见 docs/tfgrpo-self-evolution-design.html 盲区2。坏真值（rubber-stamp 采纳、低权重 reviewer 一键过、
# 极小 diff 却 resolved）污染 TF-GRPO reward；本组锁定三信号的纯函数判据 + trust_weight 数学 + 硬剔除 +
# 默认关的字节级等价。信号 A（系统性低组奖励）循环依赖 reward、需持久化奖励历史，记为后置先决，不在此。
def test_lgtm_only_detected():
    """信号 B：APPROVED 且所有非 bot approve-review 的 body 空/极短(≤max)/仅 LGTM 口头禅 → True。
    非 APPROVED 不算一键过；approve body 有实质内容 → 不 shallow；纯 bot approve（无人类）保守不命中。"""
    bot = "github-actions[bot]"
    shallow = [{"state": "APPROVED", "user": {"login": "alice"}, "body": "LGTM"}]
    assert L._lgtm_only(shallow, "APPROVED", bot) is True
    assert L._lgtm_only(shallow, "CHANGES_REQUESTED", bot) is False   # 非 APPROVED 不算一键过
    substantive = [{"state": "APPROVED", "user": {"login": "alice"},
                    "body": "Auth flow is correct and edge cases are covered."}]  # 实质内容 → 不 shallow
    assert L._lgtm_only(substantive, "APPROVED", bot) is False
    bot_only = [{"state": "APPROVED", "user": {"login": bot}, "body": ""}]
    assert L._lgtm_only(bot_only, "APPROVED", bot) is False           # 无人类 approve → 保守不命中


def test_low_weight_reviewer_detected():
    """信号 C：resolved 发现的 resolver_association ∈ LOW_ASSOCIATIONS(NONE/FIRST_TIME_*/MANNEQUIN) → True。
    MEMBER/OWNER/CONTRIBUTOR 的采纳不算坏真值；未 resolved 的发现不计入（不在采纳集）。"""
    bot = "github-actions[bot]"
    big_diff = "+a\n+b\n+c\n+d\n+e\n+f\n"                            # 6 added → 不触发 D，隔离 C
    fa_none = [{"rule_id": "PRA-X", "resolved": True, "resolver_association": "NONE"}]
    assert L._truth_signals([], fa_none, big_diff, "CHANGES_REQUESTED", bot)["low_weight_reviewer"] is True
    fa_member = [{"rule_id": "PRA-X", "resolved": True, "resolver_association": "MEMBER"}]
    assert L._truth_signals([], fa_member, big_diff, "CHANGES_REQUESTED", bot)["low_weight_reviewer"] is False
    fa_unresolved = [{"rule_id": "PRA-X", "resolved": False, "resolver_association": "NONE"}]
    assert L._truth_signals([], fa_unresolved, big_diff, "CHANGES_REQUESTED", bot)["low_weight_reviewer"] is False


def test_parse_review_threads_reads_authorassociation_field():
    """association 取自评论节点的 authorAssociation（comment 顶层），非 author 子字段——
    GitHub GraphQL 的 Actor 无 association（曾用 author{association} → 整查询 undefinedField 报错、
    崩全部 build_ground_truth）。锁真实 schema 形状，防回退到非法字段。"""
    from touchstone import calibrate as C
    data = {"data": {"repository": {"pullRequest": {"reviewThreads": {"nodes": [
        {"isResolved": True, "resolvedBy": {"login": "alice"},
         "comments": {"nodes": [
             {"author": {"login": "alice"}, "authorAssociation": "MEMBER", "body": "b"}]}}]}}}}}
    parsed = C.parse_review_threads(data)
    assert parsed[0]["comments"][0]["association"] == "MEMBER"        # 读 authorAssociation
    assert parsed[0]["comments"][0]["author"] == "alice"
    # 缺 authorAssociation → 空串（容错，不崩）
    data2 = {"data": {"repository": {"pullRequest": {"reviewThreads": {"nodes": [
        {"isResolved": False, "comments": {"nodes": [
            {"author": {"login": "x"}, "body": "b"}]}}]}}}}}
    assert C.parse_review_threads(data2)[0]["comments"][0]["association"] == ""


def test_resolver_association_excludes_bot_trailing_comment():
    """信号 C 的 resolver 取线程末条【人类】评论的 association——bot 尾评（association 常 NONE，
    属 LOW_ASSOCIATIONS）不污染 resolver 身份。bot 在末位、人类(MEMBER)在前 → resolver=MEMBER。
    修复前取末条(bot)→误判 NONE 触发低权重信号（pr-agent review #120）。"""
    from touchstone import calibrate as C
    bot = "github-actions[bot]"
    threads = C.parse_review_threads({"data": {"repository": {"pullRequest": {"reviewThreads": {"nodes": [
        {"isResolved": True, "resolvedBy": {"login": "member1"},
         "comments": {"nodes": [
             {"author": {"login": "github-actions[bot]"}, "authorAssociation": "NONE",
              "body": "<!-- touchstone-finding: " + json.dumps({"rule_id": "PRA-X"}) + " -->"},
             {"author": {"login": "member1"}, "authorAssociation": "MEMBER", "body": "fixed"},
             {"author": {"login": "github-actions[bot]"}, "authorAssociation": "NONE",
              "body": "bot trailing ack"}]}}]}}}}})
    fa = C.thread_findings(threads, bot)
    assert fa[0]["resolver_association"] == "MEMBER"          # bot 尾评 NONE 被排除，取人类 MEMBER
    # 全 bot 线程（无人类评论）→ resolver 空（不误触发 C）
    threads_allbot = C.parse_review_threads({"data": {"repository": {"pullRequest": {"reviewThreads": {"nodes": [
        {"isResolved": True, "comments": {"nodes": [
            {"author": {"login": "github-actions[bot]"}, "authorAssociation": "NONE",
             "body": "<!-- touchstone-finding: " + json.dumps({"rule_id": "PRA-Y"}) + " -->"}]}}]}}}}})
    fa2 = C.thread_findings(threads_allbot, bot)
    assert fa2[0]["resolver_association"] == ""               # 无人类评论 → resolver 空


def test_tiny_diff_resolved_detected():
    """信号 D：added 行数 < TINY_DIFF_LINES(默认5) 且有 resolved 发现 → True。
    大 diff 即使有 resolved → False；小 diff 但无 resolved → False。"""
    bot = "github-actions[bot]"
    fa_resolved = [{"rule_id": "PRA-X", "resolved": True, "resolver_association": "MEMBER"}]  # MEMBER → 不触发 C
    tiny = "+a\n"                                                    # 1 added line
    assert L._truth_signals([], fa_resolved, tiny, "CHANGES_REQUESTED", bot)["tiny_diff_resolved"] is True
    big = "+a\n+b\n+c\n+d\n+e\n"                                     # 5 added → 5<5 False
    assert L._truth_signals([], fa_resolved, big, "CHANGES_REQUESTED", bot)["tiny_diff_resolved"] is False
    assert L._truth_signals([], [], tiny, "CHANGES_REQUESTED", bot)["tiny_diff_resolved"] is False  # 无 resolved


def test_trust_weight_math(monkeypatch):
    """默认 penalty=0.34 / hard_drop=3：0 信号→1.0、1→0.66、2→0.32、3+→0（硬剔除）。False 信号不计。"""
    monkeypatch.delenv("TOUCHSTONE_TRUTH_PENALTY", raising=False)
    monkeypatch.delenv("TOUCHSTONE_TRUTH_HARD_DROP", raising=False)
    assert L._trust_weight({}) == 1.0
    assert L._trust_weight({"a": True}) == 0.66
    assert L._trust_weight({"a": True, "b": True}) == 0.32
    assert L._trust_weight({"a": True, "b": True, "c": True}) == 0.0   # ≥3 → 硬剔除
    assert L._trust_weight({"a": True, "b": False, "c": False}) == 0.66  # False 不计


def test_truth_quality_disabled_by_default(monkeypatch):
    """env 默认关 → 不算信号、weight 恒 1.0、不剔除：即便该 PR 命中全部坏真值信号也原样保留，
    trust_weight=1.0 / truth_signals={}（与改前字节级一致）。这是零行为变化的安全中间态。"""
    monkeypatch.delenv("TOUCHSTONE_TRUTH_QUALITY", raising=False)
    from touchstone import calibrate as C
    result_marker = "<!-- touchstone-result: " + json.dumps({"findings": [{"rule_id": "PRA-X"}]}) + " -->"
    threads = {"data": {"repository": {"pullRequest": {"reviewThreads": {"nodes": [
        {"isResolved": True, "comments": {"nodes": [
            {"author": {"login": "github-actions[bot]"},
             "body": "<!-- touchstone-finding: " + json.dumps({"rule_id": "PRA-X"}) + " -->"},
            {"author": {"login": "newbie"}, "authorAssociation": "NONE", "body": "fixed"}]}}   # 命中 C（env 开时会三连）
    ]}}}}}

    def fake_gh(path, token, accept="application/vnd.github+json"):
        if "state=closed" in path:
            return [{"number": 1, "title": "t", "merged_at": "x"}]
        if "issues/1/comments" in path:
            return [{"body": result_marker}]
        if "pulls/1/reviews" in path:
            return [{"state": "APPROVED", "user": {"login": "alice"}, "body": "lgtm"}]  # 命中 B
        if "pulls/1/files" in path:
            return [{"filename": "a.py"}]
        if path.endswith("/pulls/1") and accept.endswith("diff"):
            return "+a\n"                                            # 命中 D
        return []
    monkeypatch.setattr(GT, "_gh_get", fake_gh)
    monkeypatch.setattr(C, "gql", lambda q, v, t: threads)
    gt = L.build_ground_truth("o", "r", "tok")
    assert len(gt) == 1                                             # env 关 → 不剔除，保留
    assert gt[0]["trust_weight"] == 1.0                             # 默认 weight，字节级不变
    assert gt[0]["truth_signals"] == {}                             # 默认空 signals


def test_hard_drop_removes_entry(monkeypatch, capsys):
    """env 开：PR#1 命中 3 信号(B+C+D)→weight=0 硬剔除（不 append + 打 [learn] 坏真值硬剔除 stderr）；
    PR#2 仅 B 信号→weight=0.66 保留、携带降权与 signals。证剔除是选择性的（非全量丢）且保留条目带 weight。"""
    from touchstone import calibrate as C
    monkeypatch.setenv("TOUCHSTONE_TRUTH_QUALITY", "1")
    result_marker = "<!-- touchstone-result: " + json.dumps({"findings": [{"rule_id": "PRA-X"}]}) + " -->"
    finding = lambda r: "<!-- touchstone-finding: " + json.dumps({"rule_id": r}) + " -->"
    threads = {
        1: {"data": {"repository": {"pullRequest": {"reviewThreads": {"nodes": [
            {"isResolved": True, "comments": {"nodes": [            # PR#1: resolved by NONE → C
                {"author": {"login": "github-actions[bot]"}, "body": finding("PRA-X")},
                {"author": {"login": "newbie"}, "authorAssociation": "NONE", "body": "fixed"}]}}]}}}}},
        2: {"data": {"repository": {"pullRequest": {"reviewThreads": {"nodes": [
            {"isResolved": False, "comments": {"nodes": [           # PR#2: unresolved → 无 C 无 resolved
                {"author": {"login": "github-actions[bot]"}, "body": finding("PRA-X")}]}},
        ]}}}}},
    }

    def fake_gh(path, token, accept="application/vnd.github+json"):
        if "state=closed" in path:
            return [{"number": 1, "title": "t1", "merged_at": "x"},
                    {"number": 2, "title": "t2", "merged_at": "x"}]
        if "issues/1/comments" in path or "issues/2/comments" in path:
            return [{"body": result_marker}]
        if "pulls/1/reviews" in path or "pulls/2/reviews" in path:
            return [{"state": "APPROVED", "user": {"login": "alice"}, "body": "lgtm"}]  # B
        if "pulls/1/files" in path or "pulls/2/files" in path:
            return [{"filename": "a.py"}]
        if path.endswith("/pulls/1") and accept.endswith("diff"):
            return "+a\n"                                            # PR#1: 1 line + resolved → D
        if path.endswith("/pulls/2") and accept.endswith("diff"):
            return "+a\n+b\n+c\n+d\n+e\n+f\n"                        # PR#2: 6 lines → 非 tiny
        return []
    monkeypatch.setattr(GT, "_gh_get", fake_gh)
    monkeypatch.setattr(C, "gql", lambda q, v, t: threads.get(v["num"], {"data": {}}))
    gt = L.build_ground_truth("o", "r", "tok")
    assert [e["pr_id"] for e in gt] == ["2"]                        # PR#1 硬剔除，只剩 PR#2
    kept = gt[0]
    assert kept["trust_weight"] == 0.66                             # 仅 B → 降权保留
    assert kept["truth_signals"] == {"lgtm_only": True,
                                     "low_weight_reviewer": False,
                                     "tiny_diff_resolved": False}
    err = capsys.readouterr().err
    assert "坏真值硬剔除" in err and "PR#1" in err                  # 剔除诊断打到 stderr（非 _log）


def test_make_gt_entry_trust_weight_default():
    """make_gt_entry 不传 trust_weight → 默认 1.0 + 空 signals（向后兼容：旧调用点字节级不变）；
    显式传 → 透传进条目（供 distill reward 施加）。"""
    e = L.make_gt_entry(1, "o/r", "python", "t", "d", [{"rule_id": "PRA-A"}],
                        {"PRA-A"}, "APPROVED", True)
    assert e["trust_weight"] == 1.0 and e["truth_signals"] == {}
    e2 = L.make_gt_entry(2, "o/r", "python", "t", "d", [], set(), "APPROVED", True,
                         trust_weight=0.32,
                         truth_signals={"lgtm_only": True, "low_weight_reviewer": True})
    assert e2["trust_weight"] == 0.32
    assert e2["truth_signals"] == {"lgtm_only": True, "low_weight_reviewer": True}
