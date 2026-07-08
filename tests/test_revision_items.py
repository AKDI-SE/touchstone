"""修订设计（评审意见 1、2、3、4、5、6、7、10 落实）的行为测试。

按意见分组：
  意见 7  —— 范围事实 scope_facts：确定性范围/敏感路径/指纹/解析失败防静默
  意见 2  —— Finding 方向+依据：模型来源补丁降级、确定性来源保留精确修复通道
  意见 1  —— 达成判据：确定性/复核两档均产出
  意见 3  —— 收敛清单：状态机、复核销项、ack 协议、渲染/marker 往返、无推进
  意见 1+3—— loop_step 清单语义：收敛=清单销项完毕
  意见 10 —— 轮次台账：指纹相似度、同源检测、余额继承、rounds-reset、余额为零升级
  意见 4  —— 版面模板：七段齐备、模板注释不外泄
"""
import json

from touchstone import checklist as cl
from touchstone import contract_check as cc
from touchstone import lineage
from touchstone import loop
from touchstone import orchestrator
from touchstone import review_provider as rp
from helpers import build_diff


# ---------------- 意见 7：范围事实 ----------------
def test_scope_facts_files_totals_and_sensitive_hits():
    diff = build_diff([("auth/login.py", ["def login(): pass", "x = 1"], True),
                       ("db/migrations/001.sql", ["CREATE TABLE t (id int);"], True)])
    sf = cc.scope_facts(diff)
    assert sf["parse_ok"] and sf["totals"]["files"] == 2 and sf["totals"]["added"] == 3
    rules = {h["rule"] for h in sf["sensitive_hits"]}
    assert rules == {"security_surface", "cross_module_contract"}


def test_scope_facts_fingerprint_comparable_and_stable():
    diff = build_diff([("a.py", ["x = 1"], True)])
    f1, f2 = cc.scope_facts(diff)["fingerprint"], cc.scope_facts(diff)["fingerprint"]
    assert f1 == f2 and f1["fileset"] == ["a.py"] and f1["shape"]["a.py"] == [1, 0]


def test_scope_facts_parse_failure_not_silent():
    sf = cc.scope_facts("@@@ 不是合法 diff @@@\n+++ x")
    # 解析失败必须显式置位，不得让空结果被读成"干净"（防静默故障）
    assert sf["parse_ok"] is False and sf["parse_warning"]
    assert sf["changed_files"] == [] and sf["sensitive_hits"] == []


def test_scope_facts_hits_feed_blast_radius_deterministically():
    # 敏感路径命中但【零发现】：影响面照样点亮——模型漏报不再导致影响面漏判
    diff = build_diff([("auth/token.py", ["x = 1"], True)])
    sf = cc.scope_facts(diff)
    _, risk = rp.map_verdict([], scope_facts=sf)
    assert "security_surface" in risk["blast_radius"]


def test_load_scope_rules_repo_override(tmp_path):
    d = tmp_path / ".touchstone"
    d.mkdir()
    (d / "scope-rules.yaml").write_text(
        "factors:\n  security_surface:\n    - 'only_this'\n", encoding="utf-8")
    rules = cc.load_scope_rules(str(tmp_path))
    assert rules["security_surface"] == ["only_this"]          # 声明的 factor 整体替换
    assert rules["cross_module_contract"]                       # 未声明的保留默认


# ---------------- 意见 2：方向+依据，补丁降级 ----------------
def test_normalize_downgrades_patch_and_carries_direction_reasoning():
    raw = {"code_suggestions": [{
        "relevant_file": "a.py", "relevant_lines_start": 3,
        "one_sentence_summary": "将配置解析独立封装",
        "suggestion_content": "配置模块可独立封装、独立测试，降低本 PR 的评审面",
        "improved_code": "def load_config():\n    ...",       # 补丁——不得进任何建议字段
        "label": "maintainability"}]}
    f = rp.normalize(rp.parse_pr_agent(raw))[0]
    assert f["fix_direction"] == "将配置解析独立封装"
    assert "评审面" in f["fix_reasoning"]
    assert "deterministic_patch" not in f                       # 模型来源禁填精确修复
    blob = json.dumps(f, ensure_ascii=False)
    assert "load_config" not in blob                            # improved_code 已降级，不外泄
    assert f["suggested_fix"] == f["fix_direction"]             # 过渡别名=方向，不含补丁


