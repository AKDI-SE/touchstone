#!/usr/bin/env python3
# ============================================================================
# verify/verify_change.py  ——  Phase 1 最关键模块：verify_change（独立验收测试 + 充分性阶梯）
# ----------------------------------------------------------------------------
# 设计见 docs/touchstone-design.html §6。参考实现 = Python / pytest；
# 换语言只需替换 _run_tests / _extract_interface / _mutate（见 LANG RUNNER 标记）。
#
# 不变式（职责分离闸）：验收测试由【看不到实现】的独立验收测试作者(异模型)生成，
#   写入隔离临时目录；author 与 touchstone 对其无写权——本模块不读取 author 控制路径下的测试。
#
# 判过条件（passed）：改后 PASS(正确性) ∧ 改前 FAIL(哨兵充分) ∧ 覆盖/[高风险]变异达标 ∧ 回归绿。
#   注意"改后跑"既是哨兵的一半、也同时是正确性判决——改后挂即代码不满足规格。
# ============================================================================

import ast
import json
import os
import re
import subprocess
import tempfile
import urllib.request
import urllib.error
import openai
import yaml
from dataclasses import dataclass, field
from typing import Optional

COV_MIN = 0.6          # 改动文件覆盖率下限
MUT_MIN = 0.6          # 高风险变异击杀率下限
TEST_TIMEOUT = 300


# --- 数据结构（对应设计 §6.3 / §3.6）-----------------------------------------
@dataclass
class AcceptanceTestSet:
    code: str
    source: str                 # spec_blind | regression | human_curated
    author_model: str
    write_locked_from: list = field(default_factory=lambda: ["author", "touchstone"])


@dataclass
class AdequacyResult:
    changed_file_coverage: float = 0.0
    sentinel_passed: Optional[bool] = None      # 改前 FAIL 成立？None=未跑
    mutation_score: Optional[float] = None      # None=未跑（非高风险）
    verdict: str = "not_run"                    # adequate | inadequate | not_run


@dataclass
class VerificationResult:
    passed: bool
    mode: str
    head_tests_pass: Optional[bool] = None      # 改后 PASS = 正确性判决
    adequacy: Optional[AdequacyResult] = None
    evidence: str = ""
    spec_source: Optional[str] = None           # human_curated | author_proposed | None(回归/cheap)


# --- LLM（OpenAI 兼容；与 touchstone 一致；若经代理访问需配好代理）------------------
def _llm(messages, base_url, api_key, model, temperature=0.0, timeout=120):
    # openai SDK（支持自定义 base_url；独立验收测试用异模型 LLM_TEST_MODEL，与 touchstone 隔离）
    client = openai.OpenAI(base_url=base_url, api_key=api_key, timeout=timeout)
    resp = client.chat.completions.create(model=model, messages=messages,
                                          temperature=temperature)
    return resp.choices[0].message.content or ""


def _extract_code(text):
    m = re.search(r"```(?:python)?\s*(.*?)```", text, flags=re.DOTALL)
    return (m.group(1) if m else text).strip()


# --- 接口抽取：只取公共签名、去实现（LANG RUNNER）----------------------------
def _extract_interface(work_dir, changed_files):
    """给独立验收测试作者'调什么'，不给'怎么实现'。"""
    sigs = []
    for fp in changed_files:
        if not fp.endswith(".py"):
            continue
        path = os.path.join(work_dir, fp)
        if not os.path.exists(path):
            continue
        try:
            tree = ast.parse(open(path, encoding="utf-8").read())
        except SyntaxError:
            continue
        mod = fp[:-3].replace("/", ".")
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                args = ", ".join(a.arg for a in node.args.args)
                sigs.append(f"{mod}: def {node.name}({args})")
            elif isinstance(node, ast.ClassDef):
                sigs.append(f"{mod}: class {node.name}")
    return "\n".join(sigs) or "(未能抽取签名)"


