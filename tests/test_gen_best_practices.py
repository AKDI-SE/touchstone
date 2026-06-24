"""standards.yaml → PR-Agent best_practices.md 生成器：只取主观规则、排除可机检、pattern-based。"""
import os

import yaml

import gen_best_practices as G

_STD = os.path.join(os.path.dirname(G.__file__), "..", ".touchstone", "standards.yaml")
_STANDARDS = yaml.safe_load(open(_STD, encoding="utf-8"))

_SUBJECTIVE = {"DUP-001", "CONV-002", "OE-001", "ERR-001", "TEST-002",
               "COR-001", "COR-002", "SCOPE-001", "SPR-VAL-001"}
_MACHINE = {"CONV-001", "TEST-001", "SEC-001", "SEC-002", "CTR-001",
            "SPR-DI-001", "SPR-TX-001", "JAVA-EQ-001", "JAVA-EXC-001", "JAVA-LOG-001"}


def test_select_subjective_picks_only_non_machine_checkable():
    sub = G.select_subjective(_STANDARDS)
    ids = {r["id"] for r in sub}
    assert ids == _SUBJECTIVE
    assert all(not r.get("machine_checkable", False) for r in sub)


def test_render_includes_subjective_excludes_machine_checkable():
    md = G.render_best_practices(G.select_subjective(_STANDARDS))
    for rid in _SUBJECTIVE:
        assert rid in md
    for rid in _MACHINE:
        assert rid not in md                      # 可机检规则不进 best_practices
    assert "Organization best practice" in md     # PR-Agent 的标签语义在头部说明


def test_render_is_pattern_based():
    md = G.render_best_practices(G.select_subjective(_STANDARDS))
    assert md.count("Pattern ") == len(_SUBJECTIVE)        # 每条主观规则一个 pattern
    assert "Pattern 1 (" in md
    assert "- Why:" in md and "- Do:" in md                # 带 why/do，非裸 bullet


def test_render_groups_by_scope():
    md = G.render_best_practices(G.select_subjective(_STANDARDS))
    assert "## 通用 (all languages)" in md
    # java-only 规则单列到自己的 scope 分组
    java_idx = md.index("SPR-VAL-001")
    assert "## java" in md and md.index("## java") < java_idx


def test_render_deterministic_and_bounded():
    a = G.render_best_practices(G.select_subjective(_STANDARDS))
    b = G.render_best_practices(G.select_subjective(_STANDARDS))
    assert a == b                                  # 确定性：可作 CI 一致性校验
    assert a.count("\n") < 800                     # PR-Agent 建议 <800 行


def test_generate_matches_committed_file():
    # 生成结果应与仓内提交的 .touchstone/best_practices.md 一致（防手改漂移）
    committed = open(os.path.join(os.path.dirname(_STD), "best_practices.md"), encoding="utf-8").read()
    assert G.generate(_STD) == committed