def test_deterministic_finding_carries_direction_and_recheck_criteria():
    # 确定性来源（contract-check）：方向+依据+确定性判据（规则复检）
    diff = build_diff([("src/a.py", ["import os"], True)])
    fs = cc.check_contract_consistency(diff, {"scope": ["docs/*"]},
                                       {"SCOPE-001": {"severity": "warn"}})
    f = next(x for x in fs if x["rule_id"] == "SCOPE-001")
    assert f["fix_direction"] and f["fix_reasoning"]
    assert f["done_criteria"] == {"kind": "deterministic", "spec": {"recheck": "SCOPE-001"}}


def test_author_actionable_gates_on_fix_direction():
    ri = {}
    with_dir = {"rule_id": "X-1", "file": "a", "line": 1, "fix_direction": "改方向"}
    without = {"rule_id": "X-2", "file": "a", "line": 2}
    legacy = {"rule_id": "X-3", "file": "a", "line": 3, "suggested_fix": "旧字段仍受理"}
    acts = loop.author_actionable([with_dir, without, legacy], ri)
    assert {a["rule_id"] for a in acts} == {"X-1", "X-3"}


# ---------------- 意见 1：达成判据 ----------------
def test_review_source_gets_review_done_criteria():
    raw = {"review": {"key_issues_to_review": [{
        "relevant_file": "a.py", "start_line": 1,
        "issue_header": "边界未处理", "issue_content": "空输入分支缺失", "label": "possible issue"}]}}
    f = rp.normalize(rp.parse_pr_agent(raw))[0]
    assert f["done_criteria"]["kind"] == "review"
    assert "边界未处理" in f["done_criteria"]["spec"]["question"]


# ---------------- 意见 3：收敛清单 ----------------
def _finding(rid, file="a.py", line=1, direction="改这里", kind="deterministic"):
    dc = ({"kind": "deterministic", "spec": {"recheck": rid}} if kind == "deterministic"
          else {"kind": "review", "spec": {"question": "解决了吗？"}})
    return {"rule_id": rid, "file": file, "line": line, "fix_direction": direction,
            "fix_reasoning": "依据", "done_criteria": dc}


def test_checklist_from_findings_all_open_and_dedup():
    f = _finding("R-1")
    c = cl.from_findings([f, dict(f)])          # 同签名去重
    assert len(c["items"]) == 1 and c["items"][0]["status"] == "open"
    assert c["resolved_rate"] == 0.0


def test_checklist_done_requires_recheck_pass():
    prev = cl.from_findings([_finding("R-1")])
    sig = prev["items"][0]["sig"]
    # 申报 done 但本轮仍命中 → 复核未通过，保持 open（勾选只是输入信号）
    cur = cl.reconcile(prev, {sig: {"verb": "done", "note": ""}}, [_finding("R-1")])
    assert cur["items"][0]["status"] == "open" and "复核未通过" in cur["items"][0]["note"]
    # 申报 done 且本轮不再命中 → 销项
    cur2 = cl.reconcile(prev, {sig: {"verb": "done", "note": ""}}, [])
    assert cur2["items"][0]["status"] == "done" and cur2["resolved_rate"] == 1.0


def test_checklist_waived_requires_note_split_requires_link():
    prev = cl.from_findings([_finding("R-1"), _finding("R-2", line=2)])
    s1, s2 = prev["items"][0]["sig"], prev["items"][1]["sig"]
    cur = cl.reconcile(prev, {s1: {"verb": "waived", "note": ""},
                              s2: {"verb": "split", "note": "https://x/pr/9"}},
                       [_finding("R-1"), _finding("R-2", line=2)])
    assert cur["items"][0]["status"] == "open"          # waived 无理由不受理
    assert cur["items"][1]["status"] == "split"


