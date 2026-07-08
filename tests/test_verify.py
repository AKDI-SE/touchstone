"""质量门禁命门：runner 可插拔 + 重构 regression_only。"""
import os

import pytest
from verify import verify_change as V
from verify import runners as R


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
    # diff hunk 必须自洽：@@ -1,1 +1,3 @@ = 原 1 行、新 3 行（ctx + 2 added）
    diff = ("--- a/x.py\n+++ b/x.py\n@@ -1,1 +1,3 @@\n ctx\n+new1\n+new2\n"
            "--- a/d.py\n+++ /dev/null\n@@ -1,1 +0,0 @@\n-gone\n")
    assert V.parse_changed_lines(diff) == {"x.py": {2, 3}}      # 删除文件(/dev/null)不计
    cov = {"files": {"x.py": {"executed_lines": [2], "missing_lines": [3]}}}
    assert V._coverage_json_line_ratio(cov, {"x.py": {2, 3}}) == 0.5
    assert V._coverage_json_line_ratio(cov, {}) == 1.0          # 无可覆盖行 → 1.0
    assert V._coverage_json_line_ratio({}, {"x.py": {2}}) == 1.0  # 文件缺 → 1.0


# ============ 外部变异工具接缝（mutmut/cosmic-ray/PIT）回归 ============
def test_parse_mutation_output_takes_last_number():
    from verify import verify_change as V
    assert V._parse_mutation_output("killed 10/12\nscore: 83%") == 0.83
    assert V._parse_mutation_output("mutation score 0.6") == 0.6
    assert V._parse_mutation_output("no numbers here") is None

def test_external_mutation_cmd_used_when_set(monkeypatch, tmp_path):
    from verify import verify_change as V
    monkeypatch.setenv("TOUCHSTONE_MUTATION_CMD", "echo killed 3/4 = 75%")
    assert V.external_mutation_score(str(tmp_path), ["a.py"]) == 0.75
    monkeypatch.delenv("TOUCHSTONE_MUTATION_CMD")
    assert V.external_mutation_score(str(tmp_path), ["a.py"]) is None   # 未设 → 回退内置


# ---------------- 纯函数补测 ----------------


def test_extract_code_with_and_without_fence():
    assert V._extract_code("```python\nprint(1)\n```") == "print(1)"
    assert V._extract_code("bare code") == "bare code"


def test_extract_interface_skips_non_py_and_missing(tmp_path):
    (tmp_path / "m.py").write_text("def f(a):\n    return a\nclass C:\n    pass\n", encoding="utf-8")
    (tmp_path / "x.txt").write_text("ignore", encoding="utf-8")
    out = V._extract_interface(str(tmp_path), ["m.py", "x.txt", "nope.py"])
    assert "def f(a)" in out and "class C" in out


def test_extract_interface_syntax_error_skipped(tmp_path):
    (tmp_path / "bad.py").write_text("def (", encoding="utf-8")
    assert V._extract_interface(str(tmp_path), ["bad.py"]) == "(未能抽取签名)"


def test_generate_spec_blind_pytest(monkeypatch):
    monkeypatch.setattr(V, "_llm", lambda msgs, **cfg: "```python\ndef test_x(): assert 1\n```")
    ts = V.generate_spec_blind_tests(["它应返回 1"], "def f():", {"base_url": "u", "api_key": "k", "model": "m"})
    assert ts.code == "def test_x(): assert 1" and ts.source == "spec_blind" and ts.author_model == "m"


def test_generate_spec_blind_junit(monkeypatch):
    monkeypatch.setattr(V, "_llm", lambda msgs, **cfg: "```java\n@Test void t(){}\n```")
    ts = V.generate_spec_blind_tests(["x"], "i", {"base_url": "u", "api_key": "k", "model": "m"}, framework="junit5")
    assert "@Test" in ts.code


