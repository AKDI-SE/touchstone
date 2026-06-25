"""质量门禁命门：runner 可插拔 + 重构 regression_only。"""
import os

import pytest
import verify_change as V


# ---------------- select_runner / is_refactor ----------------
def test_select_runner_maven_on_pom(tmp_path):
    (tmp_path / "pom.xml").write_text("<project/>")
    assert V.select_runner(str(tmp_path), []).lang == "maven"


def test_select_runner_maven_on_java(tmp_path):
    assert V.select_runner(str(tmp_path), ["x/Foo.java"]).lang == "maven"


def test_select_runner_python_default(tmp_path):
    assert V.select_runner(str(tmp_path), ["x/foo.py"]).lang == "python"


def test_select_runner_none_for_unsupported_language(tmp_path):
    assert V.select_runner(str(tmp_path), ["x/main.go"]) is None
    assert V.select_runner(str(tmp_path), ["x/app.ts"]) is None
    assert V.select_runner(str(tmp_path), []) is None          # 空改动也 None，不再误判 python


def test_verify_change_unsupported_language_is_neutral(tmp_path):
    res = V.verify_change(str(tmp_path), {}, ["x/main.go"], "b", "h", "targeted_tests",
                          {"base_url": "u", "api_key": "k", "model": "m"}, "")
    assert res.passed is None and res.mode == "unsupported"


def test_is_refactor():
    assert V.is_refactor({}, "refactor(openjiuwen): extract memory runtime rail")
    assert V.is_refactor({"intent": "重构 MemoryRuntimeRail"}, "")
    assert not V.is_refactor({"intent": "add new feature"}, "feat: x")


# ---------------- JaCoCo / PIT 解析 ----------------
def test_jacoco_changed_coverage(tmp_path):
    jd = tmp_path / "mod/target/site/jacoco"
    jd.mkdir(parents=True)
    (jd / "jacoco.xml").write_text(
        '<report><package name="p"><sourcefile name="Foo.java">'
        '<counter type="INSTRUCTION" missed="5" covered="20"/>'
        '<counter type="LINE" missed="2" covered="8"/></sourcefile></package></report>')
    cov = V._jacoco_changed_coverage(str(tmp_path), ["a/p/Foo.java", "b/README.md"])
    assert abs(cov - 0.8) < 1e-9


def test_pit_score(tmp_path):
    pd = tmp_path / "mod/target/pit-reports/202606"
    pd.mkdir(parents=True)
    (pd / "mutations.xml").write_text(
        '<mutations><mutation status="KILLED"/><mutation status="TIMED_OUT"/>'
        '<mutation status="SURVIVED"/></mutations>')
    assert abs(V._pit_score(str(tmp_path)) - 2 / 3) < 1e-9


def test_extract_java_signatures(tmp_path):
    (tmp_path / "Bar.java").write_text("public final class Bar {\n  public void doIt(int x){}\n}\n")
    sig = V._extract_java_signatures(str(tmp_path), ["Bar.java"])
    assert "class Bar" in sig and "method doIt" in sig


# ---------------- regression_only 编排（桩 runner + worktree）----------------
class _FakeRunner:
    lang = "maven"
    supports_spec_blind = False

    def __init__(self, suite=True, cov=0.9, mut=None):
        self._s, self._c, self._m = suite, cov, mut

    def run_suite(self, wd):
        return (self._s, "suite-out")

    def changed_coverage(self, wd, cf, changed_lines=None):
        return self._c

    def mutation(self, wd, cf, test_code=None):
        return self._m

    def extract_interface(self, wd, cf):
        return "iface"

    def run_generated(self, wd, code):
        return (True, "gen-out")

    def cover_generated(self, wd, code, cf, changed_lines=None):
        return self._c


@pytest.fixture
def stub_worktree(monkeypatch, tmp_path):
    monkeypatch.setattr(V, "_worktree", lambda repo, ref: str(tmp_path))
    monkeypatch.setattr(V, "_rm_worktree", lambda repo, d: None)


def test_regression_pass_when_green_and_covered(stub_worktree):
    r = V._verify_regression(".", _FakeRunner(True, 0.9), ["a/Foo.java"], "b", "h", "targeted_tests")
    assert r.passed and r.adequacy.verdict == "adequate" and r.mode == "regression_only"


def test_regression_fail_when_suite_red(stub_worktree):
    r = V._verify_regression(".", _FakeRunner(False, 0.9), ["a/Foo.java"], "b", "h", "targeted_tests")
    assert not r.passed


def test_regression_fail_when_coverage_low(stub_worktree):
    r = V._verify_regression(".", _FakeRunner(True, 0.3), ["a/Foo.java"], "b", "h", "targeted_tests")
    assert not r.passed and r.adequacy.verdict == "inadequate"


