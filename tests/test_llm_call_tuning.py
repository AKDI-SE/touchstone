# ============================================================================
# tests/test_llm_call_tuning.py —— LLM 调用调优离线单测
#
# 不依赖 pr_agent / litellm / tenacity / 网络：
#   • 重试谓词/stop/围栏是纯函数，直接测（tenacity 以 retry_state 调用纯函数谓词、
#     seconds_since_start / attempt_number 语义均经真实 tenacity 概念验证）。
#   • _install_llm_call_tuning 的接线用 sys.modules 注入假 pr_agent 依赖树测。
# 数据依据（勿删——这是默认 N=0 的理由）：183 runs / 96 PRs 全量分析，真实失败
# （hard timeout + 长生成断连）全部发生在调用 600s+ 后，轮内重试救回率 0/8；
# 轮级转移 slow→slow 18:7 且变快间隔为小时级。
# ============================================================================
import asyncio
import sys
import types

import httpx
import openai
import pytest

from touchstone import pr_agent_runner as R


def _req():
    return httpx.Request("POST", "http://llm.test/v1/chat/completions")


def _rs(exc, elapsed, attempt=1):
    """最小 tenacity retry_state 替身：outcome / seconds_since_start / attempt_number。"""
    outcome = types.SimpleNamespace(failed=exc is not None, exception=lambda: exc)
    return types.SimpleNamespace(outcome=outcome, seconds_since_start=elapsed,
                                 attempt_number=attempt)


# ------------------------------------------------------------- 重试谓词矩阵

def test_default_n0_fast_jitter_gets_one_retry():
    # N=0：快窗内抖动类失败 → 允许 N+1=1 次重试（第 1 次失败放行、第 2 次失败截断）
    pol = R._make_retry_policy(0, 120)
    blip = openai.APIConnectionError(request=_req())
    assert pol(_rs(blip, 3.0, attempt=1)) is True
    assert pol(_rs(blip, 6.0, attempt=2)) is False


def test_default_n0_slow_conn_drop_no_retry():
    # 长生成断连（PR#81/#88/#83 降级轮的真实形态）：类型是抖动类但发生在快窗外 → 0 次重试
    pol = R._make_retry_policy(0, 120)
    drop = openai.APIConnectionError(request=_req())
    assert pol(_rs(drop, 650.0, attempt=1)) is False


def test_default_n0_timeout_never_retries_even_fast():
    # 超时无论何时发生都拿不到快窗加成（类型维度排除，与长生成同源）
    pol = R._make_retry_policy(0, 120)
    assert pol(_rs(openai.APITimeoutError(request=_req()), 5.0, attempt=1)) is False


def test_ratelimit_never_retries_regardless_of_n():
    pol = R._make_retry_policy(3, 120)
    resp = httpx.Response(429, request=_req())
    rl = openai.RateLimitError("rate", response=resp, body=None)
    assert pol(_rs(rl, 1.0, attempt=1)) is False


def test_n2_slow_failure_gets_exactly_two_retries():
    # N=2：慢失败（含超时）允许恰 2 次重试——N 是显式旋钮，部署方设了就尊重
    pol = R._make_retry_policy(2, 120)
    to = openai.APITimeoutError(request=_req())
    assert pol(_rs(to, 650.0, attempt=1)) is True
    assert pol(_rs(to, 1300.0, attempt=2)) is True
    assert pol(_rs(to, 1950.0, attempt=3)) is False


def test_fast_window_zero_disables_bonus():
    # 快窗 0 = 纯 N 次语义（N=0 即"任何失败都不重试"的一刀切表达）
    pol = R._make_retry_policy(0, 0)
    assert pol(_rs(openai.APIConnectionError(request=_req()), 0.0, attempt=1)) is False


def test_success_outcome_no_retry():
    pol = R._make_retry_policy(0, 120)
    assert pol(_rs(None, 1.0, attempt=1)) is False


def test_stop_ceiling_is_n_plus_2_attempts():
    stop = R._make_stop(0)
    assert stop(_rs(None, 0, attempt=1)) is False
    assert stop(_rs(None, 0, attempt=2)) is True   # 最多 2 次尝试（N=0 + 快窗加成路径）


