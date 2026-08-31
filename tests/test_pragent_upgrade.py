# -*- coding: utf-8 -*-
"""PR-Agent 0.44.0 升级伴随行为的回归锁（propagate_tool_errors + 评审覆盖面透传）。

三层：
  1. runner 全流程（sys.modules 桩 pr_agent 树，模式同 test_llm_call_tuning）：
     - propagate_tool_errors 被开启（fail-closed 旋钮）
     - remaining_files_list → review._unreviewed_files（清洗 + 截断 + 缺失回空）
     - 工具 run() 抛异常 → _degraded=llm_failed（0.44 re-raise 语义下的活路径）
  2. review_provider：_extract_unreviewed 边界防御 + fetch 出口 meta + 覆盖面清单
     不灌水 engaged 计数（_NONCONTENT_REVIEW_KEYS 契约）。
  3. orchestrator（pr_agent_output 注入）：覆盖面清单 → llm_notes 横幅 + 返回值。
"""
import asyncio
import sys
import types

import pytest

import touchstone.pr_agent_runner as R
import touchstone.review_provider as RP


# ---------------- 1. runner 全流程（桩 pr_agent 树）----------------
class _Cfg:
    def __init__(self):
        self.publish_output = True
        self.publish_output_progress = True


class _Settings:
    def __init__(self):
        self.config = _Cfg()
        self.github = types.SimpleNamespace()


def _fake_pr_agent_tree(monkeypatch, *, reviewer_cls):
    """铺 runner.run() 消费的完整 pr_agent 模块树（模式同 test_llm_call_tuning 的
    _install_fake_tree，扩展到 config_loader/tools）。"""
    settings = _Settings()

    mod_root = types.ModuleType("pr_agent")
    mod_algo = types.ModuleType("pr_agent.algo")
    mod_algo.STREAMING_REQUIRED_MODELS = []
    mod_utils = types.ModuleType("pr_agent.algo.utils")

    def _load_yaml(text, **kw):
        return {"review": {"key_issues_to_review": [
            {"relevant_file": "a.py", "issue_header": "h", "issue_content": "c"}]}}

    mod_utils.load_yaml = _load_yaml
    mod_cfg = types.ModuleType("pr_agent.config_loader")
    mod_cfg.get_settings = lambda: settings
    mod_tools = types.ModuleType("pr_agent.tools")
    mod_cs = types.ModuleType("pr_agent.tools.pr_code_suggestions")
    mod_cs.PRCodeSuggestions = object          # mode=review 不构造 cs
    mod_rv = types.ModuleType("pr_agent.tools.pr_reviewer")
    mod_rv.PRReviewer = reviewer_cls
    # litellm 调优的导入面（缺失属性只会 fail-loud 打印，不影响断言）
    mod_lah = types.ModuleType("pr_agent.algo.ai_handlers.litellm_ai_handler")
    mod_lah.acompletion = lambda *a, **k: None
    mod_lah.LiteLLMAIHandler = type("H", (), {"chat_completion": None})
    mod_aih = types.ModuleType("pr_agent.algo.ai_handlers")

    for name, mod in {
        "pr_agent": mod_root, "pr_agent.algo": mod_algo,
        "pr_agent.algo.utils": mod_utils, "pr_agent.config_loader": mod_cfg,
        "pr_agent.tools": mod_tools, "pr_agent.tools.pr_code_suggestions": mod_cs,
        "pr_agent.tools.pr_reviewer": mod_rv,
        "pr_agent.algo.ai_handlers": mod_aih,
        "pr_agent.algo.ai_handlers.litellm_ai_handler": mod_lah,
    }.items():
        monkeypatch.setitem(sys.modules, name, mod)
    return settings


def _mk_reviewer(*, remaining=None, prediction="review:\n  key_issues_to_review: []\n", exc=None):
    class _RV:
        def __init__(self, pr_url):
            self.prediction = prediction
            if remaining is not None:
                self.remaining_files_list = remaining

        async def run(self):
            if exc:
                raise exc
    return _RV


def _run_env(monkeypatch):
    monkeypatch.setenv("TOUCHSTONE_LLM_PING", "false")     # 跳过 LLM 预检（无真实端点）
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    # LLM 配置完备性检查需要三件套齐（ping 已关，不会真触网）
    monkeypatch.setenv("LLM_MODEL", "glm-test")
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("LLM_BASE_URL", "http://127.0.0.1:1")
    monkeypatch.delenv("TOUCHSTONE_INTERACTION_LOG", raising=False)


def test_run_sets_propagate_tool_errors(monkeypatch):
    """0.44 新旋钮必须开启：工具内部错误 re-raise → llm_failed 活路径（fail-closed）。"""
    _run_env(monkeypatch)
    _fake_pr_agent_tree(monkeypatch, reviewer_cls=_mk_reviewer())
    out = R.run("https://github.com/o/r/pull/1", "review")
    assert out.get("review", {}).get("key_issues_to_review")    # 正常路径通了
    settings = _cur_settings(monkeypatch)
    assert settings.config.propagate_tool_errors is True
    assert settings.config.publish_output is False              # 既有行为不回归


def _cur_settings(monkeypatch):
    # get_settings 桩是同一个闭包对象：经 config_loader 模块取回
    return sys.modules["pr_agent.config_loader"].get_settings()


def test_run_surfaces_unreviewed_files(monkeypatch):
    """remaining_files_list → review._unreviewed_files：str 化、去空、保序。"""
    _run_env(monkeypatch)
    _fake_pr_agent_tree(monkeypatch,
                        reviewer_cls=_mk_reviewer(remaining=["b.py", " a.py ", "", 7, None]))
    out = R.run("https://github.com/o/r/pull/1", "review")
    assert out["review"]["_unreviewed_files"] == ["b.py", "a.py"]   # 7/None 非 str 丢弃