class _FakeCov:
    """模拟 coverage.Coverage——用 analysis2（statements + missing）替代已废弃的
    CoverageData.lines/missing_lines（pr-agent 审计发现 missing_lines 不存在）。"""
    def __init__(self, lines_map, missing_map):
        # lines_map = executed lines, missing_map = not-executed lines
        # analysis2 返回 (filename, statements, excluded, missing, missing_formatted)
        self._lines = lines_map
        self._missing = missing_map
    def analysis2(self, path):
        executed = self._lines.get(path) or set()
        missing = self._missing.get(path) or set()
        statements = sorted(executed | missing)
        return (path, statements, [], sorted(missing), "")
    def get_data(self):
        class _D:
            def lines(_, p): return self._lines.get(p)
        return _D()


def test_coverage_ratio_file_level():
    cov = _FakeCov({"a.py": {1, 2}}, {"a.py": {3}})   # 执行{1,2} missing{3} → 2/3
    assert V._coverage_ratio(cov, ["a.py"]) == 2 / 3


def test_coverage_ratio_empty_files():
    assert V._coverage_ratio(_FakeCov({}, {}), []) == 0.0


def test_coverage_ratio_line_level():
    cov = _FakeCov({"a.py": {1, 2}}, {"a.py": set()})     # 行 {1,2} 全执行
    assert V._coverage_ratio(cov, ["a.py"], {"a.py": {1, 2}}) == 1.0


def test_coverage_ratio_line_level_none_coverable():
    cov = _FakeCov({"a.py": set()}, {"a.py": set()})
    assert V._coverage_ratio(cov, ["a.py"], {"a.py": {99}}) == 1.0  # 无可覆盖行 → 1.0


def test_coverage_ratio_line_level_list_input():
    # changed_lines 值为 list 时不应 set&list 抛 TypeError 静默失败（pr-agent 第3轮 :91 回归保护）
    cov = _FakeCov({"a.py": {1, 2}}, {"a.py": set()})
    assert V._coverage_ratio(cov, ["a.py"], {"a.py": [1, 2]}) == 1.0


def test_coverage_json_line_ratio_list_input():
    # 同一缺陷类：_coverage_json_line_ratio 的 & lines 也须容忍 list 输入
    cov = {"files": {"x.py": {"executed_lines": [11, 12], "missing_lines": [22]}}}
    assert abs(V._coverage_json_line_ratio(cov, {"x.py": [11, 12, 22]}) - 2 / 3) < 1e-9


def test_changed_file_coverage_no_py_returns_one():
    assert V._changed_file_coverage(".", "code", ["a.js"]) == 1.0


def test_changed_file_coverage_subprocess_path(monkeypatch, tmp_path):
    monkeypatch.setattr(R, "_run_coverage_subprocess",
                        lambda wd, args: _FakeCov({"a.py": {1}}, {"a.py": set()}))
    assert V._changed_file_coverage(str(tmp_path), "def test_x(): assert 1", ["a.py"]) == 1.0


def test_changed_file_coverage_exception_returns_zero(monkeypatch, tmp_path):
    def boom(*a, **k):
        raise RuntimeError("cov failed")
    monkeypatch.setattr(R, "_run_coverage_subprocess", boom)
    assert V._changed_file_coverage(str(tmp_path), "x", ["a.py"]) == 0.0


def test_run_coverage_subprocess_loads_on_test_failure(monkeypatch, tmp_path):
    # pytest 测试失败（退出码 1）时 coverage 仍写出 .coverage——不应因退出码非零丢采集
    # （pr-agent 第3轮 :72 回归保护）
    def fake_run(*a, **k):
        (tmp_path / ".coverage").write_text("")   # 模拟 coverage 落盘（即便测试失败）
        return R.subprocess.CompletedProcess(a[0], 1)

    class _Cov:
        def __init__(self, data_file=None):
            pass
        def load(self):
            pass

    monkeypatch.setattr(R.subprocess, "run", fake_run)
    monkeypatch.setattr("coverage.Coverage", _Cov)
    assert R._run_coverage_subprocess(str(tmp_path), ["-m", "pytest", "-q", "x.py"]) is not None