# ---------------- 分发：重构 PR → regression_only ----------------
def test_dispatch_refactor_routes_to_regression(monkeypatch, tmp_path):
    hit = {}
    monkeypatch.setattr(V, "_verify_regression",
                        lambda *a, **k: hit.setdefault("y", True) or V.VerificationResult(True, "regression_only"))
    V.verify_change(str(tmp_path), {"intent": "refactor extract"}, ["x.py"], "b", "h",
                    "targeted_tests", {"base_url": "b", "api_key": "k", "model": "m"},
                    "refactor(x): y")
    assert hit.get("y")


def test_cheap_only_passes_without_runner(tmp_path):
    r = V.verify_change(str(tmp_path), {}, ["x.py"], "b", "h", "cheap_only",
                        {"base_url": "b", "api_key": "k", "model": "m"})
    assert r.passed and r.mode == "cheap_only"


# ============================================================================
# #4 质量门禁加固：改动行级覆盖 + Java 独立验收测试生成
# ============================================================================

# ---------------- 改动行级覆盖 ----------------
def test_parse_changed_lines():
    diff = ("diff --git a/x.py b/x.py\n--- a/x.py\n+++ b/x.py\n"
            "@@ -10,0 +11,2 @@\n+    a = 1\n+    b = 2\n"
            "@@ -20,1 +22,1 @@\n-old\n+    c = 3\n")
    cl = V.parse_changed_lines(diff)
    assert cl["x.py"] == {11, 12, 22}


def test_coverage_json_line_ratio():
    cov = {"files": {"x.py": {"executed_lines": [11, 12], "missing_lines": [22]}}}
    # 改动行 11,12,22 都可覆盖；执行到 11,12 → 2/3
    assert abs(V._coverage_json_line_ratio(cov, {"x.py": {11, 12, 22}}) - 2 / 3) < 1e-9
    # 全覆盖
    assert V._coverage_json_line_ratio(cov, {"x.py": {11, 12}}) == 1.0
    # 改动行不在可覆盖集合（如纯注释行）→ 视为 1.0（无可覆盖改动行）
    assert V._coverage_json_line_ratio(cov, {"x.py": {99}}) == 1.0


def test_jacoco_line_ratio(tmp_path):
    import xml.etree.ElementTree as ET
    xml = ('<report><sourcefile name="Foo.java">'
           '<line nr="11" mi="0" ci="3"/><line nr="12" mi="2" ci="0"/>'
           '<line nr="13" mi="0" ci="5"/></sourcefile></report>')
    root = ET.fromstring(xml)
    # 改动行 11,12 → 11 覆盖(ci>0)、12 未覆盖 → 1/2
    assert V._jacoco_line_ratio([root], {"Foo.java": {11, 12}}) == 0.5
    # 改动行 11,13 → 都覆盖 → 1.0
    assert V._jacoco_line_ratio([root], {"Foo.java": {11, 13}}) == 1.0


# ---------------- JUnit 放置 ----------------
def test_place_junit_with_package(tmp_path):
    code = "package com.x.y;\nimport org.junit.jupiter.api.Test;\npublic class FooSpecTest { }\n"
    cname, path = V._place_junit(str(tmp_path), code)
    assert cname == "FooSpecTest"
    assert path.endswith(os.path.join("src", "test", "java", "com", "x", "y", "FooSpecTest.java"))
    assert os.path.exists(path)


def test_place_junit_without_package(tmp_path):
    cname, path = V._place_junit(str(tmp_path), "class BarTest {}\n")
    assert cname == "BarTest"
    assert path.endswith(os.path.join("src", "test", "java", "BarTest.java"))


# ---------------- Java 独立验收测试生成（盲于实现）----------------
def test_generate_spec_blind_junit_prompt(monkeypatch):
    captured = {}

    def stub_llm(messages, **cfg):
        captured["sys"] = messages[0]["content"]
        captured["user"] = messages[1]["content"]
        return "```java\npublic class GenTest {}\n```"

    monkeypatch.setattr(V, "_llm", stub_llm)
    ts = V.generate_spec_blind_tests(["返回非负", "空输入抛异常"], "Foo: method bar()",
                                     {"base_url": "b", "api_key": "k", "model": "test-model"},
                                     framework="junit5")
    assert ts.source == "spec_blind" and ts.author_model == "test-model"
    assert "JUnit 5" in captured["sys"] and "看不到实现" in captured["sys"]
    assert "返回非负" in captured["user"] and "Foo: method bar()" in captured["user"]
    assert "class GenTest" in ts.code


def test_maven_supports_spec_blind():
    assert V.MavenRunner().supports_spec_blind is True


# ---------------- 语言无关独立验收测试分支（桩化端到端）----------------
class _SpecRunner:
    lang = "maven"
    supports_spec_blind = True

    def __init__(self):
        self.n = 0

    def extract_interface(self, wd, cf):
        return "iface"

    def run_generated(self, wd, code):
        self.n += 1
        return (True, "head") if self.n == 1 else (False, "base")   # 1=改后过, 2=改前挂(哨兵成立)

    def cover_generated(self, wd, code, cf, changed_lines=None):
        return 0.9

    def mutation(self, wd, cf, test_code=None):
        return None