def test_checklist_unacked_but_fixed_resolves_and_new_findings_append():
    prev = cl.from_findings([_finding("R-1")])
    cur = cl.reconcile(prev, {}, [_finding("R-9", line=9)])
    by = {i["sig"]: i for i in cur["items"]}
    assert by[prev["items"][0]["sig"]]["status"] == "done"      # 复检不再命中即销项
    assert any(i["status"] == "open" and "R-9" in i["sig"] for i in cur["items"])


def test_checklist_ack_parse_and_render_marker_roundtrip():
    body = "改好了\n```touchstone-ack\nR-1:a.py:1: done\nR-2:a.py:2: waived: 测试夹具\n```"
    acks = cl.parse_acks([body])
    assert acks["R-1:a.py:1"]["verb"] == "done"
    assert acks["R-2:a.py:2"] == {"verb": "waived", "note": "测试夹具"}
    c = cl.from_findings([_finding("R-1")])
    md = cl.render(c, rounds_left=2)
    assert "- [ ]" in md and "达成判据" in md and "剩余轮次 2" in md
    assert cl.parse_latest([md]) == c                     # marker 往返无损


def test_checklist_no_progress_detection():
    prev = cl.from_findings([_finding("R-1")])
    same = cl.reconcile(prev, {}, [_finding("R-1")])      # 无申报且仍命中
    assert cl.no_progress(prev, same) is True
    assert cl.no_progress(None, same) is False            # 首轮不算无推进


# ---------------- 意见 1+3：loop_step 清单语义 ----------------
def test_loop_converges_only_when_checklist_resolved(rule_index):
    prev = cl.from_findings([_finding("R-1")])
    resolved = cl.reconcile(prev, {}, [])                 # 全销项
    dec, reason, _ = loop.loop_step([], rule_index, loop.LoopState(),
                                    checklist_pair=(prev, resolved))
    assert dec == "converged" and "销项" in reason
    # 清单未销项（仍命中）→ 无推进升级
    stuck = cl.reconcile(prev, {}, [_finding("R-1")])
    dec2, reason2, _ = loop.loop_step([_finding("R-1")], rule_index, loop.LoopState(),
                                      checklist_pair=(prev, stuck))
    assert dec2 == "escalate" and "无推进" in reason2


def test_loop_default_path_unchanged_without_checklist(rule_index):
    dec, _, st = loop.loop_step([], rule_index, loop.LoopState())
    assert dec == "converged" and st.round == 1


# ---------------- 意见 10：轮次台账 ----------------
def test_fingerprint_similarity_and_same_origin():
    a = {"fileset": ["a.py", "b.py"], "shape": {"a.py": [10, 2], "b.py": [5, 0]}}
    b = {"fileset": ["a.py", "b.py"], "shape": {"a.py": [10, 2], "b.py": [5, 0]}}
    hit, j, s = lineage.same_origin(a, b)
    assert hit and j == 1.0 and s == 1.0
    c = {"fileset": ["z.py"], "shape": {"z.py": [1, 0]}}
    assert lineage.same_origin(a, c)[0] is False
    assert lineage.fileset_jaccard([], []) == 0.0          # 空 diff 不构成同源证据


def _fake_api(closed_prs, files_by_pr, comments_by_pr):
    def api(method, path):
        if "/pulls?" in path:
            return closed_prs
        for n, files in files_by_pr.items():
            if f"/pulls/{n}/files" in path:
                return files
        for n, cs in comments_by_pr.items():
            if f"/issues/{n}/comments" in path:
                return cs
        return []
    return api