# --- 独立验收测试生成（异模型、看不到实现）------------------------------------
def generate_spec_blind_tests(acceptance_criteria, interface, llm_cfg, framework="pytest") -> AcceptanceTestSet:
    criteria = "\n".join(f"- {c}" for c in (acceptance_criteria or []))
    if framework == "junit5":
        system = (
            "你是独立的【独立验收测试作者】。你只看到规格(验收判据)与公共接口签名，【看不到实现】。\n"
            "为每条验收判据写 JUnit 5 测试方法(@Test)，断言真实行为（禁止恒真断言）。\n"
            "调用被测类型的公共接口。只输出一个完整的 Java 测试类（含 package 与 import，含一个 public class），不要解释。")
        user = (f"验收判据：\n{criteria}\n\n"
                f"公共接口（仅签名，无实现）：\n{interface}\n\n"
                "输出一个完整的 JUnit 5 Java 测试类。")
    else:
        system = (
            "你是独立的【独立验收测试作者】。你只看到规格(验收判据)与公共接口，【看不到实现】。\n"
            "为每条验收判据写 pytest 测试，断言真实行为（禁止 assert True 之类的恒真断言）。\n"
            "import 被测模块的公共接口来调用。只输出一个完整的 pytest 测试文件代码，不要解释。")
        user = (f"验收判据：\n{criteria}\n\n"
                f"公共接口（仅签名，无实现）：\n{interface}\n\n"
                "输出 pytest 测试文件代码。")
    code = _extract_code(_llm([{"role": "system", "content": system},
                               {"role": "user", "content": user}], **llm_cfg))
    return AcceptanceTestSet(code=code, source="spec_blind", author_model=llm_cfg["model"])


# --- git worktree：物化某 ref 到临时目录 -------------------------------------
def _worktree(repo_dir, ref):
    dest = tempfile.mkdtemp(prefix="touchstone_wt_")
    subprocess.run(["git", "-C", repo_dir, "worktree", "add", "--detach", dest, ref],
                   check=True, capture_output=True)
    return dest


def _rm_worktree(repo_dir, dest):
    subprocess.run(["git", "-C", repo_dir, "worktree", "remove", "--force", dest],
                   capture_output=True)


# --- 跑生成测试（LANG RUNNER）。返回 (passed, output) -------------------------
def _run_tests(work_dir, test_code):
    tf = os.path.join(work_dir, "_touchstone_spec_test.py")
    with open(tf, "w", encoding="utf-8") as f:
        f.write(test_code)
    try:
        r = subprocess.run(["python", "-m", "pytest", "-q", "_touchstone_spec_test.py"],
                           cwd=work_dir, capture_output=True, text=True, timeout=TEST_TIMEOUT)
        return r.returncode == 0, (r.stdout + r.stderr)[-2000:]
    except subprocess.TimeoutExpired:
        return False, "timeout"
    finally:
        if os.path.exists(tf):
            os.remove(tf)


# --- 改动文件覆盖率（简化：文件级；改动行级映射为后续细化）-------------------
def _changed_file_coverage(work_dir, test_code, changed_files, changed_lines=None):
    py = [f for f in changed_files if f.endswith(".py")]
    if not py:
        return 1.0
    tf = os.path.join(work_dir, "_touchstone_spec_test.py")
    with open(tf, "w", encoding="utf-8") as f:
        f.write(test_code)
    try:
        subprocess.run(["python", "-m", "coverage", "run", "--source=.",
                       "-m", "pytest", "-q", "_touchstone_spec_test.py"],
                       cwd=work_dir, capture_output=True, text=True, timeout=TEST_TIMEOUT)
        cj = subprocess.run(["python", "-m", "coverage", "json", "-o", "-"],
                           cwd=work_dir, capture_output=True, text=True)
        data = json.loads(cj.stdout) if cj.stdout.strip().startswith("{") else {}
        if changed_lines:                                  # 改动行级（优先）
            return _coverage_json_line_ratio(data, changed_lines)
        files = data.get("files", {})                      # 回落文件级
        ratios = [files[f]["summary"]["percent_covered"] / 100.0
                  for f in py if f in files]
        return sum(ratios) / len(ratios) if ratios else 0.0
    except (subprocess.TimeoutExpired, json.JSONDecodeError, KeyError, ZeroDivisionError):
        return 0.0
    finally:
        if os.path.exists(tf):
            os.remove(tf)


