#!/usr/bin/env python3
"""
gitcode_check.py  ——  GitCode 上的确定性门禁（无需 GitHub API / LLM）

在 GitCode Pipeline 中运行，对本仓自身的 PR 做离线确定性检查：
  - 契约一致性核对 (contract_check: scope/测试/复用/密钥扫描)
  - 栈专项规则 (stack_rules: CTR/SPR/JAVA 等 machine_checkable 规则)
  - 聚合输出总闸结论

用法：
  python touchstone/gitcode_check.py            # 自动检测 diff（PR/push）
  python touchstone/gitcode_check.py --diff -    # 从 stdin 读 diff
  python touchstone/gitcode_check.py --base main # 指定 base 分支

环境变量：
  GITCODE_DIFF_CMD    覆盖默认的 git diff 命令
  TOUCHSTONE_STANDARDS 规范文件路径（默认 .touchstone/standards.yaml）
  TOUCHSTONE_CONTRACT  契约文件路径（默认 .touchstone/pr.yaml）
"""
import os
import shlex
import subprocess
import sys

# 确保能 import 同目录的 touchstone 模块

import yaml
from touchstone import contract_check
from touchstone import stack_rules


def load_yaml(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_diff_from_git(base_branch="main"):
    """尝试多种方式获取 diff：PR merge-base diff → HEAD~1 → 工作区变更。

    返回 (diff_text or None, any_ok)。any_ok = 至少一条命令成功执行（rc==0，哪怕输出为空）。
    审计 #25：调用方据此区分「真没改动」（PASS 合法）与「git 全挂/仓库缺失」（fail-closed）。
    审计 #26：降级到 HEAD~1/工作区 diff 时大声告警——它们检查的【不是】本 PR 相对 base 的
    完整范围，静默降级会让"范围查不全的门禁绿灯"看起来与正常通过无异。"""
    commands = [
        # PR 场景：从 base 到 HEAD 的 diff
        ["git", "diff", f"origin/{base_branch}...HEAD"],
        # 备选：origin/main..HEAD
        ["git", "diff", f"origin/{base_branch}..HEAD"],
        # 备选：最近一次提交
        ["git", "diff", "HEAD~1"],
        # 备选：工作区变更
        ["git", "diff", "HEAD"],
    ]
    any_ok = False
    for idx, cmd in enumerate(commands):
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                any_ok = True
                if result.stdout.strip():
                    print(f"[gitcode_check] 使用 diff 命令: {' '.join(cmd)}")
                    if idx >= 2:      # 审计 #26：降级路径大声说清楚"查的不是全范围"
                        print(f"[gitcode_check] ⚠️ 降级回退到 '{' '.join(cmd)}'：前序 diff 命令失败或为空，"
                              f"本结论只覆盖该 diff，不保证是本 PR 相对 {base_branch} 的完整改动范围。",
                              file=sys.stderr)
                    return result.stdout, True
                # rc==0 但输出为空 → 继续试下一条（push 事件下 origin/base...HEAD 恒空，
                # 靠 HEAD~1 取增量——这不是失败，不告警）
            else:
                print(f"[gitcode_check] ⚠️ diff 命令失败 (rc={result.returncode}): "
                      f"{' '.join(cmd)}: {(result.stderr or '').strip()[-160:]}", file=sys.stderr)
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
            print(f"[gitcode_check] ⚠️ diff 命令异常: {' '.join(cmd)}: {e}", file=sys.stderr)
    return None, any_ok


def _format_finding(f, idx):
    """格式化单条发现为可读文本"""
    sev = f.get("severity", "?")
    icon = {"block_candidate": "🚫", "warn": "⚠️", "info": "ℹ️"}.get(sev, "•")
    return (
        f"  {idx}. {icon} [{sev}] {f['rule_id']} "
        f"({f.get('agent','?')}) conf={f.get('confidence',0):.2f}\n"
        f"     {f.get('file','?')}:{f.get('line','?')}\n"
        f"     {f.get('rationale','')[:200]}\n"
        f"     → {f.get('suggested_fix','')[:200]}"
    )


def main():
    # 解析参数
    base_branch = "main"
    diff_text = None
    explicit = False        # 审计 #25：显式提供 diff（--diff/GITCODE_DIFF_CMD）= 范围可信，空即真空

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--diff" and i + 1 < len(args):
            if args[i + 1] == "-":
                diff_text = sys.stdin.read()
            else:
                diff_text = args[i + 1]
            explicit = True
            i += 2
        elif args[i] == "--base" and i + 1 < len(args):
            base_branch = args[i + 1]
            i += 2
        else:
            i += 1

    # 获取 diff
    diff_any_ok = False
    explicit_cmd_failed = False
    if diff_text is None:
        diff_cmd = os.environ.get("GITCODE_DIFF_CMD")
        if diff_cmd:
            # 不走 shell（自家 SEC 规则同款精神：不给注入面）。需要管道时请显式写
            # GITCODE_DIFF_CMD='bash -c "git diff ... | filter"'，让 shell 语义成为明示选择。
            try:
                result = subprocess.run(shlex.split(diff_cmd), capture_output=True,
                                        text=True, timeout=30)
                if result.returncode == 0:
                    # 部署方显式指定了 diff 源：rc==0 即采信其输出（空输出=真无改动，
                    # 不再回落 git 链——那条链可能查到与本事件无关的 HEAD~1）
                    diff_text, diff_any_ok = result.stdout, True
                else:
                    # pr-agent 第五轮评审：显式 diff 源失败【不得静默回落】内置 git 链——部署方
                    # 指定它恰恰因为内置链查错对象（HEAD~1 无关事件）；回落=拿错 diff 评审还看似
                    # 正常。保持空 diff + not-ok，交给末尾总闸 fail-closed（exit 1）。
                    print(f"[gitcode_check] ⚠️ 自定义 diff 命令非零退出 (rc={result.returncode})，"
                          f"不回落内置 git 链（总闸将 FAIL）：{(result.stderr or '').strip()[-200:]}",
                          file=sys.stderr)
                    explicit_cmd_failed = True
            except (subprocess.TimeoutExpired, OSError) as e:
                print(f"[gitcode_check] 自定义 diff 命令失败（不回落内置 git 链）：{e}", file=sys.stderr)
                explicit_cmd_failed = True

    if diff_text is None and not explicit_cmd_failed:
        diff_text, diff_any_ok = get_diff_from_git(base_branch)

    if not diff_text or not diff_text.strip():
        if explicit or diff_any_ok:
            print("[gitcode_check] ✅ diff 为空（无文本改动/非 PR 事件）——无可检查内容，总闸 PASS")
            return 0
        # 审计 #25：一条 diff 命令都没成功——门禁在「不知道改了什么」的状态下必须 fail-closed，
        # 绝不能报 PASS（浅克隆无 origin/ref 名不对/git 不在 PATH 都会走到这里，旧版一律绿灯）。
        print("[gitcode_check] ❌ 所有 diff 来源均失败——无法确定检查范围，门禁 fail-closed（拒绝放行）",
              file=sys.stderr)
        print("[gitcode_check] ❌ 总闸: FAIL (无法获取 diff)")
        return 1

    # 加载规范与契约
    standards_path = os.environ.get("TOUCHSTONE_STANDARDS", ".touchstone/standards.yaml")
    contract_path = os.environ.get("TOUCHSTONE_CONTRACT", ".touchstone/pr.yaml")

    standards = load_yaml(standards_path)
    if not standards:
        print(f"[gitcode_check] ❌ 未找到规范文件 {standards_path}")
        return 1

    rule_index = {}
    for r in standards.get("rules", []) or []:
        _rid = (r or {}).get("id") if isinstance(r, dict) else None   # 审计 #7：缺 id 跳过+告警
        if not _rid:
            print(f"[gitcode_check] ⚠️ 规则缺 id（跳过该条）: {r!r}"[:300], file=sys.stderr)
            continue
        rule_index[_rid] = r
    contract = load_yaml(contract_path, {})

    # ─── 运行确定性检查 ───────────────────────────────────────────
    print("=" * 60)
    print(" Touchstone 确定性门禁 · GitCode")
    print("=" * 60)
    print(f" 规范: {standards_path} ({len(rule_index)} 条规则)")
    print(f" diff: {len(diff_text)} 字符")
    print()

    # 1. 契约一致性核对
    print("─ 契约核对 (contract_check) ─")
    contract_findings = contract_check.check_contract_consistency(diff_text, contract, rule_index)
    if contract_findings:
        for idx, f in enumerate(contract_findings, 1):
            print(_format_finding(f, idx))
    else:
        print("  ✅ 无契约违规发现")
    print()

    # 2. 栈专项规则
    print("─ 栈规则 (stack_rules) ─")
    stack_findings = stack_rules.check_stack_rules(diff_text, rule_index)
    if stack_findings:
        for idx, f in enumerate(stack_findings, 1):
            print(_format_finding(f, idx))
    else:
        print("  ✅ 无栈规则违规发现")
    print()

    # ─── 聚合总闸 ─────────────────────────────────────────────────
    all_findings = contract_findings + stack_findings
    blocks = [f for f in all_findings if f.get("severity") == "block_candidate"]
    warns = [f for f in all_findings if f.get("severity") == "warn"]
    infos = [f for f in all_findings if f.get("severity") == "info"]

    print("=" * 60)
    print(" 总闸 (touchstone/gate)")
    print(f"   🚫 阻断级: {len(blocks)} 条")
    print(f"   ⚠️  警告级: {len(warns)} 条")
    print(f"   ℹ️  信息级: {len(infos)} 条")

    if blocks:
        print()
        print(" ❌ GATE FAILURE — 以下阻断级发现必须修复：")
        for f in blocks:
            print(f"    [{f['rule_id']}] {f.get('file','?')}:{f.get('line','?')} — {f.get('rationale','')[:120]}")
        print("=" * 60)
        return 1
    else:
        print(" ✅ GATE PASS — 无阻断级发现，确定性门禁通过")
        print("=" * 60)
        return 0


if __name__ == "__main__":
    sys.exit(main())
