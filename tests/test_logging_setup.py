#!/usr/bin/env python3
# ============================================================================
# tests/test_logging_setup.py —— 日志基础设施行为锁
# ----------------------------------------------------------------------------
# 锁：① get_logger 返回挂在 touchstone.* 下的 logger；② 默认级别 INFO、env 可调；
# ③ 默认 handler 写 stderr（保持旧 print 的可捕获性）；④ JSON 格式 env 生效；
# ⑤ 重复取 logger 不叠加 handler（幂等）；⑥ 日志经 caplog 可捕获（未切断冒泡）。
# ============================================================================

import json
import logging

import pytest

from touchstone import logging_setup as ls


@pytest.fixture(autouse=True)
def _reset_logging():
    """每个用例前后复位本包 logger 与模块配置标志，避免用例间串扰。"""
    ls._CONFIGURED = False
    root = logging.getLogger(ls._ROOT_NAME)
    saved = root.handlers[:]
    root.handlers[:] = []
    yield
    root.handlers[:] = saved
    ls._CONFIGURED = False


def test_get_logger_under_package_tree():
    lg = ls.get_logger("pr_agent")
    assert lg.name == "touchstone.pr_agent"


def test_default_level_info(monkeypatch):
    monkeypatch.delenv("TOUCHSTONE_LOG_LEVEL", raising=False)
    ls.get_logger("x")
    assert logging.getLogger(ls._ROOT_NAME).level == logging.INFO


def test_env_sets_level(monkeypatch):
    monkeypatch.setenv("TOUCHSTONE_LOG_LEVEL", "DEBUG")
    ls.get_logger("x")
    assert logging.getLogger(ls._ROOT_NAME).level == logging.DEBUG


def test_default_handler_writes_stderr():
    import sys
    ls.get_logger("x")
    handlers = logging.getLogger(ls._ROOT_NAME).handlers
    defaults = [h for h in handlers if getattr(h, "_touchstone_default", False)]
    assert len(defaults) == 1
    # 绑定的是配置时刻的 sys.stderr（pytest 捕获模式下会替换 sys.stderr，故比对对象本身
    # 而非 .name == "<stderr>"）。
    assert defaults[0].stream is sys.stderr


def test_idempotent_no_duplicate_handlers():
    ls.get_logger("a")
    ls.get_logger("b")
    ls.get_logger("c")
    defaults = [h for h in logging.getLogger(ls._ROOT_NAME).handlers
                if getattr(h, "_touchstone_default", False)]
    assert len(defaults) == 1, "重复取 logger 不得叠加默认 handler"


def test_json_format(monkeypatch, capsys):
    monkeypatch.setenv("TOUCHSTONE_LOG_FORMAT", "json")
    lg = ls.get_logger("jsontest")
    lg.warning("端点不可达")
    err = capsys.readouterr().err.strip().splitlines()[-1]
    parsed = json.loads(err)                       # 单行必须是合法 JSON
    assert parsed["level"] == "WARNING"
    assert parsed["logger"] == "touchstone.jsontest"
    assert parsed["msg"] == "端点不可达"


def test_host_takeover_not_overridden(monkeypatch):
    """宿主先在本包 logger 挂了自己的 handler → 不叠加默认 handler（不劫持宿主配置）。"""
    root = logging.getLogger(ls._ROOT_NAME)
    host_handler = logging.StreamHandler()
    root.addHandler(host_handler)
    ls._CONFIGURED = False
    ls.get_logger("x")
    defaults = [h for h in root.handlers if getattr(h, "_touchstone_default", False)]
    assert defaults == [], "宿主已接管时不应再挂默认 handler"
    root.removeHandler(host_handler)


def test_captured_by_caplog(caplog):
    """日志经 caplog 可捕获——证明未切断向 root 的冒泡（宿主 root handler 亦能收集）。"""
    with caplog.at_level(logging.INFO, logger="touchstone.captest"):
        ls.get_logger("captest").info("配置就绪")
    assert "配置就绪" in caplog.text
