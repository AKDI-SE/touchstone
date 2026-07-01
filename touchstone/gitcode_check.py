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
import subprocess
import sys

# 确保能 import 同目录的 touchstone 模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import yaml
import contract_check
import stack_rules


def load_yaml(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_diff_from_git(base_branch="main"):
    """尝试多种方式获取 diff：PR merge-base diff → HEAD~1 → 工作区变更"""
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
    for cmd in commands:
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0 and result.stdout.strip():
                print(f"[gitcode_check] 使用 diff 命令: {' '.join(cmd)}")
                return result.stdout
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            continue
    return None


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

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--diff" and i + 1 < len(args):
            if args[i + 1] == "-":
                diff_text = sys.stdin.read()
            else:
                diff_text = args[i + 1]
            i += 2
        elif args[i] == "--base" and i + 1 < len(args):
            base_branch = args[i + 1]
            i += 2
        else:
            i += 1

    # 获取 diff
    if diff_text is None:
        diff_cmd = os.environ.get("GITCODE_DIFF_CMD")
        if diff_cmd:
            try:
                result = subprocess.run(diff_cmd, shell=True, capture_output=True, text=True, timeout=30)
                diff_text = result.stdout
            except (subprocess.TimeoutExpired, OSError) as e:
                print(f"[gitcode_check] 自定义 diff 命令失败: {e}", file=sys.stderr)

    if diff_text is None:
        diff_text = get_diff_from_git(base_branch)

    if not diff_text or not diff_text.strip():
        print("[gitcode_check] ⚠️ 无法获取 diff，跳过确定性检查（非 PR 事件或空 diff）")
        print("[gitcode_check] ✅ 总闸: PASS (无可检查内容)")
        return 0

    # 加载规范与契约
    standards_path = os.environ.get("TOUCHSTONE_STANDARDS", ".touchstone/standards.yaml")
    contract_path = os.environ.get("TOUCHSTONE_CONTRACT", ".touchstone/pr.yaml")

    standards = load_yaml(standards_path)
    if not standards:
        print(f"[gitcode_check] ❌ 未找到规范文件 {standards_path}")
        return 1

    rule_index = {r["id"]: r for r in standards.get("rules", [])}
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
    print(f" 总闸 (touchstone/gate)")
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