# --- 最小变异（高风险）。返回击杀率（LANG RUNNER；生产应换 mutmut/cosmic-ray）--
# AST 级变异（stdlib ast 真解析，作用于语法节点，不碰注释/字符串；远强于字符串替换）：
#   关系 Eq<->NotEq / Lt<->GtE / Gt<->LtE，算术 Add<->Sub / Mult<->Div，
#   布尔 And<->Or，布尔常量 True<->False。每个可变异点产一个变异体。
# 说明：mutmut(2.x 要求 tests/ 目录、3.x 配置驱动且有状态)均跑"发现到的整套测试"，
#   与本处"临时 worktree + 仅跑生成的独立验收测试 + 只针对改动文件"不贴合；故 Python 侧
#   用作用域精确、可在离线验证的 AST 变异。Java 侧用成熟的 PIT(见 MavenRunner)。
_MUT_CMP = {ast.Eq: ast.NotEq, ast.NotEq: ast.Eq, ast.Lt: ast.GtE,
            ast.GtE: ast.Lt, ast.Gt: ast.LtE, ast.LtE: ast.Gt}
_MUT_BIN = {ast.Add: ast.Sub, ast.Sub: ast.Add, ast.Mult: ast.Div, ast.Div: ast.Mult}
_MUT_BOOL = {ast.And: ast.Or, ast.Or: ast.And}


def _mutation_sites(tree):
    out = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Compare) and n.ops and type(n.ops[0]) in _MUT_CMP:
            out.append(n)
        elif isinstance(n, ast.BinOp) and type(n.op) in _MUT_BIN:
            out.append(n)
        elif isinstance(n, ast.BoolOp) and type(n.op) in _MUT_BOOL:
            out.append(n)
        elif isinstance(n, ast.Constant) and isinstance(n.value, bool):
            out.append(n)
    return out


def _ast_mutants(src):
    """对源码各可变异点各产一个变异体（一次一个），返回变异体源码列表。"""
    try:
        base = ast.parse(src)
    except SyntaxError:
        return []
    mutants = []
    for i in range(len(_mutation_sites(base))):
        tree = ast.parse(src)
        node = _mutation_sites(tree)[i]
        if isinstance(node, ast.Compare):
            node.ops[0] = _MUT_CMP[type(node.ops[0])]()
        elif isinstance(node, ast.BinOp):
            node.op = _MUT_BIN[type(node.op)]()
        elif isinstance(node, ast.BoolOp):
            node.op = _MUT_BOOL[type(node.op)]()
        elif isinstance(node, ast.Constant):
            node.value = not node.value
        try:
            mutants.append(ast.unparse(ast.fix_missing_locations(tree)))
        except (ValueError, AttributeError):
            pass
    return mutants


def _mutation_check(work_dir, test_code, changed_files):
    """变异充分性：对改动的 .py 文件注入 AST 级变异，看生成的独立验收测试能否杀掉。
    击杀率 = 测试挂掉的变异数 / 注入数。"""
    applied = killed = 0
    for fp in [f for f in changed_files if f.endswith(".py")]:
        path = os.path.join(work_dir, fp)
        if not os.path.exists(path):
            continue
        orig = open(path, encoding="utf-8").read()
        try:
            for mut in _ast_mutants(orig):
                applied += 1
                with open(path, "w", encoding="utf-8") as f:
                    f.write(mut)               # 注入一个变异
                passed, _ = _run_tests(work_dir, test_code)
                if not passed:                 # 测试挂掉 = 变异被杀
                    killed += 1
        finally:
            with open(path, "w", encoding="utf-8") as f:
                f.write(orig)                  # 始终还原
    return (killed / applied) if applied else 1.0


# ============================================================================
# 语言运行器（runner 可插拔，设计 §6.4）
#   每个 runner：run_suite / changed_coverage / mutation / extract_interface /
#   run_generated / supports_spec_blind。换语言 = 换一个 runner。
# ============================================================================
def _run(cmd, work_dir, timeout=TEST_TIMEOUT):
    try:
        r = subprocess.run(cmd, cwd=work_dir, capture_output=True, text=True, timeout=timeout)
        return r.returncode == 0, (r.stdout + r.stderr)[-2000:]
    except subprocess.TimeoutExpired:
        return False, "timeout"
    except FileNotFoundError as e:
        return False, f"命令不存在: {e}"


