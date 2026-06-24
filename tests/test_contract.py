"""确定性契约核对 + 回贴渲染（orchestrator.anchor_inline）。
评审由 PR-Agent 承担（见 test_review_provider.py）；本文件只覆盖
PR-Agent 不做的确定性部分：契约一致性、无 manifest 的 diff 检查、内联锚定。"""
import orchestrator
import contract_check as cc
from helpers import build_diff


# ---------------- contract_check ----------------
def test_parse_diff_collects_files_and_added():
    diff = build_diff([("a/x.py", ["def f(): pass", "return 1"], True)])
    files, added = cc.parse_diff(diff)
    assert "a/x.py" in files
    assert any("def f()" in text for _ln, text in added["a/x.py"])


def test_scope_violation_fires(rule_index):
    diff = build_diff([("b/out.py", ["x = 1"], True)])
    contract = {"scope": ["a/**"]}
    finds = cc.check_contract_consistency(diff, contract, rule_index)
    assert any(f["rule_id"] == "SCOPE-001" for f in finds)


def test_tests_claimed_but_absent_fires(rule_index):
    diff = build_diff([("a/x.py", ["x = 1"], True)])
    contract = {"scope": ["a/**"], "tests_added": ["test_x.py"]}
    finds = cc.check_contract_consistency(diff, contract, rule_index)
    assert any(f["rule_id"] == "TEST-001" for f in finds)


def test_reuse_claimed_but_absent_fires(rule_index):
    diff = build_diff([("a/x.py", ["x = 1"], True)])
    contract = {"scope": ["a/**"], "reused_components": ["AgentRail"]}
    finds = cc.check_contract_consistency(diff, contract, rule_index)
    assert any(f["rule_id"] == "DUP-001" for f in finds)


def test_no_false_positive_when_all_satisfied(rule_index):
    diff = build_diff([
        ("a/x.py", ["import AgentRail", "x = 1"], True),
        ("a/test_x.py", ["def test_x(): assert True"], True),
    ])
    contract = {"scope": ["a/**"], "tests_added": ["test_x.py"], "reused_components": ["AgentRail"]}
    finds = cc.check_contract_consistency(diff, contract, rule_index)
    assert finds == []


def test_standards_has_java_rules(rule_index):
    java = [rid for rid, r in rule_index.items() if r.get("applies_to") == ["java"]]
    assert set(java) == {"SPR-DI-001", "SPR-TX-001", "SPR-VAL-001",
                         "JAVA-EQ-001", "JAVA-EXC-001", "JAVA-LOG-001"}
    assert sum(rule_index[r]["machine_checkable"] for r in java) >= 4


# ---------------- 内联锚定（删除行/超界行降级）----------------
_ANCHOR_DIFF = (
    "diff --git a/app/x.py b/app/x.py\n--- a/app/x.py\n+++ b/app/x.py\n"
    "@@ -1,2 +1,4 @@\n def f():\n-    return 1\n+    return 2\n+    return 3\n+    return 4\n"
)


def test_anchor_inline_on_added_line():
    out = orchestrator.anchor_inline(
        [{"rule_id": "OE-001", "agent": "a", "file": "app/x.py", "line": 3,
          "rationale": "r", "suggested_fix": "s"}], _ANCHOR_DIFF)
    assert len(out) == 1 and out[0]["line"] == 3 and out[0]["side"] == "RIGHT"
    assert "原指" not in out[0]["body"]


def test_anchor_inline_snaps_offdiff_line():
    out = orchestrator.anchor_inline(
        [{"rule_id": "OE-001", "agent": "a", "file": "app/x.py", "line": 99,
          "rationale": "r", "suggested_fix": "s"}], _ANCHOR_DIFF)
    assert out[0]["line"] == 4 and "（原指 :99）" in out[0]["body"]


