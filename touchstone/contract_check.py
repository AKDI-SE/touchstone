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


def parse_diff(diff_text):
    """返回 (changed_files:set[str], added_lines:dict[file -> list[(lineno, text)]])。
    用成熟库 unidiff 解析，稳妥处理重命名/合并/边界等长尾（替代早期手写状态机）。"""
    files, added = set(), {}
    try:
        patch = PatchSet(diff_text or "")
    except UnidiffParseError:
        return files, added                  # 解析失败 → 返回空，调用方据空降级
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


def _finding(rule_id, file, line, category, rationale, fix, rule_index,
             confidence=1.0, severity=None):
    return {
        "rule_id": rule_id, "file": file, "line": line, "category": category,
        "severity": severity or rule_index.get(rule_id, {}).get("severity", "warn"),
        "confidence": confidence,        # 确定性核对默认 1.0；纯启发式可下调
        "rationale": rationale, "suggested_fix": fix, "agent": "contract-check",
    }


def _match_any(path, globs):
    return any(fnmatch.fnmatch(path, g) for g in globs)


def check_scope(files, scope, rule_index):
    if not scope:
        return []
    return [_finding("SCOPE-001", f, 0, "scope_creep",
                     "改动文件不在提交契约声明的 scope 内（疑似越界）",
                     f"将 {f} 的改动拆到独立 PR，或在 scope 中显式声明", rule_index)
            for f in sorted(files) if not _match_any(f, scope)]


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


def _identifiers(text):
    """从代码文本抽出标识符集合：完整点链 + 叶子名。供精确成员匹配（非子串）。"""
    out = set()
    for t in re.findall(r"[A-Za-z_][A-Za-z0-9_.]+", text):
        out.add(t)
        out.add(t.split(".")[-1])
    return out


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


_CODE_EXT = {".java", ".kt", ".py", ".go", ".ts", ".tsx", ".js", ".jsx", ".rs", ".scala"}


def _is_test(p):
    return "test" in p.lower() or "spec" in p.lower()


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


def check_contract_consistency(diff_text, contract, rule_index):
    """确定性核对契约三项声明（需 manifest）+ 无 manifest 也能跑的纯 diff 事实检查。"""
    contract = contract or {}
    files, added = parse_diff(diff_text)
    return (check_scope(files, contract.get("scope"), rule_index)
            + check_tests(files, contract.get("tests_added"), rule_index)
            + check_reuse(added, contract.get("reused_components"), rule_index)
            + check_untested_code(files, rule_index))