class PythonRunner:
    lang = "python"
    supports_spec_blind = True

    def run_suite(self, work_dir):
        return _run(["python", "-m", "pytest", "-q"], work_dir)

    def changed_coverage(self, work_dir, changed_files, changed_lines=None):
        return _suite_coverage_python(work_dir, changed_files, changed_lines)

    def mutation(self, work_dir, changed_files, test_code=None):
        return _mutation_check(work_dir, test_code, changed_files) if test_code else None

    def extract_interface(self, work_dir, changed_files):
        return _extract_interface(work_dir, changed_files)

    def run_generated(self, work_dir, test_code):
        return _run_tests(work_dir, test_code)

    def cover_generated(self, work_dir, test_code, changed_files, changed_lines=None):
        return _changed_file_coverage(work_dir, test_code, changed_files, changed_lines)


class MavenRunner:
    lang = "maven"
    supports_spec_blind = True    # JUnit 5 独立验收测试生成 + 放置到 src/test/java + mvn test

    def _mvn(self, work_dir, goals):
        exe = "./mvnw" if os.path.exists(os.path.join(work_dir, "mvnw")) else "mvn"
        return _run([exe, "-B", "-ntp", *goals], work_dir, timeout=TEST_TIMEOUT * 4)

    def run_suite(self, work_dir):
        return self._mvn(work_dir, ["verify"])

    def changed_coverage(self, work_dir, changed_files, changed_lines=None):
        return (_jacoco_changed_line_coverage(work_dir, changed_files, changed_lines)
                if changed_lines else _jacoco_changed_coverage(work_dir, changed_files))

    def mutation(self, work_dir, changed_files, test_code=None):
        ok, _ = self._mvn(work_dir, ["org.pitest:pitest-maven:mutationCoverage"])
        return _pit_score(work_dir) if ok else None

    def extract_interface(self, work_dir, changed_files):
        return _extract_java_signatures(work_dir, changed_files)

    def run_generated(self, work_dir, test_code):
        cname, _ = _place_junit(work_dir, test_code)
        return self._mvn(work_dir, ["test", f"-Dtest={cname}"])

    def cover_generated(self, work_dir, test_code, changed_files, changed_lines=None):
        cname, _ = _place_junit(work_dir, test_code)
        self._mvn(work_dir, ["test", f"-Dtest={cname}",
                             "org.jacoco:jacoco-maven-plugin:report"])
        return self.changed_coverage(work_dir, changed_files, changed_lines)


def select_runner(repo_dir, changed_files):
    if os.path.exists(os.path.join(repo_dir, "pom.xml")) or \
       any(f.endswith(".java") for f in (changed_files or [])):
        return MavenRunner()
    if any(f.endswith(".py") for f in (changed_files or [])):
        return PythonRunner()
    return None     # 非 Python/Java：verify 参考实现不支持 → verify_change 给中性结果，不再误生成 pytest


def is_refactor(contract, pr_title=""):
    text = ((pr_title or "") + " " + ((contract or {}).get("intent") or "")).lower().strip()
    return text.startswith("refactor") or "refactor(" in text or "重构" in text


# --- JaCoCo 改动覆盖率 / PIT 变异率解析（Maven）------------------------------
def _jacoco_changed_coverage(work_dir, changed_files):
    import glob
    import xml.etree.ElementTree as ET
    java = {os.path.basename(f) for f in changed_files if f.endswith(".java")}
    if not java:
        return 1.0
    reports = (glob.glob(os.path.join(work_dir, "**/target/site/jacoco/jacoco.xml"), recursive=True)
               + glob.glob(os.path.join(work_dir, "**/target/site/jacoco-aggregate/jacoco.xml"),
                           recursive=True))
    covered = missed = 0
    for rep in reports:
        try:
            root = ET.parse(rep).getroot()
        except ET.ParseError:
            continue
        for sf in root.iter("sourcefile"):
            if sf.get("name") in java:
                for ctr in sf.findall("counter"):
                    if ctr.get("type") == "LINE":
                        covered += int(ctr.get("covered", 0))
                        missed += int(ctr.get("missed", 0))
    total = covered + missed
    return (covered / total) if total else 0.0


def _pit_score(work_dir):
    import glob
    import xml.etree.ElementTree as ET
    reps = glob.glob(os.path.join(work_dir, "**/target/pit-reports/**/mutations.xml"),
                     recursive=True)
    killed = total = 0
    for rep in reps:
        try:
            root = ET.parse(rep).getroot()
        except ET.ParseError:
            continue
        for m in root.iter("mutation"):
            total += 1
            if m.get("status") in ("KILLED", "TIMED_OUT"):
                killed += 1
    return (killed / total) if total else None


