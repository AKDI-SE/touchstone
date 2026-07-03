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


def test_scope_placeholder_template_does_not_fire(rule_index):
    """未填的 pr.yaml 模板（scope 为 <...> 占位符）不应刷屏 SCOPE-001——
    与 SEC-001 豁免测试文件同类：系统不应因自己的模板/夹具产生假阳性。"""
    diff = build_diff([("src/a.py", ["x = 1"], True), ("docs/b.md", ["y"], True)])
    contract = {"scope": ["<path/glob，如 src/parser/**>"]}   # pr.yaml 模板里的占位符
    finds = cc.check_contract_consistency(diff, contract, rule_index)
    assert not any(f["rule_id"] == "SCOPE-001" for f in finds)


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


# ---------------- SEC-001：硬编码密钥/凭据扫描（确定性、离线）----------------
def test_sec001_detects_hardcoded_secrets(rule_index):
    diff = build_diff([("src/api/auth.py", [
        'AWS_KEY = "AKIAIOSFODNN7EXAMPLE"',
        'token = "ghp_abcdefghijklmnopqrstuvwxyz0123456789AB"',   # 36 chars after ghp_
        'api_key = "AIzaSyA" + "B" * 29',                        # Google key 形状
    ], True)])
    finds = cc.check_contract_consistency(diff, {}, rule_index)
    sec = [f for f in finds if f["rule_id"] == "SEC-001"]
    assert sec and all(f["category"] == "security" for f in sec)
    # 注意：上面的占位值会被 _PLACEHOLDER 过滤；用真值再验一次
    diff2 = build_diff([("src/c.py", ['TOKEN = "sk-proj-abcd1234efgh5678ijkl9012mnop3456"'], True)])
    finds2 = cc.check_contract_consistency(diff2, {}, rule_index)
    assert any(f["rule_id"] == "SEC-001" for f in finds2)


def test_sec001_detects_pem_private_key(rule_index):
    diff = build_diff([("deploy/key.pem", ["-----BEGIN RSA PRIVATE KEY-----", "MIIE..."], True)])
    finds = cc.check_contract_consistency(diff, {}, rule_index)
    assert any(f["rule_id"] == "SEC-001" for f in finds)


def test_sec001_skips_placeholders(rule_index):
    diff = build_diff([("src/c.py", [
        'api_key = "your_api_key_here"',
        'password = "example-password"',
        'token = "<replace-me>"',
    ], True)])
    finds = cc.check_contract_consistency(diff, {}, rule_index)
    assert not any(f["rule_id"] == "SEC-001" for f in finds)


def test_sec002_injection_not_built_in(rule_index):
    """SEC-002（SQL/命令注入）依赖外部 SAST，内置扫描器不检出——锁死边界。"""
    diff = build_diff([("src/q.py", ['sql = "SELECT * FROM u WHERE n=\'" + name + "\'"'], True)])
    finds = cc.check_contract_consistency(diff, {}, rule_index)
    assert not any(f["rule_id"] == "SEC-002" for f in finds)


def test_sec001_skips_test_file_fixtures(rule_index):
    """测试文件里的密钥是故意夹具（测扫描器本身），不据此阻断——兑现『宁可漏不误拦』。"""
    diff = build_diff([("tests/test_secrets.py",
                        ['token = "ghp_abcdefghijklmnopqrstuvwxyz0123456789AB"'], True)])
    finds = cc.check_contract_consistency(diff, {}, rule_index)
    assert not any(f["rule_id"] == "SEC-001" for f in finds)


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
