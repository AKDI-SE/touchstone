# -*- coding: utf-8 -*-
# 守卫上下文（issue #139）测试：A 旋钮 / B 生成侧摘要 / C 判后核销面。
import os

from touchstone import guard_context as gc

_SRC = '''\
import os


def loader(path, mode):
    if not path:
        raise ValueError("path required")
    if mode not in ("r", "rb"):
        return None
    assert isinstance(path, str)
    if os.path.exists(path):
        try:
            data = open(path, mode).read()
            result = data.strip()          # ← 命中行（L12）：上有 4 层守卫
        except OSError:
            return None
        return result
    return None
'''


def _repo(tmp_path):
    (tmp_path / "pkg").mkdir(exist_ok=True)
    (tmp_path / "pkg" / "loader.py").write_text(_SRC, encoding="utf-8")
    return str(tmp_path)


# ---------------------------------------------------------------- 底层提取

def test_guard_facts_extracts_all_guard_kinds(tmp_path):
    """命中行的路径守卫（if/try）、前置早退、前置断言全部被提取。"""
    facts = gc.guard_facts(_repo(tmp_path), "pkg/loader.py", 12)
    assert facts["fn"] == "loader"
    joined = " ".join(facts["path_guards"])
    assert "if os.path.exists(path)" in joined          # 条件路径守卫
    assert "try/except OSError" in joined               # try 守卫
    assert any("if not path" in e for e in facts["early_exits"])   # 早退（raise）
    assert any('mode not in' in e for e in facts["early_exits"])   # 早退（return）
    assert facts["asserts"] == 1                        # 前置断言


def test_guard_facts_fail_open_to_none(tmp_path):
    """非 py / 文件不存在 / 语法坏 → None（失败即空，绝不抛出）。"""
    repo = _repo(tmp_path)
    assert gc.guard_facts(repo, "pkg/loader.md", 3) is None
    assert gc.guard_facts(repo, "pkg/nope.py", 3) is None
    (tmp_path / "pkg" / "bad.py").write_text("def broken(:\n", encoding="utf-8")
    assert gc.guard_facts(repo, "pkg/bad.py", 1) is None


def test_facts_line_compact_and_empty_safe():
    assert gc.facts_line(None) == ""
    line = gc.facts_line({"fn": "f", "path_guards": ["if a < b"],
                          "early_exits": ["if not x"], "asserts": 2})
    assert "函数 f" in line and "if a < b" in line and "前置断言×2" in line


# ---------------------------------------------------------------- B：生成侧摘要

_DIFF = """\
diff --git a/pkg/loader.py b/pkg/loader.py
--- a/pkg/loader.py
+++ b/pkg/loader.py
@@ -11,3 +11,3 @@ def loader(path, mode):
         try:
-            data = open(path, mode).read()
+            data = open(path, mode).read()  # touched
             result = data.strip()
"""


def test_render_guard_digest_covers_hit_hunk(tmp_path):
    txt = gc.render_guard_digest(_DIFF, _repo(tmp_path))
    assert "守卫上下文" in txt and "pkg/loader.py" in txt
    assert "try/except OSError" in txt
    assert "不要报缺校验" in txt                         # 指令语义在场


def test_render_guard_digest_fail_open_to_empty(tmp_path):
    assert gc.render_guard_digest("@@@ 不是 diff @@@", _repo(tmp_path)) == ""
    assert gc.render_guard_digest("", _repo(tmp_path)) == ""


# ---------------------------------------------------------------- C：判后核销面

def test_sig_location_parses_both_shapes():
    assert gc._sig_location("PRA-REVIEW:touchstone/probe.py:160") == ("touchstone/probe.py", 160)
    assert gc._sig_location("RULE-X@pkg/loader.py:12") == ("pkg/loader.py", 12)
    assert gc._sig_location("SIZE-001::0") == (None, None)


def test_render_adjudication_only_open_items(tmp_path):
    repo = _repo(tmp_path)
    items = [{"sig": "PRA-REVIEW:pkg/loader.py:12", "status": "open"},
             {"sig": "PRA-REVIEW:pkg/loader.py:12", "status": "done"},
             {"sig": "SIZE-001::0", "status": "open"}]          # 无位置 → 跳过
    txt = gc.render_adjudication(items, repo)
    assert txt.count("pkg/loader.py:12") == 1                   # 只收 open、且不重复
    assert "不要再报同一问题" in txt
    assert gc.render_adjudication([], repo) == ""


