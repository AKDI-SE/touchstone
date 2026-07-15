"""#防静默故障：LLM 出错时，review 不得伪装成"干净 / 可信 / 可收敛"。

本套端到端注入各 LLM 故障模式（子进程超时、坏 JSON、非零退出、`_degraded` 自报、
吞没失败、内容过滤、可疑空收敛），断言可靠性链
  engine_status → review_reliable → loop 收敛
不假收敛、不放行未评审代码。这是 Touchstone 最大风险类——LLM 随机性 / 内容过滤 / 子进程
边界出错时返回看似合法的空评审，被误判成"审完无问题"。

全部离线 mock（注入 seam `pr_agent_output` + `subprocess.run` 打桩），不触网、不真调 LLM、
进 CI。真 LLM 故障场景见 test_e2e_llm.py（按需跑）。
"""
import json
import os
import subprocess as _sp

import pytest

from touchstone import orchestrator as orc
from touchstone import review_provider as RP
from touchstone import loop as _lp
from helpers import build_diff


def _standards():
    import yaml
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return yaml.safe_load(open(os.path.join(root, ".touchstone", "standards.yaml"), encoding="utf-8"))


def _pr(diff_pairs, pr_agent_output="__omit__"):
    """最小 PR 上下文。diff_pairs: [(path, [lines], is_added), ...]；直接喂 build_diff。
    pr_agent_output="__omit__" 时不放该键（走子进程路径），否则走注入 seam。"""
    diff = build_diff(diff_pairs)
    pr = {"owner": "o", "repo": "r", "number": 1, "sha": "s", "token": "t", "diff": diff}
    if pr_agent_output != "__omit__":
        pr["pr_agent_output"] = pr_agent_output
    return pr


class _Proc:
    """subprocess.run 打桩返回体。"""
    def __init__(self, rc=0, out="", err=""):
        self.returncode, self.stdout, self.stderr = rc, out, err


@pytest.fixture(autouse=True)
def _no_diff_limit(monkeypatch):
    """显式关闭 SIZE-001 体量门禁（防 skipped_large_diff 干扰引擎降级断言）。
    默认值已是 1000（size-gate-default-1000），这里 setenv 0 强制关，与默认值解耦、稳定隔离。"""
    monkeypatch.setenv("TOUCHSTONE_MAX_DIFF_LINES", "0")


# ============================================================================
# 性质：engaged 不救引擎降级（防假收敛的基石）
# ============================================================================
def test_reliable_engaged_does_not_rescue_engine_degradation():
    """引擎降级时，即便 engaged=True，review_reliable 仍 False。
    engaged 只放宽"可疑空收敛"，不救"引擎没真跑 / LLM 调用失败"——
    LLM 挂了 → 0 建议是缺审，非审完无问题。这是防静默故障的基石。"""
    for degraded in ("no_engine", "llm_failed", "provider_failed", "skipped_large_diff"):
        assert RP.review_reliable(degraded, 0, 200, engaged=True) is False
        assert RP.review_reliable(degraded, 5, 200, engaged=True) is False   # 有建议也救不回降级


def test_reliable_ok_engaged_clean_is_trusted():
    """对照：engine ok + 大改动 + 0 建议 + engaged（glm 真多段评审）= 审完无问题，可信。
    （PR #57 ed7e57b 真场景：effort/relevant_tests/security_concerns 三段、0 issues/suggestions。）"""
    assert RP.review_reliable("ok", 0, 200, engaged=True) is True


def test_reliable_suspicious_empty_when_not_engaged():
    """engine ok + 大改动(>=20) + 0 建议 + 未 engaged = 可疑空收敛（diff 可能被裁空），不可信。"""
    assert RP.review_reliable("ok", 0, 20, engaged=False) is False
    assert RP.review_reliable("ok", 0, 500, engaged=False) is False