def test_run_coverage_subprocess_raises_when_no_data(monkeypatch, tmp_path):
    # 起跑前已清空 .coverage；跑完仍无数据产出（coverage 崩溃/超时未落盘）→ raise，绝不加载 stale
    monkeypatch.setattr(R.subprocess, "run",
                        lambda *a, **k: R.subprocess.CompletedProcess(a[0], 1))
    with pytest.raises(RuntimeError, match="未产出数据"):
        R._run_coverage_subprocess(str(tmp_path), ["-m", "pytest", "-q", "x.py"])


def test_mutation_sites_finds_binary_ops():
    import ast
    tree = ast.parse("def f(a, b):\n    return a + b\n")
    sites = V._mutation_sites(tree)
    assert sites and any(isinstance(n, ast.BinOp) for n in sites)


def test_basename_lines_groups_by_basename():
    bl = V._basename_lines({"src/a.py": {1, 2}, "test/a.py": {3}})
    assert bl["a.py"] == {1, 2, 3}


def test_changed_lines_uses_git_diff(monkeypatch):
    class _R:
        returncode = 0
        stdout = "diff --git a/f.py b/f.py\n--- a/f.py\n+++ b/f.py\n@@ -0,0 +1,2 @@\n+new\n+new2\n"
    monkeypatch.setattr(V.subprocess, "run", lambda *a, **k: _R())
    cl = V._changed_lines(".", "b", "h")
    assert cl.get("f.py") == {1, 2}


def test_external_mutation_score_no_cmd_no_mutmut(monkeypatch, tmp_path):
    monkeypatch.delenv("TOUCHSTONE_MUTATION_CMD", raising=False)
    monkeypatch.setattr(V.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError))
    assert V.external_mutation_score(str(tmp_path), ["a.py"]) is None


def test_suite_coverage_python_no_py(tmp_path):
    assert V._suite_coverage_python(str(tmp_path), ["a.js"]) == 1.0


def test_verify_regression_pass(monkeypatch, tmp_path):
    monkeypatch.setattr(V, "_worktree", lambda repo, ref: str(tmp_path / ref))
    monkeypatch.setattr(V, "_rm_worktree", lambda repo, d: None)
    monkeypatch.setattr(V, "_changed_lines", lambda *a: {"a.py": {1}})

    class FR:
        lang = "pytest"
        def run_suite(self, d): return True, "ok"
        def changed_coverage(self, d, cf, cl): return 1.0
        def mutation(self, d, cf): return None
    r = V._verify_regression(str(tmp_path), FR(), ["a.py"], "b", "h", "regression_only")
    assert r.passed is True and r.mode == "regression_only" and r.head_tests_pass is True


def test_verify_regression_low_coverage_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(V, "_worktree", lambda repo, ref: str(tmp_path / ref))
    monkeypatch.setattr(V, "_rm_worktree", lambda repo, d: None)
    monkeypatch.setattr(V, "_changed_lines", lambda *a: {"a.py": {1}})

    class FR:
        lang = "maven"
        def run_suite(self, d): return True, "ok"
        def changed_coverage(self, d, cf, cl): return 0.1   # 低于 COV_MIN
        def mutation(self, d, cf): return None
    r = V._verify_regression(str(tmp_path), FR(), ["a.py"], "b", "h", "regression_only")
    assert r.passed is False


# ---------------- Runner 方法（mock 底层 subprocess/helper）----------------
def test_python_runner_run_suite(monkeypatch):
    monkeypatch.setattr(R, "_run", lambda cmd, wd, timeout=None: (True, "ok"))
    assert V.PythonRunner().run_suite("wd") == (True, "ok")