def test_attach_guard_facts_open_only_and_idempotent(tmp_path):
    repo = _repo(tmp_path)
    cl = {"items": [{"sig": "PRA-REVIEW:pkg/loader.py:12", "status": "open", "note": ""},
                    {"sig": "PRA-REVIEW:pkg/loader.py:12", "status": "done", "note": ""}]}
    gc.attach_guard_facts(cl, repo)
    assert "try/except OSError" in cl["items"][0].get("guard", "")
    assert "guard" not in cl["items"][1]                        # done 不附着
    cl["items"][0]["guard"] = "已有事实不覆盖"
    gc.attach_guard_facts(cl, repo)
    assert cl["items"][0]["guard"] == "已有事实不覆盖"           # 幂等：不覆盖已有


# ---------------------------------------------------------------- A：扩窗旋钮

def test_patch_context_settings_defaults_and_env_override(monkeypatch):
    from touchstone import pr_agent_runner as r
    for k in ("TOUCHSTONE_DYNAMIC_CONTEXT_MAX", "TOUCHSTONE_PATCH_EXTRA_BEFORE",
              "TOUCHSTONE_PATCH_EXTRA_AFTER"):
        monkeypatch.delenv(k, raising=False)
    s = r._patch_context_settings()
    assert s == {"allow_dynamic_context": True,
                 "max_extra_lines_before_dynamic_context": 30,
                 "patch_extra_lines_before": 10, "patch_extra_lines_after": 3}
    monkeypatch.setenv("TOUCHSTONE_DYNAMIC_CONTEXT_MAX", "10")   # 消融回调到上游默认
    monkeypatch.setenv("TOUCHSTONE_PATCH_EXTRA_BEFORE", "5")
    monkeypatch.setenv("TOUCHSTONE_PATCH_EXTRA_AFTER", "not-a-number")   # 坏值回默认
    s = r._patch_context_settings()
    assert s["max_extra_lines_before_dynamic_context"] == 10
    assert s["patch_extra_lines_before"] == 5
    assert s["patch_extra_lines_after"] == 3


# ============================ PR #140 round-1 销项回归 ============================
_NESTED_SRC = '''\
def outer(x):
    def helper(y):
        assert y > 0
        if not y:
            raise ValueError("inner")
        return y * 2
    value = helper(x)
    result = value + 1        # ← 命中行（L8）：内层守卫不得泄漏
    return result
'''


def test_nested_function_guards_do_not_leak(tmp_path):
    """R1-01：闭包/内层 def 的 assert 与早退不得计入外层函数事实——
    虚假守卫会让核销面压制真报，比误报更危险。"""
    (tmp_path / "pkg").mkdir(exist_ok=True)
    (tmp_path / "pkg" / "nested.py").write_text(_NESTED_SRC, encoding="utf-8")
    facts = gc.guard_facts(str(tmp_path), "pkg/nested.py", 8)
    assert facts["fn"] == "outer"
    assert facts["asserts"] == 0                                 # 内层 assert 不泄漏
    assert not any("not y" in e for e in facts["early_exits"])   # 内层早退不泄漏
    inner = gc.guard_facts(str(tmp_path), "pkg/nested.py", 6)    # 内层自身仍正常提取
    assert inner["fn"] == "helper" and inner["asserts"] == 1


def test_digest_parses_each_file_once(tmp_path, monkeypatch):
    """R1-02/03：hunk 多行探测每文件只 parse 一次（消除逐行重复读盘+重解析）。"""
    repo = _repo(tmp_path)
    calls = {"n": 0}
    real = gc._parse
    def counting(repo_dir, path):
        calls["n"] += 1
        return real(repo_dir, path)
    monkeypatch.setattr(gc, "_parse", counting)
    src_lines = _SRC.splitlines()                                 # 真实宽 hunk：全文件上下文 +
    body = [" " + l for l in src_lines]                           # 中段一行改动（跨度 = 文件全长）
    body[11] = "-" + src_lines[11]
    body.insert(12, "+" + src_lines[11] + "  # touched")
    wide = ("diff --git a/pkg/loader.py b/pkg/loader.py\n--- a/pkg/loader.py\n+++ b/pkg/loader.py\n"
            f"@@ -1,{len(src_lines)} +1,{len(src_lines)} @@\n" + "\n".join(body) + "\n")
    txt = gc.render_guard_digest(wide, repo)
    assert "pkg/loader.py" in txt
    assert calls["n"] == 1                                        # 全跨度多点探测仍只 parse 一次
