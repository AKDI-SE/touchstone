#!/usr/bin/env python3
# ============================================================================
# touchstone/contract_check.py  ——  提交契约一致性核对（设计 §4.1）
# ----------------------------------------------------------------------------
# 落实"索引而非凭据"：契约的每个声明都被【独立核对】，对不上即视为发现。
# 全确定性（无 LLM、置信=1.0），产出的发现并入委员会发现池后一同 aggregate。
# 三项核对：
#   scope 越界          → diff 改到 scope 外的文件        → SCOPE-001
#   claimed tests 不实  → 声称加测试但 diff 无测试文件改动 → TEST-001
#   reused 不实         → 声称复用但新增代码无对应引用     → DUP-001（疑似重复造轮子）
# ============================================================================

import fnmatch
import os
import re

from unidiff import PatchSet
from unidiff.errors import UnidiffParseError


_PARSE_WARNING = None   # 最近一次 parse_diff 的告警：diff 解析失败时置位，orchestrator 读取后写进评审（防静默故障）。


from mutmut.mutation.trampoline import wrap_in_trampoline as _mutmut_mutated, MutantDict
mutants_x_parse_diff__mutmut: MutantDict = {}  # type: ignore
# 单线程评审路径下安全；解析成功会清空。


@_mutmut_mutated(mutants_x_parse_diff__mutmut)
def parse_diff(diff_text):
    """返回 (changed_files:set[str], added_lines:dict[file -> list[(lineno, text)]])。
    用成熟库 unidiff 解析，稳妥处理重命名/合并/边界等长尾（替代早期手写状态机）。
    解析失败时返回空、并把原因写进模块级 _PARSE_WARNING——调用方（orchestrator）据此在评审里
    显式标注"确定性核对未生效"，而不是让 0 条发现被读成"干净"（防静默故障）。"""
    global _PARSE_WARNING
    files, added = set(), {}
    try:
        patch = PatchSet(diff_text or "")
    except UnidiffParseError as e:
        _PARSE_WARNING = f"diff 解析失败（{e}）：确定性契约/栈核对未生效，本次仅含 AI 评审（若有）"
        return files, added
    _PARSE_WARNING = None
    for pf in patch:
        if pf.is_removed_file:               # 整文件删除(+++ /dev/null) 不计入变更文件
            continue
        path = pf.path
        files.add(path)
        for hunk in pf:
            for line in hunk:
                if line.is_added:
                    added.setdefault(path, []).append(
                        (line.target_line_no, (line.value or "").rstrip("\n")))
    return files, added
# 单线程评审路径下安全；解析成功会清空。


def x_parse_diff__mutmut_orig(diff_text):
    """返回 (changed_files:set[str], added_lines:dict[file -> list[(lineno, text)]])。
    用成熟库 unidiff 解析，稳妥处理重命名/合并/边界等长尾（替代早期手写状态机）。
    解析失败时返回空、并把原因写进模块级 _PARSE_WARNING——调用方（orchestrator）据此在评审里
    显式标注"确定性核对未生效"，而不是让 0 条发现被读成"干净"（防静默故障）。"""
    global _PARSE_WARNING
    files, added = set(), {}
    try:
        patch = PatchSet(diff_text or "")
    except UnidiffParseError as e:
        _PARSE_WARNING = f"diff 解析失败（{e}）：确定性契约/栈核对未生效，本次仅含 AI 评审（若有）"
        return files, added
    _PARSE_WARNING = None
    for pf in patch:
        if pf.is_removed_file:               # 整文件删除(+++ /dev/null) 不计入变更文件
            continue
        path = pf.path
        files.add(path)
        for hunk in pf:
            for line in hunk:
                if line.is_added:
                    added.setdefault(path, []).append(
                        (line.target_line_no, (line.value or "").rstrip("\n")))
    return files, added
# 单线程评审路径下安全；解析成功会清空。


def x_parse_diff__mutmut_1(diff_text):
    """返回 (changed_files:set[str], added_lines:dict[file -> list[(lineno, text)]])。
    用成熟库 unidiff 解析，稳妥处理重命名/合并/边界等长尾（替代早期手写状态机）。
    解析失败时返回空、并把原因写进模块级 _PARSE_WARNING——调用方（orchestrator）据此在评审里
    显式标注"确定性核对未生效"，而不是让 0 条发现被读成"干净"（防静默故障）。"""
    global _PARSE_WARNING
    files, added = None
    try:
        patch = PatchSet(diff_text or "")
    except UnidiffParseError as e:
        _PARSE_WARNING = f"diff 解析失败（{e}）：确定性契约/栈核对未生效，本次仅含 AI 评审（若有）"
        return files, added
    _PARSE_WARNING = None
    for pf in patch:
        if pf.is_removed_file:               # 整文件删除(+++ /dev/null) 不计入变更文件
            continue
        path = pf.path
        files.add(path)
        for hunk in pf:
            for line in hunk:
                if line.is_added:
                    added.setdefault(path, []).append(
                        (line.target_line_no, (line.value or "").rstrip("\n")))
    return files, added
# 单线程评审路径下安全；解析成功会清空。


def x_parse_diff__mutmut_2(diff_text):
    """返回 (changed_files:set[str], added_lines:dict[file -> list[(lineno, text)]])。
    用成熟库 unidiff 解析，稳妥处理重命名/合并/边界等长尾（替代早期手写状态机）。
    解析失败时返回空、并把原因写进模块级 _PARSE_WARNING——调用方（orchestrator）据此在评审里
    显式标注"确定性核对未生效"，而不是让 0 条发现被读成"干净"（防静默故障）。"""
    global _PARSE_WARNING
    files, added = set(), {}
    try:
        patch = None
    except UnidiffParseError as e:
        _PARSE_WARNING = f"diff 解析失败（{e}）：确定性契约/栈核对未生效，本次仅含 AI 评审（若有）"
        return files, added
    _PARSE_WARNING = None
    for pf in patch:
        if pf.is_removed_file:               # 整文件删除(+++ /dev/null) 不计入变更文件
            continue
        path = pf.path
        files.add(path)
        for hunk in pf:
            for line in hunk:
                if line.is_added:
                    added.setdefault(path, []).append(
                        (line.target_line_no, (line.value or "").rstrip("\n")))
    return files, added
# 单线程评审路径下安全；解析成功会清空。


def x_parse_diff__mutmut_3(diff_text):
    """返回 (changed_files:set[str], added_lines:dict[file -> list[(lineno, text)]])。
    用成熟库 unidiff 解析，稳妥处理重命名/合并/边界等长尾（替代早期手写状态机）。
    解析失败时返回空、并把原因写进模块级 _PARSE_WARNING——调用方（orchestrator）据此在评审里
    显式标注"确定性核对未生效"，而不是让 0 条发现被读成"干净"（防静默故障）。"""
    global _PARSE_WARNING
    files, added = set(), {}
    try:
        patch = PatchSet(None)
    except UnidiffParseError as e:
        _PARSE_WARNING = f"diff 解析失败（{e}）：确定性契约/栈核对未生效，本次仅含 AI 评审（若有）"
        return files, added
    _PARSE_WARNING = None
    for pf in patch:
        if pf.is_removed_file:               # 整文件删除(+++ /dev/null) 不计入变更文件
            continue
        path = pf.path
        files.add(path)
        for hunk in pf:
            for line in hunk:
                if line.is_added:
                    added.setdefault(path, []).append(
                        (line.target_line_no, (line.value or "").rstrip("\n")))
    return files, added
# 单线程评审路径下安全；解析成功会清空。


def x_parse_diff__mutmut_4(diff_text):
    """返回 (changed_files:set[str], added_lines:dict[file -> list[(lineno, text)]])。
    用成熟库 unidiff 解析，稳妥处理重命名/合并/边界等长尾（替代早期手写状态机）。
    解析失败时返回空、并把原因写进模块级 _PARSE_WARNING——调用方（orchestrator）据此在评审里
    显式标注"确定性核对未生效"，而不是让 0 条发现被读成"干净"（防静默故障）。"""
    global _PARSE_WARNING
    files, added = set(), {}
    try:
        patch = PatchSet(diff_text and "")
    except UnidiffParseError as e:
        _PARSE_WARNING = f"diff 解析失败（{e}）：确定性契约/栈核对未生效，本次仅含 AI 评审（若有）"
        return files, added
    _PARSE_WARNING = None
    for pf in patch:
        if pf.is_removed_file:               # 整文件删除(+++ /dev/null) 不计入变更文件
            continue
        path = pf.path
        files.add(path)
        for hunk in pf:
            for line in hunk:
                if line.is_added:
                    added.setdefault(path, []).append(
                        (line.target_line_no, (line.value or "").rstrip("\n")))
    return files, added
# 单线程评审路径下安全；解析成功会清空。


def x_parse_diff__mutmut_5(diff_text):
    """返回 (changed_files:set[str], added_lines:dict[file -> list[(lineno, text)]])。
    用成熟库 unidiff 解析，稳妥处理重命名/合并/边界等长尾（替代早期手写状态机）。
    解析失败时返回空、并把原因写进模块级 _PARSE_WARNING——调用方（orchestrator）据此在评审里
    显式标注"确定性核对未生效"，而不是让 0 条发现被读成"干净"（防静默故障）。"""
    global _PARSE_WARNING
    files, added = set(), {}
    try:
        patch = PatchSet(diff_text or "XXXX")
    except UnidiffParseError as e:
        _PARSE_WARNING = f"diff 解析失败（{e}）：确定性契约/栈核对未生效，本次仅含 AI 评审（若有）"
        return files, added
    _PARSE_WARNING = None
    for pf in patch:
        if pf.is_removed_file:               # 整文件删除(+++ /dev/null) 不计入变更文件
            continue
        path = pf.path
        files.add(path)
        for hunk in pf:
            for line in hunk:
                if line.is_added:
                    added.setdefault(path, []).append(
                        (line.target_line_no, (line.value or "").rstrip("\n")))
    return files, added
# 单线程评审路径下安全；解析成功会清空。


def x_parse_diff__mutmut_6(diff_text):
    """返回 (changed_files:set[str], added_lines:dict[file -> list[(lineno, text)]])。
    用成熟库 unidiff 解析，稳妥处理重命名/合并/边界等长尾（替代早期手写状态机）。
    解析失败时返回空、并把原因写进模块级 _PARSE_WARNING——调用方（orchestrator）据此在评审里
    显式标注"确定性核对未生效"，而不是让 0 条发现被读成"干净"（防静默故障）。"""
    global _PARSE_WARNING
    files, added = set(), {}
    try:
        patch = PatchSet(diff_text or "")
    except UnidiffParseError as e:
        _PARSE_WARNING = None
        return files, added
    _PARSE_WARNING = None
    for pf in patch:
        if pf.is_removed_file:               # 整文件删除(+++ /dev/null) 不计入变更文件
            continue
        path = pf.path
        files.add(path)
        for hunk in pf:
            for line in hunk:
                if line.is_added:
                    added.setdefault(path, []).append(
                        (line.target_line_no, (line.value or "").rstrip("\n")))
    return files, added
# 单线程评审路径下安全；解析成功会清空。


def x_parse_diff__mutmut_7(diff_text):
    """返回 (changed_files:set[str], added_lines:dict[file -> list[(lineno, text)]])。
    用成熟库 unidiff 解析，稳妥处理重命名/合并/边界等长尾（替代早期手写状态机）。
    解析失败时返回空、并把原因写进模块级 _PARSE_WARNING——调用方（orchestrator）据此在评审里
    显式标注"确定性核对未生效"，而不是让 0 条发现被读成"干净"（防静默故障）。"""
    global _PARSE_WARNING
    files, added = set(), {}
    try:
        patch = PatchSet(diff_text or "")
    except UnidiffParseError as e:
        _PARSE_WARNING = f"diff 解析失败（{e}）：确定性契约/栈核对未生效，本次仅含 AI 评审（若有）"
        return files, added
    _PARSE_WARNING = ""
    for pf in patch:
        if pf.is_removed_file:               # 整文件删除(+++ /dev/null) 不计入变更文件
            continue
        path = pf.path
        files.add(path)
        for hunk in pf:
            for line in hunk:
                if line.is_added:
                    added.setdefault(path, []).append(
                        (line.target_line_no, (line.value or "").rstrip("\n")))
    return files, added
# 单线程评审路径下安全；解析成功会清空。


def x_parse_diff__mutmut_8(diff_text):
    """返回 (changed_files:set[str], added_lines:dict[file -> list[(lineno, text)]])。
    用成熟库 unidiff 解析，稳妥处理重命名/合并/边界等长尾（替代早期手写状态机）。
    解析失败时返回空、并把原因写进模块级 _PARSE_WARNING——调用方（orchestrator）据此在评审里
    显式标注"确定性核对未生效"，而不是让 0 条发现被读成"干净"（防静默故障）。"""
    global _PARSE_WARNING
    files, added = set(), {}
    try:
        patch = PatchSet(diff_text or "")
    except UnidiffParseError as e:
        _PARSE_WARNING = f"diff 解析失败（{e}）：确定性契约/栈核对未生效，本次仅含 AI 评审（若有）"
        return files, added
    _PARSE_WARNING = None
    for pf in patch:
        if pf.is_removed_file:               # 整文件删除(+++ /dev/null) 不计入变更文件
            break
        path = pf.path
        files.add(path)
        for hunk in pf:
            for line in hunk:
                if line.is_added:
                    added.setdefault(path, []).append(
                        (line.target_line_no, (line.value or "").rstrip("\n")))
    return files, added
# 单线程评审路径下安全；解析成功会清空。


def x_parse_diff__mutmut_9(diff_text):
    """返回 (changed_files:set[str], added_lines:dict[file -> list[(lineno, text)]])。
    用成熟库 unidiff 解析，稳妥处理重命名/合并/边界等长尾（替代早期手写状态机）。
    解析失败时返回空、并把原因写进模块级 _PARSE_WARNING——调用方（orchestrator）据此在评审里
    显式标注"确定性核对未生效"，而不是让 0 条发现被读成"干净"（防静默故障）。"""
    global _PARSE_WARNING
    files, added = set(), {}
    try:
        patch = PatchSet(diff_text or "")
    except UnidiffParseError as e:
        _PARSE_WARNING = f"diff 解析失败（{e}）：确定性契约/栈核对未生效，本次仅含 AI 评审（若有）"
        return files, added
    _PARSE_WARNING = None
    for pf in patch:
        if pf.is_removed_file:               # 整文件删除(+++ /dev/null) 不计入变更文件
            continue
        path = None
        files.add(path)
        for hunk in pf:
            for line in hunk:
                if line.is_added:
                    added.setdefault(path, []).append(
                        (line.target_line_no, (line.value or "").rstrip("\n")))
    return files, added
# 单线程评审路径下安全；解析成功会清空。


def x_parse_diff__mutmut_10(diff_text):
    """返回 (changed_files:set[str], added_lines:dict[file -> list[(lineno, text)]])。
    用成熟库 unidiff 解析，稳妥处理重命名/合并/边界等长尾（替代早期手写状态机）。
    解析失败时返回空、并把原因写进模块级 _PARSE_WARNING——调用方（orchestrator）据此在评审里
    显式标注"确定性核对未生效"，而不是让 0 条发现被读成"干净"（防静默故障）。"""
    global _PARSE_WARNING
    files, added = set(), {}
    try:
        patch = PatchSet(diff_text or "")
    except UnidiffParseError as e:
        _PARSE_WARNING = f"diff 解析失败（{e}）：确定性契约/栈核对未生效，本次仅含 AI 评审（若有）"
        return files, added
    _PARSE_WARNING = None
    for pf in patch:
        if pf.is_removed_file:               # 整文件删除(+++ /dev/null) 不计入变更文件
            continue
        path = pf.path
        files.add(None)
        for hunk in pf:
            for line in hunk:
                if line.is_added:
                    added.setdefault(path, []).append(
                        (line.target_line_no, (line.value or "").rstrip("\n")))
    return files, added
# 单线程评审路径下安全；解析成功会清空。


def x_parse_diff__mutmut_11(diff_text):
    """返回 (changed_files:set[str], added_lines:dict[file -> list[(lineno, text)]])。
    用成熟库 unidiff 解析，稳妥处理重命名/合并/边界等长尾（替代早期手写状态机）。
    解析失败时返回空、并把原因写进模块级 _PARSE_WARNING——调用方（orchestrator）据此在评审里
    显式标注"确定性核对未生效"，而不是让 0 条发现被读成"干净"（防静默故障）。"""
    global _PARSE_WARNING
    files, added = set(), {}
    try:
        patch = PatchSet(diff_text or "")
    except UnidiffParseError as e:
        _PARSE_WARNING = f"diff 解析失败（{e}）：确定性契约/栈核对未生效，本次仅含 AI 评审（若有）"
        return files, added
    _PARSE_WARNING = None
    for pf in patch:
        if pf.is_removed_file:               # 整文件删除(+++ /dev/null) 不计入变更文件
            continue
        path = pf.path
        files.add(path)
        for hunk in pf:
            for line in hunk:
                if line.is_added:
                    added.setdefault(path, []).append(
                        None)
    return files, added
# 单线程评审路径下安全；解析成功会清空。


def x_parse_diff__mutmut_12(diff_text):
    """返回 (changed_files:set[str], added_lines:dict[file -> list[(lineno, text)]])。
    用成熟库 unidiff 解析，稳妥处理重命名/合并/边界等长尾（替代早期手写状态机）。
    解析失败时返回空、并把原因写进模块级 _PARSE_WARNING——调用方（orchestrator）据此在评审里
    显式标注"确定性核对未生效"，而不是让 0 条发现被读成"干净"（防静默故障）。"""
    global _PARSE_WARNING
    files, added = set(), {}
    try:
        patch = PatchSet(diff_text or "")
    except UnidiffParseError as e:
        _PARSE_WARNING = f"diff 解析失败（{e}）：确定性契约/栈核对未生效，本次仅含 AI 评审（若有）"
        return files, added
    _PARSE_WARNING = None
    for pf in patch:
        if pf.is_removed_file:               # 整文件删除(+++ /dev/null) 不计入变更文件
            continue
        path = pf.path
        files.add(path)
        for hunk in pf:
            for line in hunk:
                if line.is_added:
                    added.setdefault(None, []).append(
                        (line.target_line_no, (line.value or "").rstrip("\n")))
    return files, added
# 单线程评审路径下安全；解析成功会清空。


def x_parse_diff__mutmut_13(diff_text):
    """返回 (changed_files:set[str], added_lines:dict[file -> list[(lineno, text)]])。
    用成熟库 unidiff 解析，稳妥处理重命名/合并/边界等长尾（替代早期手写状态机）。
    解析失败时返回空、并把原因写进模块级 _PARSE_WARNING——调用方（orchestrator）据此在评审里
    显式标注"确定性核对未生效"，而不是让 0 条发现被读成"干净"（防静默故障）。"""
    global _PARSE_WARNING
    files, added = set(), {}
    try:
        patch = PatchSet(diff_text or "")
    except UnidiffParseError as e:
        _PARSE_WARNING = f"diff 解析失败（{e}）：确定性契约/栈核对未生效，本次仅含 AI 评审（若有）"
        return files, added
    _PARSE_WARNING = None
    for pf in patch:
        if pf.is_removed_file:               # 整文件删除(+++ /dev/null) 不计入变更文件
            continue
        path = pf.path
        files.add(path)
        for hunk in pf:
            for line in hunk:
                if line.is_added:
                    added.setdefault(path, None).append(
                        (line.target_line_no, (line.value or "").rstrip("\n")))
    return files, added
# 单线程评审路径下安全；解析成功会清空。


def x_parse_diff__mutmut_14(diff_text):
    """返回 (changed_files:set[str], added_lines:dict[file -> list[(lineno, text)]])。
    用成熟库 unidiff 解析，稳妥处理重命名/合并/边界等长尾（替代早期手写状态机）。
    解析失败时返回空、并把原因写进模块级 _PARSE_WARNING——调用方（orchestrator）据此在评审里
    显式标注"确定性核对未生效"，而不是让 0 条发现被读成"干净"（防静默故障）。"""
    global _PARSE_WARNING
    files, added = set(), {}
    try:
        patch = PatchSet(diff_text or "")
    except UnidiffParseError as e:
        _PARSE_WARNING = f"diff 解析失败（{e}）：确定性契约/栈核对未生效，本次仅含 AI 评审（若有）"
        return files, added
    _PARSE_WARNING = None
    for pf in patch:
        if pf.is_removed_file:               # 整文件删除(+++ /dev/null) 不计入变更文件
            continue
        path = pf.path
        files.add(path)
        for hunk in pf:
            for line in hunk:
                if line.is_added:
                    added.setdefault([]).append(
                        (line.target_line_no, (line.value or "").rstrip("\n")))
    return files, added
# 单线程评审路径下安全；解析成功会清空。


def x_parse_diff__mutmut_15(diff_text):
    """返回 (changed_files:set[str], added_lines:dict[file -> list[(lineno, text)]])。
    用成熟库 unidiff 解析，稳妥处理重命名/合并/边界等长尾（替代早期手写状态机）。
    解析失败时返回空、并把原因写进模块级 _PARSE_WARNING——调用方（orchestrator）据此在评审里
    显式标注"确定性核对未生效"，而不是让 0 条发现被读成"干净"（防静默故障）。"""
    global _PARSE_WARNING
    files, added = set(), {}
    try:
        patch = PatchSet(diff_text or "")
    except UnidiffParseError as e:
        _PARSE_WARNING = f"diff 解析失败（{e}）：确定性契约/栈核对未生效，本次仅含 AI 评审（若有）"
        return files, added
    _PARSE_WARNING = None
    for pf in patch:
        if pf.is_removed_file:               # 整文件删除(+++ /dev/null) 不计入变更文件
            continue
        path = pf.path
        files.add(path)
        for hunk in pf:
            for line in hunk:
                if line.is_added:
                    added.setdefault(path, ).append(
                        (line.target_line_no, (line.value or "").rstrip("\n")))
    return files, added
# 单线程评审路径下安全；解析成功会清空。


def x_parse_diff__mutmut_16(diff_text):
    """返回 (changed_files:set[str], added_lines:dict[file -> list[(lineno, text)]])。
    用成熟库 unidiff 解析，稳妥处理重命名/合并/边界等长尾（替代早期手写状态机）。
    解析失败时返回空、并把原因写进模块级 _PARSE_WARNING——调用方（orchestrator）据此在评审里
    显式标注"确定性核对未生效"，而不是让 0 条发现被读成"干净"（防静默故障）。"""
    global _PARSE_WARNING
    files, added = set(), {}
    try:
        patch = PatchSet(diff_text or "")
    except UnidiffParseError as e:
        _PARSE_WARNING = f"diff 解析失败（{e}）：确定性契约/栈核对未生效，本次仅含 AI 评审（若有）"
        return files, added
    _PARSE_WARNING = None
    for pf in patch:
        if pf.is_removed_file:               # 整文件删除(+++ /dev/null) 不计入变更文件
            continue
        path = pf.path
        files.add(path)
        for hunk in pf:
            for line in hunk:
                if line.is_added:
                    added.setdefault(path, []).append(
                        (line.target_line_no, (line.value or "").rstrip(None)))
    return files, added
# 单线程评审路径下安全；解析成功会清空。


def x_parse_diff__mutmut_17(diff_text):
    """返回 (changed_files:set[str], added_lines:dict[file -> list[(lineno, text)]])。
    用成熟库 unidiff 解析，稳妥处理重命名/合并/边界等长尾（替代早期手写状态机）。
    解析失败时返回空、并把原因写进模块级 _PARSE_WARNING——调用方（orchestrator）据此在评审里
    显式标注"确定性核对未生效"，而不是让 0 条发现被读成"干净"（防静默故障）。"""
    global _PARSE_WARNING
    files, added = set(), {}
    try:
        patch = PatchSet(diff_text or "")
    except UnidiffParseError as e:
        _PARSE_WARNING = f"diff 解析失败（{e}）：确定性契约/栈核对未生效，本次仅含 AI 评审（若有）"
        return files, added
    _PARSE_WARNING = None
    for pf in patch:
        if pf.is_removed_file:               # 整文件删除(+++ /dev/null) 不计入变更文件
            continue
        path = pf.path
        files.add(path)
        for hunk in pf:
            for line in hunk:
                if line.is_added:
                    added.setdefault(path, []).append(
                        (line.target_line_no, (line.value or "").lstrip("\n")))
    return files, added
# 单线程评审路径下安全；解析成功会清空。


def x_parse_diff__mutmut_18(diff_text):
    """返回 (changed_files:set[str], added_lines:dict[file -> list[(lineno, text)]])。
    用成熟库 unidiff 解析，稳妥处理重命名/合并/边界等长尾（替代早期手写状态机）。
    解析失败时返回空、并把原因写进模块级 _PARSE_WARNING——调用方（orchestrator）据此在评审里
    显式标注"确定性核对未生效"，而不是让 0 条发现被读成"干净"（防静默故障）。"""
    global _PARSE_WARNING
    files, added = set(), {}
    try:
        patch = PatchSet(diff_text or "")
    except UnidiffParseError as e:
        _PARSE_WARNING = f"diff 解析失败（{e}）：确定性契约/栈核对未生效，本次仅含 AI 评审（若有）"
        return files, added
    _PARSE_WARNING = None
    for pf in patch:
        if pf.is_removed_file:               # 整文件删除(+++ /dev/null) 不计入变更文件
            continue
        path = pf.path
        files.add(path)
        for hunk in pf:
            for line in hunk:
                if line.is_added:
                    added.setdefault(path, []).append(
                        (line.target_line_no, (line.value and "").rstrip("\n")))
    return files, added
# 单线程评审路径下安全；解析成功会清空。


def x_parse_diff__mutmut_19(diff_text):
    """返回 (changed_files:set[str], added_lines:dict[file -> list[(lineno, text)]])。
    用成熟库 unidiff 解析，稳妥处理重命名/合并/边界等长尾（替代早期手写状态机）。
    解析失败时返回空、并把原因写进模块级 _PARSE_WARNING——调用方（orchestrator）据此在评审里
    显式标注"确定性核对未生效"，而不是让 0 条发现被读成"干净"（防静默故障）。"""
    global _PARSE_WARNING
    files, added = set(), {}
    try:
        patch = PatchSet(diff_text or "")
    except UnidiffParseError as e:
        _PARSE_WARNING = f"diff 解析失败（{e}）：确定性契约/栈核对未生效，本次仅含 AI 评审（若有）"
        return files, added
    _PARSE_WARNING = None
    for pf in patch:
        if pf.is_removed_file:               # 整文件删除(+++ /dev/null) 不计入变更文件
            continue
        path = pf.path
        files.add(path)
        for hunk in pf:
            for line in hunk:
                if line.is_added:
                    added.setdefault(path, []).append(
                        (line.target_line_no, (line.value or "XXXX").rstrip("\n")))
    return files, added
# 单线程评审路径下安全；解析成功会清空。


def x_parse_diff__mutmut_20(diff_text):
    """返回 (changed_files:set[str], added_lines:dict[file -> list[(lineno, text)]])。
    用成熟库 unidiff 解析，稳妥处理重命名/合并/边界等长尾（替代早期手写状态机）。
    解析失败时返回空、并把原因写进模块级 _PARSE_WARNING——调用方（orchestrator）据此在评审里
    显式标注"确定性核对未生效"，而不是让 0 条发现被读成"干净"（防静默故障）。"""
    global _PARSE_WARNING
    files, added = set(), {}
    try:
        patch = PatchSet(diff_text or "")
    except UnidiffParseError as e:
        _PARSE_WARNING = f"diff 解析失败（{e}）：确定性契约/栈核对未生效，本次仅含 AI 评审（若有）"
        return files, added
    _PARSE_WARNING = None
    for pf in patch:
        if pf.is_removed_file:               # 整文件删除(+++ /dev/null) 不计入变更文件
            continue
        path = pf.path
        files.add(path)
        for hunk in pf:
            for line in hunk:
                if line.is_added:
                    added.setdefault(path, []).append(
                        (line.target_line_no, (line.value or "").rstrip("XX\nXX")))
    return files, added

mutants_x_parse_diff__mutmut['_mutmut_orig'] = x_parse_diff__mutmut_orig # type: ignore # mutmut generated
mutants_x_parse_diff__mutmut['x_parse_diff__mutmut_1'] = x_parse_diff__mutmut_1 # type: ignore # mutmut generated
mutants_x_parse_diff__mutmut['x_parse_diff__mutmut_2'] = x_parse_diff__mutmut_2 # type: ignore # mutmut generated
mutants_x_parse_diff__mutmut['x_parse_diff__mutmut_3'] = x_parse_diff__mutmut_3 # type: ignore # mutmut generated
mutants_x_parse_diff__mutmut['x_parse_diff__mutmut_4'] = x_parse_diff__mutmut_4 # type: ignore # mutmut generated
mutants_x_parse_diff__mutmut['x_parse_diff__mutmut_5'] = x_parse_diff__mutmut_5 # type: ignore # mutmut generated
mutants_x_parse_diff__mutmut['x_parse_diff__mutmut_6'] = x_parse_diff__mutmut_6 # type: ignore # mutmut generated
mutants_x_parse_diff__mutmut['x_parse_diff__mutmut_7'] = x_parse_diff__mutmut_7 # type: ignore # mutmut generated
mutants_x_parse_diff__mutmut['x_parse_diff__mutmut_8'] = x_parse_diff__mutmut_8 # type: ignore # mutmut generated
mutants_x_parse_diff__mutmut['x_parse_diff__mutmut_9'] = x_parse_diff__mutmut_9 # type: ignore # mutmut generated
mutants_x_parse_diff__mutmut['x_parse_diff__mutmut_10'] = x_parse_diff__mutmut_10 # type: ignore # mutmut generated
mutants_x_parse_diff__mutmut['x_parse_diff__mutmut_11'] = x_parse_diff__mutmut_11 # type: ignore # mutmut generated
mutants_x_parse_diff__mutmut['x_parse_diff__mutmut_12'] = x_parse_diff__mutmut_12 # type: ignore # mutmut generated
mutants_x_parse_diff__mutmut['x_parse_diff__mutmut_13'] = x_parse_diff__mutmut_13 # type: ignore # mutmut generated
mutants_x_parse_diff__mutmut['x_parse_diff__mutmut_14'] = x_parse_diff__mutmut_14 # type: ignore # mutmut generated
mutants_x_parse_diff__mutmut['x_parse_diff__mutmut_15'] = x_parse_diff__mutmut_15 # type: ignore # mutmut generated
mutants_x_parse_diff__mutmut['x_parse_diff__mutmut_16'] = x_parse_diff__mutmut_16 # type: ignore # mutmut generated
mutants_x_parse_diff__mutmut['x_parse_diff__mutmut_17'] = x_parse_diff__mutmut_17 # type: ignore # mutmut generated
mutants_x_parse_diff__mutmut['x_parse_diff__mutmut_18'] = x_parse_diff__mutmut_18 # type: ignore # mutmut generated
mutants_x_parse_diff__mutmut['x_parse_diff__mutmut_19'] = x_parse_diff__mutmut_19 # type: ignore # mutmut generated
mutants_x_parse_diff__mutmut['x_parse_diff__mutmut_20'] = x_parse_diff__mutmut_20 # type: ignore # mutmut generated
mutants_x__finding__mutmut: MutantDict = {}  # type: ignore


@_mutmut_mutated(mutants_x__finding__mutmut)
def _finding(rule_id, file, line, category, rationale, fix, rule_index,
             confidence=1.0, severity=None):
    rule = rule_index.get(rule_id, {})
    # 显式 severity 优先，否则取规则 severity；被 govern 固化(enforced)的一律升为 block_candidate
    sev = severity or rule.get("severity", "warn")
    if rule.get("enforced"):
        sev = "block_candidate"
    return {
        "rule_id": rule_id, "file": file, "line": line, "category": category,
        "severity": sev,
        "confidence": confidence,        # 确定性核对默认 1.0；纯启发式可下调
        "rationale": rationale, "suggested_fix": fix, "agent": "contract-check",
    }


def x__finding__mutmut_orig(rule_id, file, line, category, rationale, fix, rule_index,
             confidence=1.0, severity=None):
    rule = rule_index.get(rule_id, {})
    # 显式 severity 优先，否则取规则 severity；被 govern 固化(enforced)的一律升为 block_candidate
    sev = severity or rule.get("severity", "warn")
    if rule.get("enforced"):
        sev = "block_candidate"
    return {
        "rule_id": rule_id, "file": file, "line": line, "category": category,
        "severity": sev,
        "confidence": confidence,        # 确定性核对默认 1.0；纯启发式可下调
        "rationale": rationale, "suggested_fix": fix, "agent": "contract-check",
    }


def x__finding__mutmut_1(rule_id, file, line, category, rationale, fix, rule_index,
             confidence=2.0, severity=None):
    rule = rule_index.get(rule_id, {})
    # 显式 severity 优先，否则取规则 severity；被 govern 固化(enforced)的一律升为 block_candidate
    sev = severity or rule.get("severity", "warn")
    if rule.get("enforced"):
        sev = "block_candidate"
    return {
        "rule_id": rule_id, "file": file, "line": line, "category": category,
        "severity": sev,
        "confidence": confidence,        # 确定性核对默认 1.0；纯启发式可下调
        "rationale": rationale, "suggested_fix": fix, "agent": "contract-check",
    }


def x__finding__mutmut_2(rule_id, file, line, category, rationale, fix, rule_index,
             confidence=1.0, severity=None):
    rule = None
    # 显式 severity 优先，否则取规则 severity；被 govern 固化(enforced)的一律升为 block_candidate
    sev = severity or rule.get("severity", "warn")
    if rule.get("enforced"):
        sev = "block_candidate"
    return {
        "rule_id": rule_id, "file": file, "line": line, "category": category,
        "severity": sev,
        "confidence": confidence,        # 确定性核对默认 1.0；纯启发式可下调
        "rationale": rationale, "suggested_fix": fix, "agent": "contract-check",
    }


def x__finding__mutmut_3(rule_id, file, line, category, rationale, fix, rule_index,
             confidence=1.0, severity=None):
    rule = rule_index.get(None, {})
    # 显式 severity 优先，否则取规则 severity；被 govern 固化(enforced)的一律升为 block_candidate
    sev = severity or rule.get("severity", "warn")
    if rule.get("enforced"):
        sev = "block_candidate"
    return {
        "rule_id": rule_id, "file": file, "line": line, "category": category,
        "severity": sev,
        "confidence": confidence,        # 确定性核对默认 1.0；纯启发式可下调
        "rationale": rationale, "suggested_fix": fix, "agent": "contract-check",
    }


def x__finding__mutmut_4(rule_id, file, line, category, rationale, fix, rule_index,
             confidence=1.0, severity=None):
    rule = rule_index.get(rule_id, None)
    # 显式 severity 优先，否则取规则 severity；被 govern 固化(enforced)的一律升为 block_candidate
    sev = severity or rule.get("severity", "warn")
    if rule.get("enforced"):
        sev = "block_candidate"
    return {
        "rule_id": rule_id, "file": file, "line": line, "category": category,
        "severity": sev,
        "confidence": confidence,        # 确定性核对默认 1.0；纯启发式可下调
        "rationale": rationale, "suggested_fix": fix, "agent": "contract-check",
    }


def x__finding__mutmut_5(rule_id, file, line, category, rationale, fix, rule_index,
             confidence=1.0, severity=None):
    rule = rule_index.get({})
    # 显式 severity 优先，否则取规则 severity；被 govern 固化(enforced)的一律升为 block_candidate
    sev = severity or rule.get("severity", "warn")
    if rule.get("enforced"):
        sev = "block_candidate"
    return {
        "rule_id": rule_id, "file": file, "line": line, "category": category,
        "severity": sev,
        "confidence": confidence,        # 确定性核对默认 1.0；纯启发式可下调
        "rationale": rationale, "suggested_fix": fix, "agent": "contract-check",
    }


def x__finding__mutmut_6(rule_id, file, line, category, rationale, fix, rule_index,
             confidence=1.0, severity=None):
    rule = rule_index.get(rule_id, )
    # 显式 severity 优先，否则取规则 severity；被 govern 固化(enforced)的一律升为 block_candidate
    sev = severity or rule.get("severity", "warn")
    if rule.get("enforced"):
        sev = "block_candidate"
    return {
        "rule_id": rule_id, "file": file, "line": line, "category": category,
        "severity": sev,
        "confidence": confidence,        # 确定性核对默认 1.0；纯启发式可下调
        "rationale": rationale, "suggested_fix": fix, "agent": "contract-check",
    }


def x__finding__mutmut_7(rule_id, file, line, category, rationale, fix, rule_index,
             confidence=1.0, severity=None):
    rule = rule_index.get(rule_id, {})
    # 显式 severity 优先，否则取规则 severity；被 govern 固化(enforced)的一律升为 block_candidate
    sev = None
    if rule.get("enforced"):
        sev = "block_candidate"
    return {
        "rule_id": rule_id, "file": file, "line": line, "category": category,
        "severity": sev,
        "confidence": confidence,        # 确定性核对默认 1.0；纯启发式可下调
        "rationale": rationale, "suggested_fix": fix, "agent": "contract-check",
    }


def x__finding__mutmut_8(rule_id, file, line, category, rationale, fix, rule_index,
             confidence=1.0, severity=None):
    rule = rule_index.get(rule_id, {})
    # 显式 severity 优先，否则取规则 severity；被 govern 固化(enforced)的一律升为 block_candidate
    sev = severity and rule.get("severity", "warn")
    if rule.get("enforced"):
        sev = "block_candidate"
    return {
        "rule_id": rule_id, "file": file, "line": line, "category": category,
        "severity": sev,
        "confidence": confidence,        # 确定性核对默认 1.0；纯启发式可下调
        "rationale": rationale, "suggested_fix": fix, "agent": "contract-check",
    }


def x__finding__mutmut_9(rule_id, file, line, category, rationale, fix, rule_index,
             confidence=1.0, severity=None):
    rule = rule_index.get(rule_id, {})
    # 显式 severity 优先，否则取规则 severity；被 govern 固化(enforced)的一律升为 block_candidate
    sev = severity or rule.get(None, "warn")
    if rule.get("enforced"):
        sev = "block_candidate"
    return {
        "rule_id": rule_id, "file": file, "line": line, "category": category,
        "severity": sev,
        "confidence": confidence,        # 确定性核对默认 1.0；纯启发式可下调
        "rationale": rationale, "suggested_fix": fix, "agent": "contract-check",
    }


def x__finding__mutmut_10(rule_id, file, line, category, rationale, fix, rule_index,
             confidence=1.0, severity=None):
    rule = rule_index.get(rule_id, {})
    # 显式 severity 优先，否则取规则 severity；被 govern 固化(enforced)的一律升为 block_candidate
    sev = severity or rule.get("severity", None)
    if rule.get("enforced"):
        sev = "block_candidate"
    return {
        "rule_id": rule_id, "file": file, "line": line, "category": category,
        "severity": sev,
        "confidence": confidence,        # 确定性核对默认 1.0；纯启发式可下调
        "rationale": rationale, "suggested_fix": fix, "agent": "contract-check",
    }


def x__finding__mutmut_11(rule_id, file, line, category, rationale, fix, rule_index,
             confidence=1.0, severity=None):
    rule = rule_index.get(rule_id, {})
    # 显式 severity 优先，否则取规则 severity；被 govern 固化(enforced)的一律升为 block_candidate
    sev = severity or rule.get("warn")
    if rule.get("enforced"):
        sev = "block_candidate"
    return {
        "rule_id": rule_id, "file": file, "line": line, "category": category,
        "severity": sev,
        "confidence": confidence,        # 确定性核对默认 1.0；纯启发式可下调
        "rationale": rationale, "suggested_fix": fix, "agent": "contract-check",
    }


def x__finding__mutmut_12(rule_id, file, line, category, rationale, fix, rule_index,
             confidence=1.0, severity=None):
    rule = rule_index.get(rule_id, {})
    # 显式 severity 优先，否则取规则 severity；被 govern 固化(enforced)的一律升为 block_candidate
    sev = severity or rule.get("severity", )
    if rule.get("enforced"):
        sev = "block_candidate"
    return {
        "rule_id": rule_id, "file": file, "line": line, "category": category,
        "severity": sev,
        "confidence": confidence,        # 确定性核对默认 1.0；纯启发式可下调
        "rationale": rationale, "suggested_fix": fix, "agent": "contract-check",
    }


def x__finding__mutmut_13(rule_id, file, line, category, rationale, fix, rule_index,
             confidence=1.0, severity=None):
    rule = rule_index.get(rule_id, {})
    # 显式 severity 优先，否则取规则 severity；被 govern 固化(enforced)的一律升为 block_candidate
    sev = severity or rule.get("XXseverityXX", "warn")
    if rule.get("enforced"):
        sev = "block_candidate"
    return {
        "rule_id": rule_id, "file": file, "line": line, "category": category,
        "severity": sev,
        "confidence": confidence,        # 确定性核对默认 1.0；纯启发式可下调
        "rationale": rationale, "suggested_fix": fix, "agent": "contract-check",
    }


def x__finding__mutmut_14(rule_id, file, line, category, rationale, fix, rule_index,
             confidence=1.0, severity=None):
    rule = rule_index.get(rule_id, {})
    # 显式 severity 优先，否则取规则 severity；被 govern 固化(enforced)的一律升为 block_candidate
    sev = severity or rule.get("SEVERITY", "warn")
    if rule.get("enforced"):
        sev = "block_candidate"
    return {
        "rule_id": rule_id, "file": file, "line": line, "category": category,
        "severity": sev,
        "confidence": confidence,        # 确定性核对默认 1.0；纯启发式可下调
        "rationale": rationale, "suggested_fix": fix, "agent": "contract-check",
    }


def x__finding__mutmut_15(rule_id, file, line, category, rationale, fix, rule_index,
             confidence=1.0, severity=None):
    rule = rule_index.get(rule_id, {})
    # 显式 severity 优先，否则取规则 severity；被 govern 固化(enforced)的一律升为 block_candidate
    sev = severity or rule.get("severity", "XXwarnXX")
    if rule.get("enforced"):
        sev = "block_candidate"
    return {
        "rule_id": rule_id, "file": file, "line": line, "category": category,
        "severity": sev,
        "confidence": confidence,        # 确定性核对默认 1.0；纯启发式可下调
        "rationale": rationale, "suggested_fix": fix, "agent": "contract-check",
    }


def x__finding__mutmut_16(rule_id, file, line, category, rationale, fix, rule_index,
             confidence=1.0, severity=None):
    rule = rule_index.get(rule_id, {})
    # 显式 severity 优先，否则取规则 severity；被 govern 固化(enforced)的一律升为 block_candidate
    sev = severity or rule.get("severity", "WARN")
    if rule.get("enforced"):
        sev = "block_candidate"
    return {
        "rule_id": rule_id, "file": file, "line": line, "category": category,
        "severity": sev,
        "confidence": confidence,        # 确定性核对默认 1.0；纯启发式可下调
        "rationale": rationale, "suggested_fix": fix, "agent": "contract-check",
    }


def x__finding__mutmut_17(rule_id, file, line, category, rationale, fix, rule_index,
             confidence=1.0, severity=None):
    rule = rule_index.get(rule_id, {})
    # 显式 severity 优先，否则取规则 severity；被 govern 固化(enforced)的一律升为 block_candidate
    sev = severity or rule.get("severity", "warn")
    if rule.get(None):
        sev = "block_candidate"
    return {
        "rule_id": rule_id, "file": file, "line": line, "category": category,
        "severity": sev,
        "confidence": confidence,        # 确定性核对默认 1.0；纯启发式可下调
        "rationale": rationale, "suggested_fix": fix, "agent": "contract-check",
    }


def x__finding__mutmut_18(rule_id, file, line, category, rationale, fix, rule_index,
             confidence=1.0, severity=None):
    rule = rule_index.get(rule_id, {})
    # 显式 severity 优先，否则取规则 severity；被 govern 固化(enforced)的一律升为 block_candidate
    sev = severity or rule.get("severity", "warn")
    if rule.get("XXenforcedXX"):
        sev = "block_candidate"
    return {
        "rule_id": rule_id, "file": file, "line": line, "category": category,
        "severity": sev,
        "confidence": confidence,        # 确定性核对默认 1.0；纯启发式可下调
        "rationale": rationale, "suggested_fix": fix, "agent": "contract-check",
    }


def x__finding__mutmut_19(rule_id, file, line, category, rationale, fix, rule_index,
             confidence=1.0, severity=None):
    rule = rule_index.get(rule_id, {})
    # 显式 severity 优先，否则取规则 severity；被 govern 固化(enforced)的一律升为 block_candidate
    sev = severity or rule.get("severity", "warn")
    if rule.get("ENFORCED"):
        sev = "block_candidate"
    return {
        "rule_id": rule_id, "file": file, "line": line, "category": category,
        "severity": sev,
        "confidence": confidence,        # 确定性核对默认 1.0；纯启发式可下调
        "rationale": rationale, "suggested_fix": fix, "agent": "contract-check",
    }


def x__finding__mutmut_20(rule_id, file, line, category, rationale, fix, rule_index,
             confidence=1.0, severity=None):
    rule = rule_index.get(rule_id, {})
    # 显式 severity 优先，否则取规则 severity；被 govern 固化(enforced)的一律升为 block_candidate
    sev = severity or rule.get("severity", "warn")
    if rule.get("enforced"):
        sev = None
    return {
        "rule_id": rule_id, "file": file, "line": line, "category": category,
        "severity": sev,
        "confidence": confidence,        # 确定性核对默认 1.0；纯启发式可下调
        "rationale": rationale, "suggested_fix": fix, "agent": "contract-check",
    }


def x__finding__mutmut_21(rule_id, file, line, category, rationale, fix, rule_index,
             confidence=1.0, severity=None):
    rule = rule_index.get(rule_id, {})
    # 显式 severity 优先，否则取规则 severity；被 govern 固化(enforced)的一律升为 block_candidate
    sev = severity or rule.get("severity", "warn")
    if rule.get("enforced"):
        sev = "XXblock_candidateXX"
    return {
        "rule_id": rule_id, "file": file, "line": line, "category": category,
        "severity": sev,
        "confidence": confidence,        # 确定性核对默认 1.0；纯启发式可下调
        "rationale": rationale, "suggested_fix": fix, "agent": "contract-check",
    }


def x__finding__mutmut_22(rule_id, file, line, category, rationale, fix, rule_index,
             confidence=1.0, severity=None):
    rule = rule_index.get(rule_id, {})
    # 显式 severity 优先，否则取规则 severity；被 govern 固化(enforced)的一律升为 block_candidate
    sev = severity or rule.get("severity", "warn")
    if rule.get("enforced"):
        sev = "BLOCK_CANDIDATE"
    return {
        "rule_id": rule_id, "file": file, "line": line, "category": category,
        "severity": sev,
        "confidence": confidence,        # 确定性核对默认 1.0；纯启发式可下调
        "rationale": rationale, "suggested_fix": fix, "agent": "contract-check",
    }


def x__finding__mutmut_23(rule_id, file, line, category, rationale, fix, rule_index,
             confidence=1.0, severity=None):
    rule = rule_index.get(rule_id, {})
    # 显式 severity 优先，否则取规则 severity；被 govern 固化(enforced)的一律升为 block_candidate
    sev = severity or rule.get("severity", "warn")
    if rule.get("enforced"):
        sev = "block_candidate"
    return {
        "XXrule_idXX": rule_id, "file": file, "line": line, "category": category,
        "severity": sev,
        "confidence": confidence,        # 确定性核对默认 1.0；纯启发式可下调
        "rationale": rationale, "suggested_fix": fix, "agent": "contract-check",
    }


def x__finding__mutmut_24(rule_id, file, line, category, rationale, fix, rule_index,
             confidence=1.0, severity=None):
    rule = rule_index.get(rule_id, {})
    # 显式 severity 优先，否则取规则 severity；被 govern 固化(enforced)的一律升为 block_candidate
    sev = severity or rule.get("severity", "warn")
    if rule.get("enforced"):
        sev = "block_candidate"
    return {
        "RULE_ID": rule_id, "file": file, "line": line, "category": category,
        "severity": sev,
        "confidence": confidence,        # 确定性核对默认 1.0；纯启发式可下调
        "rationale": rationale, "suggested_fix": fix, "agent": "contract-check",
    }


def x__finding__mutmut_25(rule_id, file, line, category, rationale, fix, rule_index,
             confidence=1.0, severity=None):
    rule = rule_index.get(rule_id, {})
    # 显式 severity 优先，否则取规则 severity；被 govern 固化(enforced)的一律升为 block_candidate
    sev = severity or rule.get("severity", "warn")
    if rule.get("enforced"):
        sev = "block_candidate"
    return {
        "rule_id": rule_id, "XXfileXX": file, "line": line, "category": category,
        "severity": sev,
        "confidence": confidence,        # 确定性核对默认 1.0；纯启发式可下调
        "rationale": rationale, "suggested_fix": fix, "agent": "contract-check",
    }


def x__finding__mutmut_26(rule_id, file, line, category, rationale, fix, rule_index,
             confidence=1.0, severity=None):
    rule = rule_index.get(rule_id, {})
    # 显式 severity 优先，否则取规则 severity；被 govern 固化(enforced)的一律升为 block_candidate
    sev = severity or rule.get("severity", "warn")
    if rule.get("enforced"):
        sev = "block_candidate"
    return {
        "rule_id": rule_id, "FILE": file, "line": line, "category": category,
        "severity": sev,
        "confidence": confidence,        # 确定性核对默认 1.0；纯启发式可下调
        "rationale": rationale, "suggested_fix": fix, "agent": "contract-check",
    }


def x__finding__mutmut_27(rule_id, file, line, category, rationale, fix, rule_index,
             confidence=1.0, severity=None):
    rule = rule_index.get(rule_id, {})
    # 显式 severity 优先，否则取规则 severity；被 govern 固化(enforced)的一律升为 block_candidate
    sev = severity or rule.get("severity", "warn")
    if rule.get("enforced"):
        sev = "block_candidate"
    return {
        "rule_id": rule_id, "file": file, "XXlineXX": line, "category": category,
        "severity": sev,
        "confidence": confidence,        # 确定性核对默认 1.0；纯启发式可下调
        "rationale": rationale, "suggested_fix": fix, "agent": "contract-check",
    }


def x__finding__mutmut_28(rule_id, file, line, category, rationale, fix, rule_index,
             confidence=1.0, severity=None):
    rule = rule_index.get(rule_id, {})
    # 显式 severity 优先，否则取规则 severity；被 govern 固化(enforced)的一律升为 block_candidate
    sev = severity or rule.get("severity", "warn")
    if rule.get("enforced"):
        sev = "block_candidate"
    return {
        "rule_id": rule_id, "file": file, "LINE": line, "category": category,
        "severity": sev,
        "confidence": confidence,        # 确定性核对默认 1.0；纯启发式可下调
        "rationale": rationale, "suggested_fix": fix, "agent": "contract-check",
    }


def x__finding__mutmut_29(rule_id, file, line, category, rationale, fix, rule_index,
             confidence=1.0, severity=None):
    rule = rule_index.get(rule_id, {})
    # 显式 severity 优先，否则取规则 severity；被 govern 固化(enforced)的一律升为 block_candidate
    sev = severity or rule.get("severity", "warn")
    if rule.get("enforced"):
        sev = "block_candidate"
    return {
        "rule_id": rule_id, "file": file, "line": line, "XXcategoryXX": category,
        "severity": sev,
        "confidence": confidence,        # 确定性核对默认 1.0；纯启发式可下调
        "rationale": rationale, "suggested_fix": fix, "agent": "contract-check",
    }


def x__finding__mutmut_30(rule_id, file, line, category, rationale, fix, rule_index,
             confidence=1.0, severity=None):
    rule = rule_index.get(rule_id, {})
    # 显式 severity 优先，否则取规则 severity；被 govern 固化(enforced)的一律升为 block_candidate
    sev = severity or rule.get("severity", "warn")
    if rule.get("enforced"):
        sev = "block_candidate"
    return {
        "rule_id": rule_id, "file": file, "line": line, "CATEGORY": category,
        "severity": sev,
        "confidence": confidence,        # 确定性核对默认 1.0；纯启发式可下调
        "rationale": rationale, "suggested_fix": fix, "agent": "contract-check",
    }


def x__finding__mutmut_31(rule_id, file, line, category, rationale, fix, rule_index,
             confidence=1.0, severity=None):
    rule = rule_index.get(rule_id, {})
    # 显式 severity 优先，否则取规则 severity；被 govern 固化(enforced)的一律升为 block_candidate
    sev = severity or rule.get("severity", "warn")
    if rule.get("enforced"):
        sev = "block_candidate"
    return {
        "rule_id": rule_id, "file": file, "line": line, "category": category,
        "XXseverityXX": sev,
        "confidence": confidence,        # 确定性核对默认 1.0；纯启发式可下调
        "rationale": rationale, "suggested_fix": fix, "agent": "contract-check",
    }


def x__finding__mutmut_32(rule_id, file, line, category, rationale, fix, rule_index,
             confidence=1.0, severity=None):
    rule = rule_index.get(rule_id, {})
    # 显式 severity 优先，否则取规则 severity；被 govern 固化(enforced)的一律升为 block_candidate
    sev = severity or rule.get("severity", "warn")
    if rule.get("enforced"):
        sev = "block_candidate"
    return {
        "rule_id": rule_id, "file": file, "line": line, "category": category,
        "SEVERITY": sev,
        "confidence": confidence,        # 确定性核对默认 1.0；纯启发式可下调
        "rationale": rationale, "suggested_fix": fix, "agent": "contract-check",
    }


def x__finding__mutmut_33(rule_id, file, line, category, rationale, fix, rule_index,
             confidence=1.0, severity=None):
    rule = rule_index.get(rule_id, {})
    # 显式 severity 优先，否则取规则 severity；被 govern 固化(enforced)的一律升为 block_candidate
    sev = severity or rule.get("severity", "warn")
    if rule.get("enforced"):
        sev = "block_candidate"
    return {
        "rule_id": rule_id, "file": file, "line": line, "category": category,
        "severity": sev,
        "XXconfidenceXX": confidence,        # 确定性核对默认 1.0；纯启发式可下调
        "rationale": rationale, "suggested_fix": fix, "agent": "contract-check",
    }


def x__finding__mutmut_34(rule_id, file, line, category, rationale, fix, rule_index,
             confidence=1.0, severity=None):
    rule = rule_index.get(rule_id, {})
    # 显式 severity 优先，否则取规则 severity；被 govern 固化(enforced)的一律升为 block_candidate
    sev = severity or rule.get("severity", "warn")
    if rule.get("enforced"):
        sev = "block_candidate"
    return {
        "rule_id": rule_id, "file": file, "line": line, "category": category,
        "severity": sev,
        "CONFIDENCE": confidence,        # 确定性核对默认 1.0；纯启发式可下调
        "rationale": rationale, "suggested_fix": fix, "agent": "contract-check",
    }


def x__finding__mutmut_35(rule_id, file, line, category, rationale, fix, rule_index,
             confidence=1.0, severity=None):
    rule = rule_index.get(rule_id, {})
    # 显式 severity 优先，否则取规则 severity；被 govern 固化(enforced)的一律升为 block_candidate
    sev = severity or rule.get("severity", "warn")
    if rule.get("enforced"):
        sev = "block_candidate"
    return {
        "rule_id": rule_id, "file": file, "line": line, "category": category,
        "severity": sev,
        "confidence": confidence,        # 确定性核对默认 1.0；纯启发式可下调
        "XXrationaleXX": rationale, "suggested_fix": fix, "agent": "contract-check",
    }


def x__finding__mutmut_36(rule_id, file, line, category, rationale, fix, rule_index,
             confidence=1.0, severity=None):
    rule = rule_index.get(rule_id, {})
    # 显式 severity 优先，否则取规则 severity；被 govern 固化(enforced)的一律升为 block_candidate
    sev = severity or rule.get("severity", "warn")
    if rule.get("enforced"):
        sev = "block_candidate"
    return {
        "rule_id": rule_id, "file": file, "line": line, "category": category,
        "severity": sev,
        "confidence": confidence,        # 确定性核对默认 1.0；纯启发式可下调
        "RATIONALE": rationale, "suggested_fix": fix, "agent": "contract-check",
    }


def x__finding__mutmut_37(rule_id, file, line, category, rationale, fix, rule_index,
             confidence=1.0, severity=None):
    rule = rule_index.get(rule_id, {})
    # 显式 severity 优先，否则取规则 severity；被 govern 固化(enforced)的一律升为 block_candidate
    sev = severity or rule.get("severity", "warn")
    if rule.get("enforced"):
        sev = "block_candidate"
    return {
        "rule_id": rule_id, "file": file, "line": line, "category": category,
        "severity": sev,
        "confidence": confidence,        # 确定性核对默认 1.0；纯启发式可下调
        "rationale": rationale, "XXsuggested_fixXX": fix, "agent": "contract-check",
    }


def x__finding__mutmut_38(rule_id, file, line, category, rationale, fix, rule_index,
             confidence=1.0, severity=None):
    rule = rule_index.get(rule_id, {})
    # 显式 severity 优先，否则取规则 severity；被 govern 固化(enforced)的一律升为 block_candidate
    sev = severity or rule.get("severity", "warn")
    if rule.get("enforced"):
        sev = "block_candidate"
    return {
        "rule_id": rule_id, "file": file, "line": line, "category": category,
        "severity": sev,
        "confidence": confidence,        # 确定性核对默认 1.0；纯启发式可下调
        "rationale": rationale, "SUGGESTED_FIX": fix, "agent": "contract-check",
    }


def x__finding__mutmut_39(rule_id, file, line, category, rationale, fix, rule_index,
             confidence=1.0, severity=None):
    rule = rule_index.get(rule_id, {})
    # 显式 severity 优先，否则取规则 severity；被 govern 固化(enforced)的一律升为 block_candidate
    sev = severity or rule.get("severity", "warn")
    if rule.get("enforced"):
        sev = "block_candidate"
    return {
        "rule_id": rule_id, "file": file, "line": line, "category": category,
        "severity": sev,
        "confidence": confidence,        # 确定性核对默认 1.0；纯启发式可下调
        "rationale": rationale, "suggested_fix": fix, "XXagentXX": "contract-check",
    }


def x__finding__mutmut_40(rule_id, file, line, category, rationale, fix, rule_index,
             confidence=1.0, severity=None):
    rule = rule_index.get(rule_id, {})
    # 显式 severity 优先，否则取规则 severity；被 govern 固化(enforced)的一律升为 block_candidate
    sev = severity or rule.get("severity", "warn")
    if rule.get("enforced"):
        sev = "block_candidate"
    return {
        "rule_id": rule_id, "file": file, "line": line, "category": category,
        "severity": sev,
        "confidence": confidence,        # 确定性核对默认 1.0；纯启发式可下调
        "rationale": rationale, "suggested_fix": fix, "AGENT": "contract-check",
    }


def x__finding__mutmut_41(rule_id, file, line, category, rationale, fix, rule_index,
             confidence=1.0, severity=None):
    rule = rule_index.get(rule_id, {})
    # 显式 severity 优先，否则取规则 severity；被 govern 固化(enforced)的一律升为 block_candidate
    sev = severity or rule.get("severity", "warn")
    if rule.get("enforced"):
        sev = "block_candidate"
    return {
        "rule_id": rule_id, "file": file, "line": line, "category": category,
        "severity": sev,
        "confidence": confidence,        # 确定性核对默认 1.0；纯启发式可下调
        "rationale": rationale, "suggested_fix": fix, "agent": "XXcontract-checkXX",
    }


def x__finding__mutmut_42(rule_id, file, line, category, rationale, fix, rule_index,
             confidence=1.0, severity=None):
    rule = rule_index.get(rule_id, {})
    # 显式 severity 优先，否则取规则 severity；被 govern 固化(enforced)的一律升为 block_candidate
    sev = severity or rule.get("severity", "warn")
    if rule.get("enforced"):
        sev = "block_candidate"
    return {
        "rule_id": rule_id, "file": file, "line": line, "category": category,
        "severity": sev,
        "confidence": confidence,        # 确定性核对默认 1.0；纯启发式可下调
        "rationale": rationale, "suggested_fix": fix, "agent": "CONTRACT-CHECK",
    }

mutants_x__finding__mutmut['_mutmut_orig'] = x__finding__mutmut_orig # type: ignore # mutmut generated
mutants_x__finding__mutmut['x__finding__mutmut_1'] = x__finding__mutmut_1 # type: ignore # mutmut generated
mutants_x__finding__mutmut['x__finding__mutmut_2'] = x__finding__mutmut_2 # type: ignore # mutmut generated
mutants_x__finding__mutmut['x__finding__mutmut_3'] = x__finding__mutmut_3 # type: ignore # mutmut generated
mutants_x__finding__mutmut['x__finding__mutmut_4'] = x__finding__mutmut_4 # type: ignore # mutmut generated
mutants_x__finding__mutmut['x__finding__mutmut_5'] = x__finding__mutmut_5 # type: ignore # mutmut generated
mutants_x__finding__mutmut['x__finding__mutmut_6'] = x__finding__mutmut_6 # type: ignore # mutmut generated
mutants_x__finding__mutmut['x__finding__mutmut_7'] = x__finding__mutmut_7 # type: ignore # mutmut generated
mutants_x__finding__mutmut['x__finding__mutmut_8'] = x__finding__mutmut_8 # type: ignore # mutmut generated
mutants_x__finding__mutmut['x__finding__mutmut_9'] = x__finding__mutmut_9 # type: ignore # mutmut generated
mutants_x__finding__mutmut['x__finding__mutmut_10'] = x__finding__mutmut_10 # type: ignore # mutmut generated
mutants_x__finding__mutmut['x__finding__mutmut_11'] = x__finding__mutmut_11 # type: ignore # mutmut generated
mutants_x__finding__mutmut['x__finding__mutmut_12'] = x__finding__mutmut_12 # type: ignore # mutmut generated
mutants_x__finding__mutmut['x__finding__mutmut_13'] = x__finding__mutmut_13 # type: ignore # mutmut generated
mutants_x__finding__mutmut['x__finding__mutmut_14'] = x__finding__mutmut_14 # type: ignore # mutmut generated
mutants_x__finding__mutmut['x__finding__mutmut_15'] = x__finding__mutmut_15 # type: ignore # mutmut generated
mutants_x__finding__mutmut['x__finding__mutmut_16'] = x__finding__mutmut_16 # type: ignore # mutmut generated
mutants_x__finding__mutmut['x__finding__mutmut_17'] = x__finding__mutmut_17 # type: ignore # mutmut generated
mutants_x__finding__mutmut['x__finding__mutmut_18'] = x__finding__mutmut_18 # type: ignore # mutmut generated
mutants_x__finding__mutmut['x__finding__mutmut_19'] = x__finding__mutmut_19 # type: ignore # mutmut generated
mutants_x__finding__mutmut['x__finding__mutmut_20'] = x__finding__mutmut_20 # type: ignore # mutmut generated
mutants_x__finding__mutmut['x__finding__mutmut_21'] = x__finding__mutmut_21 # type: ignore # mutmut generated
mutants_x__finding__mutmut['x__finding__mutmut_22'] = x__finding__mutmut_22 # type: ignore # mutmut generated
mutants_x__finding__mutmut['x__finding__mutmut_23'] = x__finding__mutmut_23 # type: ignore # mutmut generated
mutants_x__finding__mutmut['x__finding__mutmut_24'] = x__finding__mutmut_24 # type: ignore # mutmut generated
mutants_x__finding__mutmut['x__finding__mutmut_25'] = x__finding__mutmut_25 # type: ignore # mutmut generated
mutants_x__finding__mutmut['x__finding__mutmut_26'] = x__finding__mutmut_26 # type: ignore # mutmut generated
mutants_x__finding__mutmut['x__finding__mutmut_27'] = x__finding__mutmut_27 # type: ignore # mutmut generated
mutants_x__finding__mutmut['x__finding__mutmut_28'] = x__finding__mutmut_28 # type: ignore # mutmut generated
mutants_x__finding__mutmut['x__finding__mutmut_29'] = x__finding__mutmut_29 # type: ignore # mutmut generated
mutants_x__finding__mutmut['x__finding__mutmut_30'] = x__finding__mutmut_30 # type: ignore # mutmut generated
mutants_x__finding__mutmut['x__finding__mutmut_31'] = x__finding__mutmut_31 # type: ignore # mutmut generated
mutants_x__finding__mutmut['x__finding__mutmut_32'] = x__finding__mutmut_32 # type: ignore # mutmut generated
mutants_x__finding__mutmut['x__finding__mutmut_33'] = x__finding__mutmut_33 # type: ignore # mutmut generated
mutants_x__finding__mutmut['x__finding__mutmut_34'] = x__finding__mutmut_34 # type: ignore # mutmut generated
mutants_x__finding__mutmut['x__finding__mutmut_35'] = x__finding__mutmut_35 # type: ignore # mutmut generated
mutants_x__finding__mutmut['x__finding__mutmut_36'] = x__finding__mutmut_36 # type: ignore # mutmut generated
mutants_x__finding__mutmut['x__finding__mutmut_37'] = x__finding__mutmut_37 # type: ignore # mutmut generated
mutants_x__finding__mutmut['x__finding__mutmut_38'] = x__finding__mutmut_38 # type: ignore # mutmut generated
mutants_x__finding__mutmut['x__finding__mutmut_39'] = x__finding__mutmut_39 # type: ignore # mutmut generated
mutants_x__finding__mutmut['x__finding__mutmut_40'] = x__finding__mutmut_40 # type: ignore # mutmut generated
mutants_x__finding__mutmut['x__finding__mutmut_41'] = x__finding__mutmut_41 # type: ignore # mutmut generated
mutants_x__finding__mutmut['x__finding__mutmut_42'] = x__finding__mutmut_42 # type: ignore # mutmut generated
mutants_x__match_any__mutmut: MutantDict = {}  # type: ignore


@_mutmut_mutated(mutants_x__match_any__mutmut)
def _match_any(path, globs):
    return any(fnmatch.fnmatch(path, g) for g in globs)


def x__match_any__mutmut_orig(path, globs):
    return any(fnmatch.fnmatch(path, g) for g in globs)


def x__match_any__mutmut_1(path, globs):
    return any(None)


def x__match_any__mutmut_2(path, globs):
    return any(fnmatch.fnmatch(None, g) for g in globs)


def x__match_any__mutmut_3(path, globs):
    return any(fnmatch.fnmatch(path, None) for g in globs)


def x__match_any__mutmut_4(path, globs):
    return any(fnmatch.fnmatch(g) for g in globs)


def x__match_any__mutmut_5(path, globs):
    return any(fnmatch.fnmatch(path, ) for g in globs)

mutants_x__match_any__mutmut['_mutmut_orig'] = x__match_any__mutmut_orig # type: ignore # mutmut generated
mutants_x__match_any__mutmut['x__match_any__mutmut_1'] = x__match_any__mutmut_1 # type: ignore # mutmut generated
mutants_x__match_any__mutmut['x__match_any__mutmut_2'] = x__match_any__mutmut_2 # type: ignore # mutmut generated
mutants_x__match_any__mutmut['x__match_any__mutmut_3'] = x__match_any__mutmut_3 # type: ignore # mutmut generated
mutants_x__match_any__mutmut['x__match_any__mutmut_4'] = x__match_any__mutmut_4 # type: ignore # mutmut generated
mutants_x__match_any__mutmut['x__match_any__mutmut_5'] = x__match_any__mutmut_5 # type: ignore # mutmut generated
mutants_x_check_scope__mutmut: MutantDict = {}  # type: ignore


@_mutmut_mutated(mutants_x_check_scope__mutmut)
def check_scope(files, scope, rule_index):
    # 跳过模板占位符（以 '<' 开头，如未填的 pr.yaml 里 "<path/glob…>"）——
    # 与 check_tests 同构：占位符不算真实声明，否则会对每个文件刷假阳性 SCOPE-001。
    scope = [s for s in (scope or []) if s and not str(s).startswith("<")]
    if not scope:
        return []
    return [_finding("SCOPE-001", f, 0, "scope_creep",
                     "改动文件不在提交契约声明的 scope 内（疑似越界）",
                     f"将 {f} 的改动拆到独立 PR，或在 scope 中显式声明", rule_index)
            for f in sorted(files) if not _match_any(f, scope)]


def x_check_scope__mutmut_orig(files, scope, rule_index):
    # 跳过模板占位符（以 '<' 开头，如未填的 pr.yaml 里 "<path/glob…>"）——
    # 与 check_tests 同构：占位符不算真实声明，否则会对每个文件刷假阳性 SCOPE-001。
    scope = [s for s in (scope or []) if s and not str(s).startswith("<")]
    if not scope:
        return []
    return [_finding("SCOPE-001", f, 0, "scope_creep",
                     "改动文件不在提交契约声明的 scope 内（疑似越界）",
                     f"将 {f} 的改动拆到独立 PR，或在 scope 中显式声明", rule_index)
            for f in sorted(files) if not _match_any(f, scope)]


def x_check_scope__mutmut_1(files, scope, rule_index):
    # 跳过模板占位符（以 '<' 开头，如未填的 pr.yaml 里 "<path/glob…>"）——
    # 与 check_tests 同构：占位符不算真实声明，否则会对每个文件刷假阳性 SCOPE-001。
    scope = None
    if not scope:
        return []
    return [_finding("SCOPE-001", f, 0, "scope_creep",
                     "改动文件不在提交契约声明的 scope 内（疑似越界）",
                     f"将 {f} 的改动拆到独立 PR，或在 scope 中显式声明", rule_index)
            for f in sorted(files) if not _match_any(f, scope)]


def x_check_scope__mutmut_2(files, scope, rule_index):
    # 跳过模板占位符（以 '<' 开头，如未填的 pr.yaml 里 "<path/glob…>"）——
    # 与 check_tests 同构：占位符不算真实声明，否则会对每个文件刷假阳性 SCOPE-001。
    scope = [s for s in (scope and []) if s and not str(s).startswith("<")]
    if not scope:
        return []
    return [_finding("SCOPE-001", f, 0, "scope_creep",
                     "改动文件不在提交契约声明的 scope 内（疑似越界）",
                     f"将 {f} 的改动拆到独立 PR，或在 scope 中显式声明", rule_index)
            for f in sorted(files) if not _match_any(f, scope)]


def x_check_scope__mutmut_3(files, scope, rule_index):
    # 跳过模板占位符（以 '<' 开头，如未填的 pr.yaml 里 "<path/glob…>"）——
    # 与 check_tests 同构：占位符不算真实声明，否则会对每个文件刷假阳性 SCOPE-001。
    scope = [s for s in (scope or []) if s or not str(s).startswith("<")]
    if not scope:
        return []
    return [_finding("SCOPE-001", f, 0, "scope_creep",
                     "改动文件不在提交契约声明的 scope 内（疑似越界）",
                     f"将 {f} 的改动拆到独立 PR，或在 scope 中显式声明", rule_index)
            for f in sorted(files) if not _match_any(f, scope)]


def x_check_scope__mutmut_4(files, scope, rule_index):
    # 跳过模板占位符（以 '<' 开头，如未填的 pr.yaml 里 "<path/glob…>"）——
    # 与 check_tests 同构：占位符不算真实声明，否则会对每个文件刷假阳性 SCOPE-001。
    scope = [s for s in (scope or []) if s and str(s).startswith("<")]
    if not scope:
        return []
    return [_finding("SCOPE-001", f, 0, "scope_creep",
                     "改动文件不在提交契约声明的 scope 内（疑似越界）",
                     f"将 {f} 的改动拆到独立 PR，或在 scope 中显式声明", rule_index)
            for f in sorted(files) if not _match_any(f, scope)]


def x_check_scope__mutmut_5(files, scope, rule_index):
    # 跳过模板占位符（以 '<' 开头，如未填的 pr.yaml 里 "<path/glob…>"）——
    # 与 check_tests 同构：占位符不算真实声明，否则会对每个文件刷假阳性 SCOPE-001。
    scope = [s for s in (scope or []) if s and not str(s).startswith(None)]
    if not scope:
        return []
    return [_finding("SCOPE-001", f, 0, "scope_creep",
                     "改动文件不在提交契约声明的 scope 内（疑似越界）",
                     f"将 {f} 的改动拆到独立 PR，或在 scope 中显式声明", rule_index)
            for f in sorted(files) if not _match_any(f, scope)]


def x_check_scope__mutmut_6(files, scope, rule_index):
    # 跳过模板占位符（以 '<' 开头，如未填的 pr.yaml 里 "<path/glob…>"）——
    # 与 check_tests 同构：占位符不算真实声明，否则会对每个文件刷假阳性 SCOPE-001。
    scope = [s for s in (scope or []) if s and not str(None).startswith("<")]
    if not scope:
        return []
    return [_finding("SCOPE-001", f, 0, "scope_creep",
                     "改动文件不在提交契约声明的 scope 内（疑似越界）",
                     f"将 {f} 的改动拆到独立 PR，或在 scope 中显式声明", rule_index)
            for f in sorted(files) if not _match_any(f, scope)]


def x_check_scope__mutmut_7(files, scope, rule_index):
    # 跳过模板占位符（以 '<' 开头，如未填的 pr.yaml 里 "<path/glob…>"）——
    # 与 check_tests 同构：占位符不算真实声明，否则会对每个文件刷假阳性 SCOPE-001。
    scope = [s for s in (scope or []) if s and not str(s).startswith("XX<XX")]
    if not scope:
        return []
    return [_finding("SCOPE-001", f, 0, "scope_creep",
                     "改动文件不在提交契约声明的 scope 内（疑似越界）",
                     f"将 {f} 的改动拆到独立 PR，或在 scope 中显式声明", rule_index)
            for f in sorted(files) if not _match_any(f, scope)]


def x_check_scope__mutmut_8(files, scope, rule_index):
    # 跳过模板占位符（以 '<' 开头，如未填的 pr.yaml 里 "<path/glob…>"）——
    # 与 check_tests 同构：占位符不算真实声明，否则会对每个文件刷假阳性 SCOPE-001。
    scope = [s for s in (scope or []) if s and not str(s).startswith("<")]
    if scope:
        return []
    return [_finding("SCOPE-001", f, 0, "scope_creep",
                     "改动文件不在提交契约声明的 scope 内（疑似越界）",
                     f"将 {f} 的改动拆到独立 PR，或在 scope 中显式声明", rule_index)
            for f in sorted(files) if not _match_any(f, scope)]


def x_check_scope__mutmut_9(files, scope, rule_index):
    # 跳过模板占位符（以 '<' 开头，如未填的 pr.yaml 里 "<path/glob…>"）——
    # 与 check_tests 同构：占位符不算真实声明，否则会对每个文件刷假阳性 SCOPE-001。
    scope = [s for s in (scope or []) if s and not str(s).startswith("<")]
    if not scope:
        return []
    return [_finding(None, f, 0, "scope_creep",
                     "改动文件不在提交契约声明的 scope 内（疑似越界）",
                     f"将 {f} 的改动拆到独立 PR，或在 scope 中显式声明", rule_index)
            for f in sorted(files) if not _match_any(f, scope)]


def x_check_scope__mutmut_10(files, scope, rule_index):
    # 跳过模板占位符（以 '<' 开头，如未填的 pr.yaml 里 "<path/glob…>"）——
    # 与 check_tests 同构：占位符不算真实声明，否则会对每个文件刷假阳性 SCOPE-001。
    scope = [s for s in (scope or []) if s and not str(s).startswith("<")]
    if not scope:
        return []
    return [_finding("SCOPE-001", None, 0, "scope_creep",
                     "改动文件不在提交契约声明的 scope 内（疑似越界）",
                     f"将 {f} 的改动拆到独立 PR，或在 scope 中显式声明", rule_index)
            for f in sorted(files) if not _match_any(f, scope)]


def x_check_scope__mutmut_11(files, scope, rule_index):
    # 跳过模板占位符（以 '<' 开头，如未填的 pr.yaml 里 "<path/glob…>"）——
    # 与 check_tests 同构：占位符不算真实声明，否则会对每个文件刷假阳性 SCOPE-001。
    scope = [s for s in (scope or []) if s and not str(s).startswith("<")]
    if not scope:
        return []
    return [_finding("SCOPE-001", f, None, "scope_creep",
                     "改动文件不在提交契约声明的 scope 内（疑似越界）",
                     f"将 {f} 的改动拆到独立 PR，或在 scope 中显式声明", rule_index)
            for f in sorted(files) if not _match_any(f, scope)]


def x_check_scope__mutmut_12(files, scope, rule_index):
    # 跳过模板占位符（以 '<' 开头，如未填的 pr.yaml 里 "<path/glob…>"）——
    # 与 check_tests 同构：占位符不算真实声明，否则会对每个文件刷假阳性 SCOPE-001。
    scope = [s for s in (scope or []) if s and not str(s).startswith("<")]
    if not scope:
        return []
    return [_finding("SCOPE-001", f, 0, None,
                     "改动文件不在提交契约声明的 scope 内（疑似越界）",
                     f"将 {f} 的改动拆到独立 PR，或在 scope 中显式声明", rule_index)
            for f in sorted(files) if not _match_any(f, scope)]


def x_check_scope__mutmut_13(files, scope, rule_index):
    # 跳过模板占位符（以 '<' 开头，如未填的 pr.yaml 里 "<path/glob…>"）——
    # 与 check_tests 同构：占位符不算真实声明，否则会对每个文件刷假阳性 SCOPE-001。
    scope = [s for s in (scope or []) if s and not str(s).startswith("<")]
    if not scope:
        return []
    return [_finding("SCOPE-001", f, 0, "scope_creep",
                     None,
                     f"将 {f} 的改动拆到独立 PR，或在 scope 中显式声明", rule_index)
            for f in sorted(files) if not _match_any(f, scope)]


def x_check_scope__mutmut_14(files, scope, rule_index):
    # 跳过模板占位符（以 '<' 开头，如未填的 pr.yaml 里 "<path/glob…>"）——
    # 与 check_tests 同构：占位符不算真实声明，否则会对每个文件刷假阳性 SCOPE-001。
    scope = [s for s in (scope or []) if s and not str(s).startswith("<")]
    if not scope:
        return []
    return [_finding("SCOPE-001", f, 0, "scope_creep",
                     "改动文件不在提交契约声明的 scope 内（疑似越界）",
                     None, rule_index)
            for f in sorted(files) if not _match_any(f, scope)]


def x_check_scope__mutmut_15(files, scope, rule_index):
    # 跳过模板占位符（以 '<' 开头，如未填的 pr.yaml 里 "<path/glob…>"）——
    # 与 check_tests 同构：占位符不算真实声明，否则会对每个文件刷假阳性 SCOPE-001。
    scope = [s for s in (scope or []) if s and not str(s).startswith("<")]
    if not scope:
        return []
    return [_finding("SCOPE-001", f, 0, "scope_creep",
                     "改动文件不在提交契约声明的 scope 内（疑似越界）",
                     f"将 {f} 的改动拆到独立 PR，或在 scope 中显式声明", None)
            for f in sorted(files) if not _match_any(f, scope)]


def x_check_scope__mutmut_16(files, scope, rule_index):
    # 跳过模板占位符（以 '<' 开头，如未填的 pr.yaml 里 "<path/glob…>"）——
    # 与 check_tests 同构：占位符不算真实声明，否则会对每个文件刷假阳性 SCOPE-001。
    scope = [s for s in (scope or []) if s and not str(s).startswith("<")]
    if not scope:
        return []
    return [_finding(f, 0, "scope_creep",
                     "改动文件不在提交契约声明的 scope 内（疑似越界）",
                     f"将 {f} 的改动拆到独立 PR，或在 scope 中显式声明", rule_index)
            for f in sorted(files) if not _match_any(f, scope)]


def x_check_scope__mutmut_17(files, scope, rule_index):
    # 跳过模板占位符（以 '<' 开头，如未填的 pr.yaml 里 "<path/glob…>"）——
    # 与 check_tests 同构：占位符不算真实声明，否则会对每个文件刷假阳性 SCOPE-001。
    scope = [s for s in (scope or []) if s and not str(s).startswith("<")]
    if not scope:
        return []
    return [_finding("SCOPE-001", 0, "scope_creep",
                     "改动文件不在提交契约声明的 scope 内（疑似越界）",
                     f"将 {f} 的改动拆到独立 PR，或在 scope 中显式声明", rule_index)
            for f in sorted(files) if not _match_any(f, scope)]


def x_check_scope__mutmut_18(files, scope, rule_index):
    # 跳过模板占位符（以 '<' 开头，如未填的 pr.yaml 里 "<path/glob…>"）——
    # 与 check_tests 同构：占位符不算真实声明，否则会对每个文件刷假阳性 SCOPE-001。
    scope = [s for s in (scope or []) if s and not str(s).startswith("<")]
    if not scope:
        return []
    return [_finding("SCOPE-001", f, "scope_creep",
                     "改动文件不在提交契约声明的 scope 内（疑似越界）",
                     f"将 {f} 的改动拆到独立 PR，或在 scope 中显式声明", rule_index)
            for f in sorted(files) if not _match_any(f, scope)]


def x_check_scope__mutmut_19(files, scope, rule_index):
    # 跳过模板占位符（以 '<' 开头，如未填的 pr.yaml 里 "<path/glob…>"）——
    # 与 check_tests 同构：占位符不算真实声明，否则会对每个文件刷假阳性 SCOPE-001。
    scope = [s for s in (scope or []) if s and not str(s).startswith("<")]
    if not scope:
        return []
    return [_finding("SCOPE-001", f, 0, "改动文件不在提交契约声明的 scope 内（疑似越界）",
                     f"将 {f} 的改动拆到独立 PR，或在 scope 中显式声明", rule_index)
            for f in sorted(files) if not _match_any(f, scope)]


def x_check_scope__mutmut_20(files, scope, rule_index):
    # 跳过模板占位符（以 '<' 开头，如未填的 pr.yaml 里 "<path/glob…>"）——
    # 与 check_tests 同构：占位符不算真实声明，否则会对每个文件刷假阳性 SCOPE-001。
    scope = [s for s in (scope or []) if s and not str(s).startswith("<")]
    if not scope:
        return []
    return [_finding("SCOPE-001", f, 0, "scope_creep",
                     f"将 {f} 的改动拆到独立 PR，或在 scope 中显式声明", rule_index)
            for f in sorted(files) if not _match_any(f, scope)]


def x_check_scope__mutmut_21(files, scope, rule_index):
    # 跳过模板占位符（以 '<' 开头，如未填的 pr.yaml 里 "<path/glob…>"）——
    # 与 check_tests 同构：占位符不算真实声明，否则会对每个文件刷假阳性 SCOPE-001。
    scope = [s for s in (scope or []) if s and not str(s).startswith("<")]
    if not scope:
        return []
    return [_finding("SCOPE-001", f, 0, "scope_creep",
                     "改动文件不在提交契约声明的 scope 内（疑似越界）",
                     rule_index)
            for f in sorted(files) if not _match_any(f, scope)]


def x_check_scope__mutmut_22(files, scope, rule_index):
    # 跳过模板占位符（以 '<' 开头，如未填的 pr.yaml 里 "<path/glob…>"）——
    # 与 check_tests 同构：占位符不算真实声明，否则会对每个文件刷假阳性 SCOPE-001。
    scope = [s for s in (scope or []) if s and not str(s).startswith("<")]
    if not scope:
        return []
    return [_finding("SCOPE-001", f, 0, "scope_creep",
                     "改动文件不在提交契约声明的 scope 内（疑似越界）",
                     f"将 {f} 的改动拆到独立 PR，或在 scope 中显式声明", )
            for f in sorted(files) if not _match_any(f, scope)]


def x_check_scope__mutmut_23(files, scope, rule_index):
    # 跳过模板占位符（以 '<' 开头，如未填的 pr.yaml 里 "<path/glob…>"）——
    # 与 check_tests 同构：占位符不算真实声明，否则会对每个文件刷假阳性 SCOPE-001。
    scope = [s for s in (scope or []) if s and not str(s).startswith("<")]
    if not scope:
        return []
    return [_finding("XXSCOPE-001XX", f, 0, "scope_creep",
                     "改动文件不在提交契约声明的 scope 内（疑似越界）",
                     f"将 {f} 的改动拆到独立 PR，或在 scope 中显式声明", rule_index)
            for f in sorted(files) if not _match_any(f, scope)]


def x_check_scope__mutmut_24(files, scope, rule_index):
    # 跳过模板占位符（以 '<' 开头，如未填的 pr.yaml 里 "<path/glob…>"）——
    # 与 check_tests 同构：占位符不算真实声明，否则会对每个文件刷假阳性 SCOPE-001。
    scope = [s for s in (scope or []) if s and not str(s).startswith("<")]
    if not scope:
        return []
    return [_finding("scope-001", f, 0, "scope_creep",
                     "改动文件不在提交契约声明的 scope 内（疑似越界）",
                     f"将 {f} 的改动拆到独立 PR，或在 scope 中显式声明", rule_index)
            for f in sorted(files) if not _match_any(f, scope)]


def x_check_scope__mutmut_25(files, scope, rule_index):
    # 跳过模板占位符（以 '<' 开头，如未填的 pr.yaml 里 "<path/glob…>"）——
    # 与 check_tests 同构：占位符不算真实声明，否则会对每个文件刷假阳性 SCOPE-001。
    scope = [s for s in (scope or []) if s and not str(s).startswith("<")]
    if not scope:
        return []
    return [_finding("SCOPE-001", f, 1, "scope_creep",
                     "改动文件不在提交契约声明的 scope 内（疑似越界）",
                     f"将 {f} 的改动拆到独立 PR，或在 scope 中显式声明", rule_index)
            for f in sorted(files) if not _match_any(f, scope)]


def x_check_scope__mutmut_26(files, scope, rule_index):
    # 跳过模板占位符（以 '<' 开头，如未填的 pr.yaml 里 "<path/glob…>"）——
    # 与 check_tests 同构：占位符不算真实声明，否则会对每个文件刷假阳性 SCOPE-001。
    scope = [s for s in (scope or []) if s and not str(s).startswith("<")]
    if not scope:
        return []
    return [_finding("SCOPE-001", f, 0, "XXscope_creepXX",
                     "改动文件不在提交契约声明的 scope 内（疑似越界）",
                     f"将 {f} 的改动拆到独立 PR，或在 scope 中显式声明", rule_index)
            for f in sorted(files) if not _match_any(f, scope)]


def x_check_scope__mutmut_27(files, scope, rule_index):
    # 跳过模板占位符（以 '<' 开头，如未填的 pr.yaml 里 "<path/glob…>"）——
    # 与 check_tests 同构：占位符不算真实声明，否则会对每个文件刷假阳性 SCOPE-001。
    scope = [s for s in (scope or []) if s and not str(s).startswith("<")]
    if not scope:
        return []
    return [_finding("SCOPE-001", f, 0, "SCOPE_CREEP",
                     "改动文件不在提交契约声明的 scope 内（疑似越界）",
                     f"将 {f} 的改动拆到独立 PR，或在 scope 中显式声明", rule_index)
            for f in sorted(files) if not _match_any(f, scope)]


def x_check_scope__mutmut_28(files, scope, rule_index):
    # 跳过模板占位符（以 '<' 开头，如未填的 pr.yaml 里 "<path/glob…>"）——
    # 与 check_tests 同构：占位符不算真实声明，否则会对每个文件刷假阳性 SCOPE-001。
    scope = [s for s in (scope or []) if s and not str(s).startswith("<")]
    if not scope:
        return []
    return [_finding("SCOPE-001", f, 0, "scope_creep",
                     "XX改动文件不在提交契约声明的 scope 内（疑似越界）XX",
                     f"将 {f} 的改动拆到独立 PR，或在 scope 中显式声明", rule_index)
            for f in sorted(files) if not _match_any(f, scope)]


def x_check_scope__mutmut_29(files, scope, rule_index):
    # 跳过模板占位符（以 '<' 开头，如未填的 pr.yaml 里 "<path/glob…>"）——
    # 与 check_tests 同构：占位符不算真实声明，否则会对每个文件刷假阳性 SCOPE-001。
    scope = [s for s in (scope or []) if s and not str(s).startswith("<")]
    if not scope:
        return []
    return [_finding("SCOPE-001", f, 0, "scope_creep",
                     "改动文件不在提交契约声明的 SCOPE 内（疑似越界）",
                     f"将 {f} 的改动拆到独立 PR，或在 scope 中显式声明", rule_index)
            for f in sorted(files) if not _match_any(f, scope)]


def x_check_scope__mutmut_30(files, scope, rule_index):
    # 跳过模板占位符（以 '<' 开头，如未填的 pr.yaml 里 "<path/glob…>"）——
    # 与 check_tests 同构：占位符不算真实声明，否则会对每个文件刷假阳性 SCOPE-001。
    scope = [s for s in (scope or []) if s and not str(s).startswith("<")]
    if not scope:
        return []
    return [_finding("SCOPE-001", f, 0, "scope_creep",
                     "改动文件不在提交契约声明的 scope 内（疑似越界）",
                     f"将 {f} 的改动拆到独立 PR，或在 scope 中显式声明", rule_index)
            for f in sorted(None) if not _match_any(f, scope)]


def x_check_scope__mutmut_31(files, scope, rule_index):
    # 跳过模板占位符（以 '<' 开头，如未填的 pr.yaml 里 "<path/glob…>"）——
    # 与 check_tests 同构：占位符不算真实声明，否则会对每个文件刷假阳性 SCOPE-001。
    scope = [s for s in (scope or []) if s and not str(s).startswith("<")]
    if not scope:
        return []
    return [_finding("SCOPE-001", f, 0, "scope_creep",
                     "改动文件不在提交契约声明的 scope 内（疑似越界）",
                     f"将 {f} 的改动拆到独立 PR，或在 scope 中显式声明", rule_index)
            for f in sorted(files) if _match_any(f, scope)]


def x_check_scope__mutmut_32(files, scope, rule_index):
    # 跳过模板占位符（以 '<' 开头，如未填的 pr.yaml 里 "<path/glob…>"）——
    # 与 check_tests 同构：占位符不算真实声明，否则会对每个文件刷假阳性 SCOPE-001。
    scope = [s for s in (scope or []) if s and not str(s).startswith("<")]
    if not scope:
        return []
    return [_finding("SCOPE-001", f, 0, "scope_creep",
                     "改动文件不在提交契约声明的 scope 内（疑似越界）",
                     f"将 {f} 的改动拆到独立 PR，或在 scope 中显式声明", rule_index)
            for f in sorted(files) if not _match_any(None, scope)]


def x_check_scope__mutmut_33(files, scope, rule_index):
    # 跳过模板占位符（以 '<' 开头，如未填的 pr.yaml 里 "<path/glob…>"）——
    # 与 check_tests 同构：占位符不算真实声明，否则会对每个文件刷假阳性 SCOPE-001。
    scope = [s for s in (scope or []) if s and not str(s).startswith("<")]
    if not scope:
        return []
    return [_finding("SCOPE-001", f, 0, "scope_creep",
                     "改动文件不在提交契约声明的 scope 内（疑似越界）",
                     f"将 {f} 的改动拆到独立 PR，或在 scope 中显式声明", rule_index)
            for f in sorted(files) if not _match_any(f, None)]


def x_check_scope__mutmut_34(files, scope, rule_index):
    # 跳过模板占位符（以 '<' 开头，如未填的 pr.yaml 里 "<path/glob…>"）——
    # 与 check_tests 同构：占位符不算真实声明，否则会对每个文件刷假阳性 SCOPE-001。
    scope = [s for s in (scope or []) if s and not str(s).startswith("<")]
    if not scope:
        return []
    return [_finding("SCOPE-001", f, 0, "scope_creep",
                     "改动文件不在提交契约声明的 scope 内（疑似越界）",
                     f"将 {f} 的改动拆到独立 PR，或在 scope 中显式声明", rule_index)
            for f in sorted(files) if not _match_any(scope)]


def x_check_scope__mutmut_35(files, scope, rule_index):
    # 跳过模板占位符（以 '<' 开头，如未填的 pr.yaml 里 "<path/glob…>"）——
    # 与 check_tests 同构：占位符不算真实声明，否则会对每个文件刷假阳性 SCOPE-001。
    scope = [s for s in (scope or []) if s and not str(s).startswith("<")]
    if not scope:
        return []
    return [_finding("SCOPE-001", f, 0, "scope_creep",
                     "改动文件不在提交契约声明的 scope 内（疑似越界）",
                     f"将 {f} 的改动拆到独立 PR，或在 scope 中显式声明", rule_index)
            for f in sorted(files) if not _match_any(f, )]

mutants_x_check_scope__mutmut['_mutmut_orig'] = x_check_scope__mutmut_orig # type: ignore # mutmut generated
mutants_x_check_scope__mutmut['x_check_scope__mutmut_1'] = x_check_scope__mutmut_1 # type: ignore # mutmut generated
mutants_x_check_scope__mutmut['x_check_scope__mutmut_2'] = x_check_scope__mutmut_2 # type: ignore # mutmut generated
mutants_x_check_scope__mutmut['x_check_scope__mutmut_3'] = x_check_scope__mutmut_3 # type: ignore # mutmut generated
mutants_x_check_scope__mutmut['x_check_scope__mutmut_4'] = x_check_scope__mutmut_4 # type: ignore # mutmut generated
mutants_x_check_scope__mutmut['x_check_scope__mutmut_5'] = x_check_scope__mutmut_5 # type: ignore # mutmut generated
mutants_x_check_scope__mutmut['x_check_scope__mutmut_6'] = x_check_scope__mutmut_6 # type: ignore # mutmut generated
mutants_x_check_scope__mutmut['x_check_scope__mutmut_7'] = x_check_scope__mutmut_7 # type: ignore # mutmut generated
mutants_x_check_scope__mutmut['x_check_scope__mutmut_8'] = x_check_scope__mutmut_8 # type: ignore # mutmut generated
mutants_x_check_scope__mutmut['x_check_scope__mutmut_9'] = x_check_scope__mutmut_9 # type: ignore # mutmut generated
mutants_x_check_scope__mutmut['x_check_scope__mutmut_10'] = x_check_scope__mutmut_10 # type: ignore # mutmut generated
mutants_x_check_scope__mutmut['x_check_scope__mutmut_11'] = x_check_scope__mutmut_11 # type: ignore # mutmut generated
mutants_x_check_scope__mutmut['x_check_scope__mutmut_12'] = x_check_scope__mutmut_12 # type: ignore # mutmut generated
mutants_x_check_scope__mutmut['x_check_scope__mutmut_13'] = x_check_scope__mutmut_13 # type: ignore # mutmut generated
mutants_x_check_scope__mutmut['x_check_scope__mutmut_14'] = x_check_scope__mutmut_14 # type: ignore # mutmut generated
mutants_x_check_scope__mutmut['x_check_scope__mutmut_15'] = x_check_scope__mutmut_15 # type: ignore # mutmut generated
mutants_x_check_scope__mutmut['x_check_scope__mutmut_16'] = x_check_scope__mutmut_16 # type: ignore # mutmut generated
mutants_x_check_scope__mutmut['x_check_scope__mutmut_17'] = x_check_scope__mutmut_17 # type: ignore # mutmut generated
mutants_x_check_scope__mutmut['x_check_scope__mutmut_18'] = x_check_scope__mutmut_18 # type: ignore # mutmut generated
mutants_x_check_scope__mutmut['x_check_scope__mutmut_19'] = x_check_scope__mutmut_19 # type: ignore # mutmut generated
mutants_x_check_scope__mutmut['x_check_scope__mutmut_20'] = x_check_scope__mutmut_20 # type: ignore # mutmut generated
mutants_x_check_scope__mutmut['x_check_scope__mutmut_21'] = x_check_scope__mutmut_21 # type: ignore # mutmut generated
mutants_x_check_scope__mutmut['x_check_scope__mutmut_22'] = x_check_scope__mutmut_22 # type: ignore # mutmut generated
mutants_x_check_scope__mutmut['x_check_scope__mutmut_23'] = x_check_scope__mutmut_23 # type: ignore # mutmut generated
mutants_x_check_scope__mutmut['x_check_scope__mutmut_24'] = x_check_scope__mutmut_24 # type: ignore # mutmut generated
mutants_x_check_scope__mutmut['x_check_scope__mutmut_25'] = x_check_scope__mutmut_25 # type: ignore # mutmut generated
mutants_x_check_scope__mutmut['x_check_scope__mutmut_26'] = x_check_scope__mutmut_26 # type: ignore # mutmut generated
mutants_x_check_scope__mutmut['x_check_scope__mutmut_27'] = x_check_scope__mutmut_27 # type: ignore # mutmut generated
mutants_x_check_scope__mutmut['x_check_scope__mutmut_28'] = x_check_scope__mutmut_28 # type: ignore # mutmut generated
mutants_x_check_scope__mutmut['x_check_scope__mutmut_29'] = x_check_scope__mutmut_29 # type: ignore # mutmut generated
mutants_x_check_scope__mutmut['x_check_scope__mutmut_30'] = x_check_scope__mutmut_30 # type: ignore # mutmut generated
mutants_x_check_scope__mutmut['x_check_scope__mutmut_31'] = x_check_scope__mutmut_31 # type: ignore # mutmut generated
mutants_x_check_scope__mutmut['x_check_scope__mutmut_32'] = x_check_scope__mutmut_32 # type: ignore # mutmut generated
mutants_x_check_scope__mutmut['x_check_scope__mutmut_33'] = x_check_scope__mutmut_33 # type: ignore # mutmut generated
mutants_x_check_scope__mutmut['x_check_scope__mutmut_34'] = x_check_scope__mutmut_34 # type: ignore # mutmut generated
mutants_x_check_scope__mutmut['x_check_scope__mutmut_35'] = x_check_scope__mutmut_35 # type: ignore # mutmut generated
mutants_x_check_tests__mutmut: MutantDict = {}  # type: ignore


@_mutmut_mutated(mutants_x_check_tests__mutmut)
def check_tests(files, tests_added, rule_index):
    claimed = [t for t in (tests_added or []) if t and not str(t).startswith("<")]
    if not claimed:
        return []
    test_files = {f for f in files if "test" in f.lower() or "spec" in f.lower()}
    if not test_files:
        return [_finding("TEST-001", claimed[0], 0, "weak_test",
                         "提交契约声称新增测试，但 diff 中无测试文件改动（申报不实）",
                         "实际补充有意义断言的测试，或如实更新 tests_added", rule_index)]
    return []


def x_check_tests__mutmut_orig(files, tests_added, rule_index):
    claimed = [t for t in (tests_added or []) if t and not str(t).startswith("<")]
    if not claimed:
        return []
    test_files = {f for f in files if "test" in f.lower() or "spec" in f.lower()}
    if not test_files:
        return [_finding("TEST-001", claimed[0], 0, "weak_test",
                         "提交契约声称新增测试，但 diff 中无测试文件改动（申报不实）",
                         "实际补充有意义断言的测试，或如实更新 tests_added", rule_index)]
    return []


def x_check_tests__mutmut_1(files, tests_added, rule_index):
    claimed = None
    if not claimed:
        return []
    test_files = {f for f in files if "test" in f.lower() or "spec" in f.lower()}
    if not test_files:
        return [_finding("TEST-001", claimed[0], 0, "weak_test",
                         "提交契约声称新增测试，但 diff 中无测试文件改动（申报不实）",
                         "实际补充有意义断言的测试，或如实更新 tests_added", rule_index)]
    return []


def x_check_tests__mutmut_2(files, tests_added, rule_index):
    claimed = [t for t in (tests_added and []) if t and not str(t).startswith("<")]
    if not claimed:
        return []
    test_files = {f for f in files if "test" in f.lower() or "spec" in f.lower()}
    if not test_files:
        return [_finding("TEST-001", claimed[0], 0, "weak_test",
                         "提交契约声称新增测试，但 diff 中无测试文件改动（申报不实）",
                         "实际补充有意义断言的测试，或如实更新 tests_added", rule_index)]
    return []


def x_check_tests__mutmut_3(files, tests_added, rule_index):
    claimed = [t for t in (tests_added or []) if t or not str(t).startswith("<")]
    if not claimed:
        return []
    test_files = {f for f in files if "test" in f.lower() or "spec" in f.lower()}
    if not test_files:
        return [_finding("TEST-001", claimed[0], 0, "weak_test",
                         "提交契约声称新增测试，但 diff 中无测试文件改动（申报不实）",
                         "实际补充有意义断言的测试，或如实更新 tests_added", rule_index)]
    return []


def x_check_tests__mutmut_4(files, tests_added, rule_index):
    claimed = [t for t in (tests_added or []) if t and str(t).startswith("<")]
    if not claimed:
        return []
    test_files = {f for f in files if "test" in f.lower() or "spec" in f.lower()}
    if not test_files:
        return [_finding("TEST-001", claimed[0], 0, "weak_test",
                         "提交契约声称新增测试，但 diff 中无测试文件改动（申报不实）",
                         "实际补充有意义断言的测试，或如实更新 tests_added", rule_index)]
    return []


def x_check_tests__mutmut_5(files, tests_added, rule_index):
    claimed = [t for t in (tests_added or []) if t and not str(t).startswith(None)]
    if not claimed:
        return []
    test_files = {f for f in files if "test" in f.lower() or "spec" in f.lower()}
    if not test_files:
        return [_finding("TEST-001", claimed[0], 0, "weak_test",
                         "提交契约声称新增测试，但 diff 中无测试文件改动（申报不实）",
                         "实际补充有意义断言的测试，或如实更新 tests_added", rule_index)]
    return []


def x_check_tests__mutmut_6(files, tests_added, rule_index):
    claimed = [t for t in (tests_added or []) if t and not str(None).startswith("<")]
    if not claimed:
        return []
    test_files = {f for f in files if "test" in f.lower() or "spec" in f.lower()}
    if not test_files:
        return [_finding("TEST-001", claimed[0], 0, "weak_test",
                         "提交契约声称新增测试，但 diff 中无测试文件改动（申报不实）",
                         "实际补充有意义断言的测试，或如实更新 tests_added", rule_index)]
    return []


def x_check_tests__mutmut_7(files, tests_added, rule_index):
    claimed = [t for t in (tests_added or []) if t and not str(t).startswith("XX<XX")]
    if not claimed:
        return []
    test_files = {f for f in files if "test" in f.lower() or "spec" in f.lower()}
    if not test_files:
        return [_finding("TEST-001", claimed[0], 0, "weak_test",
                         "提交契约声称新增测试，但 diff 中无测试文件改动（申报不实）",
                         "实际补充有意义断言的测试，或如实更新 tests_added", rule_index)]
    return []


def x_check_tests__mutmut_8(files, tests_added, rule_index):
    claimed = [t for t in (tests_added or []) if t and not str(t).startswith("<")]
    if claimed:
        return []
    test_files = {f for f in files if "test" in f.lower() or "spec" in f.lower()}
    if not test_files:
        return [_finding("TEST-001", claimed[0], 0, "weak_test",
                         "提交契约声称新增测试，但 diff 中无测试文件改动（申报不实）",
                         "实际补充有意义断言的测试，或如实更新 tests_added", rule_index)]
    return []


def x_check_tests__mutmut_9(files, tests_added, rule_index):
    claimed = [t for t in (tests_added or []) if t and not str(t).startswith("<")]
    if not claimed:
        return []
    test_files = None
    if not test_files:
        return [_finding("TEST-001", claimed[0], 0, "weak_test",
                         "提交契约声称新增测试，但 diff 中无测试文件改动（申报不实）",
                         "实际补充有意义断言的测试，或如实更新 tests_added", rule_index)]
    return []


def x_check_tests__mutmut_10(files, tests_added, rule_index):
    claimed = [t for t in (tests_added or []) if t and not str(t).startswith("<")]
    if not claimed:
        return []
    test_files = {f for f in files if "test" in f.lower() and "spec" in f.lower()}
    if not test_files:
        return [_finding("TEST-001", claimed[0], 0, "weak_test",
                         "提交契约声称新增测试，但 diff 中无测试文件改动（申报不实）",
                         "实际补充有意义断言的测试，或如实更新 tests_added", rule_index)]
    return []


def x_check_tests__mutmut_11(files, tests_added, rule_index):
    claimed = [t for t in (tests_added or []) if t and not str(t).startswith("<")]
    if not claimed:
        return []
    test_files = {f for f in files if "XXtestXX" in f.lower() or "spec" in f.lower()}
    if not test_files:
        return [_finding("TEST-001", claimed[0], 0, "weak_test",
                         "提交契约声称新增测试，但 diff 中无测试文件改动（申报不实）",
                         "实际补充有意义断言的测试，或如实更新 tests_added", rule_index)]
    return []


def x_check_tests__mutmut_12(files, tests_added, rule_index):
    claimed = [t for t in (tests_added or []) if t and not str(t).startswith("<")]
    if not claimed:
        return []
    test_files = {f for f in files if "TEST" in f.lower() or "spec" in f.lower()}
    if not test_files:
        return [_finding("TEST-001", claimed[0], 0, "weak_test",
                         "提交契约声称新增测试，但 diff 中无测试文件改动（申报不实）",
                         "实际补充有意义断言的测试，或如实更新 tests_added", rule_index)]
    return []


def x_check_tests__mutmut_13(files, tests_added, rule_index):
    claimed = [t for t in (tests_added or []) if t and not str(t).startswith("<")]
    if not claimed:
        return []
    test_files = {f for f in files if "test" not in f.lower() or "spec" in f.lower()}
    if not test_files:
        return [_finding("TEST-001", claimed[0], 0, "weak_test",
                         "提交契约声称新增测试，但 diff 中无测试文件改动（申报不实）",
                         "实际补充有意义断言的测试，或如实更新 tests_added", rule_index)]
    return []


def x_check_tests__mutmut_14(files, tests_added, rule_index):
    claimed = [t for t in (tests_added or []) if t and not str(t).startswith("<")]
    if not claimed:
        return []
    test_files = {f for f in files if "test" in f.upper() or "spec" in f.lower()}
    if not test_files:
        return [_finding("TEST-001", claimed[0], 0, "weak_test",
                         "提交契约声称新增测试，但 diff 中无测试文件改动（申报不实）",
                         "实际补充有意义断言的测试，或如实更新 tests_added", rule_index)]
    return []


def x_check_tests__mutmut_15(files, tests_added, rule_index):
    claimed = [t for t in (tests_added or []) if t and not str(t).startswith("<")]
    if not claimed:
        return []
    test_files = {f for f in files if "test" in f.lower() or "XXspecXX" in f.lower()}
    if not test_files:
        return [_finding("TEST-001", claimed[0], 0, "weak_test",
                         "提交契约声称新增测试，但 diff 中无测试文件改动（申报不实）",
                         "实际补充有意义断言的测试，或如实更新 tests_added", rule_index)]
    return []


def x_check_tests__mutmut_16(files, tests_added, rule_index):
    claimed = [t for t in (tests_added or []) if t and not str(t).startswith("<")]
    if not claimed:
        return []
    test_files = {f for f in files if "test" in f.lower() or "SPEC" in f.lower()}
    if not test_files:
        return [_finding("TEST-001", claimed[0], 0, "weak_test",
                         "提交契约声称新增测试，但 diff 中无测试文件改动（申报不实）",
                         "实际补充有意义断言的测试，或如实更新 tests_added", rule_index)]
    return []


def x_check_tests__mutmut_17(files, tests_added, rule_index):
    claimed = [t for t in (tests_added or []) if t and not str(t).startswith("<")]
    if not claimed:
        return []
    test_files = {f for f in files if "test" in f.lower() or "spec" not in f.lower()}
    if not test_files:
        return [_finding("TEST-001", claimed[0], 0, "weak_test",
                         "提交契约声称新增测试，但 diff 中无测试文件改动（申报不实）",
                         "实际补充有意义断言的测试，或如实更新 tests_added", rule_index)]
    return []


def x_check_tests__mutmut_18(files, tests_added, rule_index):
    claimed = [t for t in (tests_added or []) if t and not str(t).startswith("<")]
    if not claimed:
        return []
    test_files = {f for f in files if "test" in f.lower() or "spec" in f.upper()}
    if not test_files:
        return [_finding("TEST-001", claimed[0], 0, "weak_test",
                         "提交契约声称新增测试，但 diff 中无测试文件改动（申报不实）",
                         "实际补充有意义断言的测试，或如实更新 tests_added", rule_index)]
    return []


def x_check_tests__mutmut_19(files, tests_added, rule_index):
    claimed = [t for t in (tests_added or []) if t and not str(t).startswith("<")]
    if not claimed:
        return []
    test_files = {f for f in files if "test" in f.lower() or "spec" in f.lower()}
    if test_files:
        return [_finding("TEST-001", claimed[0], 0, "weak_test",
                         "提交契约声称新增测试，但 diff 中无测试文件改动（申报不实）",
                         "实际补充有意义断言的测试，或如实更新 tests_added", rule_index)]
    return []


def x_check_tests__mutmut_20(files, tests_added, rule_index):
    claimed = [t for t in (tests_added or []) if t and not str(t).startswith("<")]
    if not claimed:
        return []
    test_files = {f for f in files if "test" in f.lower() or "spec" in f.lower()}
    if not test_files:
        return [_finding(None, claimed[0], 0, "weak_test",
                         "提交契约声称新增测试，但 diff 中无测试文件改动（申报不实）",
                         "实际补充有意义断言的测试，或如实更新 tests_added", rule_index)]
    return []


def x_check_tests__mutmut_21(files, tests_added, rule_index):
    claimed = [t for t in (tests_added or []) if t and not str(t).startswith("<")]
    if not claimed:
        return []
    test_files = {f for f in files if "test" in f.lower() or "spec" in f.lower()}
    if not test_files:
        return [_finding("TEST-001", None, 0, "weak_test",
                         "提交契约声称新增测试，但 diff 中无测试文件改动（申报不实）",
                         "实际补充有意义断言的测试，或如实更新 tests_added", rule_index)]
    return []


def x_check_tests__mutmut_22(files, tests_added, rule_index):
    claimed = [t for t in (tests_added or []) if t and not str(t).startswith("<")]
    if not claimed:
        return []
    test_files = {f for f in files if "test" in f.lower() or "spec" in f.lower()}
    if not test_files:
        return [_finding("TEST-001", claimed[0], None, "weak_test",
                         "提交契约声称新增测试，但 diff 中无测试文件改动（申报不实）",
                         "实际补充有意义断言的测试，或如实更新 tests_added", rule_index)]
    return []


def x_check_tests__mutmut_23(files, tests_added, rule_index):
    claimed = [t for t in (tests_added or []) if t and not str(t).startswith("<")]
    if not claimed:
        return []
    test_files = {f for f in files if "test" in f.lower() or "spec" in f.lower()}
    if not test_files:
        return [_finding("TEST-001", claimed[0], 0, None,
                         "提交契约声称新增测试，但 diff 中无测试文件改动（申报不实）",
                         "实际补充有意义断言的测试，或如实更新 tests_added", rule_index)]
    return []


def x_check_tests__mutmut_24(files, tests_added, rule_index):
    claimed = [t for t in (tests_added or []) if t and not str(t).startswith("<")]
    if not claimed:
        return []
    test_files = {f for f in files if "test" in f.lower() or "spec" in f.lower()}
    if not test_files:
        return [_finding("TEST-001", claimed[0], 0, "weak_test",
                         None,
                         "实际补充有意义断言的测试，或如实更新 tests_added", rule_index)]
    return []


def x_check_tests__mutmut_25(files, tests_added, rule_index):
    claimed = [t for t in (tests_added or []) if t and not str(t).startswith("<")]
    if not claimed:
        return []
    test_files = {f for f in files if "test" in f.lower() or "spec" in f.lower()}
    if not test_files:
        return [_finding("TEST-001", claimed[0], 0, "weak_test",
                         "提交契约声称新增测试，但 diff 中无测试文件改动（申报不实）",
                         None, rule_index)]
    return []


def x_check_tests__mutmut_26(files, tests_added, rule_index):
    claimed = [t for t in (tests_added or []) if t and not str(t).startswith("<")]
    if not claimed:
        return []
    test_files = {f for f in files if "test" in f.lower() or "spec" in f.lower()}
    if not test_files:
        return [_finding("TEST-001", claimed[0], 0, "weak_test",
                         "提交契约声称新增测试，但 diff 中无测试文件改动（申报不实）",
                         "实际补充有意义断言的测试，或如实更新 tests_added", None)]
    return []


def x_check_tests__mutmut_27(files, tests_added, rule_index):
    claimed = [t for t in (tests_added or []) if t and not str(t).startswith("<")]
    if not claimed:
        return []
    test_files = {f for f in files if "test" in f.lower() or "spec" in f.lower()}
    if not test_files:
        return [_finding(claimed[0], 0, "weak_test",
                         "提交契约声称新增测试，但 diff 中无测试文件改动（申报不实）",
                         "实际补充有意义断言的测试，或如实更新 tests_added", rule_index)]
    return []


def x_check_tests__mutmut_28(files, tests_added, rule_index):
    claimed = [t for t in (tests_added or []) if t and not str(t).startswith("<")]
    if not claimed:
        return []
    test_files = {f for f in files if "test" in f.lower() or "spec" in f.lower()}
    if not test_files:
        return [_finding("TEST-001", 0, "weak_test",
                         "提交契约声称新增测试，但 diff 中无测试文件改动（申报不实）",
                         "实际补充有意义断言的测试，或如实更新 tests_added", rule_index)]
    return []


def x_check_tests__mutmut_29(files, tests_added, rule_index):
    claimed = [t for t in (tests_added or []) if t and not str(t).startswith("<")]
    if not claimed:
        return []
    test_files = {f for f in files if "test" in f.lower() or "spec" in f.lower()}
    if not test_files:
        return [_finding("TEST-001", claimed[0], "weak_test",
                         "提交契约声称新增测试，但 diff 中无测试文件改动（申报不实）",
                         "实际补充有意义断言的测试，或如实更新 tests_added", rule_index)]
    return []


def x_check_tests__mutmut_30(files, tests_added, rule_index):
    claimed = [t for t in (tests_added or []) if t and not str(t).startswith("<")]
    if not claimed:
        return []
    test_files = {f for f in files if "test" in f.lower() or "spec" in f.lower()}
    if not test_files:
        return [_finding("TEST-001", claimed[0], 0, "提交契约声称新增测试，但 diff 中无测试文件改动（申报不实）",
                         "实际补充有意义断言的测试，或如实更新 tests_added", rule_index)]
    return []


def x_check_tests__mutmut_31(files, tests_added, rule_index):
    claimed = [t for t in (tests_added or []) if t and not str(t).startswith("<")]
    if not claimed:
        return []
    test_files = {f for f in files if "test" in f.lower() or "spec" in f.lower()}
    if not test_files:
        return [_finding("TEST-001", claimed[0], 0, "weak_test",
                         "实际补充有意义断言的测试，或如实更新 tests_added", rule_index)]
    return []


def x_check_tests__mutmut_32(files, tests_added, rule_index):
    claimed = [t for t in (tests_added or []) if t and not str(t).startswith("<")]
    if not claimed:
        return []
    test_files = {f for f in files if "test" in f.lower() or "spec" in f.lower()}
    if not test_files:
        return [_finding("TEST-001", claimed[0], 0, "weak_test",
                         "提交契约声称新增测试，但 diff 中无测试文件改动（申报不实）",
                         rule_index)]
    return []


def x_check_tests__mutmut_33(files, tests_added, rule_index):
    claimed = [t for t in (tests_added or []) if t and not str(t).startswith("<")]
    if not claimed:
        return []
    test_files = {f for f in files if "test" in f.lower() or "spec" in f.lower()}
    if not test_files:
        return [_finding("TEST-001", claimed[0], 0, "weak_test",
                         "提交契约声称新增测试，但 diff 中无测试文件改动（申报不实）",
                         "实际补充有意义断言的测试，或如实更新 tests_added", )]
    return []


def x_check_tests__mutmut_34(files, tests_added, rule_index):
    claimed = [t for t in (tests_added or []) if t and not str(t).startswith("<")]
    if not claimed:
        return []
    test_files = {f for f in files if "test" in f.lower() or "spec" in f.lower()}
    if not test_files:
        return [_finding("XXTEST-001XX", claimed[0], 0, "weak_test",
                         "提交契约声称新增测试，但 diff 中无测试文件改动（申报不实）",
                         "实际补充有意义断言的测试，或如实更新 tests_added", rule_index)]
    return []


def x_check_tests__mutmut_35(files, tests_added, rule_index):
    claimed = [t for t in (tests_added or []) if t and not str(t).startswith("<")]
    if not claimed:
        return []
    test_files = {f for f in files if "test" in f.lower() or "spec" in f.lower()}
    if not test_files:
        return [_finding("test-001", claimed[0], 0, "weak_test",
                         "提交契约声称新增测试，但 diff 中无测试文件改动（申报不实）",
                         "实际补充有意义断言的测试，或如实更新 tests_added", rule_index)]
    return []


def x_check_tests__mutmut_36(files, tests_added, rule_index):
    claimed = [t for t in (tests_added or []) if t and not str(t).startswith("<")]
    if not claimed:
        return []
    test_files = {f for f in files if "test" in f.lower() or "spec" in f.lower()}
    if not test_files:
        return [_finding("TEST-001", claimed[1], 0, "weak_test",
                         "提交契约声称新增测试，但 diff 中无测试文件改动（申报不实）",
                         "实际补充有意义断言的测试，或如实更新 tests_added", rule_index)]
    return []


def x_check_tests__mutmut_37(files, tests_added, rule_index):
    claimed = [t for t in (tests_added or []) if t and not str(t).startswith("<")]
    if not claimed:
        return []
    test_files = {f for f in files if "test" in f.lower() or "spec" in f.lower()}
    if not test_files:
        return [_finding("TEST-001", claimed[0], 1, "weak_test",
                         "提交契约声称新增测试，但 diff 中无测试文件改动（申报不实）",
                         "实际补充有意义断言的测试，或如实更新 tests_added", rule_index)]
    return []


def x_check_tests__mutmut_38(files, tests_added, rule_index):
    claimed = [t for t in (tests_added or []) if t and not str(t).startswith("<")]
    if not claimed:
        return []
    test_files = {f for f in files if "test" in f.lower() or "spec" in f.lower()}
    if not test_files:
        return [_finding("TEST-001", claimed[0], 0, "XXweak_testXX",
                         "提交契约声称新增测试，但 diff 中无测试文件改动（申报不实）",
                         "实际补充有意义断言的测试，或如实更新 tests_added", rule_index)]
    return []


def x_check_tests__mutmut_39(files, tests_added, rule_index):
    claimed = [t for t in (tests_added or []) if t and not str(t).startswith("<")]
    if not claimed:
        return []
    test_files = {f for f in files if "test" in f.lower() or "spec" in f.lower()}
    if not test_files:
        return [_finding("TEST-001", claimed[0], 0, "WEAK_TEST",
                         "提交契约声称新增测试，但 diff 中无测试文件改动（申报不实）",
                         "实际补充有意义断言的测试，或如实更新 tests_added", rule_index)]
    return []


def x_check_tests__mutmut_40(files, tests_added, rule_index):
    claimed = [t for t in (tests_added or []) if t and not str(t).startswith("<")]
    if not claimed:
        return []
    test_files = {f for f in files if "test" in f.lower() or "spec" in f.lower()}
    if not test_files:
        return [_finding("TEST-001", claimed[0], 0, "weak_test",
                         "XX提交契约声称新增测试，但 diff 中无测试文件改动（申报不实）XX",
                         "实际补充有意义断言的测试，或如实更新 tests_added", rule_index)]
    return []


def x_check_tests__mutmut_41(files, tests_added, rule_index):
    claimed = [t for t in (tests_added or []) if t and not str(t).startswith("<")]
    if not claimed:
        return []
    test_files = {f for f in files if "test" in f.lower() or "spec" in f.lower()}
    if not test_files:
        return [_finding("TEST-001", claimed[0], 0, "weak_test",
                         "提交契约声称新增测试，但 DIFF 中无测试文件改动（申报不实）",
                         "实际补充有意义断言的测试，或如实更新 tests_added", rule_index)]
    return []


def x_check_tests__mutmut_42(files, tests_added, rule_index):
    claimed = [t for t in (tests_added or []) if t and not str(t).startswith("<")]
    if not claimed:
        return []
    test_files = {f for f in files if "test" in f.lower() or "spec" in f.lower()}
    if not test_files:
        return [_finding("TEST-001", claimed[0], 0, "weak_test",
                         "提交契约声称新增测试，但 diff 中无测试文件改动（申报不实）",
                         "XX实际补充有意义断言的测试，或如实更新 tests_addedXX", rule_index)]
    return []


def x_check_tests__mutmut_43(files, tests_added, rule_index):
    claimed = [t for t in (tests_added or []) if t and not str(t).startswith("<")]
    if not claimed:
        return []
    test_files = {f for f in files if "test" in f.lower() or "spec" in f.lower()}
    if not test_files:
        return [_finding("TEST-001", claimed[0], 0, "weak_test",
                         "提交契约声称新增测试，但 diff 中无测试文件改动（申报不实）",
                         "实际补充有意义断言的测试，或如实更新 TESTS_ADDED", rule_index)]
    return []

mutants_x_check_tests__mutmut['_mutmut_orig'] = x_check_tests__mutmut_orig # type: ignore # mutmut generated
mutants_x_check_tests__mutmut['x_check_tests__mutmut_1'] = x_check_tests__mutmut_1 # type: ignore # mutmut generated
mutants_x_check_tests__mutmut['x_check_tests__mutmut_2'] = x_check_tests__mutmut_2 # type: ignore # mutmut generated
mutants_x_check_tests__mutmut['x_check_tests__mutmut_3'] = x_check_tests__mutmut_3 # type: ignore # mutmut generated
mutants_x_check_tests__mutmut['x_check_tests__mutmut_4'] = x_check_tests__mutmut_4 # type: ignore # mutmut generated
mutants_x_check_tests__mutmut['x_check_tests__mutmut_5'] = x_check_tests__mutmut_5 # type: ignore # mutmut generated
mutants_x_check_tests__mutmut['x_check_tests__mutmut_6'] = x_check_tests__mutmut_6 # type: ignore # mutmut generated
mutants_x_check_tests__mutmut['x_check_tests__mutmut_7'] = x_check_tests__mutmut_7 # type: ignore # mutmut generated
mutants_x_check_tests__mutmut['x_check_tests__mutmut_8'] = x_check_tests__mutmut_8 # type: ignore # mutmut generated
mutants_x_check_tests__mutmut['x_check_tests__mutmut_9'] = x_check_tests__mutmut_9 # type: ignore # mutmut generated
mutants_x_check_tests__mutmut['x_check_tests__mutmut_10'] = x_check_tests__mutmut_10 # type: ignore # mutmut generated
mutants_x_check_tests__mutmut['x_check_tests__mutmut_11'] = x_check_tests__mutmut_11 # type: ignore # mutmut generated
mutants_x_check_tests__mutmut['x_check_tests__mutmut_12'] = x_check_tests__mutmut_12 # type: ignore # mutmut generated
mutants_x_check_tests__mutmut['x_check_tests__mutmut_13'] = x_check_tests__mutmut_13 # type: ignore # mutmut generated
mutants_x_check_tests__mutmut['x_check_tests__mutmut_14'] = x_check_tests__mutmut_14 # type: ignore # mutmut generated
mutants_x_check_tests__mutmut['x_check_tests__mutmut_15'] = x_check_tests__mutmut_15 # type: ignore # mutmut generated
mutants_x_check_tests__mutmut['x_check_tests__mutmut_16'] = x_check_tests__mutmut_16 # type: ignore # mutmut generated
mutants_x_check_tests__mutmut['x_check_tests__mutmut_17'] = x_check_tests__mutmut_17 # type: ignore # mutmut generated
mutants_x_check_tests__mutmut['x_check_tests__mutmut_18'] = x_check_tests__mutmut_18 # type: ignore # mutmut generated
mutants_x_check_tests__mutmut['x_check_tests__mutmut_19'] = x_check_tests__mutmut_19 # type: ignore # mutmut generated
mutants_x_check_tests__mutmut['x_check_tests__mutmut_20'] = x_check_tests__mutmut_20 # type: ignore # mutmut generated
mutants_x_check_tests__mutmut['x_check_tests__mutmut_21'] = x_check_tests__mutmut_21 # type: ignore # mutmut generated
mutants_x_check_tests__mutmut['x_check_tests__mutmut_22'] = x_check_tests__mutmut_22 # type: ignore # mutmut generated
mutants_x_check_tests__mutmut['x_check_tests__mutmut_23'] = x_check_tests__mutmut_23 # type: ignore # mutmut generated
mutants_x_check_tests__mutmut['x_check_tests__mutmut_24'] = x_check_tests__mutmut_24 # type: ignore # mutmut generated
mutants_x_check_tests__mutmut['x_check_tests__mutmut_25'] = x_check_tests__mutmut_25 # type: ignore # mutmut generated
mutants_x_check_tests__mutmut['x_check_tests__mutmut_26'] = x_check_tests__mutmut_26 # type: ignore # mutmut generated
mutants_x_check_tests__mutmut['x_check_tests__mutmut_27'] = x_check_tests__mutmut_27 # type: ignore # mutmut generated
mutants_x_check_tests__mutmut['x_check_tests__mutmut_28'] = x_check_tests__mutmut_28 # type: ignore # mutmut generated
mutants_x_check_tests__mutmut['x_check_tests__mutmut_29'] = x_check_tests__mutmut_29 # type: ignore # mutmut generated
mutants_x_check_tests__mutmut['x_check_tests__mutmut_30'] = x_check_tests__mutmut_30 # type: ignore # mutmut generated
mutants_x_check_tests__mutmut['x_check_tests__mutmut_31'] = x_check_tests__mutmut_31 # type: ignore # mutmut generated
mutants_x_check_tests__mutmut['x_check_tests__mutmut_32'] = x_check_tests__mutmut_32 # type: ignore # mutmut generated
mutants_x_check_tests__mutmut['x_check_tests__mutmut_33'] = x_check_tests__mutmut_33 # type: ignore # mutmut generated
mutants_x_check_tests__mutmut['x_check_tests__mutmut_34'] = x_check_tests__mutmut_34 # type: ignore # mutmut generated
mutants_x_check_tests__mutmut['x_check_tests__mutmut_35'] = x_check_tests__mutmut_35 # type: ignore # mutmut generated
mutants_x_check_tests__mutmut['x_check_tests__mutmut_36'] = x_check_tests__mutmut_36 # type: ignore # mutmut generated
mutants_x_check_tests__mutmut['x_check_tests__mutmut_37'] = x_check_tests__mutmut_37 # type: ignore # mutmut generated
mutants_x_check_tests__mutmut['x_check_tests__mutmut_38'] = x_check_tests__mutmut_38 # type: ignore # mutmut generated
mutants_x_check_tests__mutmut['x_check_tests__mutmut_39'] = x_check_tests__mutmut_39 # type: ignore # mutmut generated
mutants_x_check_tests__mutmut['x_check_tests__mutmut_40'] = x_check_tests__mutmut_40 # type: ignore # mutmut generated
mutants_x_check_tests__mutmut['x_check_tests__mutmut_41'] = x_check_tests__mutmut_41 # type: ignore # mutmut generated
mutants_x_check_tests__mutmut['x_check_tests__mutmut_42'] = x_check_tests__mutmut_42 # type: ignore # mutmut generated
mutants_x_check_tests__mutmut['x_check_tests__mutmut_43'] = x_check_tests__mutmut_43 # type: ignore # mutmut generated
mutants_x__identifiers__mutmut: MutantDict = {}  # type: ignore


@_mutmut_mutated(mutants_x__identifiers__mutmut)
def _identifiers(text):
    """从代码文本抽出标识符集合：完整点链 + 叶子名。供精确成员匹配（非子串）。"""
    out = set()
    for t in re.findall(r"[A-Za-z_][A-Za-z0-9_.]+", text):
        out.add(t)
        out.add(t.split(".")[-1])
    return out


def x__identifiers__mutmut_orig(text):
    """从代码文本抽出标识符集合：完整点链 + 叶子名。供精确成员匹配（非子串）。"""
    out = set()
    for t in re.findall(r"[A-Za-z_][A-Za-z0-9_.]+", text):
        out.add(t)
        out.add(t.split(".")[-1])
    return out


def x__identifiers__mutmut_1(text):
    """从代码文本抽出标识符集合：完整点链 + 叶子名。供精确成员匹配（非子串）。"""
    out = None
    for t in re.findall(r"[A-Za-z_][A-Za-z0-9_.]+", text):
        out.add(t)
        out.add(t.split(".")[-1])
    return out


def x__identifiers__mutmut_2(text):
    """从代码文本抽出标识符集合：完整点链 + 叶子名。供精确成员匹配（非子串）。"""
    out = set()
    for t in re.findall(None, text):
        out.add(t)
        out.add(t.split(".")[-1])
    return out


def x__identifiers__mutmut_3(text):
    """从代码文本抽出标识符集合：完整点链 + 叶子名。供精确成员匹配（非子串）。"""
    out = set()
    for t in re.findall(r"[A-Za-z_][A-Za-z0-9_.]+", None):
        out.add(t)
        out.add(t.split(".")[-1])
    return out


def x__identifiers__mutmut_4(text):
    """从代码文本抽出标识符集合：完整点链 + 叶子名。供精确成员匹配（非子串）。"""
    out = set()
    for t in re.findall(text):
        out.add(t)
        out.add(t.split(".")[-1])
    return out


def x__identifiers__mutmut_5(text):
    """从代码文本抽出标识符集合：完整点链 + 叶子名。供精确成员匹配（非子串）。"""
    out = set()
    for t in re.findall(r"[A-Za-z_][A-Za-z0-9_.]+", ):
        out.add(t)
        out.add(t.split(".")[-1])
    return out


def x__identifiers__mutmut_6(text):
    """从代码文本抽出标识符集合：完整点链 + 叶子名。供精确成员匹配（非子串）。"""
    out = set()
    for t in re.findall(r"XX[A-Za-z_][A-Za-z0-9_.]+XX", text):
        out.add(t)
        out.add(t.split(".")[-1])
    return out


def x__identifiers__mutmut_7(text):
    """从代码文本抽出标识符集合：完整点链 + 叶子名。供精确成员匹配（非子串）。"""
    out = set()
    for t in re.findall(r"[a-za-z_][a-za-z0-9_.]+", text):
        out.add(t)
        out.add(t.split(".")[-1])
    return out


def x__identifiers__mutmut_8(text):
    """从代码文本抽出标识符集合：完整点链 + 叶子名。供精确成员匹配（非子串）。"""
    out = set()
    for t in re.findall(r"[A-ZA-Z_][A-ZA-Z0-9_.]+", text):
        out.add(t)
        out.add(t.split(".")[-1])
    return out


def x__identifiers__mutmut_9(text):
    """从代码文本抽出标识符集合：完整点链 + 叶子名。供精确成员匹配（非子串）。"""
    out = set()
    for t in re.findall(r"[A-Za-z_][A-Za-z0-9_.]+", text):
        out.add(None)
        out.add(t.split(".")[-1])
    return out


def x__identifiers__mutmut_10(text):
    """从代码文本抽出标识符集合：完整点链 + 叶子名。供精确成员匹配（非子串）。"""
    out = set()
    for t in re.findall(r"[A-Za-z_][A-Za-z0-9_.]+", text):
        out.add(t)
        out.add(None)
    return out


def x__identifiers__mutmut_11(text):
    """从代码文本抽出标识符集合：完整点链 + 叶子名。供精确成员匹配（非子串）。"""
    out = set()
    for t in re.findall(r"[A-Za-z_][A-Za-z0-9_.]+", text):
        out.add(t)
        out.add(t.split(None)[-1])
    return out


def x__identifiers__mutmut_12(text):
    """从代码文本抽出标识符集合：完整点链 + 叶子名。供精确成员匹配（非子串）。"""
    out = set()
    for t in re.findall(r"[A-Za-z_][A-Za-z0-9_.]+", text):
        out.add(t)
        out.add(t.split("XX.XX")[-1])
    return out


def x__identifiers__mutmut_13(text):
    """从代码文本抽出标识符集合：完整点链 + 叶子名。供精确成员匹配（非子串）。"""
    out = set()
    for t in re.findall(r"[A-Za-z_][A-Za-z0-9_.]+", text):
        out.add(t)
        out.add(t.split(".")[+1])
    return out


def x__identifiers__mutmut_14(text):
    """从代码文本抽出标识符集合：完整点链 + 叶子名。供精确成员匹配（非子串）。"""
    out = set()
    for t in re.findall(r"[A-Za-z_][A-Za-z0-9_.]+", text):
        out.add(t)
        out.add(t.split(".")[-2])
    return out

mutants_x__identifiers__mutmut['_mutmut_orig'] = x__identifiers__mutmut_orig # type: ignore # mutmut generated
mutants_x__identifiers__mutmut['x__identifiers__mutmut_1'] = x__identifiers__mutmut_1 # type: ignore # mutmut generated
mutants_x__identifiers__mutmut['x__identifiers__mutmut_2'] = x__identifiers__mutmut_2 # type: ignore # mutmut generated
mutants_x__identifiers__mutmut['x__identifiers__mutmut_3'] = x__identifiers__mutmut_3 # type: ignore # mutmut generated
mutants_x__identifiers__mutmut['x__identifiers__mutmut_4'] = x__identifiers__mutmut_4 # type: ignore # mutmut generated
mutants_x__identifiers__mutmut['x__identifiers__mutmut_5'] = x__identifiers__mutmut_5 # type: ignore # mutmut generated
mutants_x__identifiers__mutmut['x__identifiers__mutmut_6'] = x__identifiers__mutmut_6 # type: ignore # mutmut generated
mutants_x__identifiers__mutmut['x__identifiers__mutmut_7'] = x__identifiers__mutmut_7 # type: ignore # mutmut generated
mutants_x__identifiers__mutmut['x__identifiers__mutmut_8'] = x__identifiers__mutmut_8 # type: ignore # mutmut generated
mutants_x__identifiers__mutmut['x__identifiers__mutmut_9'] = x__identifiers__mutmut_9 # type: ignore # mutmut generated
mutants_x__identifiers__mutmut['x__identifiers__mutmut_10'] = x__identifiers__mutmut_10 # type: ignore # mutmut generated
mutants_x__identifiers__mutmut['x__identifiers__mutmut_11'] = x__identifiers__mutmut_11 # type: ignore # mutmut generated
mutants_x__identifiers__mutmut['x__identifiers__mutmut_12'] = x__identifiers__mutmut_12 # type: ignore # mutmut generated
mutants_x__identifiers__mutmut['x__identifiers__mutmut_13'] = x__identifiers__mutmut_13 # type: ignore # mutmut generated
mutants_x__identifiers__mutmut['x__identifiers__mutmut_14'] = x__identifiers__mutmut_14 # type: ignore # mutmut generated
mutants_x_check_reuse__mutmut: MutantDict = {}  # type: ignore


@_mutmut_mutated(mutants_x_check_reuse__mutmut)
def check_reuse(added, reused, rule_index):
    claims = [c for c in (reused or []) if c and not str(c).startswith("<")]
    if not claims:
        return []
    # 精确成员匹配：避免子串误碰（如声明 get_profile 被 get_profile_v2 假性命中）。
    # 残留：分词不剥注释/字符串，名字出现在注释里仍算命中——属 advisory 误差，跨语言精确剥离不划算。
    present = _identifiers("\n".join(t for lines in added.values() for _, t in lines))
    out = []
    for claim in claims:
        toks = re.findall(r"[A-Za-z_][A-Za-z0-9_.]+", str(claim))
        names = {tok for t in toks for tok in (t, t.split(".")[-1])}
        if names and not (names & present):
            out.append(_finding("DUP-001", "(diff)", 0, "duplication",
                                 f"提交契约声称复用「{claim}」，但新增代码中未见对应引用"
                                 "（申报不实/疑似重复造轮子）",
                                 "确认确实复用既有能力并在代码中引用，或如实更新 reused_components",
                                 rule_index))
    return out


def x_check_reuse__mutmut_orig(added, reused, rule_index):
    claims = [c for c in (reused or []) if c and not str(c).startswith("<")]
    if not claims:
        return []
    # 精确成员匹配：避免子串误碰（如声明 get_profile 被 get_profile_v2 假性命中）。
    # 残留：分词不剥注释/字符串，名字出现在注释里仍算命中——属 advisory 误差，跨语言精确剥离不划算。
    present = _identifiers("\n".join(t for lines in added.values() for _, t in lines))
    out = []
    for claim in claims:
        toks = re.findall(r"[A-Za-z_][A-Za-z0-9_.]+", str(claim))
        names = {tok for t in toks for tok in (t, t.split(".")[-1])}
        if names and not (names & present):
            out.append(_finding("DUP-001", "(diff)", 0, "duplication",
                                 f"提交契约声称复用「{claim}」，但新增代码中未见对应引用"
                                 "（申报不实/疑似重复造轮子）",
                                 "确认确实复用既有能力并在代码中引用，或如实更新 reused_components",
                                 rule_index))
    return out


def x_check_reuse__mutmut_1(added, reused, rule_index):
    claims = None
    if not claims:
        return []
    # 精确成员匹配：避免子串误碰（如声明 get_profile 被 get_profile_v2 假性命中）。
    # 残留：分词不剥注释/字符串，名字出现在注释里仍算命中——属 advisory 误差，跨语言精确剥离不划算。
    present = _identifiers("\n".join(t for lines in added.values() for _, t in lines))
    out = []
    for claim in claims:
        toks = re.findall(r"[A-Za-z_][A-Za-z0-9_.]+", str(claim))
        names = {tok for t in toks for tok in (t, t.split(".")[-1])}
        if names and not (names & present):
            out.append(_finding("DUP-001", "(diff)", 0, "duplication",
                                 f"提交契约声称复用「{claim}」，但新增代码中未见对应引用"
                                 "（申报不实/疑似重复造轮子）",
                                 "确认确实复用既有能力并在代码中引用，或如实更新 reused_components",
                                 rule_index))
    return out


def x_check_reuse__mutmut_2(added, reused, rule_index):
    claims = [c for c in (reused and []) if c and not str(c).startswith("<")]
    if not claims:
        return []
    # 精确成员匹配：避免子串误碰（如声明 get_profile 被 get_profile_v2 假性命中）。
    # 残留：分词不剥注释/字符串，名字出现在注释里仍算命中——属 advisory 误差，跨语言精确剥离不划算。
    present = _identifiers("\n".join(t for lines in added.values() for _, t in lines))
    out = []
    for claim in claims:
        toks = re.findall(r"[A-Za-z_][A-Za-z0-9_.]+", str(claim))
        names = {tok for t in toks for tok in (t, t.split(".")[-1])}
        if names and not (names & present):
            out.append(_finding("DUP-001", "(diff)", 0, "duplication",
                                 f"提交契约声称复用「{claim}」，但新增代码中未见对应引用"
                                 "（申报不实/疑似重复造轮子）",
                                 "确认确实复用既有能力并在代码中引用，或如实更新 reused_components",
                                 rule_index))
    return out


def x_check_reuse__mutmut_3(added, reused, rule_index):
    claims = [c for c in (reused or []) if c or not str(c).startswith("<")]
    if not claims:
        return []
    # 精确成员匹配：避免子串误碰（如声明 get_profile 被 get_profile_v2 假性命中）。
    # 残留：分词不剥注释/字符串，名字出现在注释里仍算命中——属 advisory 误差，跨语言精确剥离不划算。
    present = _identifiers("\n".join(t for lines in added.values() for _, t in lines))
    out = []
    for claim in claims:
        toks = re.findall(r"[A-Za-z_][A-Za-z0-9_.]+", str(claim))
        names = {tok for t in toks for tok in (t, t.split(".")[-1])}
        if names and not (names & present):
            out.append(_finding("DUP-001", "(diff)", 0, "duplication",
                                 f"提交契约声称复用「{claim}」，但新增代码中未见对应引用"
                                 "（申报不实/疑似重复造轮子）",
                                 "确认确实复用既有能力并在代码中引用，或如实更新 reused_components",
                                 rule_index))
    return out


def x_check_reuse__mutmut_4(added, reused, rule_index):
    claims = [c for c in (reused or []) if c and str(c).startswith("<")]
    if not claims:
        return []
    # 精确成员匹配：避免子串误碰（如声明 get_profile 被 get_profile_v2 假性命中）。
    # 残留：分词不剥注释/字符串，名字出现在注释里仍算命中——属 advisory 误差，跨语言精确剥离不划算。
    present = _identifiers("\n".join(t for lines in added.values() for _, t in lines))
    out = []
    for claim in claims:
        toks = re.findall(r"[A-Za-z_][A-Za-z0-9_.]+", str(claim))
        names = {tok for t in toks for tok in (t, t.split(".")[-1])}
        if names and not (names & present):
            out.append(_finding("DUP-001", "(diff)", 0, "duplication",
                                 f"提交契约声称复用「{claim}」，但新增代码中未见对应引用"
                                 "（申报不实/疑似重复造轮子）",
                                 "确认确实复用既有能力并在代码中引用，或如实更新 reused_components",
                                 rule_index))
    return out


def x_check_reuse__mutmut_5(added, reused, rule_index):
    claims = [c for c in (reused or []) if c and not str(c).startswith(None)]
    if not claims:
        return []
    # 精确成员匹配：避免子串误碰（如声明 get_profile 被 get_profile_v2 假性命中）。
    # 残留：分词不剥注释/字符串，名字出现在注释里仍算命中——属 advisory 误差，跨语言精确剥离不划算。
    present = _identifiers("\n".join(t for lines in added.values() for _, t in lines))
    out = []
    for claim in claims:
        toks = re.findall(r"[A-Za-z_][A-Za-z0-9_.]+", str(claim))
        names = {tok for t in toks for tok in (t, t.split(".")[-1])}
        if names and not (names & present):
            out.append(_finding("DUP-001", "(diff)", 0, "duplication",
                                 f"提交契约声称复用「{claim}」，但新增代码中未见对应引用"
                                 "（申报不实/疑似重复造轮子）",
                                 "确认确实复用既有能力并在代码中引用，或如实更新 reused_components",
                                 rule_index))
    return out


def x_check_reuse__mutmut_6(added, reused, rule_index):
    claims = [c for c in (reused or []) if c and not str(None).startswith("<")]
    if not claims:
        return []
    # 精确成员匹配：避免子串误碰（如声明 get_profile 被 get_profile_v2 假性命中）。
    # 残留：分词不剥注释/字符串，名字出现在注释里仍算命中——属 advisory 误差，跨语言精确剥离不划算。
    present = _identifiers("\n".join(t for lines in added.values() for _, t in lines))
    out = []
    for claim in claims:
        toks = re.findall(r"[A-Za-z_][A-Za-z0-9_.]+", str(claim))
        names = {tok for t in toks for tok in (t, t.split(".")[-1])}
        if names and not (names & present):
            out.append(_finding("DUP-001", "(diff)", 0, "duplication",
                                 f"提交契约声称复用「{claim}」，但新增代码中未见对应引用"
                                 "（申报不实/疑似重复造轮子）",
                                 "确认确实复用既有能力并在代码中引用，或如实更新 reused_components",
                                 rule_index))
    return out


def x_check_reuse__mutmut_7(added, reused, rule_index):
    claims = [c for c in (reused or []) if c and not str(c).startswith("XX<XX")]
    if not claims:
        return []
    # 精确成员匹配：避免子串误碰（如声明 get_profile 被 get_profile_v2 假性命中）。
    # 残留：分词不剥注释/字符串，名字出现在注释里仍算命中——属 advisory 误差，跨语言精确剥离不划算。
    present = _identifiers("\n".join(t for lines in added.values() for _, t in lines))
    out = []
    for claim in claims:
        toks = re.findall(r"[A-Za-z_][A-Za-z0-9_.]+", str(claim))
        names = {tok for t in toks for tok in (t, t.split(".")[-1])}
        if names and not (names & present):
            out.append(_finding("DUP-001", "(diff)", 0, "duplication",
                                 f"提交契约声称复用「{claim}」，但新增代码中未见对应引用"
                                 "（申报不实/疑似重复造轮子）",
                                 "确认确实复用既有能力并在代码中引用，或如实更新 reused_components",
                                 rule_index))
    return out


def x_check_reuse__mutmut_8(added, reused, rule_index):
    claims = [c for c in (reused or []) if c and not str(c).startswith("<")]
    if claims:
        return []
    # 精确成员匹配：避免子串误碰（如声明 get_profile 被 get_profile_v2 假性命中）。
    # 残留：分词不剥注释/字符串，名字出现在注释里仍算命中——属 advisory 误差，跨语言精确剥离不划算。
    present = _identifiers("\n".join(t for lines in added.values() for _, t in lines))
    out = []
    for claim in claims:
        toks = re.findall(r"[A-Za-z_][A-Za-z0-9_.]+", str(claim))
        names = {tok for t in toks for tok in (t, t.split(".")[-1])}
        if names and not (names & present):
            out.append(_finding("DUP-001", "(diff)", 0, "duplication",
                                 f"提交契约声称复用「{claim}」，但新增代码中未见对应引用"
                                 "（申报不实/疑似重复造轮子）",
                                 "确认确实复用既有能力并在代码中引用，或如实更新 reused_components",
                                 rule_index))
    return out


def x_check_reuse__mutmut_9(added, reused, rule_index):
    claims = [c for c in (reused or []) if c and not str(c).startswith("<")]
    if not claims:
        return []
    # 精确成员匹配：避免子串误碰（如声明 get_profile 被 get_profile_v2 假性命中）。
    # 残留：分词不剥注释/字符串，名字出现在注释里仍算命中——属 advisory 误差，跨语言精确剥离不划算。
    present = None
    out = []
    for claim in claims:
        toks = re.findall(r"[A-Za-z_][A-Za-z0-9_.]+", str(claim))
        names = {tok for t in toks for tok in (t, t.split(".")[-1])}
        if names and not (names & present):
            out.append(_finding("DUP-001", "(diff)", 0, "duplication",
                                 f"提交契约声称复用「{claim}」，但新增代码中未见对应引用"
                                 "（申报不实/疑似重复造轮子）",
                                 "确认确实复用既有能力并在代码中引用，或如实更新 reused_components",
                                 rule_index))
    return out


def x_check_reuse__mutmut_10(added, reused, rule_index):
    claims = [c for c in (reused or []) if c and not str(c).startswith("<")]
    if not claims:
        return []
    # 精确成员匹配：避免子串误碰（如声明 get_profile 被 get_profile_v2 假性命中）。
    # 残留：分词不剥注释/字符串，名字出现在注释里仍算命中——属 advisory 误差，跨语言精确剥离不划算。
    present = _identifiers(None)
    out = []
    for claim in claims:
        toks = re.findall(r"[A-Za-z_][A-Za-z0-9_.]+", str(claim))
        names = {tok for t in toks for tok in (t, t.split(".")[-1])}
        if names and not (names & present):
            out.append(_finding("DUP-001", "(diff)", 0, "duplication",
                                 f"提交契约声称复用「{claim}」，但新增代码中未见对应引用"
                                 "（申报不实/疑似重复造轮子）",
                                 "确认确实复用既有能力并在代码中引用，或如实更新 reused_components",
                                 rule_index))
    return out


def x_check_reuse__mutmut_11(added, reused, rule_index):
    claims = [c for c in (reused or []) if c and not str(c).startswith("<")]
    if not claims:
        return []
    # 精确成员匹配：避免子串误碰（如声明 get_profile 被 get_profile_v2 假性命中）。
    # 残留：分词不剥注释/字符串，名字出现在注释里仍算命中——属 advisory 误差，跨语言精确剥离不划算。
    present = _identifiers("\n".join(None))
    out = []
    for claim in claims:
        toks = re.findall(r"[A-Za-z_][A-Za-z0-9_.]+", str(claim))
        names = {tok for t in toks for tok in (t, t.split(".")[-1])}
        if names and not (names & present):
            out.append(_finding("DUP-001", "(diff)", 0, "duplication",
                                 f"提交契约声称复用「{claim}」，但新增代码中未见对应引用"
                                 "（申报不实/疑似重复造轮子）",
                                 "确认确实复用既有能力并在代码中引用，或如实更新 reused_components",
                                 rule_index))
    return out


def x_check_reuse__mutmut_12(added, reused, rule_index):
    claims = [c for c in (reused or []) if c and not str(c).startswith("<")]
    if not claims:
        return []
    # 精确成员匹配：避免子串误碰（如声明 get_profile 被 get_profile_v2 假性命中）。
    # 残留：分词不剥注释/字符串，名字出现在注释里仍算命中——属 advisory 误差，跨语言精确剥离不划算。
    present = _identifiers("XX\nXX".join(t for lines in added.values() for _, t in lines))
    out = []
    for claim in claims:
        toks = re.findall(r"[A-Za-z_][A-Za-z0-9_.]+", str(claim))
        names = {tok for t in toks for tok in (t, t.split(".")[-1])}
        if names and not (names & present):
            out.append(_finding("DUP-001", "(diff)", 0, "duplication",
                                 f"提交契约声称复用「{claim}」，但新增代码中未见对应引用"
                                 "（申报不实/疑似重复造轮子）",
                                 "确认确实复用既有能力并在代码中引用，或如实更新 reused_components",
                                 rule_index))
    return out


def x_check_reuse__mutmut_13(added, reused, rule_index):
    claims = [c for c in (reused or []) if c and not str(c).startswith("<")]
    if not claims:
        return []
    # 精确成员匹配：避免子串误碰（如声明 get_profile 被 get_profile_v2 假性命中）。
    # 残留：分词不剥注释/字符串，名字出现在注释里仍算命中——属 advisory 误差，跨语言精确剥离不划算。
    present = _identifiers("\n".join(t for lines in added.values() for _, t in lines))
    out = None
    for claim in claims:
        toks = re.findall(r"[A-Za-z_][A-Za-z0-9_.]+", str(claim))
        names = {tok for t in toks for tok in (t, t.split(".")[-1])}
        if names and not (names & present):
            out.append(_finding("DUP-001", "(diff)", 0, "duplication",
                                 f"提交契约声称复用「{claim}」，但新增代码中未见对应引用"
                                 "（申报不实/疑似重复造轮子）",
                                 "确认确实复用既有能力并在代码中引用，或如实更新 reused_components",
                                 rule_index))
    return out


def x_check_reuse__mutmut_14(added, reused, rule_index):
    claims = [c for c in (reused or []) if c and not str(c).startswith("<")]
    if not claims:
        return []
    # 精确成员匹配：避免子串误碰（如声明 get_profile 被 get_profile_v2 假性命中）。
    # 残留：分词不剥注释/字符串，名字出现在注释里仍算命中——属 advisory 误差，跨语言精确剥离不划算。
    present = _identifiers("\n".join(t for lines in added.values() for _, t in lines))
    out = []
    for claim in claims:
        toks = None
        names = {tok for t in toks for tok in (t, t.split(".")[-1])}
        if names and not (names & present):
            out.append(_finding("DUP-001", "(diff)", 0, "duplication",
                                 f"提交契约声称复用「{claim}」，但新增代码中未见对应引用"
                                 "（申报不实/疑似重复造轮子）",
                                 "确认确实复用既有能力并在代码中引用，或如实更新 reused_components",
                                 rule_index))
    return out


def x_check_reuse__mutmut_15(added, reused, rule_index):
    claims = [c for c in (reused or []) if c and not str(c).startswith("<")]
    if not claims:
        return []
    # 精确成员匹配：避免子串误碰（如声明 get_profile 被 get_profile_v2 假性命中）。
    # 残留：分词不剥注释/字符串，名字出现在注释里仍算命中——属 advisory 误差，跨语言精确剥离不划算。
    present = _identifiers("\n".join(t for lines in added.values() for _, t in lines))
    out = []
    for claim in claims:
        toks = re.findall(None, str(claim))
        names = {tok for t in toks for tok in (t, t.split(".")[-1])}
        if names and not (names & present):
            out.append(_finding("DUP-001", "(diff)", 0, "duplication",
                                 f"提交契约声称复用「{claim}」，但新增代码中未见对应引用"
                                 "（申报不实/疑似重复造轮子）",
                                 "确认确实复用既有能力并在代码中引用，或如实更新 reused_components",
                                 rule_index))
    return out


def x_check_reuse__mutmut_16(added, reused, rule_index):
    claims = [c for c in (reused or []) if c and not str(c).startswith("<")]
    if not claims:
        return []
    # 精确成员匹配：避免子串误碰（如声明 get_profile 被 get_profile_v2 假性命中）。
    # 残留：分词不剥注释/字符串，名字出现在注释里仍算命中——属 advisory 误差，跨语言精确剥离不划算。
    present = _identifiers("\n".join(t for lines in added.values() for _, t in lines))
    out = []
    for claim in claims:
        toks = re.findall(r"[A-Za-z_][A-Za-z0-9_.]+", None)
        names = {tok for t in toks for tok in (t, t.split(".")[-1])}
        if names and not (names & present):
            out.append(_finding("DUP-001", "(diff)", 0, "duplication",
                                 f"提交契约声称复用「{claim}」，但新增代码中未见对应引用"
                                 "（申报不实/疑似重复造轮子）",
                                 "确认确实复用既有能力并在代码中引用，或如实更新 reused_components",
                                 rule_index))
    return out


def x_check_reuse__mutmut_17(added, reused, rule_index):
    claims = [c for c in (reused or []) if c and not str(c).startswith("<")]
    if not claims:
        return []
    # 精确成员匹配：避免子串误碰（如声明 get_profile 被 get_profile_v2 假性命中）。
    # 残留：分词不剥注释/字符串，名字出现在注释里仍算命中——属 advisory 误差，跨语言精确剥离不划算。
    present = _identifiers("\n".join(t for lines in added.values() for _, t in lines))
    out = []
    for claim in claims:
        toks = re.findall(str(claim))
        names = {tok for t in toks for tok in (t, t.split(".")[-1])}
        if names and not (names & present):
            out.append(_finding("DUP-001", "(diff)", 0, "duplication",
                                 f"提交契约声称复用「{claim}」，但新增代码中未见对应引用"
                                 "（申报不实/疑似重复造轮子）",
                                 "确认确实复用既有能力并在代码中引用，或如实更新 reused_components",
                                 rule_index))
    return out


def x_check_reuse__mutmut_18(added, reused, rule_index):
    claims = [c for c in (reused or []) if c and not str(c).startswith("<")]
    if not claims:
        return []
    # 精确成员匹配：避免子串误碰（如声明 get_profile 被 get_profile_v2 假性命中）。
    # 残留：分词不剥注释/字符串，名字出现在注释里仍算命中——属 advisory 误差，跨语言精确剥离不划算。
    present = _identifiers("\n".join(t for lines in added.values() for _, t in lines))
    out = []
    for claim in claims:
        toks = re.findall(r"[A-Za-z_][A-Za-z0-9_.]+", )
        names = {tok for t in toks for tok in (t, t.split(".")[-1])}
        if names and not (names & present):
            out.append(_finding("DUP-001", "(diff)", 0, "duplication",
                                 f"提交契约声称复用「{claim}」，但新增代码中未见对应引用"
                                 "（申报不实/疑似重复造轮子）",
                                 "确认确实复用既有能力并在代码中引用，或如实更新 reused_components",
                                 rule_index))
    return out


def x_check_reuse__mutmut_19(added, reused, rule_index):
    claims = [c for c in (reused or []) if c and not str(c).startswith("<")]
    if not claims:
        return []
    # 精确成员匹配：避免子串误碰（如声明 get_profile 被 get_profile_v2 假性命中）。
    # 残留：分词不剥注释/字符串，名字出现在注释里仍算命中——属 advisory 误差，跨语言精确剥离不划算。
    present = _identifiers("\n".join(t for lines in added.values() for _, t in lines))
    out = []
    for claim in claims:
        toks = re.findall(r"XX[A-Za-z_][A-Za-z0-9_.]+XX", str(claim))
        names = {tok for t in toks for tok in (t, t.split(".")[-1])}
        if names and not (names & present):
            out.append(_finding("DUP-001", "(diff)", 0, "duplication",
                                 f"提交契约声称复用「{claim}」，但新增代码中未见对应引用"
                                 "（申报不实/疑似重复造轮子）",
                                 "确认确实复用既有能力并在代码中引用，或如实更新 reused_components",
                                 rule_index))
    return out


def x_check_reuse__mutmut_20(added, reused, rule_index):
    claims = [c for c in (reused or []) if c and not str(c).startswith("<")]
    if not claims:
        return []
    # 精确成员匹配：避免子串误碰（如声明 get_profile 被 get_profile_v2 假性命中）。
    # 残留：分词不剥注释/字符串，名字出现在注释里仍算命中——属 advisory 误差，跨语言精确剥离不划算。
    present = _identifiers("\n".join(t for lines in added.values() for _, t in lines))
    out = []
    for claim in claims:
        toks = re.findall(r"[a-za-z_][a-za-z0-9_.]+", str(claim))
        names = {tok for t in toks for tok in (t, t.split(".")[-1])}
        if names and not (names & present):
            out.append(_finding("DUP-001", "(diff)", 0, "duplication",
                                 f"提交契约声称复用「{claim}」，但新增代码中未见对应引用"
                                 "（申报不实/疑似重复造轮子）",
                                 "确认确实复用既有能力并在代码中引用，或如实更新 reused_components",
                                 rule_index))
    return out


def x_check_reuse__mutmut_21(added, reused, rule_index):
    claims = [c for c in (reused or []) if c and not str(c).startswith("<")]
    if not claims:
        return []
    # 精确成员匹配：避免子串误碰（如声明 get_profile 被 get_profile_v2 假性命中）。
    # 残留：分词不剥注释/字符串，名字出现在注释里仍算命中——属 advisory 误差，跨语言精确剥离不划算。
    present = _identifiers("\n".join(t for lines in added.values() for _, t in lines))
    out = []
    for claim in claims:
        toks = re.findall(r"[A-ZA-Z_][A-ZA-Z0-9_.]+", str(claim))
        names = {tok for t in toks for tok in (t, t.split(".")[-1])}
        if names and not (names & present):
            out.append(_finding("DUP-001", "(diff)", 0, "duplication",
                                 f"提交契约声称复用「{claim}」，但新增代码中未见对应引用"
                                 "（申报不实/疑似重复造轮子）",
                                 "确认确实复用既有能力并在代码中引用，或如实更新 reused_components",
                                 rule_index))
    return out


def x_check_reuse__mutmut_22(added, reused, rule_index):
    claims = [c for c in (reused or []) if c and not str(c).startswith("<")]
    if not claims:
        return []
    # 精确成员匹配：避免子串误碰（如声明 get_profile 被 get_profile_v2 假性命中）。
    # 残留：分词不剥注释/字符串，名字出现在注释里仍算命中——属 advisory 误差，跨语言精确剥离不划算。
    present = _identifiers("\n".join(t for lines in added.values() for _, t in lines))
    out = []
    for claim in claims:
        toks = re.findall(r"[A-Za-z_][A-Za-z0-9_.]+", str(None))
        names = {tok for t in toks for tok in (t, t.split(".")[-1])}
        if names and not (names & present):
            out.append(_finding("DUP-001", "(diff)", 0, "duplication",
                                 f"提交契约声称复用「{claim}」，但新增代码中未见对应引用"
                                 "（申报不实/疑似重复造轮子）",
                                 "确认确实复用既有能力并在代码中引用，或如实更新 reused_components",
                                 rule_index))
    return out


def x_check_reuse__mutmut_23(added, reused, rule_index):
    claims = [c for c in (reused or []) if c and not str(c).startswith("<")]
    if not claims:
        return []
    # 精确成员匹配：避免子串误碰（如声明 get_profile 被 get_profile_v2 假性命中）。
    # 残留：分词不剥注释/字符串，名字出现在注释里仍算命中——属 advisory 误差，跨语言精确剥离不划算。
    present = _identifiers("\n".join(t for lines in added.values() for _, t in lines))
    out = []
    for claim in claims:
        toks = re.findall(r"[A-Za-z_][A-Za-z0-9_.]+", str(claim))
        names = None
        if names and not (names & present):
            out.append(_finding("DUP-001", "(diff)", 0, "duplication",
                                 f"提交契约声称复用「{claim}」，但新增代码中未见对应引用"
                                 "（申报不实/疑似重复造轮子）",
                                 "确认确实复用既有能力并在代码中引用，或如实更新 reused_components",
                                 rule_index))
    return out


def x_check_reuse__mutmut_24(added, reused, rule_index):
    claims = [c for c in (reused or []) if c and not str(c).startswith("<")]
    if not claims:
        return []
    # 精确成员匹配：避免子串误碰（如声明 get_profile 被 get_profile_v2 假性命中）。
    # 残留：分词不剥注释/字符串，名字出现在注释里仍算命中——属 advisory 误差，跨语言精确剥离不划算。
    present = _identifiers("\n".join(t for lines in added.values() for _, t in lines))
    out = []
    for claim in claims:
        toks = re.findall(r"[A-Za-z_][A-Za-z0-9_.]+", str(claim))
        names = {tok for t in toks for tok in (t, t.split(None)[-1])}
        if names and not (names & present):
            out.append(_finding("DUP-001", "(diff)", 0, "duplication",
                                 f"提交契约声称复用「{claim}」，但新增代码中未见对应引用"
                                 "（申报不实/疑似重复造轮子）",
                                 "确认确实复用既有能力并在代码中引用，或如实更新 reused_components",
                                 rule_index))
    return out


def x_check_reuse__mutmut_25(added, reused, rule_index):
    claims = [c for c in (reused or []) if c and not str(c).startswith("<")]
    if not claims:
        return []
    # 精确成员匹配：避免子串误碰（如声明 get_profile 被 get_profile_v2 假性命中）。
    # 残留：分词不剥注释/字符串，名字出现在注释里仍算命中——属 advisory 误差，跨语言精确剥离不划算。
    present = _identifiers("\n".join(t for lines in added.values() for _, t in lines))
    out = []
    for claim in claims:
        toks = re.findall(r"[A-Za-z_][A-Za-z0-9_.]+", str(claim))
        names = {tok for t in toks for tok in (t, t.split("XX.XX")[-1])}
        if names and not (names & present):
            out.append(_finding("DUP-001", "(diff)", 0, "duplication",
                                 f"提交契约声称复用「{claim}」，但新增代码中未见对应引用"
                                 "（申报不实/疑似重复造轮子）",
                                 "确认确实复用既有能力并在代码中引用，或如实更新 reused_components",
                                 rule_index))
    return out


def x_check_reuse__mutmut_26(added, reused, rule_index):
    claims = [c for c in (reused or []) if c and not str(c).startswith("<")]
    if not claims:
        return []
    # 精确成员匹配：避免子串误碰（如声明 get_profile 被 get_profile_v2 假性命中）。
    # 残留：分词不剥注释/字符串，名字出现在注释里仍算命中——属 advisory 误差，跨语言精确剥离不划算。
    present = _identifiers("\n".join(t for lines in added.values() for _, t in lines))
    out = []
    for claim in claims:
        toks = re.findall(r"[A-Za-z_][A-Za-z0-9_.]+", str(claim))
        names = {tok for t in toks for tok in (t, t.split(".")[+1])}
        if names and not (names & present):
            out.append(_finding("DUP-001", "(diff)", 0, "duplication",
                                 f"提交契约声称复用「{claim}」，但新增代码中未见对应引用"
                                 "（申报不实/疑似重复造轮子）",
                                 "确认确实复用既有能力并在代码中引用，或如实更新 reused_components",
                                 rule_index))
    return out


def x_check_reuse__mutmut_27(added, reused, rule_index):
    claims = [c for c in (reused or []) if c and not str(c).startswith("<")]
    if not claims:
        return []
    # 精确成员匹配：避免子串误碰（如声明 get_profile 被 get_profile_v2 假性命中）。
    # 残留：分词不剥注释/字符串，名字出现在注释里仍算命中——属 advisory 误差，跨语言精确剥离不划算。
    present = _identifiers("\n".join(t for lines in added.values() for _, t in lines))
    out = []
    for claim in claims:
        toks = re.findall(r"[A-Za-z_][A-Za-z0-9_.]+", str(claim))
        names = {tok for t in toks for tok in (t, t.split(".")[-2])}
        if names and not (names & present):
            out.append(_finding("DUP-001", "(diff)", 0, "duplication",
                                 f"提交契约声称复用「{claim}」，但新增代码中未见对应引用"
                                 "（申报不实/疑似重复造轮子）",
                                 "确认确实复用既有能力并在代码中引用，或如实更新 reused_components",
                                 rule_index))
    return out


def x_check_reuse__mutmut_28(added, reused, rule_index):
    claims = [c for c in (reused or []) if c and not str(c).startswith("<")]
    if not claims:
        return []
    # 精确成员匹配：避免子串误碰（如声明 get_profile 被 get_profile_v2 假性命中）。
    # 残留：分词不剥注释/字符串，名字出现在注释里仍算命中——属 advisory 误差，跨语言精确剥离不划算。
    present = _identifiers("\n".join(t for lines in added.values() for _, t in lines))
    out = []
    for claim in claims:
        toks = re.findall(r"[A-Za-z_][A-Za-z0-9_.]+", str(claim))
        names = {tok for t in toks for tok in (t, t.split(".")[-1])}
        if names or not (names & present):
            out.append(_finding("DUP-001", "(diff)", 0, "duplication",
                                 f"提交契约声称复用「{claim}」，但新增代码中未见对应引用"
                                 "（申报不实/疑似重复造轮子）",
                                 "确认确实复用既有能力并在代码中引用，或如实更新 reused_components",
                                 rule_index))
    return out


def x_check_reuse__mutmut_29(added, reused, rule_index):
    claims = [c for c in (reused or []) if c and not str(c).startswith("<")]
    if not claims:
        return []
    # 精确成员匹配：避免子串误碰（如声明 get_profile 被 get_profile_v2 假性命中）。
    # 残留：分词不剥注释/字符串，名字出现在注释里仍算命中——属 advisory 误差，跨语言精确剥离不划算。
    present = _identifiers("\n".join(t for lines in added.values() for _, t in lines))
    out = []
    for claim in claims:
        toks = re.findall(r"[A-Za-z_][A-Za-z0-9_.]+", str(claim))
        names = {tok for t in toks for tok in (t, t.split(".")[-1])}
        if names and (names & present):
            out.append(_finding("DUP-001", "(diff)", 0, "duplication",
                                 f"提交契约声称复用「{claim}」，但新增代码中未见对应引用"
                                 "（申报不实/疑似重复造轮子）",
                                 "确认确实复用既有能力并在代码中引用，或如实更新 reused_components",
                                 rule_index))
    return out


def x_check_reuse__mutmut_30(added, reused, rule_index):
    claims = [c for c in (reused or []) if c and not str(c).startswith("<")]
    if not claims:
        return []
    # 精确成员匹配：避免子串误碰（如声明 get_profile 被 get_profile_v2 假性命中）。
    # 残留：分词不剥注释/字符串，名字出现在注释里仍算命中——属 advisory 误差，跨语言精确剥离不划算。
    present = _identifiers("\n".join(t for lines in added.values() for _, t in lines))
    out = []
    for claim in claims:
        toks = re.findall(r"[A-Za-z_][A-Za-z0-9_.]+", str(claim))
        names = {tok for t in toks for tok in (t, t.split(".")[-1])}
        if names and not (names | present):
            out.append(_finding("DUP-001", "(diff)", 0, "duplication",
                                 f"提交契约声称复用「{claim}」，但新增代码中未见对应引用"
                                 "（申报不实/疑似重复造轮子）",
                                 "确认确实复用既有能力并在代码中引用，或如实更新 reused_components",
                                 rule_index))
    return out


def x_check_reuse__mutmut_31(added, reused, rule_index):
    claims = [c for c in (reused or []) if c and not str(c).startswith("<")]
    if not claims:
        return []
    # 精确成员匹配：避免子串误碰（如声明 get_profile 被 get_profile_v2 假性命中）。
    # 残留：分词不剥注释/字符串，名字出现在注释里仍算命中——属 advisory 误差，跨语言精确剥离不划算。
    present = _identifiers("\n".join(t for lines in added.values() for _, t in lines))
    out = []
    for claim in claims:
        toks = re.findall(r"[A-Za-z_][A-Za-z0-9_.]+", str(claim))
        names = {tok for t in toks for tok in (t, t.split(".")[-1])}
        if names and not (names & present):
            out.append(None)
    return out


def x_check_reuse__mutmut_32(added, reused, rule_index):
    claims = [c for c in (reused or []) if c and not str(c).startswith("<")]
    if not claims:
        return []
    # 精确成员匹配：避免子串误碰（如声明 get_profile 被 get_profile_v2 假性命中）。
    # 残留：分词不剥注释/字符串，名字出现在注释里仍算命中——属 advisory 误差，跨语言精确剥离不划算。
    present = _identifiers("\n".join(t for lines in added.values() for _, t in lines))
    out = []
    for claim in claims:
        toks = re.findall(r"[A-Za-z_][A-Za-z0-9_.]+", str(claim))
        names = {tok for t in toks for tok in (t, t.split(".")[-1])}
        if names and not (names & present):
            out.append(_finding(None, "(diff)", 0, "duplication",
                                 f"提交契约声称复用「{claim}」，但新增代码中未见对应引用"
                                 "（申报不实/疑似重复造轮子）",
                                 "确认确实复用既有能力并在代码中引用，或如实更新 reused_components",
                                 rule_index))
    return out


def x_check_reuse__mutmut_33(added, reused, rule_index):
    claims = [c for c in (reused or []) if c and not str(c).startswith("<")]
    if not claims:
        return []
    # 精确成员匹配：避免子串误碰（如声明 get_profile 被 get_profile_v2 假性命中）。
    # 残留：分词不剥注释/字符串，名字出现在注释里仍算命中——属 advisory 误差，跨语言精确剥离不划算。
    present = _identifiers("\n".join(t for lines in added.values() for _, t in lines))
    out = []
    for claim in claims:
        toks = re.findall(r"[A-Za-z_][A-Za-z0-9_.]+", str(claim))
        names = {tok for t in toks for tok in (t, t.split(".")[-1])}
        if names and not (names & present):
            out.append(_finding("DUP-001", None, 0, "duplication",
                                 f"提交契约声称复用「{claim}」，但新增代码中未见对应引用"
                                 "（申报不实/疑似重复造轮子）",
                                 "确认确实复用既有能力并在代码中引用，或如实更新 reused_components",
                                 rule_index))
    return out


def x_check_reuse__mutmut_34(added, reused, rule_index):
    claims = [c for c in (reused or []) if c and not str(c).startswith("<")]
    if not claims:
        return []
    # 精确成员匹配：避免子串误碰（如声明 get_profile 被 get_profile_v2 假性命中）。
    # 残留：分词不剥注释/字符串，名字出现在注释里仍算命中——属 advisory 误差，跨语言精确剥离不划算。
    present = _identifiers("\n".join(t for lines in added.values() for _, t in lines))
    out = []
    for claim in claims:
        toks = re.findall(r"[A-Za-z_][A-Za-z0-9_.]+", str(claim))
        names = {tok for t in toks for tok in (t, t.split(".")[-1])}
        if names and not (names & present):
            out.append(_finding("DUP-001", "(diff)", None, "duplication",
                                 f"提交契约声称复用「{claim}」，但新增代码中未见对应引用"
                                 "（申报不实/疑似重复造轮子）",
                                 "确认确实复用既有能力并在代码中引用，或如实更新 reused_components",
                                 rule_index))
    return out


def x_check_reuse__mutmut_35(added, reused, rule_index):
    claims = [c for c in (reused or []) if c and not str(c).startswith("<")]
    if not claims:
        return []
    # 精确成员匹配：避免子串误碰（如声明 get_profile 被 get_profile_v2 假性命中）。
    # 残留：分词不剥注释/字符串，名字出现在注释里仍算命中——属 advisory 误差，跨语言精确剥离不划算。
    present = _identifiers("\n".join(t for lines in added.values() for _, t in lines))
    out = []
    for claim in claims:
        toks = re.findall(r"[A-Za-z_][A-Za-z0-9_.]+", str(claim))
        names = {tok for t in toks for tok in (t, t.split(".")[-1])}
        if names and not (names & present):
            out.append(_finding("DUP-001", "(diff)", 0, None,
                                 f"提交契约声称复用「{claim}」，但新增代码中未见对应引用"
                                 "（申报不实/疑似重复造轮子）",
                                 "确认确实复用既有能力并在代码中引用，或如实更新 reused_components",
                                 rule_index))
    return out


def x_check_reuse__mutmut_36(added, reused, rule_index):
    claims = [c for c in (reused or []) if c and not str(c).startswith("<")]
    if not claims:
        return []
    # 精确成员匹配：避免子串误碰（如声明 get_profile 被 get_profile_v2 假性命中）。
    # 残留：分词不剥注释/字符串，名字出现在注释里仍算命中——属 advisory 误差，跨语言精确剥离不划算。
    present = _identifiers("\n".join(t for lines in added.values() for _, t in lines))
    out = []
    for claim in claims:
        toks = re.findall(r"[A-Za-z_][A-Za-z0-9_.]+", str(claim))
        names = {tok for t in toks for tok in (t, t.split(".")[-1])}
        if names and not (names & present):
            out.append(_finding("DUP-001", "(diff)", 0, "duplication",
                                 None,
                                 "确认确实复用既有能力并在代码中引用，或如实更新 reused_components",
                                 rule_index))
    return out


def x_check_reuse__mutmut_37(added, reused, rule_index):
    claims = [c for c in (reused or []) if c and not str(c).startswith("<")]
    if not claims:
        return []
    # 精确成员匹配：避免子串误碰（如声明 get_profile 被 get_profile_v2 假性命中）。
    # 残留：分词不剥注释/字符串，名字出现在注释里仍算命中——属 advisory 误差，跨语言精确剥离不划算。
    present = _identifiers("\n".join(t for lines in added.values() for _, t in lines))
    out = []
    for claim in claims:
        toks = re.findall(r"[A-Za-z_][A-Za-z0-9_.]+", str(claim))
        names = {tok for t in toks for tok in (t, t.split(".")[-1])}
        if names and not (names & present):
            out.append(_finding("DUP-001", "(diff)", 0, "duplication",
                                 f"提交契约声称复用「{claim}」，但新增代码中未见对应引用"
                                 "（申报不实/疑似重复造轮子）",
                                 None,
                                 rule_index))
    return out


def x_check_reuse__mutmut_38(added, reused, rule_index):
    claims = [c for c in (reused or []) if c and not str(c).startswith("<")]
    if not claims:
        return []
    # 精确成员匹配：避免子串误碰（如声明 get_profile 被 get_profile_v2 假性命中）。
    # 残留：分词不剥注释/字符串，名字出现在注释里仍算命中——属 advisory 误差，跨语言精确剥离不划算。
    present = _identifiers("\n".join(t for lines in added.values() for _, t in lines))
    out = []
    for claim in claims:
        toks = re.findall(r"[A-Za-z_][A-Za-z0-9_.]+", str(claim))
        names = {tok for t in toks for tok in (t, t.split(".")[-1])}
        if names and not (names & present):
            out.append(_finding("DUP-001", "(diff)", 0, "duplication",
                                 f"提交契约声称复用「{claim}」，但新增代码中未见对应引用"
                                 "（申报不实/疑似重复造轮子）",
                                 "确认确实复用既有能力并在代码中引用，或如实更新 reused_components",
                                 None))
    return out


def x_check_reuse__mutmut_39(added, reused, rule_index):
    claims = [c for c in (reused or []) if c and not str(c).startswith("<")]
    if not claims:
        return []
    # 精确成员匹配：避免子串误碰（如声明 get_profile 被 get_profile_v2 假性命中）。
    # 残留：分词不剥注释/字符串，名字出现在注释里仍算命中——属 advisory 误差，跨语言精确剥离不划算。
    present = _identifiers("\n".join(t for lines in added.values() for _, t in lines))
    out = []
    for claim in claims:
        toks = re.findall(r"[A-Za-z_][A-Za-z0-9_.]+", str(claim))
        names = {tok for t in toks for tok in (t, t.split(".")[-1])}
        if names and not (names & present):
            out.append(_finding("(diff)", 0, "duplication",
                                 f"提交契约声称复用「{claim}」，但新增代码中未见对应引用"
                                 "（申报不实/疑似重复造轮子）",
                                 "确认确实复用既有能力并在代码中引用，或如实更新 reused_components",
                                 rule_index))
    return out


def x_check_reuse__mutmut_40(added, reused, rule_index):
    claims = [c for c in (reused or []) if c and not str(c).startswith("<")]
    if not claims:
        return []
    # 精确成员匹配：避免子串误碰（如声明 get_profile 被 get_profile_v2 假性命中）。
    # 残留：分词不剥注释/字符串，名字出现在注释里仍算命中——属 advisory 误差，跨语言精确剥离不划算。
    present = _identifiers("\n".join(t for lines in added.values() for _, t in lines))
    out = []
    for claim in claims:
        toks = re.findall(r"[A-Za-z_][A-Za-z0-9_.]+", str(claim))
        names = {tok for t in toks for tok in (t, t.split(".")[-1])}
        if names and not (names & present):
            out.append(_finding("DUP-001", 0, "duplication",
                                 f"提交契约声称复用「{claim}」，但新增代码中未见对应引用"
                                 "（申报不实/疑似重复造轮子）",
                                 "确认确实复用既有能力并在代码中引用，或如实更新 reused_components",
                                 rule_index))
    return out


def x_check_reuse__mutmut_41(added, reused, rule_index):
    claims = [c for c in (reused or []) if c and not str(c).startswith("<")]
    if not claims:
        return []
    # 精确成员匹配：避免子串误碰（如声明 get_profile 被 get_profile_v2 假性命中）。
    # 残留：分词不剥注释/字符串，名字出现在注释里仍算命中——属 advisory 误差，跨语言精确剥离不划算。
    present = _identifiers("\n".join(t for lines in added.values() for _, t in lines))
    out = []
    for claim in claims:
        toks = re.findall(r"[A-Za-z_][A-Za-z0-9_.]+", str(claim))
        names = {tok for t in toks for tok in (t, t.split(".")[-1])}
        if names and not (names & present):
            out.append(_finding("DUP-001", "(diff)", "duplication",
                                 f"提交契约声称复用「{claim}」，但新增代码中未见对应引用"
                                 "（申报不实/疑似重复造轮子）",
                                 "确认确实复用既有能力并在代码中引用，或如实更新 reused_components",
                                 rule_index))
    return out


def x_check_reuse__mutmut_42(added, reused, rule_index):
    claims = [c for c in (reused or []) if c and not str(c).startswith("<")]
    if not claims:
        return []
    # 精确成员匹配：避免子串误碰（如声明 get_profile 被 get_profile_v2 假性命中）。
    # 残留：分词不剥注释/字符串，名字出现在注释里仍算命中——属 advisory 误差，跨语言精确剥离不划算。
    present = _identifiers("\n".join(t for lines in added.values() for _, t in lines))
    out = []
    for claim in claims:
        toks = re.findall(r"[A-Za-z_][A-Za-z0-9_.]+", str(claim))
        names = {tok for t in toks for tok in (t, t.split(".")[-1])}
        if names and not (names & present):
            out.append(_finding("DUP-001", "(diff)", 0, f"提交契约声称复用「{claim}」，但新增代码中未见对应引用"
                                 "（申报不实/疑似重复造轮子）",
                                 "确认确实复用既有能力并在代码中引用，或如实更新 reused_components",
                                 rule_index))
    return out


def x_check_reuse__mutmut_43(added, reused, rule_index):
    claims = [c for c in (reused or []) if c and not str(c).startswith("<")]
    if not claims:
        return []
    # 精确成员匹配：避免子串误碰（如声明 get_profile 被 get_profile_v2 假性命中）。
    # 残留：分词不剥注释/字符串，名字出现在注释里仍算命中——属 advisory 误差，跨语言精确剥离不划算。
    present = _identifiers("\n".join(t for lines in added.values() for _, t in lines))
    out = []
    for claim in claims:
        toks = re.findall(r"[A-Za-z_][A-Za-z0-9_.]+", str(claim))
        names = {tok for t in toks for tok in (t, t.split(".")[-1])}
        if names and not (names & present):
            out.append(_finding("DUP-001", "(diff)", 0, "duplication",
                                 "确认确实复用既有能力并在代码中引用，或如实更新 reused_components",
                                 rule_index))
    return out


def x_check_reuse__mutmut_44(added, reused, rule_index):
    claims = [c for c in (reused or []) if c and not str(c).startswith("<")]
    if not claims:
        return []
    # 精确成员匹配：避免子串误碰（如声明 get_profile 被 get_profile_v2 假性命中）。
    # 残留：分词不剥注释/字符串，名字出现在注释里仍算命中——属 advisory 误差，跨语言精确剥离不划算。
    present = _identifiers("\n".join(t for lines in added.values() for _, t in lines))
    out = []
    for claim in claims:
        toks = re.findall(r"[A-Za-z_][A-Za-z0-9_.]+", str(claim))
        names = {tok for t in toks for tok in (t, t.split(".")[-1])}
        if names and not (names & present):
            out.append(_finding("DUP-001", "(diff)", 0, "duplication",
                                 f"提交契约声称复用「{claim}」，但新增代码中未见对应引用"
                                 "（申报不实/疑似重复造轮子）",
                                 rule_index))
    return out


def x_check_reuse__mutmut_45(added, reused, rule_index):
    claims = [c for c in (reused or []) if c and not str(c).startswith("<")]
    if not claims:
        return []
    # 精确成员匹配：避免子串误碰（如声明 get_profile 被 get_profile_v2 假性命中）。
    # 残留：分词不剥注释/字符串，名字出现在注释里仍算命中——属 advisory 误差，跨语言精确剥离不划算。
    present = _identifiers("\n".join(t for lines in added.values() for _, t in lines))
    out = []
    for claim in claims:
        toks = re.findall(r"[A-Za-z_][A-Za-z0-9_.]+", str(claim))
        names = {tok for t in toks for tok in (t, t.split(".")[-1])}
        if names and not (names & present):
            out.append(_finding("DUP-001", "(diff)", 0, "duplication",
                                 f"提交契约声称复用「{claim}」，但新增代码中未见对应引用"
                                 "（申报不实/疑似重复造轮子）",
                                 "确认确实复用既有能力并在代码中引用，或如实更新 reused_components",
                                 ))
    return out


def x_check_reuse__mutmut_46(added, reused, rule_index):
    claims = [c for c in (reused or []) if c and not str(c).startswith("<")]
    if not claims:
        return []
    # 精确成员匹配：避免子串误碰（如声明 get_profile 被 get_profile_v2 假性命中）。
    # 残留：分词不剥注释/字符串，名字出现在注释里仍算命中——属 advisory 误差，跨语言精确剥离不划算。
    present = _identifiers("\n".join(t for lines in added.values() for _, t in lines))
    out = []
    for claim in claims:
        toks = re.findall(r"[A-Za-z_][A-Za-z0-9_.]+", str(claim))
        names = {tok for t in toks for tok in (t, t.split(".")[-1])}
        if names and not (names & present):
            out.append(_finding("XXDUP-001XX", "(diff)", 0, "duplication",
                                 f"提交契约声称复用「{claim}」，但新增代码中未见对应引用"
                                 "（申报不实/疑似重复造轮子）",
                                 "确认确实复用既有能力并在代码中引用，或如实更新 reused_components",
                                 rule_index))
    return out


def x_check_reuse__mutmut_47(added, reused, rule_index):
    claims = [c for c in (reused or []) if c and not str(c).startswith("<")]
    if not claims:
        return []
    # 精确成员匹配：避免子串误碰（如声明 get_profile 被 get_profile_v2 假性命中）。
    # 残留：分词不剥注释/字符串，名字出现在注释里仍算命中——属 advisory 误差，跨语言精确剥离不划算。
    present = _identifiers("\n".join(t for lines in added.values() for _, t in lines))
    out = []
    for claim in claims:
        toks = re.findall(r"[A-Za-z_][A-Za-z0-9_.]+", str(claim))
        names = {tok for t in toks for tok in (t, t.split(".")[-1])}
        if names and not (names & present):
            out.append(_finding("dup-001", "(diff)", 0, "duplication",
                                 f"提交契约声称复用「{claim}」，但新增代码中未见对应引用"
                                 "（申报不实/疑似重复造轮子）",
                                 "确认确实复用既有能力并在代码中引用，或如实更新 reused_components",
                                 rule_index))
    return out


def x_check_reuse__mutmut_48(added, reused, rule_index):
    claims = [c for c in (reused or []) if c and not str(c).startswith("<")]
    if not claims:
        return []
    # 精确成员匹配：避免子串误碰（如声明 get_profile 被 get_profile_v2 假性命中）。
    # 残留：分词不剥注释/字符串，名字出现在注释里仍算命中——属 advisory 误差，跨语言精确剥离不划算。
    present = _identifiers("\n".join(t for lines in added.values() for _, t in lines))
    out = []
    for claim in claims:
        toks = re.findall(r"[A-Za-z_][A-Za-z0-9_.]+", str(claim))
        names = {tok for t in toks for tok in (t, t.split(".")[-1])}
        if names and not (names & present):
            out.append(_finding("DUP-001", "XX(diff)XX", 0, "duplication",
                                 f"提交契约声称复用「{claim}」，但新增代码中未见对应引用"
                                 "（申报不实/疑似重复造轮子）",
                                 "确认确实复用既有能力并在代码中引用，或如实更新 reused_components",
                                 rule_index))
    return out


def x_check_reuse__mutmut_49(added, reused, rule_index):
    claims = [c for c in (reused or []) if c and not str(c).startswith("<")]
    if not claims:
        return []
    # 精确成员匹配：避免子串误碰（如声明 get_profile 被 get_profile_v2 假性命中）。
    # 残留：分词不剥注释/字符串，名字出现在注释里仍算命中——属 advisory 误差，跨语言精确剥离不划算。
    present = _identifiers("\n".join(t for lines in added.values() for _, t in lines))
    out = []
    for claim in claims:
        toks = re.findall(r"[A-Za-z_][A-Za-z0-9_.]+", str(claim))
        names = {tok for t in toks for tok in (t, t.split(".")[-1])}
        if names and not (names & present):
            out.append(_finding("DUP-001", "(DIFF)", 0, "duplication",
                                 f"提交契约声称复用「{claim}」，但新增代码中未见对应引用"
                                 "（申报不实/疑似重复造轮子）",
                                 "确认确实复用既有能力并在代码中引用，或如实更新 reused_components",
                                 rule_index))
    return out


def x_check_reuse__mutmut_50(added, reused, rule_index):
    claims = [c for c in (reused or []) if c and not str(c).startswith("<")]
    if not claims:
        return []
    # 精确成员匹配：避免子串误碰（如声明 get_profile 被 get_profile_v2 假性命中）。
    # 残留：分词不剥注释/字符串，名字出现在注释里仍算命中——属 advisory 误差，跨语言精确剥离不划算。
    present = _identifiers("\n".join(t for lines in added.values() for _, t in lines))
    out = []
    for claim in claims:
        toks = re.findall(r"[A-Za-z_][A-Za-z0-9_.]+", str(claim))
        names = {tok for t in toks for tok in (t, t.split(".")[-1])}
        if names and not (names & present):
            out.append(_finding("DUP-001", "(diff)", 1, "duplication",
                                 f"提交契约声称复用「{claim}」，但新增代码中未见对应引用"
                                 "（申报不实/疑似重复造轮子）",
                                 "确认确实复用既有能力并在代码中引用，或如实更新 reused_components",
                                 rule_index))
    return out


def x_check_reuse__mutmut_51(added, reused, rule_index):
    claims = [c for c in (reused or []) if c and not str(c).startswith("<")]
    if not claims:
        return []
    # 精确成员匹配：避免子串误碰（如声明 get_profile 被 get_profile_v2 假性命中）。
    # 残留：分词不剥注释/字符串，名字出现在注释里仍算命中——属 advisory 误差，跨语言精确剥离不划算。
    present = _identifiers("\n".join(t for lines in added.values() for _, t in lines))
    out = []
    for claim in claims:
        toks = re.findall(r"[A-Za-z_][A-Za-z0-9_.]+", str(claim))
        names = {tok for t in toks for tok in (t, t.split(".")[-1])}
        if names and not (names & present):
            out.append(_finding("DUP-001", "(diff)", 0, "XXduplicationXX",
                                 f"提交契约声称复用「{claim}」，但新增代码中未见对应引用"
                                 "（申报不实/疑似重复造轮子）",
                                 "确认确实复用既有能力并在代码中引用，或如实更新 reused_components",
                                 rule_index))
    return out


def x_check_reuse__mutmut_52(added, reused, rule_index):
    claims = [c for c in (reused or []) if c and not str(c).startswith("<")]
    if not claims:
        return []
    # 精确成员匹配：避免子串误碰（如声明 get_profile 被 get_profile_v2 假性命中）。
    # 残留：分词不剥注释/字符串，名字出现在注释里仍算命中——属 advisory 误差，跨语言精确剥离不划算。
    present = _identifiers("\n".join(t for lines in added.values() for _, t in lines))
    out = []
    for claim in claims:
        toks = re.findall(r"[A-Za-z_][A-Za-z0-9_.]+", str(claim))
        names = {tok for t in toks for tok in (t, t.split(".")[-1])}
        if names and not (names & present):
            out.append(_finding("DUP-001", "(diff)", 0, "DUPLICATION",
                                 f"提交契约声称复用「{claim}」，但新增代码中未见对应引用"
                                 "（申报不实/疑似重复造轮子）",
                                 "确认确实复用既有能力并在代码中引用，或如实更新 reused_components",
                                 rule_index))
    return out


def x_check_reuse__mutmut_53(added, reused, rule_index):
    claims = [c for c in (reused or []) if c and not str(c).startswith("<")]
    if not claims:
        return []
    # 精确成员匹配：避免子串误碰（如声明 get_profile 被 get_profile_v2 假性命中）。
    # 残留：分词不剥注释/字符串，名字出现在注释里仍算命中——属 advisory 误差，跨语言精确剥离不划算。
    present = _identifiers("\n".join(t for lines in added.values() for _, t in lines))
    out = []
    for claim in claims:
        toks = re.findall(r"[A-Za-z_][A-Za-z0-9_.]+", str(claim))
        names = {tok for t in toks for tok in (t, t.split(".")[-1])}
        if names and not (names & present):
            out.append(_finding("DUP-001", "(diff)", 0, "duplication",
                                 f"提交契约声称复用「{claim}」，但新增代码中未见对应引用"
                                 "XX（申报不实/疑似重复造轮子）XX",
                                 "确认确实复用既有能力并在代码中引用，或如实更新 reused_components",
                                 rule_index))
    return out


def x_check_reuse__mutmut_54(added, reused, rule_index):
    claims = [c for c in (reused or []) if c and not str(c).startswith("<")]
    if not claims:
        return []
    # 精确成员匹配：避免子串误碰（如声明 get_profile 被 get_profile_v2 假性命中）。
    # 残留：分词不剥注释/字符串，名字出现在注释里仍算命中——属 advisory 误差，跨语言精确剥离不划算。
    present = _identifiers("\n".join(t for lines in added.values() for _, t in lines))
    out = []
    for claim in claims:
        toks = re.findall(r"[A-Za-z_][A-Za-z0-9_.]+", str(claim))
        names = {tok for t in toks for tok in (t, t.split(".")[-1])}
        if names and not (names & present):
            out.append(_finding("DUP-001", "(diff)", 0, "duplication",
                                 f"提交契约声称复用「{claim}」，但新增代码中未见对应引用"
                                 "（申报不实/疑似重复造轮子）",
                                 "XX确认确实复用既有能力并在代码中引用，或如实更新 reused_componentsXX",
                                 rule_index))
    return out


def x_check_reuse__mutmut_55(added, reused, rule_index):
    claims = [c for c in (reused or []) if c and not str(c).startswith("<")]
    if not claims:
        return []
    # 精确成员匹配：避免子串误碰（如声明 get_profile 被 get_profile_v2 假性命中）。
    # 残留：分词不剥注释/字符串，名字出现在注释里仍算命中——属 advisory 误差，跨语言精确剥离不划算。
    present = _identifiers("\n".join(t for lines in added.values() for _, t in lines))
    out = []
    for claim in claims:
        toks = re.findall(r"[A-Za-z_][A-Za-z0-9_.]+", str(claim))
        names = {tok for t in toks for tok in (t, t.split(".")[-1])}
        if names and not (names & present):
            out.append(_finding("DUP-001", "(diff)", 0, "duplication",
                                 f"提交契约声称复用「{claim}」，但新增代码中未见对应引用"
                                 "（申报不实/疑似重复造轮子）",
                                 "确认确实复用既有能力并在代码中引用，或如实更新 REUSED_COMPONENTS",
                                 rule_index))
    return out

mutants_x_check_reuse__mutmut['_mutmut_orig'] = x_check_reuse__mutmut_orig # type: ignore # mutmut generated
mutants_x_check_reuse__mutmut['x_check_reuse__mutmut_1'] = x_check_reuse__mutmut_1 # type: ignore # mutmut generated
mutants_x_check_reuse__mutmut['x_check_reuse__mutmut_2'] = x_check_reuse__mutmut_2 # type: ignore # mutmut generated
mutants_x_check_reuse__mutmut['x_check_reuse__mutmut_3'] = x_check_reuse__mutmut_3 # type: ignore # mutmut generated
mutants_x_check_reuse__mutmut['x_check_reuse__mutmut_4'] = x_check_reuse__mutmut_4 # type: ignore # mutmut generated
mutants_x_check_reuse__mutmut['x_check_reuse__mutmut_5'] = x_check_reuse__mutmut_5 # type: ignore # mutmut generated
mutants_x_check_reuse__mutmut['x_check_reuse__mutmut_6'] = x_check_reuse__mutmut_6 # type: ignore # mutmut generated
mutants_x_check_reuse__mutmut['x_check_reuse__mutmut_7'] = x_check_reuse__mutmut_7 # type: ignore # mutmut generated
mutants_x_check_reuse__mutmut['x_check_reuse__mutmut_8'] = x_check_reuse__mutmut_8 # type: ignore # mutmut generated
mutants_x_check_reuse__mutmut['x_check_reuse__mutmut_9'] = x_check_reuse__mutmut_9 # type: ignore # mutmut generated
mutants_x_check_reuse__mutmut['x_check_reuse__mutmut_10'] = x_check_reuse__mutmut_10 # type: ignore # mutmut generated
mutants_x_check_reuse__mutmut['x_check_reuse__mutmut_11'] = x_check_reuse__mutmut_11 # type: ignore # mutmut generated
mutants_x_check_reuse__mutmut['x_check_reuse__mutmut_12'] = x_check_reuse__mutmut_12 # type: ignore # mutmut generated
mutants_x_check_reuse__mutmut['x_check_reuse__mutmut_13'] = x_check_reuse__mutmut_13 # type: ignore # mutmut generated
mutants_x_check_reuse__mutmut['x_check_reuse__mutmut_14'] = x_check_reuse__mutmut_14 # type: ignore # mutmut generated
mutants_x_check_reuse__mutmut['x_check_reuse__mutmut_15'] = x_check_reuse__mutmut_15 # type: ignore # mutmut generated
mutants_x_check_reuse__mutmut['x_check_reuse__mutmut_16'] = x_check_reuse__mutmut_16 # type: ignore # mutmut generated
mutants_x_check_reuse__mutmut['x_check_reuse__mutmut_17'] = x_check_reuse__mutmut_17 # type: ignore # mutmut generated
mutants_x_check_reuse__mutmut['x_check_reuse__mutmut_18'] = x_check_reuse__mutmut_18 # type: ignore # mutmut generated
mutants_x_check_reuse__mutmut['x_check_reuse__mutmut_19'] = x_check_reuse__mutmut_19 # type: ignore # mutmut generated
mutants_x_check_reuse__mutmut['x_check_reuse__mutmut_20'] = x_check_reuse__mutmut_20 # type: ignore # mutmut generated
mutants_x_check_reuse__mutmut['x_check_reuse__mutmut_21'] = x_check_reuse__mutmut_21 # type: ignore # mutmut generated
mutants_x_check_reuse__mutmut['x_check_reuse__mutmut_22'] = x_check_reuse__mutmut_22 # type: ignore # mutmut generated
mutants_x_check_reuse__mutmut['x_check_reuse__mutmut_23'] = x_check_reuse__mutmut_23 # type: ignore # mutmut generated
mutants_x_check_reuse__mutmut['x_check_reuse__mutmut_24'] = x_check_reuse__mutmut_24 # type: ignore # mutmut generated
mutants_x_check_reuse__mutmut['x_check_reuse__mutmut_25'] = x_check_reuse__mutmut_25 # type: ignore # mutmut generated
mutants_x_check_reuse__mutmut['x_check_reuse__mutmut_26'] = x_check_reuse__mutmut_26 # type: ignore # mutmut generated
mutants_x_check_reuse__mutmut['x_check_reuse__mutmut_27'] = x_check_reuse__mutmut_27 # type: ignore # mutmut generated
mutants_x_check_reuse__mutmut['x_check_reuse__mutmut_28'] = x_check_reuse__mutmut_28 # type: ignore # mutmut generated
mutants_x_check_reuse__mutmut['x_check_reuse__mutmut_29'] = x_check_reuse__mutmut_29 # type: ignore # mutmut generated
mutants_x_check_reuse__mutmut['x_check_reuse__mutmut_30'] = x_check_reuse__mutmut_30 # type: ignore # mutmut generated
mutants_x_check_reuse__mutmut['x_check_reuse__mutmut_31'] = x_check_reuse__mutmut_31 # type: ignore # mutmut generated
mutants_x_check_reuse__mutmut['x_check_reuse__mutmut_32'] = x_check_reuse__mutmut_32 # type: ignore # mutmut generated
mutants_x_check_reuse__mutmut['x_check_reuse__mutmut_33'] = x_check_reuse__mutmut_33 # type: ignore # mutmut generated
mutants_x_check_reuse__mutmut['x_check_reuse__mutmut_34'] = x_check_reuse__mutmut_34 # type: ignore # mutmut generated
mutants_x_check_reuse__mutmut['x_check_reuse__mutmut_35'] = x_check_reuse__mutmut_35 # type: ignore # mutmut generated
mutants_x_check_reuse__mutmut['x_check_reuse__mutmut_36'] = x_check_reuse__mutmut_36 # type: ignore # mutmut generated
mutants_x_check_reuse__mutmut['x_check_reuse__mutmut_37'] = x_check_reuse__mutmut_37 # type: ignore # mutmut generated
mutants_x_check_reuse__mutmut['x_check_reuse__mutmut_38'] = x_check_reuse__mutmut_38 # type: ignore # mutmut generated
mutants_x_check_reuse__mutmut['x_check_reuse__mutmut_39'] = x_check_reuse__mutmut_39 # type: ignore # mutmut generated
mutants_x_check_reuse__mutmut['x_check_reuse__mutmut_40'] = x_check_reuse__mutmut_40 # type: ignore # mutmut generated
mutants_x_check_reuse__mutmut['x_check_reuse__mutmut_41'] = x_check_reuse__mutmut_41 # type: ignore # mutmut generated
mutants_x_check_reuse__mutmut['x_check_reuse__mutmut_42'] = x_check_reuse__mutmut_42 # type: ignore # mutmut generated
mutants_x_check_reuse__mutmut['x_check_reuse__mutmut_43'] = x_check_reuse__mutmut_43 # type: ignore # mutmut generated
mutants_x_check_reuse__mutmut['x_check_reuse__mutmut_44'] = x_check_reuse__mutmut_44 # type: ignore # mutmut generated
mutants_x_check_reuse__mutmut['x_check_reuse__mutmut_45'] = x_check_reuse__mutmut_45 # type: ignore # mutmut generated
mutants_x_check_reuse__mutmut['x_check_reuse__mutmut_46'] = x_check_reuse__mutmut_46 # type: ignore # mutmut generated
mutants_x_check_reuse__mutmut['x_check_reuse__mutmut_47'] = x_check_reuse__mutmut_47 # type: ignore # mutmut generated
mutants_x_check_reuse__mutmut['x_check_reuse__mutmut_48'] = x_check_reuse__mutmut_48 # type: ignore # mutmut generated
mutants_x_check_reuse__mutmut['x_check_reuse__mutmut_49'] = x_check_reuse__mutmut_49 # type: ignore # mutmut generated
mutants_x_check_reuse__mutmut['x_check_reuse__mutmut_50'] = x_check_reuse__mutmut_50 # type: ignore # mutmut generated
mutants_x_check_reuse__mutmut['x_check_reuse__mutmut_51'] = x_check_reuse__mutmut_51 # type: ignore # mutmut generated
mutants_x_check_reuse__mutmut['x_check_reuse__mutmut_52'] = x_check_reuse__mutmut_52 # type: ignore # mutmut generated
mutants_x_check_reuse__mutmut['x_check_reuse__mutmut_53'] = x_check_reuse__mutmut_53 # type: ignore # mutmut generated
mutants_x_check_reuse__mutmut['x_check_reuse__mutmut_54'] = x_check_reuse__mutmut_54 # type: ignore # mutmut generated
mutants_x_check_reuse__mutmut['x_check_reuse__mutmut_55'] = x_check_reuse__mutmut_55 # type: ignore # mutmut generated


_CODE_EXT = {".java", ".kt", ".py", ".go", ".ts", ".tsx", ".js", ".jsx", ".rs", ".scala"}
mutants_x__is_test__mutmut: MutantDict = {}  # type: ignore


@_mutmut_mutated(mutants_x__is_test__mutmut)
def _is_test(p):
    return "test" in p.lower() or "spec" in p.lower()


def x__is_test__mutmut_orig(p):
    return "test" in p.lower() or "spec" in p.lower()


def x__is_test__mutmut_1(p):
    return "test" in p.lower() and "spec" in p.lower()


def x__is_test__mutmut_2(p):
    return "XXtestXX" in p.lower() or "spec" in p.lower()


def x__is_test__mutmut_3(p):
    return "TEST" in p.lower() or "spec" in p.lower()


def x__is_test__mutmut_4(p):
    return "test" not in p.lower() or "spec" in p.lower()


def x__is_test__mutmut_5(p):
    return "test" in p.upper() or "spec" in p.lower()


def x__is_test__mutmut_6(p):
    return "test" in p.lower() or "XXspecXX" in p.lower()


def x__is_test__mutmut_7(p):
    return "test" in p.lower() or "SPEC" in p.lower()


def x__is_test__mutmut_8(p):
    return "test" in p.lower() or "spec" not in p.lower()


def x__is_test__mutmut_9(p):
    return "test" in p.lower() or "spec" in p.upper()

mutants_x__is_test__mutmut['_mutmut_orig'] = x__is_test__mutmut_orig # type: ignore # mutmut generated
mutants_x__is_test__mutmut['x__is_test__mutmut_1'] = x__is_test__mutmut_1 # type: ignore # mutmut generated
mutants_x__is_test__mutmut['x__is_test__mutmut_2'] = x__is_test__mutmut_2 # type: ignore # mutmut generated
mutants_x__is_test__mutmut['x__is_test__mutmut_3'] = x__is_test__mutmut_3 # type: ignore # mutmut generated
mutants_x__is_test__mutmut['x__is_test__mutmut_4'] = x__is_test__mutmut_4 # type: ignore # mutmut generated
mutants_x__is_test__mutmut['x__is_test__mutmut_5'] = x__is_test__mutmut_5 # type: ignore # mutmut generated
mutants_x__is_test__mutmut['x__is_test__mutmut_6'] = x__is_test__mutmut_6 # type: ignore # mutmut generated
mutants_x__is_test__mutmut['x__is_test__mutmut_7'] = x__is_test__mutmut_7 # type: ignore # mutmut generated
mutants_x__is_test__mutmut['x__is_test__mutmut_8'] = x__is_test__mutmut_8 # type: ignore # mutmut generated
mutants_x__is_test__mutmut['x__is_test__mutmut_9'] = x__is_test__mutmut_9 # type: ignore # mutmut generated
mutants_x_check_untested_code__mutmut: MutantDict = {}  # type: ignore


@_mutmut_mutated(mutants_x_check_untested_code__mutmut)
def check_untested_code(files, rule_index):
    """纯 diff 事实检查（不依赖 manifest）：改动含代码文件但 diff 中无任何测试文件。
    陈述事实(置信高)、严重度仅 warn——是否真需要测试由委员会/人判。"""
    code = [f for f in sorted(files)
            if os.path.splitext(f)[1] in _CODE_EXT and not _is_test(f)]
    tests = [f for f in files if _is_test(f)]
    if code and not tests:
        return [_finding("TEST-001", code[0], 0, "weak_test",
                         "改动包含代码文件，但 diff 中无任何测试文件改动（疑似缺测试）",
                         "为本次改动补充有意义断言的测试；若确无需测试请在 PR 说明缘由",
                         rule_index, confidence=0.9, severity="warn")]
    return []


def x_check_untested_code__mutmut_orig(files, rule_index):
    """纯 diff 事实检查（不依赖 manifest）：改动含代码文件但 diff 中无任何测试文件。
    陈述事实(置信高)、严重度仅 warn——是否真需要测试由委员会/人判。"""
    code = [f for f in sorted(files)
            if os.path.splitext(f)[1] in _CODE_EXT and not _is_test(f)]
    tests = [f for f in files if _is_test(f)]
    if code and not tests:
        return [_finding("TEST-001", code[0], 0, "weak_test",
                         "改动包含代码文件，但 diff 中无任何测试文件改动（疑似缺测试）",
                         "为本次改动补充有意义断言的测试；若确无需测试请在 PR 说明缘由",
                         rule_index, confidence=0.9, severity="warn")]
    return []


def x_check_untested_code__mutmut_1(files, rule_index):
    """纯 diff 事实检查（不依赖 manifest）：改动含代码文件但 diff 中无任何测试文件。
    陈述事实(置信高)、严重度仅 warn——是否真需要测试由委员会/人判。"""
    code = None
    tests = [f for f in files if _is_test(f)]
    if code and not tests:
        return [_finding("TEST-001", code[0], 0, "weak_test",
                         "改动包含代码文件，但 diff 中无任何测试文件改动（疑似缺测试）",
                         "为本次改动补充有意义断言的测试；若确无需测试请在 PR 说明缘由",
                         rule_index, confidence=0.9, severity="warn")]
    return []


def x_check_untested_code__mutmut_2(files, rule_index):
    """纯 diff 事实检查（不依赖 manifest）：改动含代码文件但 diff 中无任何测试文件。
    陈述事实(置信高)、严重度仅 warn——是否真需要测试由委员会/人判。"""
    code = [f for f in sorted(None)
            if os.path.splitext(f)[1] in _CODE_EXT and not _is_test(f)]
    tests = [f for f in files if _is_test(f)]
    if code and not tests:
        return [_finding("TEST-001", code[0], 0, "weak_test",
                         "改动包含代码文件，但 diff 中无任何测试文件改动（疑似缺测试）",
                         "为本次改动补充有意义断言的测试；若确无需测试请在 PR 说明缘由",
                         rule_index, confidence=0.9, severity="warn")]
    return []


def x_check_untested_code__mutmut_3(files, rule_index):
    """纯 diff 事实检查（不依赖 manifest）：改动含代码文件但 diff 中无任何测试文件。
    陈述事实(置信高)、严重度仅 warn——是否真需要测试由委员会/人判。"""
    code = [f for f in sorted(files)
            if os.path.splitext(f)[1] in _CODE_EXT or not _is_test(f)]
    tests = [f for f in files if _is_test(f)]
    if code and not tests:
        return [_finding("TEST-001", code[0], 0, "weak_test",
                         "改动包含代码文件，但 diff 中无任何测试文件改动（疑似缺测试）",
                         "为本次改动补充有意义断言的测试；若确无需测试请在 PR 说明缘由",
                         rule_index, confidence=0.9, severity="warn")]
    return []


def x_check_untested_code__mutmut_4(files, rule_index):
    """纯 diff 事实检查（不依赖 manifest）：改动含代码文件但 diff 中无任何测试文件。
    陈述事实(置信高)、严重度仅 warn——是否真需要测试由委员会/人判。"""
    code = [f for f in sorted(files)
            if os.path.splitext(None)[1] in _CODE_EXT and not _is_test(f)]
    tests = [f for f in files if _is_test(f)]
    if code and not tests:
        return [_finding("TEST-001", code[0], 0, "weak_test",
                         "改动包含代码文件，但 diff 中无任何测试文件改动（疑似缺测试）",
                         "为本次改动补充有意义断言的测试；若确无需测试请在 PR 说明缘由",
                         rule_index, confidence=0.9, severity="warn")]
    return []


def x_check_untested_code__mutmut_5(files, rule_index):
    """纯 diff 事实检查（不依赖 manifest）：改动含代码文件但 diff 中无任何测试文件。
    陈述事实(置信高)、严重度仅 warn——是否真需要测试由委员会/人判。"""
    code = [f for f in sorted(files)
            if os.path.splitext(f)[2] in _CODE_EXT and not _is_test(f)]
    tests = [f for f in files if _is_test(f)]
    if code and not tests:
        return [_finding("TEST-001", code[0], 0, "weak_test",
                         "改动包含代码文件，但 diff 中无任何测试文件改动（疑似缺测试）",
                         "为本次改动补充有意义断言的测试；若确无需测试请在 PR 说明缘由",
                         rule_index, confidence=0.9, severity="warn")]
    return []


def x_check_untested_code__mutmut_6(files, rule_index):
    """纯 diff 事实检查（不依赖 manifest）：改动含代码文件但 diff 中无任何测试文件。
    陈述事实(置信高)、严重度仅 warn——是否真需要测试由委员会/人判。"""
    code = [f for f in sorted(files)
            if os.path.splitext(f)[1] not in _CODE_EXT and not _is_test(f)]
    tests = [f for f in files if _is_test(f)]
    if code and not tests:
        return [_finding("TEST-001", code[0], 0, "weak_test",
                         "改动包含代码文件，但 diff 中无任何测试文件改动（疑似缺测试）",
                         "为本次改动补充有意义断言的测试；若确无需测试请在 PR 说明缘由",
                         rule_index, confidence=0.9, severity="warn")]
    return []


def x_check_untested_code__mutmut_7(files, rule_index):
    """纯 diff 事实检查（不依赖 manifest）：改动含代码文件但 diff 中无任何测试文件。
    陈述事实(置信高)、严重度仅 warn——是否真需要测试由委员会/人判。"""
    code = [f for f in sorted(files)
            if os.path.splitext(f)[1] in _CODE_EXT and _is_test(f)]
    tests = [f for f in files if _is_test(f)]
    if code and not tests:
        return [_finding("TEST-001", code[0], 0, "weak_test",
                         "改动包含代码文件，但 diff 中无任何测试文件改动（疑似缺测试）",
                         "为本次改动补充有意义断言的测试；若确无需测试请在 PR 说明缘由",
                         rule_index, confidence=0.9, severity="warn")]
    return []


def x_check_untested_code__mutmut_8(files, rule_index):
    """纯 diff 事实检查（不依赖 manifest）：改动含代码文件但 diff 中无任何测试文件。
    陈述事实(置信高)、严重度仅 warn——是否真需要测试由委员会/人判。"""
    code = [f for f in sorted(files)
            if os.path.splitext(f)[1] in _CODE_EXT and not _is_test(None)]
    tests = [f for f in files if _is_test(f)]
    if code and not tests:
        return [_finding("TEST-001", code[0], 0, "weak_test",
                         "改动包含代码文件，但 diff 中无任何测试文件改动（疑似缺测试）",
                         "为本次改动补充有意义断言的测试；若确无需测试请在 PR 说明缘由",
                         rule_index, confidence=0.9, severity="warn")]
    return []


def x_check_untested_code__mutmut_9(files, rule_index):
    """纯 diff 事实检查（不依赖 manifest）：改动含代码文件但 diff 中无任何测试文件。
    陈述事实(置信高)、严重度仅 warn——是否真需要测试由委员会/人判。"""
    code = [f for f in sorted(files)
            if os.path.splitext(f)[1] in _CODE_EXT and not _is_test(f)]
    tests = None
    if code and not tests:
        return [_finding("TEST-001", code[0], 0, "weak_test",
                         "改动包含代码文件，但 diff 中无任何测试文件改动（疑似缺测试）",
                         "为本次改动补充有意义断言的测试；若确无需测试请在 PR 说明缘由",
                         rule_index, confidence=0.9, severity="warn")]
    return []


def x_check_untested_code__mutmut_10(files, rule_index):
    """纯 diff 事实检查（不依赖 manifest）：改动含代码文件但 diff 中无任何测试文件。
    陈述事实(置信高)、严重度仅 warn——是否真需要测试由委员会/人判。"""
    code = [f for f in sorted(files)
            if os.path.splitext(f)[1] in _CODE_EXT and not _is_test(f)]
    tests = [f for f in files if _is_test(None)]
    if code and not tests:
        return [_finding("TEST-001", code[0], 0, "weak_test",
                         "改动包含代码文件，但 diff 中无任何测试文件改动（疑似缺测试）",
                         "为本次改动补充有意义断言的测试；若确无需测试请在 PR 说明缘由",
                         rule_index, confidence=0.9, severity="warn")]
    return []


def x_check_untested_code__mutmut_11(files, rule_index):
    """纯 diff 事实检查（不依赖 manifest）：改动含代码文件但 diff 中无任何测试文件。
    陈述事实(置信高)、严重度仅 warn——是否真需要测试由委员会/人判。"""
    code = [f for f in sorted(files)
            if os.path.splitext(f)[1] in _CODE_EXT and not _is_test(f)]
    tests = [f for f in files if _is_test(f)]
    if code or not tests:
        return [_finding("TEST-001", code[0], 0, "weak_test",
                         "改动包含代码文件，但 diff 中无任何测试文件改动（疑似缺测试）",
                         "为本次改动补充有意义断言的测试；若确无需测试请在 PR 说明缘由",
                         rule_index, confidence=0.9, severity="warn")]
    return []


def x_check_untested_code__mutmut_12(files, rule_index):
    """纯 diff 事实检查（不依赖 manifest）：改动含代码文件但 diff 中无任何测试文件。
    陈述事实(置信高)、严重度仅 warn——是否真需要测试由委员会/人判。"""
    code = [f for f in sorted(files)
            if os.path.splitext(f)[1] in _CODE_EXT and not _is_test(f)]
    tests = [f for f in files if _is_test(f)]
    if code and tests:
        return [_finding("TEST-001", code[0], 0, "weak_test",
                         "改动包含代码文件，但 diff 中无任何测试文件改动（疑似缺测试）",
                         "为本次改动补充有意义断言的测试；若确无需测试请在 PR 说明缘由",
                         rule_index, confidence=0.9, severity="warn")]
    return []


def x_check_untested_code__mutmut_13(files, rule_index):
    """纯 diff 事实检查（不依赖 manifest）：改动含代码文件但 diff 中无任何测试文件。
    陈述事实(置信高)、严重度仅 warn——是否真需要测试由委员会/人判。"""
    code = [f for f in sorted(files)
            if os.path.splitext(f)[1] in _CODE_EXT and not _is_test(f)]
    tests = [f for f in files if _is_test(f)]
    if code and not tests:
        return [_finding(None, code[0], 0, "weak_test",
                         "改动包含代码文件，但 diff 中无任何测试文件改动（疑似缺测试）",
                         "为本次改动补充有意义断言的测试；若确无需测试请在 PR 说明缘由",
                         rule_index, confidence=0.9, severity="warn")]
    return []


def x_check_untested_code__mutmut_14(files, rule_index):
    """纯 diff 事实检查（不依赖 manifest）：改动含代码文件但 diff 中无任何测试文件。
    陈述事实(置信高)、严重度仅 warn——是否真需要测试由委员会/人判。"""
    code = [f for f in sorted(files)
            if os.path.splitext(f)[1] in _CODE_EXT and not _is_test(f)]
    tests = [f for f in files if _is_test(f)]
    if code and not tests:
        return [_finding("TEST-001", None, 0, "weak_test",
                         "改动包含代码文件，但 diff 中无任何测试文件改动（疑似缺测试）",
                         "为本次改动补充有意义断言的测试；若确无需测试请在 PR 说明缘由",
                         rule_index, confidence=0.9, severity="warn")]
    return []


def x_check_untested_code__mutmut_15(files, rule_index):
    """纯 diff 事实检查（不依赖 manifest）：改动含代码文件但 diff 中无任何测试文件。
    陈述事实(置信高)、严重度仅 warn——是否真需要测试由委员会/人判。"""
    code = [f for f in sorted(files)
            if os.path.splitext(f)[1] in _CODE_EXT and not _is_test(f)]
    tests = [f for f in files if _is_test(f)]
    if code and not tests:
        return [_finding("TEST-001", code[0], None, "weak_test",
                         "改动包含代码文件，但 diff 中无任何测试文件改动（疑似缺测试）",
                         "为本次改动补充有意义断言的测试；若确无需测试请在 PR 说明缘由",
                         rule_index, confidence=0.9, severity="warn")]
    return []


def x_check_untested_code__mutmut_16(files, rule_index):
    """纯 diff 事实检查（不依赖 manifest）：改动含代码文件但 diff 中无任何测试文件。
    陈述事实(置信高)、严重度仅 warn——是否真需要测试由委员会/人判。"""
    code = [f for f in sorted(files)
            if os.path.splitext(f)[1] in _CODE_EXT and not _is_test(f)]
    tests = [f for f in files if _is_test(f)]
    if code and not tests:
        return [_finding("TEST-001", code[0], 0, None,
                         "改动包含代码文件，但 diff 中无任何测试文件改动（疑似缺测试）",
                         "为本次改动补充有意义断言的测试；若确无需测试请在 PR 说明缘由",
                         rule_index, confidence=0.9, severity="warn")]
    return []


def x_check_untested_code__mutmut_17(files, rule_index):
    """纯 diff 事实检查（不依赖 manifest）：改动含代码文件但 diff 中无任何测试文件。
    陈述事实(置信高)、严重度仅 warn——是否真需要测试由委员会/人判。"""
    code = [f for f in sorted(files)
            if os.path.splitext(f)[1] in _CODE_EXT and not _is_test(f)]
    tests = [f for f in files if _is_test(f)]
    if code and not tests:
        return [_finding("TEST-001", code[0], 0, "weak_test",
                         None,
                         "为本次改动补充有意义断言的测试；若确无需测试请在 PR 说明缘由",
                         rule_index, confidence=0.9, severity="warn")]
    return []


def x_check_untested_code__mutmut_18(files, rule_index):
    """纯 diff 事实检查（不依赖 manifest）：改动含代码文件但 diff 中无任何测试文件。
    陈述事实(置信高)、严重度仅 warn——是否真需要测试由委员会/人判。"""
    code = [f for f in sorted(files)
            if os.path.splitext(f)[1] in _CODE_EXT and not _is_test(f)]
    tests = [f for f in files if _is_test(f)]
    if code and not tests:
        return [_finding("TEST-001", code[0], 0, "weak_test",
                         "改动包含代码文件，但 diff 中无任何测试文件改动（疑似缺测试）",
                         None,
                         rule_index, confidence=0.9, severity="warn")]
    return []


def x_check_untested_code__mutmut_19(files, rule_index):
    """纯 diff 事实检查（不依赖 manifest）：改动含代码文件但 diff 中无任何测试文件。
    陈述事实(置信高)、严重度仅 warn——是否真需要测试由委员会/人判。"""
    code = [f for f in sorted(files)
            if os.path.splitext(f)[1] in _CODE_EXT and not _is_test(f)]
    tests = [f for f in files if _is_test(f)]
    if code and not tests:
        return [_finding("TEST-001", code[0], 0, "weak_test",
                         "改动包含代码文件，但 diff 中无任何测试文件改动（疑似缺测试）",
                         "为本次改动补充有意义断言的测试；若确无需测试请在 PR 说明缘由",
                         None, confidence=0.9, severity="warn")]
    return []


def x_check_untested_code__mutmut_20(files, rule_index):
    """纯 diff 事实检查（不依赖 manifest）：改动含代码文件但 diff 中无任何测试文件。
    陈述事实(置信高)、严重度仅 warn——是否真需要测试由委员会/人判。"""
    code = [f for f in sorted(files)
            if os.path.splitext(f)[1] in _CODE_EXT and not _is_test(f)]
    tests = [f for f in files if _is_test(f)]
    if code and not tests:
        return [_finding("TEST-001", code[0], 0, "weak_test",
                         "改动包含代码文件，但 diff 中无任何测试文件改动（疑似缺测试）",
                         "为本次改动补充有意义断言的测试；若确无需测试请在 PR 说明缘由",
                         rule_index, confidence=None, severity="warn")]
    return []


def x_check_untested_code__mutmut_21(files, rule_index):
    """纯 diff 事实检查（不依赖 manifest）：改动含代码文件但 diff 中无任何测试文件。
    陈述事实(置信高)、严重度仅 warn——是否真需要测试由委员会/人判。"""
    code = [f for f in sorted(files)
            if os.path.splitext(f)[1] in _CODE_EXT and not _is_test(f)]
    tests = [f for f in files if _is_test(f)]
    if code and not tests:
        return [_finding("TEST-001", code[0], 0, "weak_test",
                         "改动包含代码文件，但 diff 中无任何测试文件改动（疑似缺测试）",
                         "为本次改动补充有意义断言的测试；若确无需测试请在 PR 说明缘由",
                         rule_index, confidence=0.9, severity=None)]
    return []


def x_check_untested_code__mutmut_22(files, rule_index):
    """纯 diff 事实检查（不依赖 manifest）：改动含代码文件但 diff 中无任何测试文件。
    陈述事实(置信高)、严重度仅 warn——是否真需要测试由委员会/人判。"""
    code = [f for f in sorted(files)
            if os.path.splitext(f)[1] in _CODE_EXT and not _is_test(f)]
    tests = [f for f in files if _is_test(f)]
    if code and not tests:
        return [_finding(code[0], 0, "weak_test",
                         "改动包含代码文件，但 diff 中无任何测试文件改动（疑似缺测试）",
                         "为本次改动补充有意义断言的测试；若确无需测试请在 PR 说明缘由",
                         rule_index, confidence=0.9, severity="warn")]
    return []


def x_check_untested_code__mutmut_23(files, rule_index):
    """纯 diff 事实检查（不依赖 manifest）：改动含代码文件但 diff 中无任何测试文件。
    陈述事实(置信高)、严重度仅 warn——是否真需要测试由委员会/人判。"""
    code = [f for f in sorted(files)
            if os.path.splitext(f)[1] in _CODE_EXT and not _is_test(f)]
    tests = [f for f in files if _is_test(f)]
    if code and not tests:
        return [_finding("TEST-001", 0, "weak_test",
                         "改动包含代码文件，但 diff 中无任何测试文件改动（疑似缺测试）",
                         "为本次改动补充有意义断言的测试；若确无需测试请在 PR 说明缘由",
                         rule_index, confidence=0.9, severity="warn")]
    return []


def x_check_untested_code__mutmut_24(files, rule_index):
    """纯 diff 事实检查（不依赖 manifest）：改动含代码文件但 diff 中无任何测试文件。
    陈述事实(置信高)、严重度仅 warn——是否真需要测试由委员会/人判。"""
    code = [f for f in sorted(files)
            if os.path.splitext(f)[1] in _CODE_EXT and not _is_test(f)]
    tests = [f for f in files if _is_test(f)]
    if code and not tests:
        return [_finding("TEST-001", code[0], "weak_test",
                         "改动包含代码文件，但 diff 中无任何测试文件改动（疑似缺测试）",
                         "为本次改动补充有意义断言的测试；若确无需测试请在 PR 说明缘由",
                         rule_index, confidence=0.9, severity="warn")]
    return []


def x_check_untested_code__mutmut_25(files, rule_index):
    """纯 diff 事实检查（不依赖 manifest）：改动含代码文件但 diff 中无任何测试文件。
    陈述事实(置信高)、严重度仅 warn——是否真需要测试由委员会/人判。"""
    code = [f for f in sorted(files)
            if os.path.splitext(f)[1] in _CODE_EXT and not _is_test(f)]
    tests = [f for f in files if _is_test(f)]
    if code and not tests:
        return [_finding("TEST-001", code[0], 0, "改动包含代码文件，但 diff 中无任何测试文件改动（疑似缺测试）",
                         "为本次改动补充有意义断言的测试；若确无需测试请在 PR 说明缘由",
                         rule_index, confidence=0.9, severity="warn")]
    return []


def x_check_untested_code__mutmut_26(files, rule_index):
    """纯 diff 事实检查（不依赖 manifest）：改动含代码文件但 diff 中无任何测试文件。
    陈述事实(置信高)、严重度仅 warn——是否真需要测试由委员会/人判。"""
    code = [f for f in sorted(files)
            if os.path.splitext(f)[1] in _CODE_EXT and not _is_test(f)]
    tests = [f for f in files if _is_test(f)]
    if code and not tests:
        return [_finding("TEST-001", code[0], 0, "weak_test",
                         "为本次改动补充有意义断言的测试；若确无需测试请在 PR 说明缘由",
                         rule_index, confidence=0.9, severity="warn")]
    return []


def x_check_untested_code__mutmut_27(files, rule_index):
    """纯 diff 事实检查（不依赖 manifest）：改动含代码文件但 diff 中无任何测试文件。
    陈述事实(置信高)、严重度仅 warn——是否真需要测试由委员会/人判。"""
    code = [f for f in sorted(files)
            if os.path.splitext(f)[1] in _CODE_EXT and not _is_test(f)]
    tests = [f for f in files if _is_test(f)]
    if code and not tests:
        return [_finding("TEST-001", code[0], 0, "weak_test",
                         "改动包含代码文件，但 diff 中无任何测试文件改动（疑似缺测试）",
                         rule_index, confidence=0.9, severity="warn")]
    return []


def x_check_untested_code__mutmut_28(files, rule_index):
    """纯 diff 事实检查（不依赖 manifest）：改动含代码文件但 diff 中无任何测试文件。
    陈述事实(置信高)、严重度仅 warn——是否真需要测试由委员会/人判。"""
    code = [f for f in sorted(files)
            if os.path.splitext(f)[1] in _CODE_EXT and not _is_test(f)]
    tests = [f for f in files if _is_test(f)]
    if code and not tests:
        return [_finding("TEST-001", code[0], 0, "weak_test",
                         "改动包含代码文件，但 diff 中无任何测试文件改动（疑似缺测试）",
                         "为本次改动补充有意义断言的测试；若确无需测试请在 PR 说明缘由",
                         confidence=0.9, severity="warn")]
    return []


def x_check_untested_code__mutmut_29(files, rule_index):
    """纯 diff 事实检查（不依赖 manifest）：改动含代码文件但 diff 中无任何测试文件。
    陈述事实(置信高)、严重度仅 warn——是否真需要测试由委员会/人判。"""
    code = [f for f in sorted(files)
            if os.path.splitext(f)[1] in _CODE_EXT and not _is_test(f)]
    tests = [f for f in files if _is_test(f)]
    if code and not tests:
        return [_finding("TEST-001", code[0], 0, "weak_test",
                         "改动包含代码文件，但 diff 中无任何测试文件改动（疑似缺测试）",
                         "为本次改动补充有意义断言的测试；若确无需测试请在 PR 说明缘由",
                         rule_index, severity="warn")]
    return []


def x_check_untested_code__mutmut_30(files, rule_index):
    """纯 diff 事实检查（不依赖 manifest）：改动含代码文件但 diff 中无任何测试文件。
    陈述事实(置信高)、严重度仅 warn——是否真需要测试由委员会/人判。"""
    code = [f for f in sorted(files)
            if os.path.splitext(f)[1] in _CODE_EXT and not _is_test(f)]
    tests = [f for f in files if _is_test(f)]
    if code and not tests:
        return [_finding("TEST-001", code[0], 0, "weak_test",
                         "改动包含代码文件，但 diff 中无任何测试文件改动（疑似缺测试）",
                         "为本次改动补充有意义断言的测试；若确无需测试请在 PR 说明缘由",
                         rule_index, confidence=0.9, )]
    return []


def x_check_untested_code__mutmut_31(files, rule_index):
    """纯 diff 事实检查（不依赖 manifest）：改动含代码文件但 diff 中无任何测试文件。
    陈述事实(置信高)、严重度仅 warn——是否真需要测试由委员会/人判。"""
    code = [f for f in sorted(files)
            if os.path.splitext(f)[1] in _CODE_EXT and not _is_test(f)]
    tests = [f for f in files if _is_test(f)]
    if code and not tests:
        return [_finding("XXTEST-001XX", code[0], 0, "weak_test",
                         "改动包含代码文件，但 diff 中无任何测试文件改动（疑似缺测试）",
                         "为本次改动补充有意义断言的测试；若确无需测试请在 PR 说明缘由",
                         rule_index, confidence=0.9, severity="warn")]
    return []


def x_check_untested_code__mutmut_32(files, rule_index):
    """纯 diff 事实检查（不依赖 manifest）：改动含代码文件但 diff 中无任何测试文件。
    陈述事实(置信高)、严重度仅 warn——是否真需要测试由委员会/人判。"""
    code = [f for f in sorted(files)
            if os.path.splitext(f)[1] in _CODE_EXT and not _is_test(f)]
    tests = [f for f in files if _is_test(f)]
    if code and not tests:
        return [_finding("test-001", code[0], 0, "weak_test",
                         "改动包含代码文件，但 diff 中无任何测试文件改动（疑似缺测试）",
                         "为本次改动补充有意义断言的测试；若确无需测试请在 PR 说明缘由",
                         rule_index, confidence=0.9, severity="warn")]
    return []


def x_check_untested_code__mutmut_33(files, rule_index):
    """纯 diff 事实检查（不依赖 manifest）：改动含代码文件但 diff 中无任何测试文件。
    陈述事实(置信高)、严重度仅 warn——是否真需要测试由委员会/人判。"""
    code = [f for f in sorted(files)
            if os.path.splitext(f)[1] in _CODE_EXT and not _is_test(f)]
    tests = [f for f in files if _is_test(f)]
    if code and not tests:
        return [_finding("TEST-001", code[1], 0, "weak_test",
                         "改动包含代码文件，但 diff 中无任何测试文件改动（疑似缺测试）",
                         "为本次改动补充有意义断言的测试；若确无需测试请在 PR 说明缘由",
                         rule_index, confidence=0.9, severity="warn")]
    return []


def x_check_untested_code__mutmut_34(files, rule_index):
    """纯 diff 事实检查（不依赖 manifest）：改动含代码文件但 diff 中无任何测试文件。
    陈述事实(置信高)、严重度仅 warn——是否真需要测试由委员会/人判。"""
    code = [f for f in sorted(files)
            if os.path.splitext(f)[1] in _CODE_EXT and not _is_test(f)]
    tests = [f for f in files if _is_test(f)]
    if code and not tests:
        return [_finding("TEST-001", code[0], 1, "weak_test",
                         "改动包含代码文件，但 diff 中无任何测试文件改动（疑似缺测试）",
                         "为本次改动补充有意义断言的测试；若确无需测试请在 PR 说明缘由",
                         rule_index, confidence=0.9, severity="warn")]
    return []


def x_check_untested_code__mutmut_35(files, rule_index):
    """纯 diff 事实检查（不依赖 manifest）：改动含代码文件但 diff 中无任何测试文件。
    陈述事实(置信高)、严重度仅 warn——是否真需要测试由委员会/人判。"""
    code = [f for f in sorted(files)
            if os.path.splitext(f)[1] in _CODE_EXT and not _is_test(f)]
    tests = [f for f in files if _is_test(f)]
    if code and not tests:
        return [_finding("TEST-001", code[0], 0, "XXweak_testXX",
                         "改动包含代码文件，但 diff 中无任何测试文件改动（疑似缺测试）",
                         "为本次改动补充有意义断言的测试；若确无需测试请在 PR 说明缘由",
                         rule_index, confidence=0.9, severity="warn")]
    return []


def x_check_untested_code__mutmut_36(files, rule_index):
    """纯 diff 事实检查（不依赖 manifest）：改动含代码文件但 diff 中无任何测试文件。
    陈述事实(置信高)、严重度仅 warn——是否真需要测试由委员会/人判。"""
    code = [f for f in sorted(files)
            if os.path.splitext(f)[1] in _CODE_EXT and not _is_test(f)]
    tests = [f for f in files if _is_test(f)]
    if code and not tests:
        return [_finding("TEST-001", code[0], 0, "WEAK_TEST",
                         "改动包含代码文件，但 diff 中无任何测试文件改动（疑似缺测试）",
                         "为本次改动补充有意义断言的测试；若确无需测试请在 PR 说明缘由",
                         rule_index, confidence=0.9, severity="warn")]
    return []


def x_check_untested_code__mutmut_37(files, rule_index):
    """纯 diff 事实检查（不依赖 manifest）：改动含代码文件但 diff 中无任何测试文件。
    陈述事实(置信高)、严重度仅 warn——是否真需要测试由委员会/人判。"""
    code = [f for f in sorted(files)
            if os.path.splitext(f)[1] in _CODE_EXT and not _is_test(f)]
    tests = [f for f in files if _is_test(f)]
    if code and not tests:
        return [_finding("TEST-001", code[0], 0, "weak_test",
                         "XX改动包含代码文件，但 diff 中无任何测试文件改动（疑似缺测试）XX",
                         "为本次改动补充有意义断言的测试；若确无需测试请在 PR 说明缘由",
                         rule_index, confidence=0.9, severity="warn")]
    return []


def x_check_untested_code__mutmut_38(files, rule_index):
    """纯 diff 事实检查（不依赖 manifest）：改动含代码文件但 diff 中无任何测试文件。
    陈述事实(置信高)、严重度仅 warn——是否真需要测试由委员会/人判。"""
    code = [f for f in sorted(files)
            if os.path.splitext(f)[1] in _CODE_EXT and not _is_test(f)]
    tests = [f for f in files if _is_test(f)]
    if code and not tests:
        return [_finding("TEST-001", code[0], 0, "weak_test",
                         "改动包含代码文件，但 DIFF 中无任何测试文件改动（疑似缺测试）",
                         "为本次改动补充有意义断言的测试；若确无需测试请在 PR 说明缘由",
                         rule_index, confidence=0.9, severity="warn")]
    return []


def x_check_untested_code__mutmut_39(files, rule_index):
    """纯 diff 事实检查（不依赖 manifest）：改动含代码文件但 diff 中无任何测试文件。
    陈述事实(置信高)、严重度仅 warn——是否真需要测试由委员会/人判。"""
    code = [f for f in sorted(files)
            if os.path.splitext(f)[1] in _CODE_EXT and not _is_test(f)]
    tests = [f for f in files if _is_test(f)]
    if code and not tests:
        return [_finding("TEST-001", code[0], 0, "weak_test",
                         "改动包含代码文件，但 diff 中无任何测试文件改动（疑似缺测试）",
                         "XX为本次改动补充有意义断言的测试；若确无需测试请在 PR 说明缘由XX",
                         rule_index, confidence=0.9, severity="warn")]
    return []


def x_check_untested_code__mutmut_40(files, rule_index):
    """纯 diff 事实检查（不依赖 manifest）：改动含代码文件但 diff 中无任何测试文件。
    陈述事实(置信高)、严重度仅 warn——是否真需要测试由委员会/人判。"""
    code = [f for f in sorted(files)
            if os.path.splitext(f)[1] in _CODE_EXT and not _is_test(f)]
    tests = [f for f in files if _is_test(f)]
    if code and not tests:
        return [_finding("TEST-001", code[0], 0, "weak_test",
                         "改动包含代码文件，但 diff 中无任何测试文件改动（疑似缺测试）",
                         "为本次改动补充有意义断言的测试；若确无需测试请在 pr 说明缘由",
                         rule_index, confidence=0.9, severity="warn")]
    return []


def x_check_untested_code__mutmut_41(files, rule_index):
    """纯 diff 事实检查（不依赖 manifest）：改动含代码文件但 diff 中无任何测试文件。
    陈述事实(置信高)、严重度仅 warn——是否真需要测试由委员会/人判。"""
    code = [f for f in sorted(files)
            if os.path.splitext(f)[1] in _CODE_EXT and not _is_test(f)]
    tests = [f for f in files if _is_test(f)]
    if code and not tests:
        return [_finding("TEST-001", code[0], 0, "weak_test",
                         "改动包含代码文件，但 diff 中无任何测试文件改动（疑似缺测试）",
                         "为本次改动补充有意义断言的测试；若确无需测试请在 PR 说明缘由",
                         rule_index, confidence=1.9, severity="warn")]
    return []


def x_check_untested_code__mutmut_42(files, rule_index):
    """纯 diff 事实检查（不依赖 manifest）：改动含代码文件但 diff 中无任何测试文件。
    陈述事实(置信高)、严重度仅 warn——是否真需要测试由委员会/人判。"""
    code = [f for f in sorted(files)
            if os.path.splitext(f)[1] in _CODE_EXT and not _is_test(f)]
    tests = [f for f in files if _is_test(f)]
    if code and not tests:
        return [_finding("TEST-001", code[0], 0, "weak_test",
                         "改动包含代码文件，但 diff 中无任何测试文件改动（疑似缺测试）",
                         "为本次改动补充有意义断言的测试；若确无需测试请在 PR 说明缘由",
                         rule_index, confidence=0.9, severity="XXwarnXX")]
    return []


def x_check_untested_code__mutmut_43(files, rule_index):
    """纯 diff 事实检查（不依赖 manifest）：改动含代码文件但 diff 中无任何测试文件。
    陈述事实(置信高)、严重度仅 warn——是否真需要测试由委员会/人判。"""
    code = [f for f in sorted(files)
            if os.path.splitext(f)[1] in _CODE_EXT and not _is_test(f)]
    tests = [f for f in files if _is_test(f)]
    if code and not tests:
        return [_finding("TEST-001", code[0], 0, "weak_test",
                         "改动包含代码文件，但 diff 中无任何测试文件改动（疑似缺测试）",
                         "为本次改动补充有意义断言的测试；若确无需测试请在 PR 说明缘由",
                         rule_index, confidence=0.9, severity="WARN")]
    return []

mutants_x_check_untested_code__mutmut['_mutmut_orig'] = x_check_untested_code__mutmut_orig # type: ignore # mutmut generated
mutants_x_check_untested_code__mutmut['x_check_untested_code__mutmut_1'] = x_check_untested_code__mutmut_1 # type: ignore # mutmut generated
mutants_x_check_untested_code__mutmut['x_check_untested_code__mutmut_2'] = x_check_untested_code__mutmut_2 # type: ignore # mutmut generated
mutants_x_check_untested_code__mutmut['x_check_untested_code__mutmut_3'] = x_check_untested_code__mutmut_3 # type: ignore # mutmut generated
mutants_x_check_untested_code__mutmut['x_check_untested_code__mutmut_4'] = x_check_untested_code__mutmut_4 # type: ignore # mutmut generated
mutants_x_check_untested_code__mutmut['x_check_untested_code__mutmut_5'] = x_check_untested_code__mutmut_5 # type: ignore # mutmut generated
mutants_x_check_untested_code__mutmut['x_check_untested_code__mutmut_6'] = x_check_untested_code__mutmut_6 # type: ignore # mutmut generated
mutants_x_check_untested_code__mutmut['x_check_untested_code__mutmut_7'] = x_check_untested_code__mutmut_7 # type: ignore # mutmut generated
mutants_x_check_untested_code__mutmut['x_check_untested_code__mutmut_8'] = x_check_untested_code__mutmut_8 # type: ignore # mutmut generated
mutants_x_check_untested_code__mutmut['x_check_untested_code__mutmut_9'] = x_check_untested_code__mutmut_9 # type: ignore # mutmut generated
mutants_x_check_untested_code__mutmut['x_check_untested_code__mutmut_10'] = x_check_untested_code__mutmut_10 # type: ignore # mutmut generated
mutants_x_check_untested_code__mutmut['x_check_untested_code__mutmut_11'] = x_check_untested_code__mutmut_11 # type: ignore # mutmut generated
mutants_x_check_untested_code__mutmut['x_check_untested_code__mutmut_12'] = x_check_untested_code__mutmut_12 # type: ignore # mutmut generated
mutants_x_check_untested_code__mutmut['x_check_untested_code__mutmut_13'] = x_check_untested_code__mutmut_13 # type: ignore # mutmut generated
mutants_x_check_untested_code__mutmut['x_check_untested_code__mutmut_14'] = x_check_untested_code__mutmut_14 # type: ignore # mutmut generated
mutants_x_check_untested_code__mutmut['x_check_untested_code__mutmut_15'] = x_check_untested_code__mutmut_15 # type: ignore # mutmut generated
mutants_x_check_untested_code__mutmut['x_check_untested_code__mutmut_16'] = x_check_untested_code__mutmut_16 # type: ignore # mutmut generated
mutants_x_check_untested_code__mutmut['x_check_untested_code__mutmut_17'] = x_check_untested_code__mutmut_17 # type: ignore # mutmut generated
mutants_x_check_untested_code__mutmut['x_check_untested_code__mutmut_18'] = x_check_untested_code__mutmut_18 # type: ignore # mutmut generated
mutants_x_check_untested_code__mutmut['x_check_untested_code__mutmut_19'] = x_check_untested_code__mutmut_19 # type: ignore # mutmut generated
mutants_x_check_untested_code__mutmut['x_check_untested_code__mutmut_20'] = x_check_untested_code__mutmut_20 # type: ignore # mutmut generated
mutants_x_check_untested_code__mutmut['x_check_untested_code__mutmut_21'] = x_check_untested_code__mutmut_21 # type: ignore # mutmut generated
mutants_x_check_untested_code__mutmut['x_check_untested_code__mutmut_22'] = x_check_untested_code__mutmut_22 # type: ignore # mutmut generated
mutants_x_check_untested_code__mutmut['x_check_untested_code__mutmut_23'] = x_check_untested_code__mutmut_23 # type: ignore # mutmut generated
mutants_x_check_untested_code__mutmut['x_check_untested_code__mutmut_24'] = x_check_untested_code__mutmut_24 # type: ignore # mutmut generated
mutants_x_check_untested_code__mutmut['x_check_untested_code__mutmut_25'] = x_check_untested_code__mutmut_25 # type: ignore # mutmut generated
mutants_x_check_untested_code__mutmut['x_check_untested_code__mutmut_26'] = x_check_untested_code__mutmut_26 # type: ignore # mutmut generated
mutants_x_check_untested_code__mutmut['x_check_untested_code__mutmut_27'] = x_check_untested_code__mutmut_27 # type: ignore # mutmut generated
mutants_x_check_untested_code__mutmut['x_check_untested_code__mutmut_28'] = x_check_untested_code__mutmut_28 # type: ignore # mutmut generated
mutants_x_check_untested_code__mutmut['x_check_untested_code__mutmut_29'] = x_check_untested_code__mutmut_29 # type: ignore # mutmut generated
mutants_x_check_untested_code__mutmut['x_check_untested_code__mutmut_30'] = x_check_untested_code__mutmut_30 # type: ignore # mutmut generated
mutants_x_check_untested_code__mutmut['x_check_untested_code__mutmut_31'] = x_check_untested_code__mutmut_31 # type: ignore # mutmut generated
mutants_x_check_untested_code__mutmut['x_check_untested_code__mutmut_32'] = x_check_untested_code__mutmut_32 # type: ignore # mutmut generated
mutants_x_check_untested_code__mutmut['x_check_untested_code__mutmut_33'] = x_check_untested_code__mutmut_33 # type: ignore # mutmut generated
mutants_x_check_untested_code__mutmut['x_check_untested_code__mutmut_34'] = x_check_untested_code__mutmut_34 # type: ignore # mutmut generated
mutants_x_check_untested_code__mutmut['x_check_untested_code__mutmut_35'] = x_check_untested_code__mutmut_35 # type: ignore # mutmut generated
mutants_x_check_untested_code__mutmut['x_check_untested_code__mutmut_36'] = x_check_untested_code__mutmut_36 # type: ignore # mutmut generated
mutants_x_check_untested_code__mutmut['x_check_untested_code__mutmut_37'] = x_check_untested_code__mutmut_37 # type: ignore # mutmut generated
mutants_x_check_untested_code__mutmut['x_check_untested_code__mutmut_38'] = x_check_untested_code__mutmut_38 # type: ignore # mutmut generated
mutants_x_check_untested_code__mutmut['x_check_untested_code__mutmut_39'] = x_check_untested_code__mutmut_39 # type: ignore # mutmut generated
mutants_x_check_untested_code__mutmut['x_check_untested_code__mutmut_40'] = x_check_untested_code__mutmut_40 # type: ignore # mutmut generated
mutants_x_check_untested_code__mutmut['x_check_untested_code__mutmut_41'] = x_check_untested_code__mutmut_41 # type: ignore # mutmut generated
mutants_x_check_untested_code__mutmut['x_check_untested_code__mutmut_42'] = x_check_untested_code__mutmut_42 # type: ignore # mutmut generated
mutants_x_check_untested_code__mutmut['x_check_untested_code__mutmut_43'] = x_check_untested_code__mutmut_43 # type: ignore # mutmut generated


# --- SEC-001：硬编码密钥/凭据（离线、确定性正则扫描）----------------------------
# 规则集【冻结】：只作离线兜底，不再新增模式——沿此路线扩张终点是维护一个更差的
# gitleaks。完整密钥扫描请经 checks.yaml 的 relay 检查挂 gitleaks/semgrep（见主设计 §4.7）。
# 高精度特征串（已知格式的云/Git 凭据 + PEM 私钥头 + 通用凭据赋值）。
# SEC-002（SQL/命令注入）是污点分析、需外部 SAST 数据流，不在此——经 checks.yaml relay 接入。
_SECRET_PATTERNS = [
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS access key id"),
    (re.compile(r"aws[_-]?secret[_-]?(?:access[_-]?key)?\s*[:=]\s*['\"][A-Za-z0-9/+=]{40}['\"]", re.I),
     "AWS secret access key"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36}\b"), "GitHub token"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{59,}"), "GitHub fine-grained PAT"),
    (re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"), "Google API key"),
    (re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----"), "PEM 私钥"),
    (re.compile(r"\bsk-proj-[A-Za-z0-9]{40,}\b"), "OpenAI API key"),
    (re.compile(r"\bsk-[A-Za-z0-9]{40,}\b"), "OpenAI legacy key"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"), "Slack token"),
    (re.compile(r"\bsk_live_[A-Za-z0-9]{24}\b"), "Stripe secret key"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"), "JWT token"),
    (re.compile(r"(?:api[_-]?key|secret|token|passwd|password|pwd)\b\s*[:=]\s*['\"]"
                r"([A-Za-z0-9_\-+/=]{16,})['\"]", re.I), "硬编码凭据赋值"),
]
# 占位符/示例值：命中则跳过，压低误报（确定性扫描宁可漏不误拦）。
_PLACEHOLDER = re.compile(
    r"(example|sample|changeme|changed?|placeholder|todo|xxxx|<[^>]+>|your[_-]?\w*"
    r"|_here\b|redacted|test|dummy|fake|replace[_-]?me)", re.I)
mutants_x_check_secrets__mutmut: MutantDict = {}  # type: ignore


@_mutmut_mutated(mutants_x_check_secrets__mutmut)
def check_secrets(added, rule_index):
    """SEC-001：扫新增行里的硬编码密钥/凭据（确定性、离线）。仅当 SEC-001 在册且 machine_checkable 时生效。
    产 finding(agent=contract-check, category=security, severity 取自规则=block_candidate) → 自动进确定性门禁。"""
    rule = rule_index.get("SEC-001", {})
    if not rule.get("machine_checkable"):
        return []
    out = []
    for path, lines in added.items():
        if _is_test(path):
            continue            # 测试文件里的密钥是故意夹具，不据此阻断（真实泄密仍由外部 SAST 兜底）
        for lineno, text in lines:
            for pat, label in _SECRET_PATTERNS:
                m = pat.search(text)
                if not m:
                    continue
                matched = m.group(1) if m.groups() else m.group(0)
                if _PLACEHOLDER.search(matched):       # 示例/占位值 → 跳过
                    continue
                out.append(_finding("SEC-001", path, lineno, "security",
                                    f"疑似硬编码凭据（{label}）—— 安全红线，凭据应走密钥管理",
                                    "将凭据移至环境变量/密钥管理服务；代码中勿入硬编码凭据",
                                    rule_index))
                break                                   # 一行最多报一条
    return out


def x_check_secrets__mutmut_orig(added, rule_index):
    """SEC-001：扫新增行里的硬编码密钥/凭据（确定性、离线）。仅当 SEC-001 在册且 machine_checkable 时生效。
    产 finding(agent=contract-check, category=security, severity 取自规则=block_candidate) → 自动进确定性门禁。"""
    rule = rule_index.get("SEC-001", {})
    if not rule.get("machine_checkable"):
        return []
    out = []
    for path, lines in added.items():
        if _is_test(path):
            continue            # 测试文件里的密钥是故意夹具，不据此阻断（真实泄密仍由外部 SAST 兜底）
        for lineno, text in lines:
            for pat, label in _SECRET_PATTERNS:
                m = pat.search(text)
                if not m:
                    continue
                matched = m.group(1) if m.groups() else m.group(0)
                if _PLACEHOLDER.search(matched):       # 示例/占位值 → 跳过
                    continue
                out.append(_finding("SEC-001", path, lineno, "security",
                                    f"疑似硬编码凭据（{label}）—— 安全红线，凭据应走密钥管理",
                                    "将凭据移至环境变量/密钥管理服务；代码中勿入硬编码凭据",
                                    rule_index))
                break                                   # 一行最多报一条
    return out


def x_check_secrets__mutmut_1(added, rule_index):
    """SEC-001：扫新增行里的硬编码密钥/凭据（确定性、离线）。仅当 SEC-001 在册且 machine_checkable 时生效。
    产 finding(agent=contract-check, category=security, severity 取自规则=block_candidate) → 自动进确定性门禁。"""
    rule = None
    if not rule.get("machine_checkable"):
        return []
    out = []
    for path, lines in added.items():
        if _is_test(path):
            continue            # 测试文件里的密钥是故意夹具，不据此阻断（真实泄密仍由外部 SAST 兜底）
        for lineno, text in lines:
            for pat, label in _SECRET_PATTERNS:
                m = pat.search(text)
                if not m:
                    continue
                matched = m.group(1) if m.groups() else m.group(0)
                if _PLACEHOLDER.search(matched):       # 示例/占位值 → 跳过
                    continue
                out.append(_finding("SEC-001", path, lineno, "security",
                                    f"疑似硬编码凭据（{label}）—— 安全红线，凭据应走密钥管理",
                                    "将凭据移至环境变量/密钥管理服务；代码中勿入硬编码凭据",
                                    rule_index))
                break                                   # 一行最多报一条
    return out


def x_check_secrets__mutmut_2(added, rule_index):
    """SEC-001：扫新增行里的硬编码密钥/凭据（确定性、离线）。仅当 SEC-001 在册且 machine_checkable 时生效。
    产 finding(agent=contract-check, category=security, severity 取自规则=block_candidate) → 自动进确定性门禁。"""
    rule = rule_index.get(None, {})
    if not rule.get("machine_checkable"):
        return []
    out = []
    for path, lines in added.items():
        if _is_test(path):
            continue            # 测试文件里的密钥是故意夹具，不据此阻断（真实泄密仍由外部 SAST 兜底）
        for lineno, text in lines:
            for pat, label in _SECRET_PATTERNS:
                m = pat.search(text)
                if not m:
                    continue
                matched = m.group(1) if m.groups() else m.group(0)
                if _PLACEHOLDER.search(matched):       # 示例/占位值 → 跳过
                    continue
                out.append(_finding("SEC-001", path, lineno, "security",
                                    f"疑似硬编码凭据（{label}）—— 安全红线，凭据应走密钥管理",
                                    "将凭据移至环境变量/密钥管理服务；代码中勿入硬编码凭据",
                                    rule_index))
                break                                   # 一行最多报一条
    return out


def x_check_secrets__mutmut_3(added, rule_index):
    """SEC-001：扫新增行里的硬编码密钥/凭据（确定性、离线）。仅当 SEC-001 在册且 machine_checkable 时生效。
    产 finding(agent=contract-check, category=security, severity 取自规则=block_candidate) → 自动进确定性门禁。"""
    rule = rule_index.get("SEC-001", None)
    if not rule.get("machine_checkable"):
        return []
    out = []
    for path, lines in added.items():
        if _is_test(path):
            continue            # 测试文件里的密钥是故意夹具，不据此阻断（真实泄密仍由外部 SAST 兜底）
        for lineno, text in lines:
            for pat, label in _SECRET_PATTERNS:
                m = pat.search(text)
                if not m:
                    continue
                matched = m.group(1) if m.groups() else m.group(0)
                if _PLACEHOLDER.search(matched):       # 示例/占位值 → 跳过
                    continue
                out.append(_finding("SEC-001", path, lineno, "security",
                                    f"疑似硬编码凭据（{label}）—— 安全红线，凭据应走密钥管理",
                                    "将凭据移至环境变量/密钥管理服务；代码中勿入硬编码凭据",
                                    rule_index))
                break                                   # 一行最多报一条
    return out


def x_check_secrets__mutmut_4(added, rule_index):
    """SEC-001：扫新增行里的硬编码密钥/凭据（确定性、离线）。仅当 SEC-001 在册且 machine_checkable 时生效。
    产 finding(agent=contract-check, category=security, severity 取自规则=block_candidate) → 自动进确定性门禁。"""
    rule = rule_index.get({})
    if not rule.get("machine_checkable"):
        return []
    out = []
    for path, lines in added.items():
        if _is_test(path):
            continue            # 测试文件里的密钥是故意夹具，不据此阻断（真实泄密仍由外部 SAST 兜底）
        for lineno, text in lines:
            for pat, label in _SECRET_PATTERNS:
                m = pat.search(text)
                if not m:
                    continue
                matched = m.group(1) if m.groups() else m.group(0)
                if _PLACEHOLDER.search(matched):       # 示例/占位值 → 跳过
                    continue
                out.append(_finding("SEC-001", path, lineno, "security",
                                    f"疑似硬编码凭据（{label}）—— 安全红线，凭据应走密钥管理",
                                    "将凭据移至环境变量/密钥管理服务；代码中勿入硬编码凭据",
                                    rule_index))
                break                                   # 一行最多报一条
    return out


def x_check_secrets__mutmut_5(added, rule_index):
    """SEC-001：扫新增行里的硬编码密钥/凭据（确定性、离线）。仅当 SEC-001 在册且 machine_checkable 时生效。
    产 finding(agent=contract-check, category=security, severity 取自规则=block_candidate) → 自动进确定性门禁。"""
    rule = rule_index.get("SEC-001", )
    if not rule.get("machine_checkable"):
        return []
    out = []
    for path, lines in added.items():
        if _is_test(path):
            continue            # 测试文件里的密钥是故意夹具，不据此阻断（真实泄密仍由外部 SAST 兜底）
        for lineno, text in lines:
            for pat, label in _SECRET_PATTERNS:
                m = pat.search(text)
                if not m:
                    continue
                matched = m.group(1) if m.groups() else m.group(0)
                if _PLACEHOLDER.search(matched):       # 示例/占位值 → 跳过
                    continue
                out.append(_finding("SEC-001", path, lineno, "security",
                                    f"疑似硬编码凭据（{label}）—— 安全红线，凭据应走密钥管理",
                                    "将凭据移至环境变量/密钥管理服务；代码中勿入硬编码凭据",
                                    rule_index))
                break                                   # 一行最多报一条
    return out


def x_check_secrets__mutmut_6(added, rule_index):
    """SEC-001：扫新增行里的硬编码密钥/凭据（确定性、离线）。仅当 SEC-001 在册且 machine_checkable 时生效。
    产 finding(agent=contract-check, category=security, severity 取自规则=block_candidate) → 自动进确定性门禁。"""
    rule = rule_index.get("XXSEC-001XX", {})
    if not rule.get("machine_checkable"):
        return []
    out = []
    for path, lines in added.items():
        if _is_test(path):
            continue            # 测试文件里的密钥是故意夹具，不据此阻断（真实泄密仍由外部 SAST 兜底）
        for lineno, text in lines:
            for pat, label in _SECRET_PATTERNS:
                m = pat.search(text)
                if not m:
                    continue
                matched = m.group(1) if m.groups() else m.group(0)
                if _PLACEHOLDER.search(matched):       # 示例/占位值 → 跳过
                    continue
                out.append(_finding("SEC-001", path, lineno, "security",
                                    f"疑似硬编码凭据（{label}）—— 安全红线，凭据应走密钥管理",
                                    "将凭据移至环境变量/密钥管理服务；代码中勿入硬编码凭据",
                                    rule_index))
                break                                   # 一行最多报一条
    return out


def x_check_secrets__mutmut_7(added, rule_index):
    """SEC-001：扫新增行里的硬编码密钥/凭据（确定性、离线）。仅当 SEC-001 在册且 machine_checkable 时生效。
    产 finding(agent=contract-check, category=security, severity 取自规则=block_candidate) → 自动进确定性门禁。"""
    rule = rule_index.get("sec-001", {})
    if not rule.get("machine_checkable"):
        return []
    out = []
    for path, lines in added.items():
        if _is_test(path):
            continue            # 测试文件里的密钥是故意夹具，不据此阻断（真实泄密仍由外部 SAST 兜底）
        for lineno, text in lines:
            for pat, label in _SECRET_PATTERNS:
                m = pat.search(text)
                if not m:
                    continue
                matched = m.group(1) if m.groups() else m.group(0)
                if _PLACEHOLDER.search(matched):       # 示例/占位值 → 跳过
                    continue
                out.append(_finding("SEC-001", path, lineno, "security",
                                    f"疑似硬编码凭据（{label}）—— 安全红线，凭据应走密钥管理",
                                    "将凭据移至环境变量/密钥管理服务；代码中勿入硬编码凭据",
                                    rule_index))
                break                                   # 一行最多报一条
    return out


def x_check_secrets__mutmut_8(added, rule_index):
    """SEC-001：扫新增行里的硬编码密钥/凭据（确定性、离线）。仅当 SEC-001 在册且 machine_checkable 时生效。
    产 finding(agent=contract-check, category=security, severity 取自规则=block_candidate) → 自动进确定性门禁。"""
    rule = rule_index.get("SEC-001", {})
    if rule.get("machine_checkable"):
        return []
    out = []
    for path, lines in added.items():
        if _is_test(path):
            continue            # 测试文件里的密钥是故意夹具，不据此阻断（真实泄密仍由外部 SAST 兜底）
        for lineno, text in lines:
            for pat, label in _SECRET_PATTERNS:
                m = pat.search(text)
                if not m:
                    continue
                matched = m.group(1) if m.groups() else m.group(0)
                if _PLACEHOLDER.search(matched):       # 示例/占位值 → 跳过
                    continue
                out.append(_finding("SEC-001", path, lineno, "security",
                                    f"疑似硬编码凭据（{label}）—— 安全红线，凭据应走密钥管理",
                                    "将凭据移至环境变量/密钥管理服务；代码中勿入硬编码凭据",
                                    rule_index))
                break                                   # 一行最多报一条
    return out


def x_check_secrets__mutmut_9(added, rule_index):
    """SEC-001：扫新增行里的硬编码密钥/凭据（确定性、离线）。仅当 SEC-001 在册且 machine_checkable 时生效。
    产 finding(agent=contract-check, category=security, severity 取自规则=block_candidate) → 自动进确定性门禁。"""
    rule = rule_index.get("SEC-001", {})
    if not rule.get(None):
        return []
    out = []
    for path, lines in added.items():
        if _is_test(path):
            continue            # 测试文件里的密钥是故意夹具，不据此阻断（真实泄密仍由外部 SAST 兜底）
        for lineno, text in lines:
            for pat, label in _SECRET_PATTERNS:
                m = pat.search(text)
                if not m:
                    continue
                matched = m.group(1) if m.groups() else m.group(0)
                if _PLACEHOLDER.search(matched):       # 示例/占位值 → 跳过
                    continue
                out.append(_finding("SEC-001", path, lineno, "security",
                                    f"疑似硬编码凭据（{label}）—— 安全红线，凭据应走密钥管理",
                                    "将凭据移至环境变量/密钥管理服务；代码中勿入硬编码凭据",
                                    rule_index))
                break                                   # 一行最多报一条
    return out


def x_check_secrets__mutmut_10(added, rule_index):
    """SEC-001：扫新增行里的硬编码密钥/凭据（确定性、离线）。仅当 SEC-001 在册且 machine_checkable 时生效。
    产 finding(agent=contract-check, category=security, severity 取自规则=block_candidate) → 自动进确定性门禁。"""
    rule = rule_index.get("SEC-001", {})
    if not rule.get("XXmachine_checkableXX"):
        return []
    out = []
    for path, lines in added.items():
        if _is_test(path):
            continue            # 测试文件里的密钥是故意夹具，不据此阻断（真实泄密仍由外部 SAST 兜底）
        for lineno, text in lines:
            for pat, label in _SECRET_PATTERNS:
                m = pat.search(text)
                if not m:
                    continue
                matched = m.group(1) if m.groups() else m.group(0)
                if _PLACEHOLDER.search(matched):       # 示例/占位值 → 跳过
                    continue
                out.append(_finding("SEC-001", path, lineno, "security",
                                    f"疑似硬编码凭据（{label}）—— 安全红线，凭据应走密钥管理",
                                    "将凭据移至环境变量/密钥管理服务；代码中勿入硬编码凭据",
                                    rule_index))
                break                                   # 一行最多报一条
    return out


def x_check_secrets__mutmut_11(added, rule_index):
    """SEC-001：扫新增行里的硬编码密钥/凭据（确定性、离线）。仅当 SEC-001 在册且 machine_checkable 时生效。
    产 finding(agent=contract-check, category=security, severity 取自规则=block_candidate) → 自动进确定性门禁。"""
    rule = rule_index.get("SEC-001", {})
    if not rule.get("MACHINE_CHECKABLE"):
        return []
    out = []
    for path, lines in added.items():
        if _is_test(path):
            continue            # 测试文件里的密钥是故意夹具，不据此阻断（真实泄密仍由外部 SAST 兜底）
        for lineno, text in lines:
            for pat, label in _SECRET_PATTERNS:
                m = pat.search(text)
                if not m:
                    continue
                matched = m.group(1) if m.groups() else m.group(0)
                if _PLACEHOLDER.search(matched):       # 示例/占位值 → 跳过
                    continue
                out.append(_finding("SEC-001", path, lineno, "security",
                                    f"疑似硬编码凭据（{label}）—— 安全红线，凭据应走密钥管理",
                                    "将凭据移至环境变量/密钥管理服务；代码中勿入硬编码凭据",
                                    rule_index))
                break                                   # 一行最多报一条
    return out


def x_check_secrets__mutmut_12(added, rule_index):
    """SEC-001：扫新增行里的硬编码密钥/凭据（确定性、离线）。仅当 SEC-001 在册且 machine_checkable 时生效。
    产 finding(agent=contract-check, category=security, severity 取自规则=block_candidate) → 自动进确定性门禁。"""
    rule = rule_index.get("SEC-001", {})
    if not rule.get("machine_checkable"):
        return []
    out = None
    for path, lines in added.items():
        if _is_test(path):
            continue            # 测试文件里的密钥是故意夹具，不据此阻断（真实泄密仍由外部 SAST 兜底）
        for lineno, text in lines:
            for pat, label in _SECRET_PATTERNS:
                m = pat.search(text)
                if not m:
                    continue
                matched = m.group(1) if m.groups() else m.group(0)
                if _PLACEHOLDER.search(matched):       # 示例/占位值 → 跳过
                    continue
                out.append(_finding("SEC-001", path, lineno, "security",
                                    f"疑似硬编码凭据（{label}）—— 安全红线，凭据应走密钥管理",
                                    "将凭据移至环境变量/密钥管理服务；代码中勿入硬编码凭据",
                                    rule_index))
                break                                   # 一行最多报一条
    return out


def x_check_secrets__mutmut_13(added, rule_index):
    """SEC-001：扫新增行里的硬编码密钥/凭据（确定性、离线）。仅当 SEC-001 在册且 machine_checkable 时生效。
    产 finding(agent=contract-check, category=security, severity 取自规则=block_candidate) → 自动进确定性门禁。"""
    rule = rule_index.get("SEC-001", {})
    if not rule.get("machine_checkable"):
        return []
    out = []
    for path, lines in added.items():
        if _is_test(None):
            continue            # 测试文件里的密钥是故意夹具，不据此阻断（真实泄密仍由外部 SAST 兜底）
        for lineno, text in lines:
            for pat, label in _SECRET_PATTERNS:
                m = pat.search(text)
                if not m:
                    continue
                matched = m.group(1) if m.groups() else m.group(0)
                if _PLACEHOLDER.search(matched):       # 示例/占位值 → 跳过
                    continue
                out.append(_finding("SEC-001", path, lineno, "security",
                                    f"疑似硬编码凭据（{label}）—— 安全红线，凭据应走密钥管理",
                                    "将凭据移至环境变量/密钥管理服务；代码中勿入硬编码凭据",
                                    rule_index))
                break                                   # 一行最多报一条
    return out


def x_check_secrets__mutmut_14(added, rule_index):
    """SEC-001：扫新增行里的硬编码密钥/凭据（确定性、离线）。仅当 SEC-001 在册且 machine_checkable 时生效。
    产 finding(agent=contract-check, category=security, severity 取自规则=block_candidate) → 自动进确定性门禁。"""
    rule = rule_index.get("SEC-001", {})
    if not rule.get("machine_checkable"):
        return []
    out = []
    for path, lines in added.items():
        if _is_test(path):
            break            # 测试文件里的密钥是故意夹具，不据此阻断（真实泄密仍由外部 SAST 兜底）
        for lineno, text in lines:
            for pat, label in _SECRET_PATTERNS:
                m = pat.search(text)
                if not m:
                    continue
                matched = m.group(1) if m.groups() else m.group(0)
                if _PLACEHOLDER.search(matched):       # 示例/占位值 → 跳过
                    continue
                out.append(_finding("SEC-001", path, lineno, "security",
                                    f"疑似硬编码凭据（{label}）—— 安全红线，凭据应走密钥管理",
                                    "将凭据移至环境变量/密钥管理服务；代码中勿入硬编码凭据",
                                    rule_index))
                break                                   # 一行最多报一条
    return out


def x_check_secrets__mutmut_15(added, rule_index):
    """SEC-001：扫新增行里的硬编码密钥/凭据（确定性、离线）。仅当 SEC-001 在册且 machine_checkable 时生效。
    产 finding(agent=contract-check, category=security, severity 取自规则=block_candidate) → 自动进确定性门禁。"""
    rule = rule_index.get("SEC-001", {})
    if not rule.get("machine_checkable"):
        return []
    out = []
    for path, lines in added.items():
        if _is_test(path):
            continue            # 测试文件里的密钥是故意夹具，不据此阻断（真实泄密仍由外部 SAST 兜底）
        for lineno, text in lines:
            for pat, label in _SECRET_PATTERNS:
                m = None
                if not m:
                    continue
                matched = m.group(1) if m.groups() else m.group(0)
                if _PLACEHOLDER.search(matched):       # 示例/占位值 → 跳过
                    continue
                out.append(_finding("SEC-001", path, lineno, "security",
                                    f"疑似硬编码凭据（{label}）—— 安全红线，凭据应走密钥管理",
                                    "将凭据移至环境变量/密钥管理服务；代码中勿入硬编码凭据",
                                    rule_index))
                break                                   # 一行最多报一条
    return out


def x_check_secrets__mutmut_16(added, rule_index):
    """SEC-001：扫新增行里的硬编码密钥/凭据（确定性、离线）。仅当 SEC-001 在册且 machine_checkable 时生效。
    产 finding(agent=contract-check, category=security, severity 取自规则=block_candidate) → 自动进确定性门禁。"""
    rule = rule_index.get("SEC-001", {})
    if not rule.get("machine_checkable"):
        return []
    out = []
    for path, lines in added.items():
        if _is_test(path):
            continue            # 测试文件里的密钥是故意夹具，不据此阻断（真实泄密仍由外部 SAST 兜底）
        for lineno, text in lines:
            for pat, label in _SECRET_PATTERNS:
                m = pat.search(None)
                if not m:
                    continue
                matched = m.group(1) if m.groups() else m.group(0)
                if _PLACEHOLDER.search(matched):       # 示例/占位值 → 跳过
                    continue
                out.append(_finding("SEC-001", path, lineno, "security",
                                    f"疑似硬编码凭据（{label}）—— 安全红线，凭据应走密钥管理",
                                    "将凭据移至环境变量/密钥管理服务；代码中勿入硬编码凭据",
                                    rule_index))
                break                                   # 一行最多报一条
    return out


def x_check_secrets__mutmut_17(added, rule_index):
    """SEC-001：扫新增行里的硬编码密钥/凭据（确定性、离线）。仅当 SEC-001 在册且 machine_checkable 时生效。
    产 finding(agent=contract-check, category=security, severity 取自规则=block_candidate) → 自动进确定性门禁。"""
    rule = rule_index.get("SEC-001", {})
    if not rule.get("machine_checkable"):
        return []
    out = []
    for path, lines in added.items():
        if _is_test(path):
            continue            # 测试文件里的密钥是故意夹具，不据此阻断（真实泄密仍由外部 SAST 兜底）
        for lineno, text in lines:
            for pat, label in _SECRET_PATTERNS:
                m = pat.search(text)
                if m:
                    continue
                matched = m.group(1) if m.groups() else m.group(0)
                if _PLACEHOLDER.search(matched):       # 示例/占位值 → 跳过
                    continue
                out.append(_finding("SEC-001", path, lineno, "security",
                                    f"疑似硬编码凭据（{label}）—— 安全红线，凭据应走密钥管理",
                                    "将凭据移至环境变量/密钥管理服务；代码中勿入硬编码凭据",
                                    rule_index))
                break                                   # 一行最多报一条
    return out


def x_check_secrets__mutmut_18(added, rule_index):
    """SEC-001：扫新增行里的硬编码密钥/凭据（确定性、离线）。仅当 SEC-001 在册且 machine_checkable 时生效。
    产 finding(agent=contract-check, category=security, severity 取自规则=block_candidate) → 自动进确定性门禁。"""
    rule = rule_index.get("SEC-001", {})
    if not rule.get("machine_checkable"):
        return []
    out = []
    for path, lines in added.items():
        if _is_test(path):
            continue            # 测试文件里的密钥是故意夹具，不据此阻断（真实泄密仍由外部 SAST 兜底）
        for lineno, text in lines:
            for pat, label in _SECRET_PATTERNS:
                m = pat.search(text)
                if not m:
                    break
                matched = m.group(1) if m.groups() else m.group(0)
                if _PLACEHOLDER.search(matched):       # 示例/占位值 → 跳过
                    continue
                out.append(_finding("SEC-001", path, lineno, "security",
                                    f"疑似硬编码凭据（{label}）—— 安全红线，凭据应走密钥管理",
                                    "将凭据移至环境变量/密钥管理服务；代码中勿入硬编码凭据",
                                    rule_index))
                break                                   # 一行最多报一条
    return out


def x_check_secrets__mutmut_19(added, rule_index):
    """SEC-001：扫新增行里的硬编码密钥/凭据（确定性、离线）。仅当 SEC-001 在册且 machine_checkable 时生效。
    产 finding(agent=contract-check, category=security, severity 取自规则=block_candidate) → 自动进确定性门禁。"""
    rule = rule_index.get("SEC-001", {})
    if not rule.get("machine_checkable"):
        return []
    out = []
    for path, lines in added.items():
        if _is_test(path):
            continue            # 测试文件里的密钥是故意夹具，不据此阻断（真实泄密仍由外部 SAST 兜底）
        for lineno, text in lines:
            for pat, label in _SECRET_PATTERNS:
                m = pat.search(text)
                if not m:
                    continue
                matched = None
                if _PLACEHOLDER.search(matched):       # 示例/占位值 → 跳过
                    continue
                out.append(_finding("SEC-001", path, lineno, "security",
                                    f"疑似硬编码凭据（{label}）—— 安全红线，凭据应走密钥管理",
                                    "将凭据移至环境变量/密钥管理服务；代码中勿入硬编码凭据",
                                    rule_index))
                break                                   # 一行最多报一条
    return out


def x_check_secrets__mutmut_20(added, rule_index):
    """SEC-001：扫新增行里的硬编码密钥/凭据（确定性、离线）。仅当 SEC-001 在册且 machine_checkable 时生效。
    产 finding(agent=contract-check, category=security, severity 取自规则=block_candidate) → 自动进确定性门禁。"""
    rule = rule_index.get("SEC-001", {})
    if not rule.get("machine_checkable"):
        return []
    out = []
    for path, lines in added.items():
        if _is_test(path):
            continue            # 测试文件里的密钥是故意夹具，不据此阻断（真实泄密仍由外部 SAST 兜底）
        for lineno, text in lines:
            for pat, label in _SECRET_PATTERNS:
                m = pat.search(text)
                if not m:
                    continue
                matched = m.group(None) if m.groups() else m.group(0)
                if _PLACEHOLDER.search(matched):       # 示例/占位值 → 跳过
                    continue
                out.append(_finding("SEC-001", path, lineno, "security",
                                    f"疑似硬编码凭据（{label}）—— 安全红线，凭据应走密钥管理",
                                    "将凭据移至环境变量/密钥管理服务；代码中勿入硬编码凭据",
                                    rule_index))
                break                                   # 一行最多报一条
    return out


def x_check_secrets__mutmut_21(added, rule_index):
    """SEC-001：扫新增行里的硬编码密钥/凭据（确定性、离线）。仅当 SEC-001 在册且 machine_checkable 时生效。
    产 finding(agent=contract-check, category=security, severity 取自规则=block_candidate) → 自动进确定性门禁。"""
    rule = rule_index.get("SEC-001", {})
    if not rule.get("machine_checkable"):
        return []
    out = []
    for path, lines in added.items():
        if _is_test(path):
            continue            # 测试文件里的密钥是故意夹具，不据此阻断（真实泄密仍由外部 SAST 兜底）
        for lineno, text in lines:
            for pat, label in _SECRET_PATTERNS:
                m = pat.search(text)
                if not m:
                    continue
                matched = m.group(2) if m.groups() else m.group(0)
                if _PLACEHOLDER.search(matched):       # 示例/占位值 → 跳过
                    continue
                out.append(_finding("SEC-001", path, lineno, "security",
                                    f"疑似硬编码凭据（{label}）—— 安全红线，凭据应走密钥管理",
                                    "将凭据移至环境变量/密钥管理服务；代码中勿入硬编码凭据",
                                    rule_index))
                break                                   # 一行最多报一条
    return out


def x_check_secrets__mutmut_22(added, rule_index):
    """SEC-001：扫新增行里的硬编码密钥/凭据（确定性、离线）。仅当 SEC-001 在册且 machine_checkable 时生效。
    产 finding(agent=contract-check, category=security, severity 取自规则=block_candidate) → 自动进确定性门禁。"""
    rule = rule_index.get("SEC-001", {})
    if not rule.get("machine_checkable"):
        return []
    out = []
    for path, lines in added.items():
        if _is_test(path):
            continue            # 测试文件里的密钥是故意夹具，不据此阻断（真实泄密仍由外部 SAST 兜底）
        for lineno, text in lines:
            for pat, label in _SECRET_PATTERNS:
                m = pat.search(text)
                if not m:
                    continue
                matched = m.group(1) if m.groups() else m.group(None)
                if _PLACEHOLDER.search(matched):       # 示例/占位值 → 跳过
                    continue
                out.append(_finding("SEC-001", path, lineno, "security",
                                    f"疑似硬编码凭据（{label}）—— 安全红线，凭据应走密钥管理",
                                    "将凭据移至环境变量/密钥管理服务；代码中勿入硬编码凭据",
                                    rule_index))
                break                                   # 一行最多报一条
    return out


def x_check_secrets__mutmut_23(added, rule_index):
    """SEC-001：扫新增行里的硬编码密钥/凭据（确定性、离线）。仅当 SEC-001 在册且 machine_checkable 时生效。
    产 finding(agent=contract-check, category=security, severity 取自规则=block_candidate) → 自动进确定性门禁。"""
    rule = rule_index.get("SEC-001", {})
    if not rule.get("machine_checkable"):
        return []
    out = []
    for path, lines in added.items():
        if _is_test(path):
            continue            # 测试文件里的密钥是故意夹具，不据此阻断（真实泄密仍由外部 SAST 兜底）
        for lineno, text in lines:
            for pat, label in _SECRET_PATTERNS:
                m = pat.search(text)
                if not m:
                    continue
                matched = m.group(1) if m.groups() else m.group(1)
                if _PLACEHOLDER.search(matched):       # 示例/占位值 → 跳过
                    continue
                out.append(_finding("SEC-001", path, lineno, "security",
                                    f"疑似硬编码凭据（{label}）—— 安全红线，凭据应走密钥管理",
                                    "将凭据移至环境变量/密钥管理服务；代码中勿入硬编码凭据",
                                    rule_index))
                break                                   # 一行最多报一条
    return out


def x_check_secrets__mutmut_24(added, rule_index):
    """SEC-001：扫新增行里的硬编码密钥/凭据（确定性、离线）。仅当 SEC-001 在册且 machine_checkable 时生效。
    产 finding(agent=contract-check, category=security, severity 取自规则=block_candidate) → 自动进确定性门禁。"""
    rule = rule_index.get("SEC-001", {})
    if not rule.get("machine_checkable"):
        return []
    out = []
    for path, lines in added.items():
        if _is_test(path):
            continue            # 测试文件里的密钥是故意夹具，不据此阻断（真实泄密仍由外部 SAST 兜底）
        for lineno, text in lines:
            for pat, label in _SECRET_PATTERNS:
                m = pat.search(text)
                if not m:
                    continue
                matched = m.group(1) if m.groups() else m.group(0)
                if _PLACEHOLDER.search(None):       # 示例/占位值 → 跳过
                    continue
                out.append(_finding("SEC-001", path, lineno, "security",
                                    f"疑似硬编码凭据（{label}）—— 安全红线，凭据应走密钥管理",
                                    "将凭据移至环境变量/密钥管理服务；代码中勿入硬编码凭据",
                                    rule_index))
                break                                   # 一行最多报一条
    return out


def x_check_secrets__mutmut_25(added, rule_index):
    """SEC-001：扫新增行里的硬编码密钥/凭据（确定性、离线）。仅当 SEC-001 在册且 machine_checkable 时生效。
    产 finding(agent=contract-check, category=security, severity 取自规则=block_candidate) → 自动进确定性门禁。"""
    rule = rule_index.get("SEC-001", {})
    if not rule.get("machine_checkable"):
        return []
    out = []
    for path, lines in added.items():
        if _is_test(path):
            continue            # 测试文件里的密钥是故意夹具，不据此阻断（真实泄密仍由外部 SAST 兜底）
        for lineno, text in lines:
            for pat, label in _SECRET_PATTERNS:
                m = pat.search(text)
                if not m:
                    continue
                matched = m.group(1) if m.groups() else m.group(0)
                if _PLACEHOLDER.search(matched):       # 示例/占位值 → 跳过
                    break
                out.append(_finding("SEC-001", path, lineno, "security",
                                    f"疑似硬编码凭据（{label}）—— 安全红线，凭据应走密钥管理",
                                    "将凭据移至环境变量/密钥管理服务；代码中勿入硬编码凭据",
                                    rule_index))
                break                                   # 一行最多报一条
    return out


def x_check_secrets__mutmut_26(added, rule_index):
    """SEC-001：扫新增行里的硬编码密钥/凭据（确定性、离线）。仅当 SEC-001 在册且 machine_checkable 时生效。
    产 finding(agent=contract-check, category=security, severity 取自规则=block_candidate) → 自动进确定性门禁。"""
    rule = rule_index.get("SEC-001", {})
    if not rule.get("machine_checkable"):
        return []
    out = []
    for path, lines in added.items():
        if _is_test(path):
            continue            # 测试文件里的密钥是故意夹具，不据此阻断（真实泄密仍由外部 SAST 兜底）
        for lineno, text in lines:
            for pat, label in _SECRET_PATTERNS:
                m = pat.search(text)
                if not m:
                    continue
                matched = m.group(1) if m.groups() else m.group(0)
                if _PLACEHOLDER.search(matched):       # 示例/占位值 → 跳过
                    continue
                out.append(None)
                break                                   # 一行最多报一条
    return out


def x_check_secrets__mutmut_27(added, rule_index):
    """SEC-001：扫新增行里的硬编码密钥/凭据（确定性、离线）。仅当 SEC-001 在册且 machine_checkable 时生效。
    产 finding(agent=contract-check, category=security, severity 取自规则=block_candidate) → 自动进确定性门禁。"""
    rule = rule_index.get("SEC-001", {})
    if not rule.get("machine_checkable"):
        return []
    out = []
    for path, lines in added.items():
        if _is_test(path):
            continue            # 测试文件里的密钥是故意夹具，不据此阻断（真实泄密仍由外部 SAST 兜底）
        for lineno, text in lines:
            for pat, label in _SECRET_PATTERNS:
                m = pat.search(text)
                if not m:
                    continue
                matched = m.group(1) if m.groups() else m.group(0)
                if _PLACEHOLDER.search(matched):       # 示例/占位值 → 跳过
                    continue
                out.append(_finding(None, path, lineno, "security",
                                    f"疑似硬编码凭据（{label}）—— 安全红线，凭据应走密钥管理",
                                    "将凭据移至环境变量/密钥管理服务；代码中勿入硬编码凭据",
                                    rule_index))
                break                                   # 一行最多报一条
    return out


def x_check_secrets__mutmut_28(added, rule_index):
    """SEC-001：扫新增行里的硬编码密钥/凭据（确定性、离线）。仅当 SEC-001 在册且 machine_checkable 时生效。
    产 finding(agent=contract-check, category=security, severity 取自规则=block_candidate) → 自动进确定性门禁。"""
    rule = rule_index.get("SEC-001", {})
    if not rule.get("machine_checkable"):
        return []
    out = []
    for path, lines in added.items():
        if _is_test(path):
            continue            # 测试文件里的密钥是故意夹具，不据此阻断（真实泄密仍由外部 SAST 兜底）
        for lineno, text in lines:
            for pat, label in _SECRET_PATTERNS:
                m = pat.search(text)
                if not m:
                    continue
                matched = m.group(1) if m.groups() else m.group(0)
                if _PLACEHOLDER.search(matched):       # 示例/占位值 → 跳过
                    continue
                out.append(_finding("SEC-001", None, lineno, "security",
                                    f"疑似硬编码凭据（{label}）—— 安全红线，凭据应走密钥管理",
                                    "将凭据移至环境变量/密钥管理服务；代码中勿入硬编码凭据",
                                    rule_index))
                break                                   # 一行最多报一条
    return out


def x_check_secrets__mutmut_29(added, rule_index):
    """SEC-001：扫新增行里的硬编码密钥/凭据（确定性、离线）。仅当 SEC-001 在册且 machine_checkable 时生效。
    产 finding(agent=contract-check, category=security, severity 取自规则=block_candidate) → 自动进确定性门禁。"""
    rule = rule_index.get("SEC-001", {})
    if not rule.get("machine_checkable"):
        return []
    out = []
    for path, lines in added.items():
        if _is_test(path):
            continue            # 测试文件里的密钥是故意夹具，不据此阻断（真实泄密仍由外部 SAST 兜底）
        for lineno, text in lines:
            for pat, label in _SECRET_PATTERNS:
                m = pat.search(text)
                if not m:
                    continue
                matched = m.group(1) if m.groups() else m.group(0)
                if _PLACEHOLDER.search(matched):       # 示例/占位值 → 跳过
                    continue
                out.append(_finding("SEC-001", path, None, "security",
                                    f"疑似硬编码凭据（{label}）—— 安全红线，凭据应走密钥管理",
                                    "将凭据移至环境变量/密钥管理服务；代码中勿入硬编码凭据",
                                    rule_index))
                break                                   # 一行最多报一条
    return out


def x_check_secrets__mutmut_30(added, rule_index):
    """SEC-001：扫新增行里的硬编码密钥/凭据（确定性、离线）。仅当 SEC-001 在册且 machine_checkable 时生效。
    产 finding(agent=contract-check, category=security, severity 取自规则=block_candidate) → 自动进确定性门禁。"""
    rule = rule_index.get("SEC-001", {})
    if not rule.get("machine_checkable"):
        return []
    out = []
    for path, lines in added.items():
        if _is_test(path):
            continue            # 测试文件里的密钥是故意夹具，不据此阻断（真实泄密仍由外部 SAST 兜底）
        for lineno, text in lines:
            for pat, label in _SECRET_PATTERNS:
                m = pat.search(text)
                if not m:
                    continue
                matched = m.group(1) if m.groups() else m.group(0)
                if _PLACEHOLDER.search(matched):       # 示例/占位值 → 跳过
                    continue
                out.append(_finding("SEC-001", path, lineno, None,
                                    f"疑似硬编码凭据（{label}）—— 安全红线，凭据应走密钥管理",
                                    "将凭据移至环境变量/密钥管理服务；代码中勿入硬编码凭据",
                                    rule_index))
                break                                   # 一行最多报一条
    return out


def x_check_secrets__mutmut_31(added, rule_index):
    """SEC-001：扫新增行里的硬编码密钥/凭据（确定性、离线）。仅当 SEC-001 在册且 machine_checkable 时生效。
    产 finding(agent=contract-check, category=security, severity 取自规则=block_candidate) → 自动进确定性门禁。"""
    rule = rule_index.get("SEC-001", {})
    if not rule.get("machine_checkable"):
        return []
    out = []
    for path, lines in added.items():
        if _is_test(path):
            continue            # 测试文件里的密钥是故意夹具，不据此阻断（真实泄密仍由外部 SAST 兜底）
        for lineno, text in lines:
            for pat, label in _SECRET_PATTERNS:
                m = pat.search(text)
                if not m:
                    continue
                matched = m.group(1) if m.groups() else m.group(0)
                if _PLACEHOLDER.search(matched):       # 示例/占位值 → 跳过
                    continue
                out.append(_finding("SEC-001", path, lineno, "security",
                                    None,
                                    "将凭据移至环境变量/密钥管理服务；代码中勿入硬编码凭据",
                                    rule_index))
                break                                   # 一行最多报一条
    return out


def x_check_secrets__mutmut_32(added, rule_index):
    """SEC-001：扫新增行里的硬编码密钥/凭据（确定性、离线）。仅当 SEC-001 在册且 machine_checkable 时生效。
    产 finding(agent=contract-check, category=security, severity 取自规则=block_candidate) → 自动进确定性门禁。"""
    rule = rule_index.get("SEC-001", {})
    if not rule.get("machine_checkable"):
        return []
    out = []
    for path, lines in added.items():
        if _is_test(path):
            continue            # 测试文件里的密钥是故意夹具，不据此阻断（真实泄密仍由外部 SAST 兜底）
        for lineno, text in lines:
            for pat, label in _SECRET_PATTERNS:
                m = pat.search(text)
                if not m:
                    continue
                matched = m.group(1) if m.groups() else m.group(0)
                if _PLACEHOLDER.search(matched):       # 示例/占位值 → 跳过
                    continue
                out.append(_finding("SEC-001", path, lineno, "security",
                                    f"疑似硬编码凭据（{label}）—— 安全红线，凭据应走密钥管理",
                                    None,
                                    rule_index))
                break                                   # 一行最多报一条
    return out


def x_check_secrets__mutmut_33(added, rule_index):
    """SEC-001：扫新增行里的硬编码密钥/凭据（确定性、离线）。仅当 SEC-001 在册且 machine_checkable 时生效。
    产 finding(agent=contract-check, category=security, severity 取自规则=block_candidate) → 自动进确定性门禁。"""
    rule = rule_index.get("SEC-001", {})
    if not rule.get("machine_checkable"):
        return []
    out = []
    for path, lines in added.items():
        if _is_test(path):
            continue            # 测试文件里的密钥是故意夹具，不据此阻断（真实泄密仍由外部 SAST 兜底）
        for lineno, text in lines:
            for pat, label in _SECRET_PATTERNS:
                m = pat.search(text)
                if not m:
                    continue
                matched = m.group(1) if m.groups() else m.group(0)
                if _PLACEHOLDER.search(matched):       # 示例/占位值 → 跳过
                    continue
                out.append(_finding("SEC-001", path, lineno, "security",
                                    f"疑似硬编码凭据（{label}）—— 安全红线，凭据应走密钥管理",
                                    "将凭据移至环境变量/密钥管理服务；代码中勿入硬编码凭据",
                                    None))
                break                                   # 一行最多报一条
    return out


def x_check_secrets__mutmut_34(added, rule_index):
    """SEC-001：扫新增行里的硬编码密钥/凭据（确定性、离线）。仅当 SEC-001 在册且 machine_checkable 时生效。
    产 finding(agent=contract-check, category=security, severity 取自规则=block_candidate) → 自动进确定性门禁。"""
    rule = rule_index.get("SEC-001", {})
    if not rule.get("machine_checkable"):
        return []
    out = []
    for path, lines in added.items():
        if _is_test(path):
            continue            # 测试文件里的密钥是故意夹具，不据此阻断（真实泄密仍由外部 SAST 兜底）
        for lineno, text in lines:
            for pat, label in _SECRET_PATTERNS:
                m = pat.search(text)
                if not m:
                    continue
                matched = m.group(1) if m.groups() else m.group(0)
                if _PLACEHOLDER.search(matched):       # 示例/占位值 → 跳过
                    continue
                out.append(_finding(path, lineno, "security",
                                    f"疑似硬编码凭据（{label}）—— 安全红线，凭据应走密钥管理",
                                    "将凭据移至环境变量/密钥管理服务；代码中勿入硬编码凭据",
                                    rule_index))
                break                                   # 一行最多报一条
    return out


def x_check_secrets__mutmut_35(added, rule_index):
    """SEC-001：扫新增行里的硬编码密钥/凭据（确定性、离线）。仅当 SEC-001 在册且 machine_checkable 时生效。
    产 finding(agent=contract-check, category=security, severity 取自规则=block_candidate) → 自动进确定性门禁。"""
    rule = rule_index.get("SEC-001", {})
    if not rule.get("machine_checkable"):
        return []
    out = []
    for path, lines in added.items():
        if _is_test(path):
            continue            # 测试文件里的密钥是故意夹具，不据此阻断（真实泄密仍由外部 SAST 兜底）
        for lineno, text in lines:
            for pat, label in _SECRET_PATTERNS:
                m = pat.search(text)
                if not m:
                    continue
                matched = m.group(1) if m.groups() else m.group(0)
                if _PLACEHOLDER.search(matched):       # 示例/占位值 → 跳过
                    continue
                out.append(_finding("SEC-001", lineno, "security",
                                    f"疑似硬编码凭据（{label}）—— 安全红线，凭据应走密钥管理",
                                    "将凭据移至环境变量/密钥管理服务；代码中勿入硬编码凭据",
                                    rule_index))
                break                                   # 一行最多报一条
    return out


def x_check_secrets__mutmut_36(added, rule_index):
    """SEC-001：扫新增行里的硬编码密钥/凭据（确定性、离线）。仅当 SEC-001 在册且 machine_checkable 时生效。
    产 finding(agent=contract-check, category=security, severity 取自规则=block_candidate) → 自动进确定性门禁。"""
    rule = rule_index.get("SEC-001", {})
    if not rule.get("machine_checkable"):
        return []
    out = []
    for path, lines in added.items():
        if _is_test(path):
            continue            # 测试文件里的密钥是故意夹具，不据此阻断（真实泄密仍由外部 SAST 兜底）
        for lineno, text in lines:
            for pat, label in _SECRET_PATTERNS:
                m = pat.search(text)
                if not m:
                    continue
                matched = m.group(1) if m.groups() else m.group(0)
                if _PLACEHOLDER.search(matched):       # 示例/占位值 → 跳过
                    continue
                out.append(_finding("SEC-001", path, "security",
                                    f"疑似硬编码凭据（{label}）—— 安全红线，凭据应走密钥管理",
                                    "将凭据移至环境变量/密钥管理服务；代码中勿入硬编码凭据",
                                    rule_index))
                break                                   # 一行最多报一条
    return out


def x_check_secrets__mutmut_37(added, rule_index):
    """SEC-001：扫新增行里的硬编码密钥/凭据（确定性、离线）。仅当 SEC-001 在册且 machine_checkable 时生效。
    产 finding(agent=contract-check, category=security, severity 取自规则=block_candidate) → 自动进确定性门禁。"""
    rule = rule_index.get("SEC-001", {})
    if not rule.get("machine_checkable"):
        return []
    out = []
    for path, lines in added.items():
        if _is_test(path):
            continue            # 测试文件里的密钥是故意夹具，不据此阻断（真实泄密仍由外部 SAST 兜底）
        for lineno, text in lines:
            for pat, label in _SECRET_PATTERNS:
                m = pat.search(text)
                if not m:
                    continue
                matched = m.group(1) if m.groups() else m.group(0)
                if _PLACEHOLDER.search(matched):       # 示例/占位值 → 跳过
                    continue
                out.append(_finding("SEC-001", path, lineno, f"疑似硬编码凭据（{label}）—— 安全红线，凭据应走密钥管理",
                                    "将凭据移至环境变量/密钥管理服务；代码中勿入硬编码凭据",
                                    rule_index))
                break                                   # 一行最多报一条
    return out


def x_check_secrets__mutmut_38(added, rule_index):
    """SEC-001：扫新增行里的硬编码密钥/凭据（确定性、离线）。仅当 SEC-001 在册且 machine_checkable 时生效。
    产 finding(agent=contract-check, category=security, severity 取自规则=block_candidate) → 自动进确定性门禁。"""
    rule = rule_index.get("SEC-001", {})
    if not rule.get("machine_checkable"):
        return []
    out = []
    for path, lines in added.items():
        if _is_test(path):
            continue            # 测试文件里的密钥是故意夹具，不据此阻断（真实泄密仍由外部 SAST 兜底）
        for lineno, text in lines:
            for pat, label in _SECRET_PATTERNS:
                m = pat.search(text)
                if not m:
                    continue
                matched = m.group(1) if m.groups() else m.group(0)
                if _PLACEHOLDER.search(matched):       # 示例/占位值 → 跳过
                    continue
                out.append(_finding("SEC-001", path, lineno, "security",
                                    "将凭据移至环境变量/密钥管理服务；代码中勿入硬编码凭据",
                                    rule_index))
                break                                   # 一行最多报一条
    return out


def x_check_secrets__mutmut_39(added, rule_index):
    """SEC-001：扫新增行里的硬编码密钥/凭据（确定性、离线）。仅当 SEC-001 在册且 machine_checkable 时生效。
    产 finding(agent=contract-check, category=security, severity 取自规则=block_candidate) → 自动进确定性门禁。"""
    rule = rule_index.get("SEC-001", {})
    if not rule.get("machine_checkable"):
        return []
    out = []
    for path, lines in added.items():
        if _is_test(path):
            continue            # 测试文件里的密钥是故意夹具，不据此阻断（真实泄密仍由外部 SAST 兜底）
        for lineno, text in lines:
            for pat, label in _SECRET_PATTERNS:
                m = pat.search(text)
                if not m:
                    continue
                matched = m.group(1) if m.groups() else m.group(0)
                if _PLACEHOLDER.search(matched):       # 示例/占位值 → 跳过
                    continue
                out.append(_finding("SEC-001", path, lineno, "security",
                                    f"疑似硬编码凭据（{label}）—— 安全红线，凭据应走密钥管理",
                                    rule_index))
                break                                   # 一行最多报一条
    return out


def x_check_secrets__mutmut_40(added, rule_index):
    """SEC-001：扫新增行里的硬编码密钥/凭据（确定性、离线）。仅当 SEC-001 在册且 machine_checkable 时生效。
    产 finding(agent=contract-check, category=security, severity 取自规则=block_candidate) → 自动进确定性门禁。"""
    rule = rule_index.get("SEC-001", {})
    if not rule.get("machine_checkable"):
        return []
    out = []
    for path, lines in added.items():
        if _is_test(path):
            continue            # 测试文件里的密钥是故意夹具，不据此阻断（真实泄密仍由外部 SAST 兜底）
        for lineno, text in lines:
            for pat, label in _SECRET_PATTERNS:
                m = pat.search(text)
                if not m:
                    continue
                matched = m.group(1) if m.groups() else m.group(0)
                if _PLACEHOLDER.search(matched):       # 示例/占位值 → 跳过
                    continue
                out.append(_finding("SEC-001", path, lineno, "security",
                                    f"疑似硬编码凭据（{label}）—— 安全红线，凭据应走密钥管理",
                                    "将凭据移至环境变量/密钥管理服务；代码中勿入硬编码凭据",
                                    ))
                break                                   # 一行最多报一条
    return out


def x_check_secrets__mutmut_41(added, rule_index):
    """SEC-001：扫新增行里的硬编码密钥/凭据（确定性、离线）。仅当 SEC-001 在册且 machine_checkable 时生效。
    产 finding(agent=contract-check, category=security, severity 取自规则=block_candidate) → 自动进确定性门禁。"""
    rule = rule_index.get("SEC-001", {})
    if not rule.get("machine_checkable"):
        return []
    out = []
    for path, lines in added.items():
        if _is_test(path):
            continue            # 测试文件里的密钥是故意夹具，不据此阻断（真实泄密仍由外部 SAST 兜底）
        for lineno, text in lines:
            for pat, label in _SECRET_PATTERNS:
                m = pat.search(text)
                if not m:
                    continue
                matched = m.group(1) if m.groups() else m.group(0)
                if _PLACEHOLDER.search(matched):       # 示例/占位值 → 跳过
                    continue
                out.append(_finding("XXSEC-001XX", path, lineno, "security",
                                    f"疑似硬编码凭据（{label}）—— 安全红线，凭据应走密钥管理",
                                    "将凭据移至环境变量/密钥管理服务；代码中勿入硬编码凭据",
                                    rule_index))
                break                                   # 一行最多报一条
    return out


def x_check_secrets__mutmut_42(added, rule_index):
    """SEC-001：扫新增行里的硬编码密钥/凭据（确定性、离线）。仅当 SEC-001 在册且 machine_checkable 时生效。
    产 finding(agent=contract-check, category=security, severity 取自规则=block_candidate) → 自动进确定性门禁。"""
    rule = rule_index.get("SEC-001", {})
    if not rule.get("machine_checkable"):
        return []
    out = []
    for path, lines in added.items():
        if _is_test(path):
            continue            # 测试文件里的密钥是故意夹具，不据此阻断（真实泄密仍由外部 SAST 兜底）
        for lineno, text in lines:
            for pat, label in _SECRET_PATTERNS:
                m = pat.search(text)
                if not m:
                    continue
                matched = m.group(1) if m.groups() else m.group(0)
                if _PLACEHOLDER.search(matched):       # 示例/占位值 → 跳过
                    continue
                out.append(_finding("sec-001", path, lineno, "security",
                                    f"疑似硬编码凭据（{label}）—— 安全红线，凭据应走密钥管理",
                                    "将凭据移至环境变量/密钥管理服务；代码中勿入硬编码凭据",
                                    rule_index))
                break                                   # 一行最多报一条
    return out


def x_check_secrets__mutmut_43(added, rule_index):
    """SEC-001：扫新增行里的硬编码密钥/凭据（确定性、离线）。仅当 SEC-001 在册且 machine_checkable 时生效。
    产 finding(agent=contract-check, category=security, severity 取自规则=block_candidate) → 自动进确定性门禁。"""
    rule = rule_index.get("SEC-001", {})
    if not rule.get("machine_checkable"):
        return []
    out = []
    for path, lines in added.items():
        if _is_test(path):
            continue            # 测试文件里的密钥是故意夹具，不据此阻断（真实泄密仍由外部 SAST 兜底）
        for lineno, text in lines:
            for pat, label in _SECRET_PATTERNS:
                m = pat.search(text)
                if not m:
                    continue
                matched = m.group(1) if m.groups() else m.group(0)
                if _PLACEHOLDER.search(matched):       # 示例/占位值 → 跳过
                    continue
                out.append(_finding("SEC-001", path, lineno, "XXsecurityXX",
                                    f"疑似硬编码凭据（{label}）—— 安全红线，凭据应走密钥管理",
                                    "将凭据移至环境变量/密钥管理服务；代码中勿入硬编码凭据",
                                    rule_index))
                break                                   # 一行最多报一条
    return out


def x_check_secrets__mutmut_44(added, rule_index):
    """SEC-001：扫新增行里的硬编码密钥/凭据（确定性、离线）。仅当 SEC-001 在册且 machine_checkable 时生效。
    产 finding(agent=contract-check, category=security, severity 取自规则=block_candidate) → 自动进确定性门禁。"""
    rule = rule_index.get("SEC-001", {})
    if not rule.get("machine_checkable"):
        return []
    out = []
    for path, lines in added.items():
        if _is_test(path):
            continue            # 测试文件里的密钥是故意夹具，不据此阻断（真实泄密仍由外部 SAST 兜底）
        for lineno, text in lines:
            for pat, label in _SECRET_PATTERNS:
                m = pat.search(text)
                if not m:
                    continue
                matched = m.group(1) if m.groups() else m.group(0)
                if _PLACEHOLDER.search(matched):       # 示例/占位值 → 跳过
                    continue
                out.append(_finding("SEC-001", path, lineno, "SECURITY",
                                    f"疑似硬编码凭据（{label}）—— 安全红线，凭据应走密钥管理",
                                    "将凭据移至环境变量/密钥管理服务；代码中勿入硬编码凭据",
                                    rule_index))
                break                                   # 一行最多报一条
    return out


def x_check_secrets__mutmut_45(added, rule_index):
    """SEC-001：扫新增行里的硬编码密钥/凭据（确定性、离线）。仅当 SEC-001 在册且 machine_checkable 时生效。
    产 finding(agent=contract-check, category=security, severity 取自规则=block_candidate) → 自动进确定性门禁。"""
    rule = rule_index.get("SEC-001", {})
    if not rule.get("machine_checkable"):
        return []
    out = []
    for path, lines in added.items():
        if _is_test(path):
            continue            # 测试文件里的密钥是故意夹具，不据此阻断（真实泄密仍由外部 SAST 兜底）
        for lineno, text in lines:
            for pat, label in _SECRET_PATTERNS:
                m = pat.search(text)
                if not m:
                    continue
                matched = m.group(1) if m.groups() else m.group(0)
                if _PLACEHOLDER.search(matched):       # 示例/占位值 → 跳过
                    continue
                out.append(_finding("SEC-001", path, lineno, "security",
                                    f"疑似硬编码凭据（{label}）—— 安全红线，凭据应走密钥管理",
                                    "XX将凭据移至环境变量/密钥管理服务；代码中勿入硬编码凭据XX",
                                    rule_index))
                break                                   # 一行最多报一条
    return out


def x_check_secrets__mutmut_46(added, rule_index):
    """SEC-001：扫新增行里的硬编码密钥/凭据（确定性、离线）。仅当 SEC-001 在册且 machine_checkable 时生效。
    产 finding(agent=contract-check, category=security, severity 取自规则=block_candidate) → 自动进确定性门禁。"""
    rule = rule_index.get("SEC-001", {})
    if not rule.get("machine_checkable"):
        return []
    out = []
    for path, lines in added.items():
        if _is_test(path):
            continue            # 测试文件里的密钥是故意夹具，不据此阻断（真实泄密仍由外部 SAST 兜底）
        for lineno, text in lines:
            for pat, label in _SECRET_PATTERNS:
                m = pat.search(text)
                if not m:
                    continue
                matched = m.group(1) if m.groups() else m.group(0)
                if _PLACEHOLDER.search(matched):       # 示例/占位值 → 跳过
                    continue
                out.append(_finding("SEC-001", path, lineno, "security",
                                    f"疑似硬编码凭据（{label}）—— 安全红线，凭据应走密钥管理",
                                    "将凭据移至环境变量/密钥管理服务；代码中勿入硬编码凭据",
                                    rule_index))
                return                                   # 一行最多报一条
    return out

mutants_x_check_secrets__mutmut['_mutmut_orig'] = x_check_secrets__mutmut_orig # type: ignore # mutmut generated
mutants_x_check_secrets__mutmut['x_check_secrets__mutmut_1'] = x_check_secrets__mutmut_1 # type: ignore # mutmut generated
mutants_x_check_secrets__mutmut['x_check_secrets__mutmut_2'] = x_check_secrets__mutmut_2 # type: ignore # mutmut generated
mutants_x_check_secrets__mutmut['x_check_secrets__mutmut_3'] = x_check_secrets__mutmut_3 # type: ignore # mutmut generated
mutants_x_check_secrets__mutmut['x_check_secrets__mutmut_4'] = x_check_secrets__mutmut_4 # type: ignore # mutmut generated
mutants_x_check_secrets__mutmut['x_check_secrets__mutmut_5'] = x_check_secrets__mutmut_5 # type: ignore # mutmut generated
mutants_x_check_secrets__mutmut['x_check_secrets__mutmut_6'] = x_check_secrets__mutmut_6 # type: ignore # mutmut generated
mutants_x_check_secrets__mutmut['x_check_secrets__mutmut_7'] = x_check_secrets__mutmut_7 # type: ignore # mutmut generated
mutants_x_check_secrets__mutmut['x_check_secrets__mutmut_8'] = x_check_secrets__mutmut_8 # type: ignore # mutmut generated
mutants_x_check_secrets__mutmut['x_check_secrets__mutmut_9'] = x_check_secrets__mutmut_9 # type: ignore # mutmut generated
mutants_x_check_secrets__mutmut['x_check_secrets__mutmut_10'] = x_check_secrets__mutmut_10 # type: ignore # mutmut generated
mutants_x_check_secrets__mutmut['x_check_secrets__mutmut_11'] = x_check_secrets__mutmut_11 # type: ignore # mutmut generated
mutants_x_check_secrets__mutmut['x_check_secrets__mutmut_12'] = x_check_secrets__mutmut_12 # type: ignore # mutmut generated
mutants_x_check_secrets__mutmut['x_check_secrets__mutmut_13'] = x_check_secrets__mutmut_13 # type: ignore # mutmut generated
mutants_x_check_secrets__mutmut['x_check_secrets__mutmut_14'] = x_check_secrets__mutmut_14 # type: ignore # mutmut generated
mutants_x_check_secrets__mutmut['x_check_secrets__mutmut_15'] = x_check_secrets__mutmut_15 # type: ignore # mutmut generated
mutants_x_check_secrets__mutmut['x_check_secrets__mutmut_16'] = x_check_secrets__mutmut_16 # type: ignore # mutmut generated
mutants_x_check_secrets__mutmut['x_check_secrets__mutmut_17'] = x_check_secrets__mutmut_17 # type: ignore # mutmut generated
mutants_x_check_secrets__mutmut['x_check_secrets__mutmut_18'] = x_check_secrets__mutmut_18 # type: ignore # mutmut generated
mutants_x_check_secrets__mutmut['x_check_secrets__mutmut_19'] = x_check_secrets__mutmut_19 # type: ignore # mutmut generated
mutants_x_check_secrets__mutmut['x_check_secrets__mutmut_20'] = x_check_secrets__mutmut_20 # type: ignore # mutmut generated
mutants_x_check_secrets__mutmut['x_check_secrets__mutmut_21'] = x_check_secrets__mutmut_21 # type: ignore # mutmut generated
mutants_x_check_secrets__mutmut['x_check_secrets__mutmut_22'] = x_check_secrets__mutmut_22 # type: ignore # mutmut generated
mutants_x_check_secrets__mutmut['x_check_secrets__mutmut_23'] = x_check_secrets__mutmut_23 # type: ignore # mutmut generated
mutants_x_check_secrets__mutmut['x_check_secrets__mutmut_24'] = x_check_secrets__mutmut_24 # type: ignore # mutmut generated
mutants_x_check_secrets__mutmut['x_check_secrets__mutmut_25'] = x_check_secrets__mutmut_25 # type: ignore # mutmut generated
mutants_x_check_secrets__mutmut['x_check_secrets__mutmut_26'] = x_check_secrets__mutmut_26 # type: ignore # mutmut generated
mutants_x_check_secrets__mutmut['x_check_secrets__mutmut_27'] = x_check_secrets__mutmut_27 # type: ignore # mutmut generated
mutants_x_check_secrets__mutmut['x_check_secrets__mutmut_28'] = x_check_secrets__mutmut_28 # type: ignore # mutmut generated
mutants_x_check_secrets__mutmut['x_check_secrets__mutmut_29'] = x_check_secrets__mutmut_29 # type: ignore # mutmut generated
mutants_x_check_secrets__mutmut['x_check_secrets__mutmut_30'] = x_check_secrets__mutmut_30 # type: ignore # mutmut generated
mutants_x_check_secrets__mutmut['x_check_secrets__mutmut_31'] = x_check_secrets__mutmut_31 # type: ignore # mutmut generated
mutants_x_check_secrets__mutmut['x_check_secrets__mutmut_32'] = x_check_secrets__mutmut_32 # type: ignore # mutmut generated
mutants_x_check_secrets__mutmut['x_check_secrets__mutmut_33'] = x_check_secrets__mutmut_33 # type: ignore # mutmut generated
mutants_x_check_secrets__mutmut['x_check_secrets__mutmut_34'] = x_check_secrets__mutmut_34 # type: ignore # mutmut generated
mutants_x_check_secrets__mutmut['x_check_secrets__mutmut_35'] = x_check_secrets__mutmut_35 # type: ignore # mutmut generated
mutants_x_check_secrets__mutmut['x_check_secrets__mutmut_36'] = x_check_secrets__mutmut_36 # type: ignore # mutmut generated
mutants_x_check_secrets__mutmut['x_check_secrets__mutmut_37'] = x_check_secrets__mutmut_37 # type: ignore # mutmut generated
mutants_x_check_secrets__mutmut['x_check_secrets__mutmut_38'] = x_check_secrets__mutmut_38 # type: ignore # mutmut generated
mutants_x_check_secrets__mutmut['x_check_secrets__mutmut_39'] = x_check_secrets__mutmut_39 # type: ignore # mutmut generated
mutants_x_check_secrets__mutmut['x_check_secrets__mutmut_40'] = x_check_secrets__mutmut_40 # type: ignore # mutmut generated
mutants_x_check_secrets__mutmut['x_check_secrets__mutmut_41'] = x_check_secrets__mutmut_41 # type: ignore # mutmut generated
mutants_x_check_secrets__mutmut['x_check_secrets__mutmut_42'] = x_check_secrets__mutmut_42 # type: ignore # mutmut generated
mutants_x_check_secrets__mutmut['x_check_secrets__mutmut_43'] = x_check_secrets__mutmut_43 # type: ignore # mutmut generated
mutants_x_check_secrets__mutmut['x_check_secrets__mutmut_44'] = x_check_secrets__mutmut_44 # type: ignore # mutmut generated
mutants_x_check_secrets__mutmut['x_check_secrets__mutmut_45'] = x_check_secrets__mutmut_45 # type: ignore # mutmut generated
mutants_x_check_secrets__mutmut['x_check_secrets__mutmut_46'] = x_check_secrets__mutmut_46 # type: ignore # mutmut generated
mutants_x_check_contract_consistency__mutmut: MutantDict = {}  # type: ignore


@_mutmut_mutated(mutants_x_check_contract_consistency__mutmut)
def check_contract_consistency(diff_text, contract, rule_index):
    """确定性核对契约三项声明（需 manifest）+ 无 manifest 也能跑的纯 diff 事实检查 + SEC-001 密钥扫描。"""
    contract = contract or {}
    files, added = parse_diff(diff_text)
    return (check_scope(files, contract.get("scope"), rule_index)
            + check_tests(files, contract.get("tests_added"), rule_index)
            + check_reuse(added, contract.get("reused_components"), rule_index)
            + check_untested_code(files, rule_index)
            + check_secrets(added, rule_index))


def x_check_contract_consistency__mutmut_orig(diff_text, contract, rule_index):
    """确定性核对契约三项声明（需 manifest）+ 无 manifest 也能跑的纯 diff 事实检查 + SEC-001 密钥扫描。"""
    contract = contract or {}
    files, added = parse_diff(diff_text)
    return (check_scope(files, contract.get("scope"), rule_index)
            + check_tests(files, contract.get("tests_added"), rule_index)
            + check_reuse(added, contract.get("reused_components"), rule_index)
            + check_untested_code(files, rule_index)
            + check_secrets(added, rule_index))


def x_check_contract_consistency__mutmut_1(diff_text, contract, rule_index):
    """确定性核对契约三项声明（需 manifest）+ 无 manifest 也能跑的纯 diff 事实检查 + SEC-001 密钥扫描。"""
    contract = None
    files, added = parse_diff(diff_text)
    return (check_scope(files, contract.get("scope"), rule_index)
            + check_tests(files, contract.get("tests_added"), rule_index)
            + check_reuse(added, contract.get("reused_components"), rule_index)
            + check_untested_code(files, rule_index)
            + check_secrets(added, rule_index))


def x_check_contract_consistency__mutmut_2(diff_text, contract, rule_index):
    """确定性核对契约三项声明（需 manifest）+ 无 manifest 也能跑的纯 diff 事实检查 + SEC-001 密钥扫描。"""
    contract = contract and {}
    files, added = parse_diff(diff_text)
    return (check_scope(files, contract.get("scope"), rule_index)
            + check_tests(files, contract.get("tests_added"), rule_index)
            + check_reuse(added, contract.get("reused_components"), rule_index)
            + check_untested_code(files, rule_index)
            + check_secrets(added, rule_index))


def x_check_contract_consistency__mutmut_3(diff_text, contract, rule_index):
    """确定性核对契约三项声明（需 manifest）+ 无 manifest 也能跑的纯 diff 事实检查 + SEC-001 密钥扫描。"""
    contract = contract or {}
    files, added = None
    return (check_scope(files, contract.get("scope"), rule_index)
            + check_tests(files, contract.get("tests_added"), rule_index)
            + check_reuse(added, contract.get("reused_components"), rule_index)
            + check_untested_code(files, rule_index)
            + check_secrets(added, rule_index))


def x_check_contract_consistency__mutmut_4(diff_text, contract, rule_index):
    """确定性核对契约三项声明（需 manifest）+ 无 manifest 也能跑的纯 diff 事实检查 + SEC-001 密钥扫描。"""
    contract = contract or {}
    files, added = parse_diff(None)
    return (check_scope(files, contract.get("scope"), rule_index)
            + check_tests(files, contract.get("tests_added"), rule_index)
            + check_reuse(added, contract.get("reused_components"), rule_index)
            + check_untested_code(files, rule_index)
            + check_secrets(added, rule_index))


def x_check_contract_consistency__mutmut_5(diff_text, contract, rule_index):
    """确定性核对契约三项声明（需 manifest）+ 无 manifest 也能跑的纯 diff 事实检查 + SEC-001 密钥扫描。"""
    contract = contract or {}
    files, added = parse_diff(diff_text)
    return (check_scope(files, contract.get("scope"), rule_index)
            + check_tests(files, contract.get("tests_added"), rule_index)
            + check_reuse(added, contract.get("reused_components"), rule_index)
            + check_untested_code(files, rule_index) - check_secrets(added, rule_index))


def x_check_contract_consistency__mutmut_6(diff_text, contract, rule_index):
    """确定性核对契约三项声明（需 manifest）+ 无 manifest 也能跑的纯 diff 事实检查 + SEC-001 密钥扫描。"""
    contract = contract or {}
    files, added = parse_diff(diff_text)
    return (check_scope(files, contract.get("scope"), rule_index)
            + check_tests(files, contract.get("tests_added"), rule_index)
            + check_reuse(added, contract.get("reused_components"), rule_index) - check_untested_code(files, rule_index)
            + check_secrets(added, rule_index))


def x_check_contract_consistency__mutmut_7(diff_text, contract, rule_index):
    """确定性核对契约三项声明（需 manifest）+ 无 manifest 也能跑的纯 diff 事实检查 + SEC-001 密钥扫描。"""
    contract = contract or {}
    files, added = parse_diff(diff_text)
    return (check_scope(files, contract.get("scope"), rule_index)
            + check_tests(files, contract.get("tests_added"), rule_index) - check_reuse(added, contract.get("reused_components"), rule_index)
            + check_untested_code(files, rule_index)
            + check_secrets(added, rule_index))


def x_check_contract_consistency__mutmut_8(diff_text, contract, rule_index):
    """确定性核对契约三项声明（需 manifest）+ 无 manifest 也能跑的纯 diff 事实检查 + SEC-001 密钥扫描。"""
    contract = contract or {}
    files, added = parse_diff(diff_text)
    return (check_scope(files, contract.get("scope"), rule_index) - check_tests(files, contract.get("tests_added"), rule_index)
            + check_reuse(added, contract.get("reused_components"), rule_index)
            + check_untested_code(files, rule_index)
            + check_secrets(added, rule_index))


def x_check_contract_consistency__mutmut_9(diff_text, contract, rule_index):
    """确定性核对契约三项声明（需 manifest）+ 无 manifest 也能跑的纯 diff 事实检查 + SEC-001 密钥扫描。"""
    contract = contract or {}
    files, added = parse_diff(diff_text)
    return (check_scope(None, contract.get("scope"), rule_index)
            + check_tests(files, contract.get("tests_added"), rule_index)
            + check_reuse(added, contract.get("reused_components"), rule_index)
            + check_untested_code(files, rule_index)
            + check_secrets(added, rule_index))


def x_check_contract_consistency__mutmut_10(diff_text, contract, rule_index):
    """确定性核对契约三项声明（需 manifest）+ 无 manifest 也能跑的纯 diff 事实检查 + SEC-001 密钥扫描。"""
    contract = contract or {}
    files, added = parse_diff(diff_text)
    return (check_scope(files, None, rule_index)
            + check_tests(files, contract.get("tests_added"), rule_index)
            + check_reuse(added, contract.get("reused_components"), rule_index)
            + check_untested_code(files, rule_index)
            + check_secrets(added, rule_index))


def x_check_contract_consistency__mutmut_11(diff_text, contract, rule_index):
    """确定性核对契约三项声明（需 manifest）+ 无 manifest 也能跑的纯 diff 事实检查 + SEC-001 密钥扫描。"""
    contract = contract or {}
    files, added = parse_diff(diff_text)
    return (check_scope(files, contract.get("scope"), None)
            + check_tests(files, contract.get("tests_added"), rule_index)
            + check_reuse(added, contract.get("reused_components"), rule_index)
            + check_untested_code(files, rule_index)
            + check_secrets(added, rule_index))


def x_check_contract_consistency__mutmut_12(diff_text, contract, rule_index):
    """确定性核对契约三项声明（需 manifest）+ 无 manifest 也能跑的纯 diff 事实检查 + SEC-001 密钥扫描。"""
    contract = contract or {}
    files, added = parse_diff(diff_text)
    return (check_scope(contract.get("scope"), rule_index)
            + check_tests(files, contract.get("tests_added"), rule_index)
            + check_reuse(added, contract.get("reused_components"), rule_index)
            + check_untested_code(files, rule_index)
            + check_secrets(added, rule_index))


def x_check_contract_consistency__mutmut_13(diff_text, contract, rule_index):
    """确定性核对契约三项声明（需 manifest）+ 无 manifest 也能跑的纯 diff 事实检查 + SEC-001 密钥扫描。"""
    contract = contract or {}
    files, added = parse_diff(diff_text)
    return (check_scope(files, rule_index)
            + check_tests(files, contract.get("tests_added"), rule_index)
            + check_reuse(added, contract.get("reused_components"), rule_index)
            + check_untested_code(files, rule_index)
            + check_secrets(added, rule_index))


def x_check_contract_consistency__mutmut_14(diff_text, contract, rule_index):
    """确定性核对契约三项声明（需 manifest）+ 无 manifest 也能跑的纯 diff 事实检查 + SEC-001 密钥扫描。"""
    contract = contract or {}
    files, added = parse_diff(diff_text)
    return (check_scope(files, contract.get("scope"), )
            + check_tests(files, contract.get("tests_added"), rule_index)
            + check_reuse(added, contract.get("reused_components"), rule_index)
            + check_untested_code(files, rule_index)
            + check_secrets(added, rule_index))


def x_check_contract_consistency__mutmut_15(diff_text, contract, rule_index):
    """确定性核对契约三项声明（需 manifest）+ 无 manifest 也能跑的纯 diff 事实检查 + SEC-001 密钥扫描。"""
    contract = contract or {}
    files, added = parse_diff(diff_text)
    return (check_scope(files, contract.get(None), rule_index)
            + check_tests(files, contract.get("tests_added"), rule_index)
            + check_reuse(added, contract.get("reused_components"), rule_index)
            + check_untested_code(files, rule_index)
            + check_secrets(added, rule_index))


def x_check_contract_consistency__mutmut_16(diff_text, contract, rule_index):
    """确定性核对契约三项声明（需 manifest）+ 无 manifest 也能跑的纯 diff 事实检查 + SEC-001 密钥扫描。"""
    contract = contract or {}
    files, added = parse_diff(diff_text)
    return (check_scope(files, contract.get("XXscopeXX"), rule_index)
            + check_tests(files, contract.get("tests_added"), rule_index)
            + check_reuse(added, contract.get("reused_components"), rule_index)
            + check_untested_code(files, rule_index)
            + check_secrets(added, rule_index))


def x_check_contract_consistency__mutmut_17(diff_text, contract, rule_index):
    """确定性核对契约三项声明（需 manifest）+ 无 manifest 也能跑的纯 diff 事实检查 + SEC-001 密钥扫描。"""
    contract = contract or {}
    files, added = parse_diff(diff_text)
    return (check_scope(files, contract.get("SCOPE"), rule_index)
            + check_tests(files, contract.get("tests_added"), rule_index)
            + check_reuse(added, contract.get("reused_components"), rule_index)
            + check_untested_code(files, rule_index)
            + check_secrets(added, rule_index))


def x_check_contract_consistency__mutmut_18(diff_text, contract, rule_index):
    """确定性核对契约三项声明（需 manifest）+ 无 manifest 也能跑的纯 diff 事实检查 + SEC-001 密钥扫描。"""
    contract = contract or {}
    files, added = parse_diff(diff_text)
    return (check_scope(files, contract.get("scope"), rule_index)
            + check_tests(None, contract.get("tests_added"), rule_index)
            + check_reuse(added, contract.get("reused_components"), rule_index)
            + check_untested_code(files, rule_index)
            + check_secrets(added, rule_index))


def x_check_contract_consistency__mutmut_19(diff_text, contract, rule_index):
    """确定性核对契约三项声明（需 manifest）+ 无 manifest 也能跑的纯 diff 事实检查 + SEC-001 密钥扫描。"""
    contract = contract or {}
    files, added = parse_diff(diff_text)
    return (check_scope(files, contract.get("scope"), rule_index)
            + check_tests(files, None, rule_index)
            + check_reuse(added, contract.get("reused_components"), rule_index)
            + check_untested_code(files, rule_index)
            + check_secrets(added, rule_index))


def x_check_contract_consistency__mutmut_20(diff_text, contract, rule_index):
    """确定性核对契约三项声明（需 manifest）+ 无 manifest 也能跑的纯 diff 事实检查 + SEC-001 密钥扫描。"""
    contract = contract or {}
    files, added = parse_diff(diff_text)
    return (check_scope(files, contract.get("scope"), rule_index)
            + check_tests(files, contract.get("tests_added"), None)
            + check_reuse(added, contract.get("reused_components"), rule_index)
            + check_untested_code(files, rule_index)
            + check_secrets(added, rule_index))


def x_check_contract_consistency__mutmut_21(diff_text, contract, rule_index):
    """确定性核对契约三项声明（需 manifest）+ 无 manifest 也能跑的纯 diff 事实检查 + SEC-001 密钥扫描。"""
    contract = contract or {}
    files, added = parse_diff(diff_text)
    return (check_scope(files, contract.get("scope"), rule_index)
            + check_tests(contract.get("tests_added"), rule_index)
            + check_reuse(added, contract.get("reused_components"), rule_index)
            + check_untested_code(files, rule_index)
            + check_secrets(added, rule_index))


def x_check_contract_consistency__mutmut_22(diff_text, contract, rule_index):
    """确定性核对契约三项声明（需 manifest）+ 无 manifest 也能跑的纯 diff 事实检查 + SEC-001 密钥扫描。"""
    contract = contract or {}
    files, added = parse_diff(diff_text)
    return (check_scope(files, contract.get("scope"), rule_index)
            + check_tests(files, rule_index)
            + check_reuse(added, contract.get("reused_components"), rule_index)
            + check_untested_code(files, rule_index)
            + check_secrets(added, rule_index))


def x_check_contract_consistency__mutmut_23(diff_text, contract, rule_index):
    """确定性核对契约三项声明（需 manifest）+ 无 manifest 也能跑的纯 diff 事实检查 + SEC-001 密钥扫描。"""
    contract = contract or {}
    files, added = parse_diff(diff_text)
    return (check_scope(files, contract.get("scope"), rule_index)
            + check_tests(files, contract.get("tests_added"), )
            + check_reuse(added, contract.get("reused_components"), rule_index)
            + check_untested_code(files, rule_index)
            + check_secrets(added, rule_index))


def x_check_contract_consistency__mutmut_24(diff_text, contract, rule_index):
    """确定性核对契约三项声明（需 manifest）+ 无 manifest 也能跑的纯 diff 事实检查 + SEC-001 密钥扫描。"""
    contract = contract or {}
    files, added = parse_diff(diff_text)
    return (check_scope(files, contract.get("scope"), rule_index)
            + check_tests(files, contract.get(None), rule_index)
            + check_reuse(added, contract.get("reused_components"), rule_index)
            + check_untested_code(files, rule_index)
            + check_secrets(added, rule_index))


def x_check_contract_consistency__mutmut_25(diff_text, contract, rule_index):
    """确定性核对契约三项声明（需 manifest）+ 无 manifest 也能跑的纯 diff 事实检查 + SEC-001 密钥扫描。"""
    contract = contract or {}
    files, added = parse_diff(diff_text)
    return (check_scope(files, contract.get("scope"), rule_index)
            + check_tests(files, contract.get("XXtests_addedXX"), rule_index)
            + check_reuse(added, contract.get("reused_components"), rule_index)
            + check_untested_code(files, rule_index)
            + check_secrets(added, rule_index))


def x_check_contract_consistency__mutmut_26(diff_text, contract, rule_index):
    """确定性核对契约三项声明（需 manifest）+ 无 manifest 也能跑的纯 diff 事实检查 + SEC-001 密钥扫描。"""
    contract = contract or {}
    files, added = parse_diff(diff_text)
    return (check_scope(files, contract.get("scope"), rule_index)
            + check_tests(files, contract.get("TESTS_ADDED"), rule_index)
            + check_reuse(added, contract.get("reused_components"), rule_index)
            + check_untested_code(files, rule_index)
            + check_secrets(added, rule_index))


def x_check_contract_consistency__mutmut_27(diff_text, contract, rule_index):
    """确定性核对契约三项声明（需 manifest）+ 无 manifest 也能跑的纯 diff 事实检查 + SEC-001 密钥扫描。"""
    contract = contract or {}
    files, added = parse_diff(diff_text)
    return (check_scope(files, contract.get("scope"), rule_index)
            + check_tests(files, contract.get("tests_added"), rule_index)
            + check_reuse(None, contract.get("reused_components"), rule_index)
            + check_untested_code(files, rule_index)
            + check_secrets(added, rule_index))


def x_check_contract_consistency__mutmut_28(diff_text, contract, rule_index):
    """确定性核对契约三项声明（需 manifest）+ 无 manifest 也能跑的纯 diff 事实检查 + SEC-001 密钥扫描。"""
    contract = contract or {}
    files, added = parse_diff(diff_text)
    return (check_scope(files, contract.get("scope"), rule_index)
            + check_tests(files, contract.get("tests_added"), rule_index)
            + check_reuse(added, None, rule_index)
            + check_untested_code(files, rule_index)
            + check_secrets(added, rule_index))


def x_check_contract_consistency__mutmut_29(diff_text, contract, rule_index):
    """确定性核对契约三项声明（需 manifest）+ 无 manifest 也能跑的纯 diff 事实检查 + SEC-001 密钥扫描。"""
    contract = contract or {}
    files, added = parse_diff(diff_text)
    return (check_scope(files, contract.get("scope"), rule_index)
            + check_tests(files, contract.get("tests_added"), rule_index)
            + check_reuse(added, contract.get("reused_components"), None)
            + check_untested_code(files, rule_index)
            + check_secrets(added, rule_index))


def x_check_contract_consistency__mutmut_30(diff_text, contract, rule_index):
    """确定性核对契约三项声明（需 manifest）+ 无 manifest 也能跑的纯 diff 事实检查 + SEC-001 密钥扫描。"""
    contract = contract or {}
    files, added = parse_diff(diff_text)
    return (check_scope(files, contract.get("scope"), rule_index)
            + check_tests(files, contract.get("tests_added"), rule_index)
            + check_reuse(contract.get("reused_components"), rule_index)
            + check_untested_code(files, rule_index)
            + check_secrets(added, rule_index))


def x_check_contract_consistency__mutmut_31(diff_text, contract, rule_index):
    """确定性核对契约三项声明（需 manifest）+ 无 manifest 也能跑的纯 diff 事实检查 + SEC-001 密钥扫描。"""
    contract = contract or {}
    files, added = parse_diff(diff_text)
    return (check_scope(files, contract.get("scope"), rule_index)
            + check_tests(files, contract.get("tests_added"), rule_index)
            + check_reuse(added, rule_index)
            + check_untested_code(files, rule_index)
            + check_secrets(added, rule_index))


def x_check_contract_consistency__mutmut_32(diff_text, contract, rule_index):
    """确定性核对契约三项声明（需 manifest）+ 无 manifest 也能跑的纯 diff 事实检查 + SEC-001 密钥扫描。"""
    contract = contract or {}
    files, added = parse_diff(diff_text)
    return (check_scope(files, contract.get("scope"), rule_index)
            + check_tests(files, contract.get("tests_added"), rule_index)
            + check_reuse(added, contract.get("reused_components"), )
            + check_untested_code(files, rule_index)
            + check_secrets(added, rule_index))


def x_check_contract_consistency__mutmut_33(diff_text, contract, rule_index):
    """确定性核对契约三项声明（需 manifest）+ 无 manifest 也能跑的纯 diff 事实检查 + SEC-001 密钥扫描。"""
    contract = contract or {}
    files, added = parse_diff(diff_text)
    return (check_scope(files, contract.get("scope"), rule_index)
            + check_tests(files, contract.get("tests_added"), rule_index)
            + check_reuse(added, contract.get(None), rule_index)
            + check_untested_code(files, rule_index)
            + check_secrets(added, rule_index))


def x_check_contract_consistency__mutmut_34(diff_text, contract, rule_index):
    """确定性核对契约三项声明（需 manifest）+ 无 manifest 也能跑的纯 diff 事实检查 + SEC-001 密钥扫描。"""
    contract = contract or {}
    files, added = parse_diff(diff_text)
    return (check_scope(files, contract.get("scope"), rule_index)
            + check_tests(files, contract.get("tests_added"), rule_index)
            + check_reuse(added, contract.get("XXreused_componentsXX"), rule_index)
            + check_untested_code(files, rule_index)
            + check_secrets(added, rule_index))


def x_check_contract_consistency__mutmut_35(diff_text, contract, rule_index):
    """确定性核对契约三项声明（需 manifest）+ 无 manifest 也能跑的纯 diff 事实检查 + SEC-001 密钥扫描。"""
    contract = contract or {}
    files, added = parse_diff(diff_text)
    return (check_scope(files, contract.get("scope"), rule_index)
            + check_tests(files, contract.get("tests_added"), rule_index)
            + check_reuse(added, contract.get("REUSED_COMPONENTS"), rule_index)
            + check_untested_code(files, rule_index)
            + check_secrets(added, rule_index))


def x_check_contract_consistency__mutmut_36(diff_text, contract, rule_index):
    """确定性核对契约三项声明（需 manifest）+ 无 manifest 也能跑的纯 diff 事实检查 + SEC-001 密钥扫描。"""
    contract = contract or {}
    files, added = parse_diff(diff_text)
    return (check_scope(files, contract.get("scope"), rule_index)
            + check_tests(files, contract.get("tests_added"), rule_index)
            + check_reuse(added, contract.get("reused_components"), rule_index)
            + check_untested_code(None, rule_index)
            + check_secrets(added, rule_index))


def x_check_contract_consistency__mutmut_37(diff_text, contract, rule_index):
    """确定性核对契约三项声明（需 manifest）+ 无 manifest 也能跑的纯 diff 事实检查 + SEC-001 密钥扫描。"""
    contract = contract or {}
    files, added = parse_diff(diff_text)
    return (check_scope(files, contract.get("scope"), rule_index)
            + check_tests(files, contract.get("tests_added"), rule_index)
            + check_reuse(added, contract.get("reused_components"), rule_index)
            + check_untested_code(files, None)
            + check_secrets(added, rule_index))


def x_check_contract_consistency__mutmut_38(diff_text, contract, rule_index):
    """确定性核对契约三项声明（需 manifest）+ 无 manifest 也能跑的纯 diff 事实检查 + SEC-001 密钥扫描。"""
    contract = contract or {}
    files, added = parse_diff(diff_text)
    return (check_scope(files, contract.get("scope"), rule_index)
            + check_tests(files, contract.get("tests_added"), rule_index)
            + check_reuse(added, contract.get("reused_components"), rule_index)
            + check_untested_code(rule_index)
            + check_secrets(added, rule_index))


def x_check_contract_consistency__mutmut_39(diff_text, contract, rule_index):
    """确定性核对契约三项声明（需 manifest）+ 无 manifest 也能跑的纯 diff 事实检查 + SEC-001 密钥扫描。"""
    contract = contract or {}
    files, added = parse_diff(diff_text)
    return (check_scope(files, contract.get("scope"), rule_index)
            + check_tests(files, contract.get("tests_added"), rule_index)
            + check_reuse(added, contract.get("reused_components"), rule_index)
            + check_untested_code(files, )
            + check_secrets(added, rule_index))


def x_check_contract_consistency__mutmut_40(diff_text, contract, rule_index):
    """确定性核对契约三项声明（需 manifest）+ 无 manifest 也能跑的纯 diff 事实检查 + SEC-001 密钥扫描。"""
    contract = contract or {}
    files, added = parse_diff(diff_text)
    return (check_scope(files, contract.get("scope"), rule_index)
            + check_tests(files, contract.get("tests_added"), rule_index)
            + check_reuse(added, contract.get("reused_components"), rule_index)
            + check_untested_code(files, rule_index)
            + check_secrets(None, rule_index))


def x_check_contract_consistency__mutmut_41(diff_text, contract, rule_index):
    """确定性核对契约三项声明（需 manifest）+ 无 manifest 也能跑的纯 diff 事实检查 + SEC-001 密钥扫描。"""
    contract = contract or {}
    files, added = parse_diff(diff_text)
    return (check_scope(files, contract.get("scope"), rule_index)
            + check_tests(files, contract.get("tests_added"), rule_index)
            + check_reuse(added, contract.get("reused_components"), rule_index)
            + check_untested_code(files, rule_index)
            + check_secrets(added, None))


def x_check_contract_consistency__mutmut_42(diff_text, contract, rule_index):
    """确定性核对契约三项声明（需 manifest）+ 无 manifest 也能跑的纯 diff 事实检查 + SEC-001 密钥扫描。"""
    contract = contract or {}
    files, added = parse_diff(diff_text)
    return (check_scope(files, contract.get("scope"), rule_index)
            + check_tests(files, contract.get("tests_added"), rule_index)
            + check_reuse(added, contract.get("reused_components"), rule_index)
            + check_untested_code(files, rule_index)
            + check_secrets(rule_index))


def x_check_contract_consistency__mutmut_43(diff_text, contract, rule_index):
    """确定性核对契约三项声明（需 manifest）+ 无 manifest 也能跑的纯 diff 事实检查 + SEC-001 密钥扫描。"""
    contract = contract or {}
    files, added = parse_diff(diff_text)
    return (check_scope(files, contract.get("scope"), rule_index)
            + check_tests(files, contract.get("tests_added"), rule_index)
            + check_reuse(added, contract.get("reused_components"), rule_index)
            + check_untested_code(files, rule_index)
            + check_secrets(added, ))

mutants_x_check_contract_consistency__mutmut['_mutmut_orig'] = x_check_contract_consistency__mutmut_orig # type: ignore # mutmut generated
mutants_x_check_contract_consistency__mutmut['x_check_contract_consistency__mutmut_1'] = x_check_contract_consistency__mutmut_1 # type: ignore # mutmut generated
mutants_x_check_contract_consistency__mutmut['x_check_contract_consistency__mutmut_2'] = x_check_contract_consistency__mutmut_2 # type: ignore # mutmut generated
mutants_x_check_contract_consistency__mutmut['x_check_contract_consistency__mutmut_3'] = x_check_contract_consistency__mutmut_3 # type: ignore # mutmut generated
mutants_x_check_contract_consistency__mutmut['x_check_contract_consistency__mutmut_4'] = x_check_contract_consistency__mutmut_4 # type: ignore # mutmut generated
mutants_x_check_contract_consistency__mutmut['x_check_contract_consistency__mutmut_5'] = x_check_contract_consistency__mutmut_5 # type: ignore # mutmut generated
mutants_x_check_contract_consistency__mutmut['x_check_contract_consistency__mutmut_6'] = x_check_contract_consistency__mutmut_6 # type: ignore # mutmut generated
mutants_x_check_contract_consistency__mutmut['x_check_contract_consistency__mutmut_7'] = x_check_contract_consistency__mutmut_7 # type: ignore # mutmut generated
mutants_x_check_contract_consistency__mutmut['x_check_contract_consistency__mutmut_8'] = x_check_contract_consistency__mutmut_8 # type: ignore # mutmut generated
mutants_x_check_contract_consistency__mutmut['x_check_contract_consistency__mutmut_9'] = x_check_contract_consistency__mutmut_9 # type: ignore # mutmut generated
mutants_x_check_contract_consistency__mutmut['x_check_contract_consistency__mutmut_10'] = x_check_contract_consistency__mutmut_10 # type: ignore # mutmut generated
mutants_x_check_contract_consistency__mutmut['x_check_contract_consistency__mutmut_11'] = x_check_contract_consistency__mutmut_11 # type: ignore # mutmut generated
mutants_x_check_contract_consistency__mutmut['x_check_contract_consistency__mutmut_12'] = x_check_contract_consistency__mutmut_12 # type: ignore # mutmut generated
mutants_x_check_contract_consistency__mutmut['x_check_contract_consistency__mutmut_13'] = x_check_contract_consistency__mutmut_13 # type: ignore # mutmut generated
mutants_x_check_contract_consistency__mutmut['x_check_contract_consistency__mutmut_14'] = x_check_contract_consistency__mutmut_14 # type: ignore # mutmut generated
mutants_x_check_contract_consistency__mutmut['x_check_contract_consistency__mutmut_15'] = x_check_contract_consistency__mutmut_15 # type: ignore # mutmut generated
mutants_x_check_contract_consistency__mutmut['x_check_contract_consistency__mutmut_16'] = x_check_contract_consistency__mutmut_16 # type: ignore # mutmut generated
mutants_x_check_contract_consistency__mutmut['x_check_contract_consistency__mutmut_17'] = x_check_contract_consistency__mutmut_17 # type: ignore # mutmut generated
mutants_x_check_contract_consistency__mutmut['x_check_contract_consistency__mutmut_18'] = x_check_contract_consistency__mutmut_18 # type: ignore # mutmut generated
mutants_x_check_contract_consistency__mutmut['x_check_contract_consistency__mutmut_19'] = x_check_contract_consistency__mutmut_19 # type: ignore # mutmut generated
mutants_x_check_contract_consistency__mutmut['x_check_contract_consistency__mutmut_20'] = x_check_contract_consistency__mutmut_20 # type: ignore # mutmut generated
mutants_x_check_contract_consistency__mutmut['x_check_contract_consistency__mutmut_21'] = x_check_contract_consistency__mutmut_21 # type: ignore # mutmut generated
mutants_x_check_contract_consistency__mutmut['x_check_contract_consistency__mutmut_22'] = x_check_contract_consistency__mutmut_22 # type: ignore # mutmut generated
mutants_x_check_contract_consistency__mutmut['x_check_contract_consistency__mutmut_23'] = x_check_contract_consistency__mutmut_23 # type: ignore # mutmut generated
mutants_x_check_contract_consistency__mutmut['x_check_contract_consistency__mutmut_24'] = x_check_contract_consistency__mutmut_24 # type: ignore # mutmut generated
mutants_x_check_contract_consistency__mutmut['x_check_contract_consistency__mutmut_25'] = x_check_contract_consistency__mutmut_25 # type: ignore # mutmut generated
mutants_x_check_contract_consistency__mutmut['x_check_contract_consistency__mutmut_26'] = x_check_contract_consistency__mutmut_26 # type: ignore # mutmut generated
mutants_x_check_contract_consistency__mutmut['x_check_contract_consistency__mutmut_27'] = x_check_contract_consistency__mutmut_27 # type: ignore # mutmut generated
mutants_x_check_contract_consistency__mutmut['x_check_contract_consistency__mutmut_28'] = x_check_contract_consistency__mutmut_28 # type: ignore # mutmut generated
mutants_x_check_contract_consistency__mutmut['x_check_contract_consistency__mutmut_29'] = x_check_contract_consistency__mutmut_29 # type: ignore # mutmut generated
mutants_x_check_contract_consistency__mutmut['x_check_contract_consistency__mutmut_30'] = x_check_contract_consistency__mutmut_30 # type: ignore # mutmut generated
mutants_x_check_contract_consistency__mutmut['x_check_contract_consistency__mutmut_31'] = x_check_contract_consistency__mutmut_31 # type: ignore # mutmut generated
mutants_x_check_contract_consistency__mutmut['x_check_contract_consistency__mutmut_32'] = x_check_contract_consistency__mutmut_32 # type: ignore # mutmut generated
mutants_x_check_contract_consistency__mutmut['x_check_contract_consistency__mutmut_33'] = x_check_contract_consistency__mutmut_33 # type: ignore # mutmut generated
mutants_x_check_contract_consistency__mutmut['x_check_contract_consistency__mutmut_34'] = x_check_contract_consistency__mutmut_34 # type: ignore # mutmut generated
mutants_x_check_contract_consistency__mutmut['x_check_contract_consistency__mutmut_35'] = x_check_contract_consistency__mutmut_35 # type: ignore # mutmut generated
mutants_x_check_contract_consistency__mutmut['x_check_contract_consistency__mutmut_36'] = x_check_contract_consistency__mutmut_36 # type: ignore # mutmut generated
mutants_x_check_contract_consistency__mutmut['x_check_contract_consistency__mutmut_37'] = x_check_contract_consistency__mutmut_37 # type: ignore # mutmut generated
mutants_x_check_contract_consistency__mutmut['x_check_contract_consistency__mutmut_38'] = x_check_contract_consistency__mutmut_38 # type: ignore # mutmut generated
mutants_x_check_contract_consistency__mutmut['x_check_contract_consistency__mutmut_39'] = x_check_contract_consistency__mutmut_39 # type: ignore # mutmut generated
mutants_x_check_contract_consistency__mutmut['x_check_contract_consistency__mutmut_40'] = x_check_contract_consistency__mutmut_40 # type: ignore # mutmut generated
mutants_x_check_contract_consistency__mutmut['x_check_contract_consistency__mutmut_41'] = x_check_contract_consistency__mutmut_41 # type: ignore # mutmut generated
mutants_x_check_contract_consistency__mutmut['x_check_contract_consistency__mutmut_42'] = x_check_contract_consistency__mutmut_42 # type: ignore # mutmut generated
mutants_x_check_contract_consistency__mutmut['x_check_contract_consistency__mutmut_43'] = x_check_contract_consistency__mutmut_43 # type: ignore # mutmut generated