def test_reliable_small_change_relaxes_and_findings_trust():
    """engine ok + 小改动(<20) + 0 建议 = 合理（无米下锅），可信；有原始建议则不论大小可信。"""
    assert RP.review_reliable("ok", 0, 19, engaged=False) is True
    assert RP.review_reliable("ok", 3, 5, engaged=False) is True
    assert RP.review_reliable("ok", 1, 200, engaged=False) is True


# ============================================================================
# compute_engaged：内部标志键不得灌水（本 PR 修复，锁死）
# ============================================================================
def test_compute_engaged_internal_flag_keys_do_not_inflate():
    """_engaged / _raw_excerpt 是 runner 注入的内部标志，非真评审段——不计入 engaged 段数。
    修复前：仅 _engaged=True 无真段 → 误判 True → 假 review_reliable → 假收敛。
    单一真源 _NONCONTENT_REVIEW_KEYS 同时服务 compute_engaged 与 extract_review_excerpt。"""
    assert RP.compute_engaged({"review": {"_engaged": True}}) is False
    assert RP.compute_engaged({"review": {"_engaged": True, "_raw_excerpt": {"x": "1"}}}) is False
    assert RP.compute_engaged({"review": {"estimated_effort_to_review": "2",
                                          "_raw_excerpt": {"a": "1"}}}) is False   # 仅 1 真段
    # 对照：2 个真段（不含任何内部键）→ True
    assert RP.compute_engaged({"review": {"estimated_effort_to_review": "2",
                                          "security_concerns": "No"}}) is True


# ============================================================================
# 端到端：子进程故障 → review_pr engine_status 降级 → review_reliable False
# ============================================================================
@pytest.mark.parametrize("rc,out,err,expected_status", [
    ("timeout", None, None, "llm_failed"),                              # 子进程超时
    (2, "", "boom-detail", "no_engine"),                                # 非零退出（适配器自身崩）
    (0, "not json at all", "", "no_engine"),                            # 坏 JSON（无哨兵、raw_decode 也失败）
])
def test_e2e_subprocess_hard_fault_degrades(monkeypatch, rc, out, err, expected_status):
    """子进程硬故障（超时 / 非零退出 / 坏 JSON）→ engine_status 降级 → 不可信。"""
    def fake_run(*a, **k):
        if rc == "timeout":
            raise _sp.TimeoutExpired(cmd="pr-agent", timeout=1)
        return _Proc(rc, out=out, err=err)
    monkeypatch.setattr(RP.subprocess, "run", fake_run)
    pr = _pr([("src/Main.java", ["public class Main { int x; }"], True)])
    out_dict = orc.review_pr(pr, {}, _standards())
    assert out_dict["engine_status"] == expected_status
    assert RP.review_reliable(out_dict["engine_status"], out_dict["ai_raw_count"],
                              out_dict["added_lines"], out_dict["engaged"]) is False


def test_e2e_degraded_field_self_report_degrades(monkeypatch):
    """runner 自报 _degraded 字段（如 LLM AuthError / 内容过滤被 runner 捕获）→ 降级。"""
    payload = json.dumps({"_degraded": "llm_failed", "reason": "AuthError: 401",
                          "code_suggestions": [], "review": {"key_issues_to_review": []}})
    monkeypatch.setattr(RP.subprocess, "run", lambda *a, **k: _Proc(0, out=payload, err=""))
    pr = _pr([("src/Main.java", ["public class Main { int x; }"], True)])
    out = orc.review_pr(pr, {}, _standards())
    assert out["engine_status"] == "llm_failed"
    assert RP.review_reliable(out["engine_status"], 0, out["added_lines"], out["engaged"]) is False


def test_e2e_swallowed_failure_degrades(monkeypatch):
    """吞没失败：退出码 0、无 _degraded 字段、但 stderr 含失败签名 + 本轮 0 原始建议
    （LLM 空 content 被 retry 吞、run() 再吞）→ 命中 prediction_swallowed_failure → llm_failed。
    这是最阴险的静默故障：表面"正常返回 0 建议"，实为 LLM 失败。"""
    payload = json.dumps({"code_suggestions": [], "review": {"key_issues_to_review": []}})
    err = "...Failed to generate prediction with any model...\n"
    monkeypatch.setattr(RP.subprocess, "run", lambda *a, **k: _Proc(0, out=payload, err=err))
    pr = _pr([("src/Main.java", ["public class Main { int x; }"], True)])
    out = orc.review_pr(pr, {}, _standards())
    assert out["engine_status"] == "llm_failed"
    assert RP.review_reliable(out["engine_status"], 0, out["added_lines"], out["engaged"]) is False