def test_python_runner_mutation_branches(monkeypatch, tmp_path):
    r = V.PythonRunner()
    # 外部变异工具有值 → 直接用
    monkeypatch.setattr(R, "external_mutation_score", lambda wd, cf: 0.7)
    assert r.mutation(str(tmp_path), ["a.py"], test_code="t") == 0.7
    # 外部返回 None + 有 test_code → _mutation_check
    monkeypatch.setattr(R, "external_mutation_score", lambda wd, cf: None)
    monkeypatch.setattr(R, "_mutation_check", lambda wd, tc, cf: 0.4)
    assert r.mutation(str(tmp_path), ["a.py"], test_code="t") == 0.4
    # 外部 None + 无 test_code → None
    assert r.mutation(str(tmp_path), ["a.py"]) is None


def test_python_runner_run_generated_and_cover(monkeypatch, tmp_path):
    monkeypatch.setattr(R, "_run_tests", lambda wd, tc: (True, "out"))
    assert V.PythonRunner().run_generated(str(tmp_path), "code") == (True, "out")
    monkeypatch.setattr(R, "_changed_file_coverage", lambda wd, tc, cf, cl=None: 0.9)
    assert V.PythonRunner().cover_generated(str(tmp_path), "code", ["a.py"]) == 0.9


def test_maven_runner_run_suite_and_mutation(monkeypatch, tmp_path):
    monkeypatch.setattr(R, "_run", lambda cmd, wd, timeout=None: (True, "ok"))
    r = V.MavenRunner()
    assert r.run_suite(str(tmp_path)) == (True, "ok")
    # mutation：mvn 成功 → _pit_score
    monkeypatch.setattr(R, "_pit_score", lambda wd: 0.55)
    assert r.mutation(str(tmp_path), ["A.java"]) == 0.55
    # mvn 失败 → None
    monkeypatch.setattr(R, "_run", lambda cmd, wd, timeout=None: (False, "fail"))
    assert r.mutation(str(tmp_path), ["A.java"]) is None


def test_maven_runner_changed_coverage(monkeypatch, tmp_path):
    monkeypatch.setattr(R, "_jacoco_changed_coverage", lambda wd, cf: 0.6)
    monkeypatch.setattr(R, "_jacoco_changed_line_coverage", lambda wd, cf, cl: 0.8)
    r = V.MavenRunner()
    assert r.changed_coverage(str(tmp_path), ["A.java"]) == 0.6               # 无 changed_lines
    assert r.changed_coverage(str(tmp_path), ["A.java"], {"A.java": {1}}) == 0.8


def test_maven_runner_run_generated_and_cover(monkeypatch, tmp_path):
    monkeypatch.setattr(R, "_place_junit", lambda wd, tc: ("TestX", "p"))
    monkeypatch.setattr(R, "_run", lambda cmd, wd, timeout=None: (True, "ok"))
    monkeypatch.setattr(R, "_jacoco_changed_coverage", lambda wd, cf: 0.9)
    r = V.MavenRunner()
    assert r.run_generated(str(tmp_path), "code") == (True, "ok")
    assert r.cover_generated(str(tmp_path), "code", ["A.java"]) == 0.9


def test_maven_runner_mvnw_preferred(monkeypatch, tmp_path):
    # 存在 mvnw → 用 ./mvnw
    (tmp_path / "mvnw").write_text("#!/bin/sh", encoding="utf-8")
    seen = {}
    def fake_run(cmd, wd, timeout=None):
        seen["cmd"] = cmd
        return (True, "ok")
    monkeypatch.setattr(R, "_run", fake_run)
    V.MavenRunner().run_suite(str(tmp_path))
    assert seen["cmd"][0] == "./mvnw"


# ---------------- worktree / CLI 配置错分支 ----------------
def test_worktree_success_and_rm(monkeypatch, tmp_path):
    monkeypatch.setattr(V.subprocess, "run", lambda *a, **k: V.subprocess.CompletedProcess(a[0], 0))
    dest = V._worktree(str(tmp_path), "HEAD")
    assert dest.startswith("/tmp") or "touchstone_wt" in dest
    V._rm_worktree(str(tmp_path), dest)              # 走 returncode==0 分支