def test_run_unreviewed_missing_attr_and_cap(monkeypatch):
    """旧版（0.39–0.43）无属性 → 空清单；畸形巨表 → 截断至 100。"""
    _run_env(monkeypatch)
    _fake_pr_agent_tree(monkeypatch, reviewer_cls=_mk_reviewer())
    out = R.run("https://github.com/o/r/pull/1", "review")
    assert out["review"]["_unreviewed_files"] == []

    _fake_pr_agent_tree(monkeypatch,
                        reviewer_cls=_mk_reviewer(remaining=[f"f{i}.py" for i in range(150)]))
    out = R.run("https://github.com/o/r/pull/1", "review")
    assert len(out["review"]["_unreviewed_files"]) == 100
    assert out["review"]["_unreviewed_total"] == 150     # 截断保真：总数不随列表截小


def test_run_tool_exception_degrades_llm_failed(monkeypatch):
    """0.44 propagate_tool_errors 语义：工具 re-raise → 既有 except → llm_failed，
    绝不把崩溃伪装成空结果（假绿灯）。"""
    _run_env(monkeypatch)
    _fake_pr_agent_tree(
        monkeypatch,
        reviewer_cls=_mk_reviewer(exc=RuntimeError("boom inside tool")))
    out = R.run("https://github.com/o/r/pull/1", "review")
    assert out.get("_degraded") == "llm_failed"
    assert "boom inside tool" in out.get("reason", "")


# ---------------- 2. review_provider ----------------
def test_extract_unreviewed_defense():
    raw = {"review": {"_unreviewed_files": ["a.py", " b.py ", "", 3, None]}}
    assert RP._extract_unreviewed(raw) == ["a.py", "b.py"]          # 3 非 str 丢弃
    assert RP._extract_unreviewed({}) == []
    assert RP._extract_unreviewed(None) == []
    assert RP._extract_unreviewed({"review": None}) == []
    assert RP._extract_unreviewed({"review": {"_unreviewed_files": "a.py"}}) == []
    assert RP._extract_unreviewed({"review": {"_unreviewed_files": [None, "  ", 3]}}) == []


def test_unreviewed_not_counted_as_engaged_content():
    """覆盖面清单是元信号不是评审内容段：仅它非空不得抬高 engaged（假 review_reliable）。"""
    data = {"review": {"_unreviewed_files": ["a.py", "b.py"]}}
    assert RP.compute_engaged(data) is False
    assert RP._extract_engaged(data) is False


def test_extract_unreviewed_total_defense():
    """总数键：int 原样、bool 拒收（isinstance(True,int)）、负数/畸形 → None 回退 len。"""
    raw = {"review": {"_unreviewed_total": 150}}
    assert RP._extract_unreviewed_total(raw) == 150
    assert RP._extract_unreviewed_total({"review": {"_unreviewed_total": True}}) is None
    assert RP._extract_unreviewed_total({"review": {"_unreviewed_total": -1}}) is None
    assert RP._extract_unreviewed_total({"review": {"_unreviewed_total": "9"}}) is None
    assert RP._extract_unreviewed_total({}) is None


def test_fetch_sets_unreviewed_meta():
    """fetch 出口把覆盖面清单写进 _LAST_META（注入路径同子进程路径同口径）。"""
    prov = RP.PRAgentProvider()
    prov.fetch({"pr_agent_output": {"review": {"_unreviewed_files": ["x.py"], "_unreviewed_total": 9,
                                           "key_issues_to_review": []}}})
    assert RP.invoke_meta().get("unreviewed_files") == ["x.py"]
    assert RP.invoke_meta().get("unreviewed_total") == 9


# ---------------- 3. orchestrator（注入端到端）----------------
def test_review_pr_banners_unreviewed_files():
    """覆盖面非空 → llm_notes 横幅点名（前 5 + 总数）+ 返回值透传（findings 产物落盘源）。"""
    from touchstone import orchestrator as orc
    diff = "diff --git a/f.py b/f.py\n--- a/f.py\n+++ b/f.py\n@@ -0,0 +1,2 @@\n+a\n+b\n"
    pr = {"diff": diff, "pr_agent_output": {
        "code_suggestions": [], "review": {"key_issues_to_review": [],
                                           "_unreviewed_files": [f"big{i}.py" for i in range(7)],
                                           "_unreviewed_total": 9}}}
    out = orc.review_pr(pr, {}, {})
    assert out["unreviewed_files"] == [f"big{i}.py" for i in range(7)]
    assert out["unreviewed_total"] == 9
    note = [n for n in out["llm_notes"] if "评审覆盖面" in n]
    # 总数按真值 9 报（列表只有 7）：截断/部分清单不得把覆盖缺口报小
    assert note and "9 个文件" in note[0] and "big0.py" in note[0] and "等" in note[0]


def test_review_pr_no_banner_when_fully_covered():
    """覆盖面空（含 _unreviewed_files 缺失/空清单）→ 不出横幅（不过度声明覆盖缺口）。"""
    from touchstone import orchestrator as orc
    diff = "diff --git a/f.py b/f.py\n--- a/f.py\n+++ b/f.py\n@@ -0,0 +1,2 @@\n+a\n+b\n"
    pr = {"diff": diff, "pr_agent_output": {
        "code_suggestions": [], "review": {"key_issues_to_review": [], "_unreviewed_files": []}}}
    out = orc.review_pr(pr, {}, {})
    assert out["unreviewed_files"] == []
    assert out["unreviewed_total"] == 0
    assert not [n for n in out["llm_notes"] if "评审覆盖面" in n]
