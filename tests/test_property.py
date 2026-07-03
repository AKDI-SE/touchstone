"""#5 属性测试（property-based）：对纯解析器喂随机/畸形输入，断言不变量
（永不抛、结果类型稳定、roundtrip）。hypothesis 未装则整体 skip。"""
import pytest
hypothesis = pytest.importorskip("hypothesis")  # noqa
from hypothesis import given, settings, strategies as st


# ---------------- _extract_json：任意输入永不抛 + 返回 default 或 JSON ----------------
import learning_loop as L


@given(st.text(max_size=200))
@settings(max_examples=100)
def test_extract_json_never_raises_and_returns_default_or_parsed(text):
    out = L._extract_json(text, "DEF")
    assert out == "DEF" or out is not None     # 要么 default，要么解析出的值（永不为 None-抛错）


# ---------------- parse_diff / parse_changed_lines：任意输入永不抛 ----------------
import contract_check as cc
import verify_change as V


@given(st.text(max_size=500))
@settings(max_examples=100)
def test_parse_diff_never_raises(text):
    files, added = cc.parse_diff(text)
    assert isinstance(files, set) and isinstance(added, dict)


@given(st.text(max_size=500))
@settings(max_examples=100)
def test_parse_changed_lines_never_raises(text):
    out = V.parse_changed_lines(text)
    assert isinstance(out, dict) and all(isinstance(v, set) for v in out.values())


# ---------------- parse_pr_agent：任意 dict/list 永不抛 ----------------
import review_provider as rp


@given(st.one_of(st.dictionaries(st.text(min_size=1, max_size=8),
                                 st.one_of(st.text(), st.integers(), st.lists(st.text()))),
                 st.lists(st.integers()), st.none()))
@settings(max_examples=80)
def test_parse_pr_agent_never_raises(raw):
    out = rp.parse_pr_agent(raw)
    assert isinstance(out, list)


# ---------------- diff roundtrip：构造的单文件 diff，parse_diff 抽出的 added 行数正确 ----------------
@given(st.lists(st.text(alphabet="abc ", min_size=0, max_size=20), min_size=0, max_size=5))
@settings(max_examples=60)
def test_parse_diff_roundtrip_added_lines(lines):
    # 构造一个合法的单文件纯新增 diff
    body = "".join(f"+{ln}\n" for ln in lines)
    diff = (f"diff --git a/m.py b/m.py\n--- a/m.py\n+++ b/m.py\n"
            f"@@ -0,0 +1,{len(lines) or 1} @@\n{body}")
    _, added = cc.parse_diff(diff)
    # 该文件的 added 行数应等于输入行数（unidiff 解析合法 diff）
    assert len(added.get("m.py", [])) == len(lines)
