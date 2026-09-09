# -*- coding: utf-8 -*-
"""PR 列表页零点击可见性（用户诉求：不想每个 PR 点进去拖到底才知道销项状态）。

两层信号，均 GitHub-only：
  1. 标签：converged（绿）/ open-findings + 未销项量级桶（1–3 / 4–10 / 11+）——
     列表页常驻徽章，零点击；
  2. check-run 标题：悬停 checks 图标即见「✅ 已闭环 / 🔁 未销项 N 项 / ⬆️ 已升级到人」。
GitCode 守卫跳过（标签通路与渲染未核实，同 #219 折叠守卫模式）。全部离线 mock。
"""
from urllib.parse import quote

import pytest
import requests

from touchstone import orchestrator as orc

_RISK = {"risk_band": "low", "human_action": "skip",
         "verification_decision": "cheap_only", "blast_radius": []}


def _cl(*statuses):
    return {"items": [{"status": s, "sig": f"sig-{i}"} for i, s in enumerate(statuses)]}


class _GH:
    """gh() 桩：记录调用；GET /labels/{name} 恒 404（触发带色预建）；其余成功。"""

    def __init__(self, fail_all=False):
        self.calls = []
        self.fail_all = fail_all

    def __call__(self, method, path, token, data=None, accept="application/vnd.github+json"):
        self.calls.append((method, path, data))
        if self.fail_all:
            raise requests.exceptions.ConnectionError("api down")
        if method == "GET" and "/labels/" in path:
            raise requests.exceptions.HTTPError("404")
        return {}


# ---------------- 标签同步 ----------------
def test_sync_converged_adds_green_removes_open(monkeypatch):
    """converged → 加绿徽章；旧 open 状态/桶标签全清（残留即说谎）。"""
    gh = _GH()
    monkeypatch.setattr(orc, "gh", gh)
    orc._sync_state_labels("o", "r", 1, "t", "converged", _cl("done", "waived"))
    adds = [c for c in gh.calls if c[0] == "POST" and c[1].endswith("/issues/1/labels")]
    assert adds and adds[0][2]["labels"] == ["touchstone:converged"]
    dels = {c[1].rsplit("/", 1)[-1] for c in gh.calls if c[0] == "DELETE"}
    assert {quote(n) for n in orc._TS_OPEN_LABELS} <= dels
    pre = [c for c in gh.calls if c[0] == "POST" and c[1].endswith("/labels")
           and isinstance(c[2], dict) and c[2].get("name")]
    assert pre and pre[0][2]["color"] == "0E8A16"     # 预建带色（非灰默认）


@pytest.mark.parametrize("open_n,want", [(0, "touchstone:open-1-3"), (2, "touchstone:open-1-3"),
                                         (3, "touchstone:open-1-3"), (4, "touchstone:open-4-10"),
                                         (10, "touchstone:open-4-10"), (11, "touchstone:open-11+"),
                                         (99, "touchstone:open-11+")])
def test_sync_open_bucket_selection(monkeypatch, open_n, want):
    """未闭环 → open-findings + 量级桶；其他桶与 converged 全清，当前桶不误删。"""
    gh = _GH()
    monkeypatch.setattr(orc, "gh", gh)
    orc._sync_state_labels("o", "r", 1, "t", "continue", _cl(*(["open"] * open_n)))
    adds = [c for c in gh.calls if c[0] == "POST" and c[1].endswith("/issues/1/labels")]
    assert adds and adds[0][2]["labels"] == ["touchstone:open-findings", want]
    dels = {c[1].rsplit("/", 1)[-1] for c in gh.calls if c[0] == "DELETE"}
    assert quote("touchstone:converged") in dels
    for b in ("touchstone:open-1-3", "touchstone:open-4-10", "touchstone:open-11+"):
        if b != want:
            assert quote(b) in dels
        else:
            assert quote(b) not in dels


def test_sync_escalate_keeps_open_labels(monkeypatch):
    """escalate 也未闭环：open 标签照打（needs-human 由既有 escalate 块负责，不在此测）。"""
    gh = _GH()
    monkeypatch.setattr(orc, "gh", gh)
    orc._sync_state_labels("o", "r", 1, "t", "escalate", _cl("open", "open", "done"))
    adds = [c for c in gh.calls if c[0] == "POST" and c[1].endswith("/issues/1/labels")]
    assert adds and adds[0][2]["labels"] == ["touchstone:open-findings", "touchstone:open-1-3"]


def test_sync_gitcode_guard_skips(monkeypatch):
    """GitCode 守卫：零 API 调用 + [info] 留痕（通路未核实，不做半吊子适配）。"""
    gh = _GH()
    monkeypatch.setattr(orc, "gh", gh)
    monkeypatch.setenv("TOUCHSTONE_PLATFORM", "gitcode")
    orc._sync_state_labels("o", "r", 1, "t", "continue", _cl("open"))
    assert not gh.calls


def test_set_labels_never_raises(monkeypatch, capsys):
    """API 全挂 → 只 [warn] 不抛（标签是传达渠道，评论/check-run 才是契约本体）。"""
    monkeypatch.setattr(orc, "gh", _GH(fail_all=True))
    orc._set_labels("o", "r", 1, "t", add=["x"], remove=["y"])            # 不抛即通过
    orc._sync_state_labels("o", "r", 1, "t", "continue", _cl("open"))    # 不抛即通过
    assert "标签增删失败" in capsys.readouterr().err


def test_set_labels_noop_on_empty(monkeypatch):
    gh = _GH()
    monkeypatch.setattr(orc, "gh", gh)
    orc._set_labels("o", "r", 1, "t", add=[], remove=[])
    assert not gh.calls


# ---------------- check-run 标题 ----------------
def test_checkrun_title_carries_loop_state(monkeypatch):
    """标题三态：✅ 已闭环 / 🔁 未销项 N 项（精确数） / ⬆️ 已升级到人。"""
    titles = []

    def fake_gh(method, path, token, data=None, accept=""):
        if method == "GET" and "/labels/" in path:
            raise requests.exceptions.HTTPError("404")
        if method == "POST" and path.endswith("/check-runs"):
            titles.append(data["output"]["title"])
        return {}

    monkeypatch.setattr(orc, "gh", fake_gh)
    for loop_info, cl, frag in (
            (("converged", "r", "<!-- m -->"), _cl("done"), "✅ 已闭环"),
            (("continue", "r", "<!-- m -->"), _cl("open", "done"), "🔁 未销项 1 项"),
            (("escalate", "r", "<!-- m -->"), _cl("open"), "⬆️ 已升级到人")):
        orc.post_results("o", "r", 5, "sha", "t", _RISK, [], loop_info=loop_info, checklist=cl)
        assert frag in titles[-1]
    assert "风险等级" in titles[0]        # 原有信息不丢