def test_e2e_litellm_stdout_pollution_does_not_degrade(monkeypatch):
    """对照：litellm 延迟打印 'Logging Details LiteLLM-Async Success Call' 污染 stdout
    （PR #49 真根因）→ 哨兵/raw_decode 必须救回 → engine ok（不误降级）。"""
    payload = json.dumps({"code_suggestions": [], "review": {"key_issues_to_review": []}})
    noisy = payload + "Logging Details LiteLLM-Async Success Call, cache_hit=None"
    monkeypatch.setattr(RP.subprocess, "run", lambda *a, **k: _Proc(0, out=noisy, err=""))
    pr = _pr([("src/Main.java", ["public class Main { int x; }"], True)])
    out = orc.review_pr(pr, {}, _standards())
    assert out["engine_status"] == "ok"


# ============================================================================
# 注入 seam：数据级故障 / 正当干净评审
# ============================================================================
def _big_diff_pairs():
    """>=20 行新增（触发可疑空收敛阈值的"大改动"）。"""
    return [("src/Big.java", [f"int v{i} = {i};" for i in range(25)], True)]


def test_e2e_suspicious_empty_review_not_reliable():
    """大改动 + LLM 返回空 review（无任何结构段、not engaged）+ 0 建议 → 可疑空收敛，不可信。
    （模拟 diff 被 pr-agent 裁空 → glm 无米下锅 → 近乎空 review。）"""
    pr = _pr(_big_diff_pairs(), {"code_suggestions": [], "review": {"key_issues_to_review": []}})
    out = orc.review_pr(pr, {}, _standards())
    assert out["engine_status"] == "ok"
    assert out["ai_raw_count"] == 0
    assert out["engaged"] is False                       # 无真段
    assert out["added_lines"] >= 20
    assert RP.review_reliable(out["engine_status"], 0, out["added_lines"], out["engaged"]) is False


def test_e2e_legitimate_engaged_clean_is_reliable():
    """对照：大改动 + 0 建议 + glm 真多段评审（engaged）= 审完无问题，可信。
    锁正当路径——防我们把"engaged 干净"误伤成可疑空收敛。"""
    pr = _pr(_big_diff_pairs(), {"code_suggestions": [], "review": {
        "estimated_effort_to_review": "2", "relevant_tests": "Yes",
        "key_issues_to_review": [], "security_concerns": "No"}})
    out = orc.review_pr(pr, {}, _standards())
    assert out["engine_status"] == "ok"
    assert out["engaged"] is True
    assert RP.review_reliable(out["engine_status"], 0, out["added_lines"], out["engaged"]) is True


# ============================================================================
# loop：不可靠评审 → 不收敛（可靠性链的终点闸）
# ============================================================================
def test_loop_withholds_convergence_when_review_unreliable(rule_index):
    """review_reliable=False 时，即便无可自改发现、CI 绿，loop 也不收敛——
    "0 发现"在 diff 被裁空 / LLM 随机性下不可靠，回落 continue 待可靠轮复核。
    （PR #44 round-1 真根因兜底：首轮 diff 被裁空 → 0 发现 → 此处阻止假收敛。）"""
    dec, reason, _ = _lp.loop_step([], rule_index, _lp.LoopState(),
                                   ci_passed=True, review_reliable=False)
    assert dec != "converged"
    # 对照：可靠 + 无发现 + CI 绿 → 收敛
    dec_ok, _, _ = _lp.loop_step([], rule_index, _lp.LoopState(),
                                 ci_passed=True, review_reliable=True)
    assert dec_ok == "converged"
