"""自进化评审学习回路（Phase 2）：经验库 + 训练-free 蒸馏 + shadow达标 + 退役 + 注入。
全离线、纯函数；TF-GRPO 的 rollout/语义优势内省以注入的假 llm 离线覆盖，真实 A/B 跑批在你的环境做。"""
import json
import os
import learning_loop as L


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
    assert "PRA-MAINTAINABILITY" in [s.split(":")[1] for s in grad] or "suppress:PRA-MAINTAINABILITY" in grad
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
    if "list the review findings" in sysp:
        return ('[{"finding_type":"PRA-POSSIBLE_BUG","file":"a.py","note":"npe"},'
                '{"finding_type":"PRA-TYPO","file":"a.py","note":"typo"}]')
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
    assert store["experiences"][0]["id"] == "emphasize:PRA-SECURITY"
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
                                         {"outputs": [[{"finding_type": "PRA-SECURITY"}]], "rewards": [0.0]},
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
    import calibrate as C
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
            return [{"body": marker, "user": {"login": "github-actions[bot]"}}]
        if "issues/2/comments" in path:
            return []                                                       # 无 marker → 跳过
        if "pulls/1/reviews" in path:
            return [{"state": "APPROVED", "user": {"login": "alice"}}]
        if "pulls/1/files" in path:
            return [{"filename": "src/a.py"}]
        if path.endswith("/pulls/1") and accept.endswith("diff"):
            return "diff --git a.py"
        return []
    monkeypatch.setattr(L, "_gh_get", fake_gh)
    monkeypatch.setattr(C, "gql", lambda q, v, t: threads_payload if v["num"] == 1 else {"data": {}})

    gt = L.build_ground_truth("o", "r", "tok")
    assert len(gt) == 1                                                     # PR#2 无 marker 被跳过
    entry = gt[0]
    assert entry["pr_id"] == "1" and entry["stack"] == "python"
    assert entry["human_adopted"] == ["PRA-POSSIBLE_BUG"]                   # 人 resolve 的 → 采纳
    assert entry["human_ignored"] == ["PRA-TYPO"]                           # 人没采纳 → 噪声
    assert entry["merged"] is True and entry["human_state"] == "APPROVED"


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


# ---------------- aggregate_ab + 自动 graduate（修复 N2 接线）----------------
def test_make_gt_entry_carries_injected_and_raised():
    ts = [{"rule_id": "PRA-A"}, {"rule_id": "PRA-B"}]
    e = L.make_gt_entry(1, "o/r", "python", "t", "d", ts, {"PRA-A"}, "APPROVED", True,
                        injected_types=["PRA-A", "PRA-C"])
    assert e["raised_types"] == ["PRA-A", "PRA-B"]
    assert e["injected_types"] == ["PRA-A", "PRA-C"]


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


# ---------------- 健壮性：I3 矛盾消解 / I4 退化组 / I2 真迭代 ----------------
def test_render_injection_drops_contradictory_same_type():
    """I3：同 finding_type 的 emphasize + suppress 都 active → 矛盾，两者都不注入。"""
    store = {"experiences": [
        {"finding_type": "PRA-X", "kind": "emphasize", "status": "active", "text": "do X"},
        {"finding_type": "PRA-X", "kind": "suppress",  "status": "active", "text": "dont X"},
        {"finding_type": "PRA-Y", "kind": "emphasize", "status": "active", "text": "do Y"}]}
    inj = L.render_injection(store)
    assert "do Y" in inj                                        # 无冲突的保留
    assert "do X" not in inj and "dont X" not in inj           # 冲突对都丢


def test_distill_semantic_advantage_skips_degenerate_group():
    """I4：所有 rollout 都空（端点全失败等）→ 无可内省对象，跳过避免幻觉式产经验。"""
    pr = {"pr_id": "1", "summary": "s"}
    llm = lambda m: '[{"finding_type":"PRA-A","kind":"emphasize","text":"x"}]'   # 即便 llm 想产，全空组也拦
    assert L.distill_semantic_advantage(pr, {"outputs": [[], []], "rewards": [0.0, 0.0]}, llm) == []


def test_conditioning_text_includes_active_and_candidate():
    """I2：rollout 自条件文本含 active + candidate（区别于 render_injection 只 active）。"""
    store = {"experiences": [
        {"finding_type": "PRA-A", "status": "active",    "text": "active one"},
        {"finding_type": "PRA-B", "status": "candidate", "text": "cand one"},
        {"finding_type": "PRA-C", "status": "retired",   "text": "gone"}]}
    txt = L._conditioning_text(store)
    assert "active one" in txt and "cand one" in txt and "gone" not in txt
    assert L._conditioning_text({"experiences": []}) == ""


def test_distill_via_llm_iterates_across_epochs():
    """I2：epochs>1 不崩、仍返回候选；多轮用工作库（active+candidate）自条件。"""
    def fake_llm(messages):
        sysp, user = messages[0]["content"], messages[1]["content"]
        if "emphasize|suppress" in sysp:                                  # distill 步
            return '[{"finding_type":"PRA-A","kind":"emphasize","text":"keep A"}]'
        return '[{"finding_type":"PRA-A"}]' if "variant 0" in user \
            else '[{"finding_type":"PRA-Z"}]'                             # variant1 报噪声 → 奖励不同
    gt = [{"pr_id": "1", "summary": "s", "diff": "d", "human_adopted": ["PRA-A"]}]
    cands = L._distill_via_llm(gt, {"experiences": []}, llm=fake_llm, group_size=2, epochs=3)
    assert len(cands) == 1 and cands[0]["finding_type"] == "PRA-A"        # 跨 3 轮去重仍 1 条
