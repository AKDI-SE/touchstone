#!/usr/bin/env python3
# ============================================================================
# touchstone/envutil.py —— env 数值解析的统一兜底（审计 #13-#19 家族的单一收口点）
# ----------------------------------------------------------------------------
# 背景：此前 7 个模块各自在 import 期/调用期裸写
#   int((os.environ.get("X") or "").strip() or "5")
# CI 的 vars. 未设常被插成空串、运维手滑填非数字，任何一处即 ValueError：
#   - import 期常量（distill/autonomy/calibrate/ground_truth/govern/review_provider）
#     → 导入即崩，整条评审/学习链死，且表现为无诊断价值的 traceback；
#   - 调用期解析（experience_store shadow 参数、ground_truth 阈值）→ 每轮评审必经路径崩溃。
# 本模块提供 fail-loud-but-not-crash 的统一解析：坏值回落默认 + stderr 留痕（不静默），
# 可选下限夹取（0/1 等）。与 loop.py MAX_ROUNDS、distill._env_num 的既有兜底风格一致。
# ============================================================================

import os
import sys


def _raw(name):
    v = os.environ.get(name)
    if v is None:
        return None, False          # 未设：静默用默认（合法常态）
    v = v.strip()
    if not v:
        return None, False          # 空串（GHA vars 未设的常见插值）：静默用默认
    return v, True


def env_int(name, default, *, minimum=None):
    """env → int；未设/空/坏值 → default（坏值 stderr 留痕）。minimum 给定时下夹。"""
    v, present = _raw(name)
    if not present:
        return default
    try:
        n = int(v)
    except ValueError:
        print(f"[envutil] {name}={v!r} 非整数，回落默认 {default}", file=sys.stderr)
        return default
    if minimum is not None and n < minimum:
        print(f"[envutil] {name}={n} 低于下限 {minimum}，夹取为 {minimum}", file=sys.stderr)
        n = minimum
    return n


def env_float(name, default, *, minimum=None):
    """env → float；未设/空/坏值 → default（坏值 stderr 留痕）。minimum 给定时下夹。"""
    v, present = _raw(name)
    if not present:
        return default
    try:
        n = float(v)
    except ValueError:
        print(f"[envutil] {name}={v!r} 非数值，回落默认 {default}", file=sys.stderr)
        return default
    if minimum is not None and n < minimum:
        print(f"[envutil] {name}={n} 低于下限 {minimum}，夹取为 {minimum}", file=sys.stderr)
        n = minimum
    return n


def env_flag(name, default=False):
    """env → 布尔开关。default 通常给 False（kill-switch 风格：显式 "1/true/yes/on" 才开）。
    与 learning_loop 的 TOUCHSTONE_RETIRE_NEGATIVE_LIFT、checks 的阴影开关同一口径。"""
    v, present = _raw(name)
    if not present:
        return default
    return v.lower() in ("1", "true", "yes", "on")


def env_pr_event():
    """GITHUB_EVENT_NAME 是否 PR 类事件（pull_request / pull_request_target / pull_request_review…）。

    pr-agent 评审（PR #203 第三轮）收口：本仓 touchstone workflow 的触发器是
    **pull_request_target**，GITHUB_EVENT_NAME 即 "pull_request_target"——若精确匹配
    == "pull_request"，防投毒闸（EXPERIENCE_REF 门）在真实生产路径上【永不生效】，
    恰好保护了它要防的场景。前缀匹配覆盖全部 PR 类事件；schedule/push/workflow_dispatch
    等非 PR 事件不受影响。"""
    ev = (os.environ.get("GITHUB_EVENT_NAME") or "").strip().lower()
    return ev == "pull_request" or ev.startswith("pull_request_")