def test_worktree_failure_raises_and_cleans(monkeypatch, tmp_path):
    def fake(*a, **k):
        if "worktree" in a[0] and "add" in a[0]:
            raise RuntimeError("add failed")
        return V.subprocess.CompletedProcess(a[0], 0)
    monkeypatch.setattr(V.subprocess, "run", fake)
    import pytest
    with pytest.raises(RuntimeError):
        V._worktree(str(tmp_path), "HEAD")


def test_rm_worktree_fallback_on_nonzero(monkeypatch, tmp_path):
    calls = []
    def fake(cmd, *a, **k):
        calls.append(cmd)
        return V.subprocess.CompletedProcess(cmd, 1)   # remove 失败 → 走 rmtree+prune 兜底
    monkeypatch.setattr(V.subprocess, "run", fake)
    d = tmp_path / "wt"
    d.mkdir()
    V._rm_worktree(str(tmp_path), str(d))
    assert any("prune" in c for c in calls)


def test_run_tests_pass_and_timeout(monkeypatch, tmp_path):
    monkeypatch.setattr(V.subprocess, "run",
                        lambda *a, **k: V.subprocess.CompletedProcess(a[0], 0, stdout="ok", stderr=""))
    assert V._run_tests(str(tmp_path), "def test_x(): assert 1") == (True, "ok")
    import subprocess as sp
    def boom(*a, **k):
        raise sp.TimeoutExpired(cmd=a[0], timeout=1)
    monkeypatch.setattr(V.subprocess, "run", boom)
    assert V._run_tests(str(tmp_path), "x") == (False, "timeout")


def test_cli_missing_llm_env_exits_2():
    import subprocess, sys, os
    # -m 运行（第一轮起全仓标准；verify 内部为包导入，不再支持脚本式路径调用）
    r = subprocess.run([sys.executable, "-m", "verify.verify_change"],
                       capture_output=True, text=True, env={})
    assert r.returncode == 2 and "LLM" in r.stderr


def test_cli_missing_refs_exits_2(monkeypatch):
    import subprocess, sys, os
    env = {**os.environ, "LLM_BASE_URL": "u", "LLM_API_KEY": "k", "LLM_MODEL": "m",
           "PATH": os.environ.get("PATH", "")}
    # 去掉 BASE_REF/HEAD_REF
    env.pop("BASE_REF", None); env.pop("HEAD_REF", None)
    r = subprocess.run([sys.executable, "-m", "verify.verify_change"],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 2 and "BASE_REF" in r.stderr


def test_run_success_timeout_notfound(monkeypatch):
    import subprocess as sp
    seq = [V.subprocess.CompletedProcess(["x"], 0, stdout="o", stderr=""),
           sp.TimeoutExpired(cmd=["x"], timeout=1),
           FileNotFoundError("nope")]
    def fake(cmd, *a, **k):
        v = seq.pop(0)
        if isinstance(v, Exception):
            raise v
        return v
    monkeypatch.setattr(V.subprocess, "run", fake)
    assert V._run(["x"], ".") == (True, "o")
    assert V._run(["x"], ".") == (False, "timeout")
    res = V._run(["x"], ".")
    assert res[0] is False and "命令不存在" in res[1]


def test_external_mutation_cmd_parse_and_fail(monkeypatch, tmp_path):
    # 设了 cmd + 正常百分数输出 → 解析击杀率
    monkeypatch.setenv("TOUCHSTONE_MUTATION_CMD", "echo mutation score: 75%")
    assert V.external_mutation_score(str(tmp_path), ["a.py"]) == 0.75
    # cmd 抛错 → None
    monkeypatch.setenv("TOUCHSTONE_MUTATION_CMD", "false")
    assert V.external_mutation_score(str(tmp_path), ["a.py"]) is None
