# ============================================================================
# tests/test_verify_phases.py —— verify 两阶段拆分（凭据隔离）专项
# ----------------------------------------------------------------------------
# 核心不变式：
#   1. plan 阶段【绝不执行】PR 代码（run_generated/run_suite/覆盖/变异都不许碰）
#   2. plan 产物可 JSON 序列化，经落盘再读回后 execute 结果与单进程 verify_change 等价
#   3. execute 阶段不需要 llm_cfg（凭据只进 plan）
# ============================================================================
import json

import pytest

from verify import verify_change as V


class _FakeRunner:
    lang = "python"
    supports_spec_blind = True

    def __init__(self, log):
        self.log = log

    def extract_interface(self, work_dir, changed_files):
        self.log.append("extract_interface")
        return "def f(x): ..."

    def run_generated(self, work_dir, code):
        self.log.append("run_generated")
        return True, "ok"

    def run_suite(self, work_dir):
        self.log.append("run_suite")
        return True, "ok"

    def changed_coverage(self, work_dir, changed_files, changed_lines):
        self.log.append("changed_coverage")
        return 0.9

    def mutation(self, work_dir, changed_files):
        self.log.append("mutation")
        return 0.9


@pytest.fixture
def wired(monkeypatch, tmp_path):
    """把 select_runner/worktree/LLM/规格/充分性全部 mock 成确定性假件，返回 (log, runner)。"""
    log = []
    runner = _FakeRunner(log)
    monkeypatch.setattr(V, "select_runner", lambda repo, files: runner)
    monkeypatch.setattr(V, "_worktree", lambda repo, ref: str(tmp_path / ref))
    monkeypatch.setattr(V, "_rm_worktree", lambda repo, d: None)
    monkeypatch.setattr(V, "_changed_lines", lambda repo, b, h: {})
    monkeypatch.setattr(V, "resolve_acceptance_spec",
                        lambda contract, repo: (["f 返回 x+1"], "human_curated"))
    monkeypatch.setattr(V, "generate_spec_blind_tests",
                        lambda criteria, interface, llm, fw: (
                            log.append("llm_generate") or
                            V.AcceptanceTestSet(code="def test_a(): assert 1",
                                                source="spec_blind", author_model="m")))
    monkeypatch.setattr(V, "check_adequacy",
                        lambda *a, **k: V.AdequacyResult(changed_file_coverage=0.9,
                                                         sentinel_passed=True,
                                                         mutation_score=None,
                                                         verdict="adequate"))
    return log, runner


def test_plan_never_executes_pr_code(wired):
    """不变式 1：plan 阶段只读接口 + 调 LLM，绝不 run_generated/run_suite/覆盖/变异。"""
    log, _ = wired
    plan = V.plan_verification(".", {}, ["a.py"], "base", "head",
                               "targeted_tests", {"base_url": "u", "api_key": "k", "model": "m"})
    assert plan["route"] == "spec_blind"
    assert "llm_generate" in log and "extract_interface" in log
    forbidden = {"run_generated", "run_suite", "changed_coverage", "mutation"}
    assert not (set(log) & forbidden), f"plan 阶段执行了 PR 代码: {set(log) & forbidden}"


def test_plan_roundtrip_execute_equals_single_shot(wired, tmp_path):
    """不变式 2：plan 落盘 JSON → 读回 → execute 与单进程 verify_change 等价判决。"""
    log, _ = wired
    llm = {"base_url": "u", "api_key": "k", "model": "m"}
    single = V.verify_change(".", {}, ["a.py"], "base", "head", "targeted_tests", llm)

    plan = V.plan_verification(".", {}, ["a.py"], "base", "head", "targeted_tests", llm)
    p = tmp_path / "acceptance-tests.json"
    p.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    reloaded = json.loads(p.read_text(encoding="utf-8"))
    split = V.execute_verification(".", reloaded, ["a.py"], "base", "head")

    assert (split.passed, split.mode, split.head_tests_pass, split.spec_source) == \
           (single.passed, single.mode, single.head_tests_pass, single.spec_source)


def test_execute_needs_no_llm_cfg(wired):
    """不变式 3：execute 签名/路径完全不接触 llm_cfg——凭据只进 plan。"""
    plan = {"schema": 1, "mode": "targeted_tests", "route": "spec_blind",
            "spec_source": "human_curated", "framework": "pytest",
            "tests": {"code": "def test_a(): assert 1", "source": "spec_blind",
                      "author_model": "m"}}
    res = V.execute_verification(".", plan, ["a.py"], "base", "head")
    assert res.passed is True and res.mode == "targeted_tests"


def test_plan_routes_cheap_and_regression(wired):
    log, runner = wired
    assert V.plan_verification(".", {}, ["a.py"], "b", "h", "cheap_only", {})["route"] == "cheap_only"
    assert V.plan_verification(".", {}, ["a.py"], "b", "h", "regression_only", {})["route"] == "regression"
    # 无规格 → 回归 route + 提示前缀（execute 时拼进 evidence）
    import verify.verify_change as VV
    orig = VV.resolve_acceptance_spec
    VV.resolve_acceptance_spec = lambda c, r: ([], None)
    try:
        plan = V.plan_verification(".", {}, ["a.py"], "b", "h", "targeted_tests", {})
        assert plan["route"] == "regression" and "无验收规格" in plan["evidence_prefix"]
        res = V.execute_verification(".", plan, ["a.py"], "b", "h")
        assert res.evidence.startswith("无验收规格")
    finally:
        VV.resolve_acceptance_spec = orig


def test_execute_missing_plan_route_unsupported(monkeypatch):
    """仓库状态漂移兜底：execute 阶段选不出 runner → unsupported，不崩。"""
    monkeypatch.setattr(V, "select_runner", lambda repo, files: None)
    res = V.execute_verification(".", {"schema": 1, "mode": "targeted_tests",
                                       "route": "spec_blind"}, ["a.py"], "b", "h")
    assert res.passed is None and res.mode == "unsupported"