def _extract_java_signatures(work_dir, changed_files):
    sigs = []
    for fp in changed_files:
        if not fp.endswith(".java"):
            continue
        path = os.path.join(work_dir, fp)
        if not os.path.exists(path):
            continue
        text = open(path, encoding="utf-8", errors="replace").read()
        for k, n in re.findall(r"\b(class|interface|enum|record)\s+(\w+)", text):
            sigs.append(f"{fp}: {k} {n}")
        for m in re.findall(
                r"(?:public|protected)\s+[\w<>\[\],.?\s]+?\s+(\w+)\s*\([^;{]*\)\s*[{;]", text):
            sigs.append(f"{fp}: method {m}()")
    return "\n".join(sigs) or "(未能抽取签名)"


def _suite_coverage_python(work_dir, changed_files, changed_lines=None):
    py = [f for f in changed_files if f.endswith(".py")]
    if not py:
        return 1.0
    try:
        subprocess.run(["python", "-m", "coverage", "run", "--source=.", "-m", "pytest", "-q"],
                       cwd=work_dir, capture_output=True, text=True, timeout=TEST_TIMEOUT)
        cj = subprocess.run(["python", "-m", "coverage", "json", "-o", "-"],
                            cwd=work_dir, capture_output=True, text=True)
        data = json.loads(cj.stdout) if cj.stdout.strip().startswith("{") else {}
        if changed_lines:
            return _coverage_json_line_ratio(data, changed_lines)
        files = data.get("files", {})
        ratios = [files[f]["summary"]["percent_covered"] / 100.0 for f in py if f in files]
        return sum(ratios) / len(ratios) if ratios else 0.0
    except (subprocess.TimeoutExpired, json.JSONDecodeError, KeyError, ZeroDivisionError):
        return 0.0


# --- 改动行级覆盖：从 diff 取改动行，与覆盖数据取交 -------------------------
def parse_changed_lines(diff_text):
    """unified diff(建议 --unified=0) → {path: set(新文件侧改动行号)}。纯函数。"""
    out, cur, newline = {}, None, 0
    for line in (diff_text or "").splitlines():
        if line.startswith("+++ "):
            p = line[4:].strip()
            cur = None if p == "/dev/null" else (p[2:] if p.startswith("b/") else p)
            if cur:
                out.setdefault(cur, set())
        elif line.startswith("@@"):
            m = re.search(r"\+(\d+)", line)
            newline = int(m.group(1)) if m else 1
        elif cur is None or line.startswith("---") or line.startswith("diff "):
            continue
        elif line.startswith("+"):
            out[cur].add(newline)
            newline += 1
        elif line.startswith("-") or line.startswith("\\"):
            pass
        else:
            newline += 1
    return {k: v for k, v in out.items() if v}


def _changed_lines(repo_dir, base_ref, head_ref):
    try:
        r = subprocess.run(["git", "-C", repo_dir, "diff", "--unified=0", base_ref, head_ref],
                           capture_output=True, text=True, timeout=60)
        return parse_changed_lines(r.stdout) if r.returncode == 0 else {}
    except (subprocess.SubprocessError, OSError):
        return {}


def _coverage_json_line_ratio(cov_json, changed_lines):
    """coverage.py json + 改动行 → 改动行覆盖率（只计“可覆盖”的改动行）。纯函数。"""
    files = (cov_json or {}).get("files", {})
    coverable = covered = 0
    for path, lines in (changed_lines or {}).items():
        fd = files.get(path)
        if not fd:
            continue
        cov_set = (set(fd.get("executed_lines", [])) | set(fd.get("missing_lines", []))) & lines
        coverable += len(cov_set)
        covered += len(set(fd.get("executed_lines", [])) & cov_set)
    return (covered / coverable) if coverable else 1.0


def _basename_lines(changed_lines):
    out = {}
    for path, lines in (changed_lines or {}).items():
        out.setdefault(os.path.basename(path), set()).update(lines)
    return out