def test_spec_blind_branch_language_agnostic(monkeypatch, tmp_path):
    monkeypatch.setattr(V, "select_runner", lambda repo, cf: _SpecRunner())
    monkeypatch.setattr(V, "_worktree", lambda repo, ref: str(tmp_path))
    monkeypatch.setattr(V, "_rm_worktree", lambda repo, d: None)
    monkeypatch.setattr(V, "_changed_lines", lambda *a: {"Foo.java": {11}})
    monkeypatch.setattr(V, "generate_spec_blind_tests",
                        lambda *a, **k: V.AcceptanceTestSet(code="class T{}", source="spec_blind",
                                                            author_model="m"))
    r = V.verify_change(str(tmp_path), {"intent": "add feature", "acceptance_criteria": ["x"]},
                        ["Foo.java"], "b", "h", "targeted_tests",
                        {"base_url": "b", "api_key": "k", "model": "m"}, "feat: x")
    assert r.passed and r.mode == "targeted_tests"
    assert r.adequacy.sentinel_passed is True and r.adequacy.changed_file_coverage == 0.9


# ---------------- 验收规格来源治理（acceptance_criteria 收口）----------------
def test_resolve_acceptance_spec_falls_back_to_author(tmp_path):
    crit, src = V.resolve_acceptance_spec(
        {"acceptance_criteria": ["author 自报"]}, str(tmp_path))
    assert crit == ["author 自报"] and src == "author_proposed"


def test_resolve_acceptance_spec_prefers_human_curated(tmp_path):
    import os
    os.makedirs(tmp_path / ".touchstone")
    (tmp_path / ".touchstone" / "acceptance.yaml").write_text(
        "acceptance_criteria:\n  - 人核准的验收点\n", encoding="utf-8")
    crit, src = V.resolve_acceptance_spec(
        {"acceptance_criteria": ["author 自报"]}, str(tmp_path))
    assert crit == ["人核准的验收点"] and src == "human_curated"


# ---------------- AST 级变异（替代字符串替换 toy）----------------
def test_ast_mutants_flips_operators():
    src = "def f(a, b):\n    if a > b:\n        return a + b\n    return 0\n"
    muts = V._ast_mutants(src)
    assert any("a <= b" in m for m in muts)    # 关系翻转 Gt->LtE
    assert any("a - b" in m for m in muts)     # 算术翻转 Add->Sub
    assert len(muts) >= 2


def test_mutation_check_strong_test_kills(tmp_path):
    (tmp_path / "m.py").write_text("def f(a, b):\n    return a + b\n", encoding="utf-8")
    strong = ("import sys; sys.path.insert(0, '.')\nfrom m import f\n"
              "def test_f():\n    assert f(2, 3) == 5\n")
    assert V._mutation_check(str(tmp_path), strong, ["m.py"]) == 1.0   # a+b->a-b 被 5≠-1 抓到


def test_mutation_check_weak_test_survives(tmp_path):
    (tmp_path / "m.py").write_text("def f(a, b):\n    return a + b\n", encoding="utf-8")
    weak = ("import sys; sys.path.insert(0, '.')\nfrom m import f\n"
            "def test_f():\n    assert f(2, 3) is not None\n")
    assert V._mutation_check(str(tmp_path), weak, ["m.py"]) == 0.0     # a-b 仍非 None → 变异存活


# ---------------- 边界：纯函数（评级/重构判定/diff 解析/覆盖率）----------------
def test_grade_verdicts_boundaries():
    assert V._grade(0.8, True, None).verdict == "adequate"
    assert V._grade(0.8, False, None).verdict == "inadequate"   # 哨兵不过
    assert V._grade(0.5, True, None).verdict == "inadequate"    # 覆盖 <0.6
    assert V._grade(0.6, True, None).verdict == "adequate"      # 覆盖 ==0.6（含等号）
    assert V._grade(0.9, True, 0.5).verdict == "inadequate"     # 变异 <0.6
    assert V._grade(0.9, True, 0.6).verdict == "adequate"       # 变异 ==0.6


def test_is_refactor_variants():
    assert V.is_refactor({"intent": "refactor user service"})
    assert V.is_refactor({}, "refactor(core): tidy")
    assert V.is_refactor({"intent": "重构鉴权模块"})
    assert not V.is_refactor({"intent": "add new endpoint"}, "feat: x")


def test_parse_changed_lines_and_coverage_ratio():
    diff = ("--- a/x.py\n+++ b/x.py\n@@ -1,2 +1,3 @@\n ctx\n+new1\n+new2\n"
            "--- a/d.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-gone\n")
    assert V.parse_changed_lines(diff) == {"x.py": {2, 3}}      # 删除文件(/dev/null)不计
    cov = {"files": {"x.py": {"executed_lines": [2], "missing_lines": [3]}}}
    assert V._coverage_json_line_ratio(cov, {"x.py": {2, 3}}) == 0.5
    assert V._coverage_json_line_ratio(cov, {}) == 1.0          # 无可覆盖行 → 1.0
    assert V._coverage_json_line_ratio({}, {"x.py": {2}}) == 1.0  # 文件缺 → 1.0