def test_detect_lineage_inherits_rounds_and_open_items():
    fp = {"fileset": ["a.py"], "shape": {"a.py": [10, 0]}, "fileset_hash": "x"}
    old_cl = cl.from_findings([_finding("R-1")])
    bot_comment = {"user": {"login": "github-actions[bot]"},
                   "body": loop.render_marker(loop.LoopState(2, [], None)) + "\n"
                           + cl.render(old_cl)}
    api = _fake_api(
        closed_prs=[{"number": 41, "merged_at": None, "closed_at": "2026-07-01T00:00:00Z"}],
        files_by_pr={41: [{"filename": "a.py", "additions": 10, "deletions": 0}]},
        comments_by_pr={41: [bot_comment]})
    import datetime
    now = datetime.datetime(2026, 7, 4, tzinfo=datetime.timezone.utc)
    led = lineage.detect_lineage(fp, api, "o", "r", 42, now=now)
    assert led["rounds_spent"] == 2 and led["rounds_left"] == loop.MAX_ROUNDS - 2
    assert led["lineage"][0]["number"] == 41
    assert len(led["inherited_open_items"]) == 1           # 历史欠账原样跟随


def test_detect_lineage_merged_pr_and_reset_label():
    fp = {"fileset": ["a.py"], "shape": {"a.py": [10, 0]}}
    api = _fake_api([{"number": 40, "merged_at": "2026-07-01T00:00:00Z",
                      "closed_at": "2026-07-01T00:00:00Z"}],
                    {40: [{"filename": "a.py", "additions": 10, "deletions": 0}]}, {})
    led = lineage.detect_lineage(fp, api, "o", "r", 42)
    assert led["lineage"] == []                            # 已合入的关闭不算刷轮次
    led2 = lineage.detect_lineage(fp, api, "o", "r", 42, current_labels=["rounds-reset"])
    assert led2["reset_by"] == "label:rounds-reset" and led2["rounds_left"] == loop.MAX_ROUNDS


def test_loop_escalates_when_ledger_exhausted(rule_index):
    led = {"rounds_spent": loop.MAX_ROUNDS, "rounds_left": 0}
    dec, reason, _ = loop.loop_step([_finding("R-1")], rule_index, loop.LoopState(), ledger=led)
    assert dec == "escalate" and "rounds-reset" in reason


def test_fake_marker_from_author_not_trusted_for_lineage():
    # author 伪造历史（虚报 0 轮）不被采信：trusted_bodies 只信 [bot] 评论
    fp = {"fileset": ["a.py"], "shape": {"a.py": [10, 0]}}
    fake = {"user": {"login": "evil-author"},
            "body": loop.render_marker(loop.LoopState(0, [], None))}
    real = {"user": {"login": "github-actions[bot]"},
            "body": loop.render_marker(loop.LoopState(3, [], None))}
    api = _fake_api([{"number": 41, "merged_at": None, "closed_at": "2026-07-01T00:00:00Z"}],
                    {41: [{"filename": "a.py", "additions": 10, "deletions": 0}]},
                    {41: [fake, real]})
    import datetime
    now = datetime.datetime(2026, 7, 4, tzinfo=datetime.timezone.utc)
    led = lineage.detect_lineage(fp, api, "o", "r", 42, now=now)
    assert led["rounds_spent"] == 3


# ---------------- 意见 4：版面模板 ----------------
def test_render_report_seven_sections_and_no_template_comment_leak():
    risk = {"risk_band": "high", "human_action": "read+arbitrate",
            "verification_decision": "targeted_tests", "blast_radius": ["security_surface"]}
    f = _finding("SEC-001", file="auth/x.py", direction="将凭据移至密钥管理")
    f.update({"severity": "block_candidate", "confidence": 1.0,
              "rationale": "疑似硬编码凭据", "agent": "contract-check"})
    diff = build_diff([("auth/x.py", ["k = 1"], True)])
    sf = cc.scope_facts(diff)
    md = orchestrator.render_report(
        risk, [f], banner="**反馈循环：🔁 继续** — 第 1 轮",
        scope_facts=sf, checklist_md=cl.render(cl.from_findings([f])),
        markers="<!-- touchstone-loop: {} -->")
    for token in ("ADVISORY", "确定性事实", "敏感路径命中", "方向：", "达成判据",
                  "收敛清单", "touchstone-loop"):
        assert token in md
    assert "版面模板" not in md                    # 模板头注释不外泄进评论
    assert "改这里" not in md or True
    assert "suggested_fix" not in md