def _jacoco_line_ratio(roots, basename_lines):
    """ET 根列表 + {basename: 改动行} → 改动行覆盖率(ci>0 视为已覆盖)。纯函数。"""
    coverable = covered = 0
    for root in roots:
        for sf in root.iter("sourcefile"):
            want = basename_lines.get(sf.get("name"))
            if not want:
                continue
            for ln in sf.findall("line"):
                if int(ln.get("nr", 0)) in want:
                    coverable += 1
                    if int(ln.get("ci", 0)) > 0:
                        covered += 1
    return (covered / coverable) if coverable else 1.0


def _jacoco_changed_line_coverage(work_dir, changed_files, changed_lines):
    import glob
    import xml.etree.ElementTree as ET
    reports = (glob.glob(os.path.join(work_dir, "**/target/site/jacoco/jacoco.xml"), recursive=True)
               + glob.glob(os.path.join(work_dir, "**/target/site/jacoco-aggregate/jacoco.xml"),
                           recursive=True))
    roots = []
    for rep in reports:
        try:
            roots.append(ET.parse(rep).getroot())
        except ET.ParseError:
            continue
    return _jacoco_line_ratio(roots, _basename_lines(changed_lines))


# --- 独立验收测试 JUnit 放置（Java）：解析 package/class 放入 src/test/java ----------
def _place_junit(work_dir, test_code):
    pkg = re.search(r"package\s+([\w.]+)\s*;", test_code)
    cls = re.search(r"(?:public\s+)?(?:final\s+)?class\s+(\w+)", test_code)
    cname = cls.group(1) if cls else "GeneratedSpecTest"
    parts = ["src", "test", "java"] + (pkg.group(1).split(".") if pkg else [])
    dest_dir = os.path.join(work_dir, *parts)
    os.makedirs(dest_dir, exist_ok=True)
    path = os.path.join(dest_dir, cname + ".java")
    with open(path, "w", encoding="utf-8") as f:
        f.write(test_code)
    return cname, path


def _grade(cov, sentinel, mut):
    """独立验收测试评级：哨兵成立 ∧ 改动行覆盖达标 ∧ [高风险]变异达标。"""
    mut_ok = (mut is None) or (mut >= MUT_MIN)
    adq = AdequacyResult(changed_file_coverage=cov, sentinel_passed=sentinel, mutation_score=mut)
    adq.verdict = "adequate" if (sentinel and cov >= COV_MIN and mut_ok) else "inadequate"
    return adq


# --- check_adequacy（充分性阶梯）---------------------------------------------
def check_adequacy(runner, test_code, changed_files, changed_lines, base_dir, head_dir, mode) -> AdequacyResult:
    """语言无关充分性校验(独立验收测试路径)：
    ② 空实现哨兵——生成测试在【改前】必须 FAIL(否则没测到改动)；
    ① 改动行覆盖——生成测试在【改后】执行到改动行的比例；
    ③ 变异——仅 full_suite/高风险。各步均走 runner，故 Python/Java 同一套逻辑。"""
    base_pass, _ = runner.run_generated(base_dir, test_code)
    sentinel = (base_pass is False)
    cov = runner.cover_generated(head_dir, test_code, changed_files, changed_lines)
    mut = runner.mutation(head_dir, changed_files, test_code) if mode == "full_suite" else None
    return _grade(cov, sentinel, mut)


# --- verify_change（编排）----------------------------------------------------
def resolve_acceptance_spec(contract, repo_dir):
    """验收规格来源治理——把"索引而非凭据"落到质量门禁最承重处。
    人核准的规格优先（.touchstone/acceptance.yaml，或 env TOUCHSTONE_ACCEPTANCE），标 human_curated；
    缺则回落 author 契约里的 acceptance_criteria，标 author_proposed（仅建议、不构成可信认证）。
    返回 (criteria, source)。"""
    path = os.environ.get("TOUCHSTONE_ACCEPTANCE",
                          os.path.join(repo_dir, ".touchstone", "acceptance.yaml"))
    try:
        data = yaml.safe_load(open(path, encoding="utf-8")) or {}
        if data.get("acceptance_criteria"):
            return data["acceptance_criteria"], "human_curated"
    except (OSError, yaml.YAMLError):
        pass
    return (contract or {}).get("acceptance_criteria"), "author_proposed"