# ------------------------------------------------------------- env 旋钮

def test_num_retries_env_default_and_invalid(monkeypatch, capsys):
    monkeypatch.delenv("TOUCHSTONE_LLM_NUM_RETRIES", raising=False)
    assert R._llm_num_retries() == 0                       # secret 未设 → 默认 0
    monkeypatch.setenv("TOUCHSTONE_LLM_NUM_RETRIES", "")
    assert R._llm_num_retries() == 0                       # secret 为空串（GHA 未配置时的形态）
    monkeypatch.setenv("TOUCHSTONE_LLM_NUM_RETRIES", "2")
    assert R._llm_num_retries() == 2
    monkeypatch.setenv("TOUCHSTONE_LLM_NUM_RETRIES", "abc")
    assert R._llm_num_retries() == 0
    assert "TOUCHSTONE_LLM_NUM_RETRIES 非法" in capsys.readouterr().err
    monkeypatch.setenv("TOUCHSTONE_LLM_NUM_RETRIES", "-3")
    assert R._llm_num_retries() == 0


def test_fast_window_env(monkeypatch, capsys):
    monkeypatch.delenv("TOUCHSTONE_LLM_RETRY_FAST_WINDOW", raising=False)
    assert R._retry_fast_window() == 120
    monkeypatch.setenv("TOUCHSTONE_LLM_RETRY_FAST_WINDOW", "60")
    assert R._retry_fast_window() == 60
    monkeypatch.setenv("TOUCHSTONE_LLM_RETRY_FAST_WINDOW", "abc")
    assert R._retry_fast_window() == 120
    assert "TOUCHSTONE_LLM_RETRY_FAST_WINDOW 非法" in capsys.readouterr().err


# ------------------------------------------------------------- 围栏

def test_guard_injects_client_zero_retries():
    captured = {}

    async def fake(**kw):
        captured.update(kw)
        return "ok"

    g = R._guard_acompletion(fake)
    assert asyncio.run(g(model="m", messages=[])) == "ok"
    assert captured["max_retries"] == 0


def test_guard_respects_explicit_upstream():
    captured = {}

    async def fake(**kw):
        captured.update(kw)

    g = R._guard_acompletion(fake)
    asyncio.run(g(model="m", max_retries=5))
    assert captured["max_retries"] == 5


# ------------------------------------------------------------- 接线（假 pr_agent）

def _install_fake_tree(monkeypatch):
    calls = {}

    async def fake_aco(**kw):
        calls.update(kw)
        return "resp"

    pol = types.SimpleNamespace(retry="ORIGINAL", stop="ORIGINAL")
    fake_lah = types.ModuleType("pr_agent.algo.ai_handlers.litellm_ai_handler")
    fake_lah.acompletion = fake_aco
    fake_lah.LiteLLMAIHandler = types.SimpleNamespace(
        chat_completion=types.SimpleNamespace(retry=pol))
    fake_algo = types.ModuleType("pr_agent.algo")
    fake_algo.STREAMING_REQUIRED_MODELS = ["openai/qwq-plus"]
    for name, mod in {
        "pr_agent": types.ModuleType("pr_agent"),
        "pr_agent.algo": fake_algo,
        "pr_agent.algo.ai_handlers": types.ModuleType("pr_agent.algo.ai_handlers"),
        "pr_agent.algo.ai_handlers.litellm_ai_handler": fake_lah,
    }.items():
        monkeypatch.setitem(sys.modules, name, mod)
    return fake_lah, fake_algo, calls, pol