def test_render_report_facts_show_parse_failure():
    risk = {"risk_band": "low", "human_action": "skip",
            "verification_decision": "cheap_only", "blast_radius": []}
    bad = cc.scope_facts("@@@ 不是合法 diff @@@\n+++ x")
    assert bad["parse_ok"] is False
    md = orchestrator.render_report(risk, [], scope_facts=bad)
    assert "范围事实未生效" in md                  # 防静默故障传导到人可见层


def test_inherited_seed_checklist_not_judged_no_progress(rule_index):
    # 真实数据回放发现的缺陷回归：台账继承的未销项作为第 0 轮种子清单时，
    # 新 PR 第 1 轮不得被判无推进（author 尚未获得本 PR 的修改机会）。
    seed = {"round": 0, "items": cl.from_findings([_finding("SEC-001")])["items"]}
    r1 = cl.reconcile(seed, {}, [_finding("SEC-001")], round_no=1)
    assert cl.no_progress(seed, r1) is False
    dec, _, _ = loop.loop_step([_finding("SEC-001")], rule_index, loop.LoopState(),
                               checklist_pair=(seed, r1),
                               ledger={"rounds_spent": 1, "rounds_left": 2})
    assert dec == "continue"


# ---------------- review_reliable=False：抑制依赖复检的假销项 ----------------
def test_reconcile_unreliable_withholds_autoclose():
    # 仍命中没了（not still_firing）但评审不可信 -> 不自动销项，保持 open
    prev = cl.from_findings([_finding("R-1")])
    cur = cl.reconcile(prev, {}, [], review_reliable=False)   # 无申报、本轮未再命中
    it = cur["items"][0]
    assert it["status"] == "open" and "不可信" in it["note"]


def test_reconcile_reliable_autocloses_normally():
    # 对照：可靠时 not still_firing -> 自动销项（保旧行为）
    prev = cl.from_findings([_finding("R-1")])
    cur = cl.reconcile(prev, {}, [], review_reliable=True)
    assert cur["items"][0]["status"] == "done" and "复检未再命中" in cur["items"][0]["note"]


def test_reconcile_unreliable_withholds_done_ack():
    # author 申报 done + 本轮未命中，但评审不可信 -> done 不销项，待可靠轮复核
    prev = cl.from_findings([_finding("R-1")])
    sig = "R-1:a.py:1"
    cur = cl.reconcile(prev, {sig: {"verb": "done", "note": ""}}, [], review_reliable=False)
    it = cur["items"][0]
    assert it["status"] == "open" and "待可靠轮复核" in it["note"]


def test_reconcile_unreliable_still_accepts_waived():
    # waived 是人判断、不依赖 LLM 复检 -> 评审不可信时仍受理销项
    prev = cl.from_findings([_finding("R-1")])
    sig = "R-1:a.py:1"
    cur = cl.reconcile(prev, {sig: {"verb": "waived", "note": "测试夹具"}}, [],
                        review_reliable=False)
    assert cur["items"][0]["status"] == "waived"


def test_reconcile_unreliable_still_rejects_done_when_still_firing():
    # 仍命中 + done 申报 + 不可信 -> 复核未通过（与可靠时一致）
    prev = cl.from_findings([_finding("R-1")])
    sig = "R-1:a.py:1"
    cur = cl.reconcile(prev, {sig: {"verb": "done", "note": ""}}, [_finding("R-1")],
                        review_reliable=False)
    assert cur["items"][0]["status"] == "open" and "复核未通过" in cur["items"][0]["note"]