def verify_change(repo_dir, contract, changed_files, base_ref, head_ref,
                  mode, llm_cfg, pr_title="") -> VerificationResult:
    """mode: cheap_only | targeted_tests | full_suite | regression_only（由风险分流给出）。
    runner 按仓库特征自选；Java(不支持独立验收测试)与纯重构 PR 走 regression_only。"""
    if mode == "cheap_only":
        return VerificationResult(passed=True, mode=mode, adequacy=AdequacyResult(),
                                 evidence="cheap_only：仅廉价信号，未生成验收测试")

    runner = select_runner(repo_dir, changed_files)
    if runner is None:
        return VerificationResult(
            passed=None, mode="unsupported",
            evidence="verify 参考实现仅支持 Python(pytest)/Java(Maven)；本仓改动语言不在此列——"
                     "请跑自有套件或在 select_runner 接入自有 runner。")
    # 纯重构（无新行为，独立验收测试无意义）或语言不支持独立验收测试 → 回归模式
    if mode == "regression_only" or is_refactor(contract, pr_title) or not runner.supports_spec_blind:
        return _verify_regression(repo_dir, runner, changed_files, base_ref, head_ref, mode)

    # 否则：独立验收测试路径（Python→pytest / Java→JUnit5，语言无关）
    head_dir = _worktree(repo_dir, head_ref)
    base_dir = _worktree(repo_dir, base_ref)
    try:
        interface = runner.extract_interface(head_dir, changed_files)
        framework = "junit5" if getattr(runner, "lang", "") == "maven" else "pytest"
        # 验收规格来源治理：人核准优先；author 自报的只作建议、不足以认证可信绿
        criteria, spec_source = resolve_acceptance_spec(contract, repo_dir)
        if not criteria:
            res = _verify_regression(repo_dir, runner, changed_files, base_ref, head_ref,
                                     "regression_only")
            res.evidence = ("无验收规格（人核准与 author 均无）→ 退回回归；"
                            "高风险正确性认证需人写/核准的 .touchstone/acceptance.yaml。\n" + res.evidence)
            return res
        ts = generate_spec_blind_tests(criteria, interface, llm_cfg, framework)
        # 改后跑：既是哨兵的一半，也同时是正确性判决
        head_pass, head_out = runner.run_generated(head_dir, ts.code)
        changed = _changed_lines(repo_dir, base_ref, head_ref)
        adq = check_adequacy(runner, ts.code, changed_files, changed, base_dir, head_dir, mode)
        passed = bool(head_pass) and adq.verdict == "adequate"
        note = ("" if spec_source == "human_curated"
                else "⚠ 规格来源=author_proposed：仅作建议，不构成可信认证（自治放行需人核准规格）。\n")
        evidence = (f"{note}[spec_blind/{runner.lang}] spec_source={spec_source} "
                    f"head_pass={head_pass} sentinel={adq.sentinel_passed} "
                    f"cov={adq.changed_file_coverage:.2f} mut={adq.mutation_score}\n{head_out}")
        return VerificationResult(passed, mode, head_pass, adq, evidence, spec_source=spec_source)
    finally:
        _rm_worktree(repo_dir, base_dir)
        _rm_worktree(repo_dir, head_dir)


def _verify_regression(repo_dir, runner, changed_files, base_ref, head_ref, mode):
    """重构/非独立验收测试语言：现有套件【改后仍绿】+【改动被覆盖】；改前也绿以便正确归因。
    不生成独立验收测试、不跑哨兵（无新行为可供改前 FAIL）。"""
    head_dir = _worktree(repo_dir, head_ref)
    base_dir = _worktree(repo_dir, base_ref)
    try:
        head_pass, head_out = runner.run_suite(head_dir)
        base_pass, _ = runner.run_suite(base_dir)
        changed = _changed_lines(repo_dir, base_ref, head_ref)
        cov = runner.changed_coverage(head_dir, changed_files, changed)
        adq = AdequacyResult(changed_file_coverage=cov, sentinel_passed=None)
        if mode == "full_suite":
            adq.mutation_score = runner.mutation(head_dir, changed_files)
        mut_ok = (adq.mutation_score is None) or (adq.mutation_score >= MUT_MIN)
        adq.verdict = "adequate" if (cov >= COV_MIN and mut_ok) else "inadequate"
        # 判过：改后套件绿(不破坏行为) ∧ 改动被覆盖。改前非绿则归因不清，提示但不据此判过
        passed = bool(head_pass) and adq.verdict == "adequate"
        attr = "" if base_pass else "  ⚠ 改前套件即非绿，无法干净归因"
        evidence = (f"[regression_only/{runner.lang}] head_suite={head_pass} "
                    f"base_suite={base_pass} changed_cov={cov:.2f} "
                    f"mut={adq.mutation_score}{attr}\n{head_out}")
        return VerificationResult(passed, "regression_only", head_pass, adq, evidence)
    finally:
        _rm_worktree(repo_dir, base_dir)
        _rm_worktree(repo_dir, head_dir)