def test_anchor_inline_skips_file_without_added_lines():
    out = orchestrator.anchor_inline(
        [{"rule_id": "CTR-001", "agent": "a", "file": "deleted/only.py", "line": 5,
          "rationale": "r", "suggested_fix": "s"}], _ANCHOR_DIFF)
    assert out == []


# ---------------- 无 manifest 的纯 diff 检查：代码改动无测试 ----------------
def test_check_untested_code_fires(rule_index):
    diff = ("diff --git a/app/y.py b/app/y.py\n--- /dev/null\n+++ b/app/y.py\n"
            "@@ -0,0 +1,2 @@\n+def g():\n+    return 1\n")
    out = cc.check_contract_consistency(diff, {}, rule_index)
    ids = [f["rule_id"] for f in out]
    assert "TEST-001" in ids
    t = next(f for f in out if f["rule_id"] == "TEST-001")
    assert t["severity"] == "warn" and t["confidence"] == 0.9


def test_check_untested_code_silent_when_tests_present(rule_index):
    diff = ("diff --git a/app/y.py b/app/y.py\n--- /dev/null\n+++ b/app/y.py\n"
            "@@ -0,0 +1 @@\n+def g(): return 1\n"
            "diff --git a/tests/test_y.py b/tests/test_y.py\n--- /dev/null\n+++ b/tests/test_y.py\n"
            "@@ -0,0 +1 @@\n+def test_g(): assert g()==1\n")
    out = cc.check_contract_consistency(diff, {}, rule_index)
    assert "TEST-001" not in [f["rule_id"] for f in out]


def test_check_untested_code_silent_for_docs_only(rule_index):
    diff = ("diff --git a/README.md b/README.md\n--- a/README.md\n+++ b/README.md\n"
            "@@ -1 +1,2 @@\n doc\n+more doc\n")
    out = cc.check_contract_consistency(diff, {}, rule_index)
    assert out == []


# ---------------- check_reuse 精确成员匹配（消除子串误碰）----------------
def test_check_reuse_no_substring_false_pass(rule_index):
    added = {"a.py": [(1, "x = obj.get_profile_v2()")]}
    out = cc.check_reuse(added, ["svc.get_profile"], rule_index)
    assert "DUP-001" in [f["rule_id"] for f in out]


def test_check_reuse_silent_on_real_reuse(rule_index):
    added = {"a.py": [(1, "x = svc.get_profile()")]}
    assert cc.check_reuse(added, ["svc.get_profile"], rule_index) == []


# ---------------- parse_diff 对抗性边界 ----------------
def test_parse_diff_content_with_atat_not_treated_as_hunk():
    diff = ("diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n"
            "@@ -1,1 +1,2 @@\n x = 1\n+s = \"@@ not a header @@\"\n")
    files, added = cc.parse_diff(diff)
    assert files == {"a.py"}
    assert added["a.py"] == [(2, 's = "@@ not a header @@"')]


def test_parse_diff_content_looking_like_file_header():
    diff = ("diff --git a/a.py b/a.py\n--- /dev/null\n+++ b/a.py\n"
            "@@ -0,0 +1 @@\n+text = \"+++ b/evil.py\"\n")
    files, added = cc.parse_diff(diff)
    assert files == {"a.py"}
    assert "evil.py" not in files
    assert added["a.py"] == [(1, 'text = "+++ b/evil.py"')]


def test_parse_diff_multiple_hunks_line_numbers():
    diff = ("diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n"
            "@@ -1,1 +1,2 @@\n c1\n+added10\n"
            "@@ -50,1 +51,2 @@\n c2\n+added52\n")
    _, added = cc.parse_diff(diff)
    nums = [n for n, _ in added["a.py"]]
    assert nums == [2, 52]


def test_parse_diff_fully_deleted_file_not_captured():
    diff = ("diff --git a/gone.py b/gone.py\n--- a/gone.py\n+++ /dev/null\n"
            "@@ -1,1 +0,0 @@\n-was here\n")
    files, _ = cc.parse_diff(diff)
    assert "gone.py" not in files