def test_install_wires_guard_policy_and_streaming(monkeypatch):
    fake_lah, fake_algo, calls, pol = _install_fake_tree(monkeypatch)
    monkeypatch.setenv("TOUCHSTONE_LLM_REFLECT_MODEL", "glm-4.5-air")
    monkeypatch.delenv("TOUCHSTONE_LLM_NUM_RETRIES", raising=False)
    monkeypatch.delenv("TOUCHSTONE_LLM_STREAM", raising=False)

    R._install_llm_call_tuning("glm-5.2")

    # 围栏生效
    asyncio.run(fake_lah.acompletion(model="m"))
    assert calls["max_retries"] == 0
    # tenacity 谓词/上限被替换为可调用，且行为符合 N=0（慢失败不放行）
    assert callable(pol.retry) and callable(pol.stop)
    drop = openai.APIConnectionError(request=_req())
    assert pol.retry(_rs(drop, 650.0, attempt=1)) is False
    assert pol.retry(_rs(drop, 3.0, attempt=1)) is True
    # 主模型 + 自评模型均入流式清单
    assert "openai/glm-5.2" in fake_algo.STREAMING_REQUIRED_MODELS
    assert "openai/glm-4.5-air" in fake_algo.STREAMING_REQUIRED_MODELS


def test_install_stream_optout(monkeypatch):
    _lah, fake_algo, _calls, _pol = _install_fake_tree(monkeypatch)
    monkeypatch.setenv("TOUCHSTONE_LLM_STREAM", "false")
    R._install_llm_call_tuning("glm-5.2")
    assert "openai/glm-5.2" not in fake_algo.STREAMING_REQUIRED_MODELS


def test_install_without_pr_agent_failloud_noop(monkeypatch, capsys):
    for name in list(sys.modules):
        if name == "pr_agent" or name.startswith("pr_agent."):
            monkeypatch.delitem(sys.modules, name, raising=False)
    monkeypatch.setitem(sys.modules, "pr_agent", None)
    R._install_llm_call_tuning("glm-5.2")
    assert "LLM 调用调优未安装" in capsys.readouterr().err


# ------------------------------------------------------------- 思考开关

def test_thinking_env_three_states(monkeypatch, capsys):
    monkeypatch.delenv("TOUCHSTONE_LLM_THINKING", raising=False)
    assert R._llm_thinking_extra_body() is None                       # 未设 → 端点默认
    monkeypatch.setenv("TOUCHSTONE_LLM_THINKING", "")
    assert R._llm_thinking_extra_body() is None                       # secret 未配置时的空串形态
    monkeypatch.setenv("TOUCHSTONE_LLM_THINKING", "disabled")
    assert R._llm_thinking_extra_body() == {"thinking": {"type": "disabled"}}
    monkeypatch.setenv("TOUCHSTONE_LLM_THINKING", "Enabled")          # 大小写宽容
    assert R._llm_thinking_extra_body() == {"thinking": {"type": "enabled"}}
    monkeypatch.setenv("TOUCHSTONE_LLM_THINKING", "off")              # 非法值 fail-loud 不注入
    assert R._llm_thinking_extra_body() is None
    assert "TOUCHSTONE_LLM_THINKING 非法" in capsys.readouterr().err


def test_guard_injects_thinking_extra_body():
    captured = {}

    async def fake(**kw):
        captured.update(kw)

    g = R._guard_acompletion(fake, extra_body={"thinking": {"type": "disabled"}})
    asyncio.run(g(model="m"))
    assert captured["extra_body"] == {"thinking": {"type": "disabled"}}
    # 上游显式传参不覆盖
    captured.clear()
    asyncio.run(g(model="m", extra_body={"a": 1}))
    assert captured["extra_body"] == {"a": 1}


def test_guard_without_thinking_injects_nothing(monkeypatch):
    captured = {}

    async def fake(**kw):
        captured.update(kw)

    g = R._guard_acompletion(fake)                                    # extra_body 默认 None
    asyncio.run(g(model="m"))
    assert "extra_body" not in captured


def test_install_wires_thinking(monkeypatch):
    fake_lah, _algo, calls, _pol = _install_fake_tree(monkeypatch)
    monkeypatch.setenv("TOUCHSTONE_LLM_THINKING", "disabled")
    R._install_llm_call_tuning("glm-5.2")
    asyncio.run(fake_lah.acompletion(model="m"))
    assert calls["extra_body"] == {"thinking": {"type": "disabled"}}
    assert calls["max_retries"] == 0