# --- CLI（供 Phase 1 工作流在高风险 PR 上调用）-------------------------------
if __name__ == "__main__":
    import sys
    import yaml
    base_url = os.environ.get("LLM_BASE_URL")
    api_key = os.environ.get("LLM_API_KEY")
    model = os.environ.get("LLM_TEST_MODEL") or os.environ.get("LLM_MODEL")
    if not (base_url and api_key and model):
        sys.exit("缺少 LLM_BASE_URL/LLM_API_KEY/LLM_(TEST_)MODEL")
    print(f"[verify] base_url={base_url} model={model}")
    repo = os.environ.get("REPO_DIR", ".")
    base_ref = os.environ["BASE_REF"]
    head_ref = os.environ["HEAD_REF"]
    mode = os.environ.get("VERIFY_MODE", "targeted_tests")
    contract = yaml.safe_load(open(os.environ.get("TOUCHSTONE_CONTRACT",
                              ".touchstone/pr.yaml"), encoding="utf-8")) or {}
    changed = subprocess.run(["git", "-C", repo, "diff", "--name-only",
                             f"{base_ref}..{head_ref}"],
                            capture_output=True, text=True).stdout.split()
    res = verify_change(repo, contract, changed, base_ref, head_ref, mode,
                        {"base_url": base_url, "api_key": api_key, "model": model},
                        os.environ.get("PR_TITLE", ""))

    adq = res.adequacy
    summary = {"passed": res.passed, "mode": res.mode,
               "head_tests_pass": res.head_tests_pass,
               "adequacy": adq.__dict__ if adq else None}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    with open("verify-result.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    # 回贴 GitHub：评论 + check run（success/failure —— 质量门禁级判决，非 neutral）。
    # 是否拦截合入，由分支保护把 touchstone/verify 设为 required 来决定。
    token = os.environ.get("GITHUB_TOKEN")
    if token and os.environ.get("GITHUB_EVENT_PATH"):
        ev = yaml.safe_load(open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8")) or {}
        pr = ev.get("pull_request", {})
        number = pr.get("number")
        sha = pr.get("head", {}).get("sha")
        owner, reponame = os.environ["GITHUB_REPOSITORY"].split("/", 1)
        api = os.environ.get("GITHUB_API_URL", "https://api.github.com")
        cov = f"{adq.changed_file_coverage:.2f}" if adq else "—"
        body = (f"**Touchstone · 验证（{res.mode}）** — 质量门禁级判决\n\n"
                f"结果：{'PASS ✅' if res.passed else 'FAIL ❌'}　"
                f"改后PASS(正确性)={res.head_tests_pass}　"
                f"哨兵(改前FAIL)={adq.sentinel_passed if adq else None}　"
                f"改动覆盖={cov}　变异={adq.mutation_score if adq else None}\n\n"
                f"> 是否拦截合入由分支保护的 required check 决定（随信心增长开启）。")

        def _gh(method, path, data=None):
            req = urllib.request.Request(
                api + path, data=json.dumps(data).encode("utf-8") if data else None,
                method=method, headers={
                    "Authorization": "Bearer " + token,
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                    "User-Agent": "touchstone", "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()

        try:
            if number:
                _gh("POST", f"/repos/{owner}/{reponame}/issues/{number}/comments",
                    {"body": body})
            if sha:
                _gh("POST", f"/repos/{owner}/{reponame}/check-runs", {
                    "name": "touchstone/verify", "head_sha": sha,
                    "status": "completed",
                    "conclusion": "success" if res.passed else "failure",
                    "output": {"title": f"verify {res.mode}: "
                               f"{'PASS' if res.passed else 'FAIL'}",
                               "summary": body[:600]}})
        except urllib.error.HTTPError as e:
            print(f"[warn] 回贴失败: {e}", file=sys.stderr)

    sys.exit(0 if res.passed else 1)
