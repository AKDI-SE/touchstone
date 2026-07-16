#!/usr/bin/env python3
# ============================================================================
# touchstone/logging_setup.py —— 统一日志基础设施
# ----------------------------------------------------------------------------
# 为什么需要：此前全仓用 120 处 print 做诊断/结果输出，没有级别、无结构化、无法接
# 客户环境的日志采集。作为 GitHub Action 时够用（Actions 直接抓 stdout/stderr），
# 但作为可安装、要在客户内网排障的工具，运维必须能：① 调级别（默认 INFO，排障开
# DEBUG）；② 把日志接到自己的 handler（文件/syslog/JSON 采集）。
#
# 设计约束（为什么不粗暴全量替换 print）：
#   1. 结果输出（CLI 给人看的报告、gate 结论）仍走 print → stdout：那是【产物】不是
#      日志，管道下游要 grep/重定向它，不该被日志级别过滤掉。
#   2. 诊断输出（[pr-agent]/[gate]/[autonomy] 前缀那类）是【日志】→ 迁到本模块的
#      logger，默认落 stderr（保持与旧 print(file=sys.stderr) 相同的可捕获性，
#      现有 capsys.readouterr().err 断言不破）。
#   3. 默认【不】动 root logger、不加多个 handler：库不该劫持宿主的日志配置。只在本
#      包 logger 树('touchstone')上挂一个 stderr handler，且只挂一次（幂等）。
#
# 客户接管方式：
#   - 环境变量 TOUCHSTONE_LOG_LEVEL=DEBUG|INFO|WARNING|ERROR 调级别。
#   - 环境变量 TOUCHSTONE_LOG_FORMAT=json 输出单行 JSON（便于采集器解析）。
#   - 或在宿主代码里 logging.getLogger("touchstone").handlers[:] = [自己的 handler]
#     —— 本模块的 handler 带标记，宿主可识别并替换。
# ============================================================================

import json
import logging
import os
import sys

_ROOT_NAME = "touchstone"
_CONFIGURED = False


class _JsonFormatter(logging.Formatter):
    """单行 JSON 格式：便于客户侧日志采集器（fluentbit/loki 等）无正则解析。"""

    def format(self, record):
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def _level_from_env():
    raw = (os.environ.get("TOUCHSTONE_LOG_LEVEL") or "INFO").upper()
    return getattr(logging, raw, logging.INFO)


def _configure_once():
    """在 'touchstone' 包 logger 上幂等挂一个 stderr handler。
    不碰 root logger（不劫持宿主日志配置）。已被外部接管（handler 非本模块所建）
    时不重复挂。"""
    global _CONFIGURED
    root = logging.getLogger(_ROOT_NAME)
    # 若宿主已给本包 logger 配了自己的 handler，尊重之，不叠加。
    if any(getattr(h, "_touchstone_default", False) for h in root.handlers):
        _CONFIGURED = True
    if _CONFIGURED:
        root.setLevel(_level_from_env())
        return
    if root.handlers:
        # 宿主已接管：只设级别，不加 handler。
        _CONFIGURED = True
        return
    handler = logging.StreamHandler(sys.stderr)   # 默认 stderr：与旧 print 可捕获性一致
    handler._touchstone_default = True            # 标记：宿主可据此识别并替换
    if (os.environ.get("TOUCHSTONE_LOG_FORMAT") or "").lower() == "json":
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("[%(name)s] %(message)s"))
    root.addHandler(handler)
    root.setLevel(_level_from_env())
    # 注意：刻意【不】设 propagate=False。库若切断冒泡，宿主的 root handler 与测试的
    # caplog（挂 root、靠 propagate 收集）都收不到本包日志。保留冒泡的代价是：宿主
    # 若自己也配了 root handler，会与本模块 handler 各输出一份——那是宿主的显式选择，
    # 宿主可通过替换带 _touchstone_default 标记的 handler 消除双份（见模块头注）。
    _CONFIGURED = True


def get_logger(name):
    """取子 logger。name 建议传模块短名（如 'pr_agent'），自动挂在 touchstone.* 下。
    首次调用惰性配置默认 handler。"""
    _configure_once()
    return logging.getLogger(f"{_ROOT_NAME}.{name}")