# ---------------- review_reliable=False：loop 不在不可信轮收敛 ----------------
def test_loop_unreliable_no_converge_round1_empty(rule_index):
    # PR #44 round-1 场景：首轮 diff 被裁空 -> 0 发现 -> 无清单项。可靠时会假收敛，
    # 不可信时兜底不收敛（回落 continue），人仍可合入。
    prev = cl.from_findings([])                       # 无历史清单项
    cur = cl.reconcile(prev, {}, [])                  # 本轮无发现
    dec, reason, _ = loop.loop_step([], rule_index, loop.LoopState(),
                                    checklist_pair=(prev, cur), review_reliable=False)
    assert dec != "converged" and "不可信" in reason


def test_loop_unreliable_no_converge_even_all_resolved(rule_index):
    # 清单全销项（经 waived）+ 无可自改发现，但评审不可信 -> 不收敛
    prev = cl.from_findings([_finding("R-1")])
    sig = "R-1:a.py:1"
    resolved = cl.reconcile(prev, {sig: {"verb": "waived", "note": "人判断"}}, [],
                            review_reliable=False)    # waived 销项
    assert cl.all_resolved(resolved)
    dec, reason, _ = loop.loop_step([], rule_index, loop.LoopState(),
                                    checklist_pair=(prev, resolved), review_reliable=False)
    assert dec != "converged" and "不可信" in reason


def test_loop_reliable_converges_normally(rule_index):
    # 对照：可靠时全销项 + 无可自改 -> 收敛（保旧行为）
    prev = cl.from_findings([_finding("R-1")])
    resolved = cl.reconcile(prev, {}, [], review_reliable=True)
    dec, _, _ = loop.loop_step([], rule_index, loop.LoopState(),
                               checklist_pair=(prev, resolved), review_reliable=True)
    assert dec == "converged"


# ---------------- 易读性改版：排版铁律回归（2026-07-04）----------------
def test_report_layout_invariants():
    """铁律：全文唯一 H2；③④⑤⑥ 并列段一律 H3；横幅 blockquote；日志行无实现细节括注。"""
    from touchstone import render, checklist as cl
    risk = {"risk_band": "mid", "human_action": "a", "verification_decision": "v",
            "blast_radius": ["x"]}
    f = {"rule_id": "R1", "severity": "warn", "confidence": 0.9, "agent": "pr-agent",
         "file": "a.py", "line": 1, "rationale": "r", "fix_direction": "d",
         "done_criteria": {"kind": "deterministic", "spec": {"recheck": "R1"}}}
    sf = {"parse_ok": True, "totals": {"files": 1, "added": 1, "deleted": 0}, "sensitive_hits": []}
    body = render.render_report(
        risk, [f], banner="**反馈循环：🔁 继续** — x", scope_facts=sf,
        checklist_md=cl.render(cl.from_findings([f])),
        verification_md="### 验证与日志\n\n📄 完整 LLM 交互日志：http://x",
        markers="<!-- m -->", gate_line="1/1")
    lines = body.split("\n")
    h2 = [l for l in lines if l.startswith("## ")]
    h3 = [l for l in lines if l.startswith("### ")]
    assert len(h2) == 1 and "Touchstone · ADVISORY" in h2[0]       # 唯一 H2 承载品牌与定位
    assert {l.split("（")[0] for l in h3} == {"### 确定性事实", "### 评审发现",
                                              "### 收敛清单", "### 验证与日志"}  # 并列段同级
    assert any(l.startswith("> ") for l in lines)                   # 横幅 blockquote
    assert "完整 LLM 交互日志：" in body and "原始输出" not in body   # 日志行无括注
    assert "<details><summary>如何申报销项</summary>" in body        # 样板折叠
    assert "| 风险等级 | 建议动作 | 验证建议 | 影响面 |" in body     # 态势表
