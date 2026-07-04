#!/usr/bin/env python3
"""#2 变异测试审计（手动运行，不进 pytest 默认套件——避免审计中改源码污染并行测试）。

对关键纯函数注入"真实变异"，跑对应测试，确认【被抓住】（测试非零退出）。
mutmut 3.x 与本仓 flat-layout + sys.path 测试集成需单独配置（mutants/ 只复制
被变文件，跨模块 import 会断），故先用此脚本兑现"测试质量审计"的价值。
用法：python tests/mutation_audit.py
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable

# (相对路径, 原文, 变异文, 覆盖它的测试文件, 说明)
MUTATIONS = [
    ("touchstone/contract_check.py",
     "if line.is_added:",
     "if not line.is_added:",
     "tests/test_contract.py",
     "parse_diff：把 is_added 取反 → 改动行解析全反"),
    ("touchstone/contract_check.py",
     r're.compile(r"AKIA[0-9A-Z]{16}")',
     r're.compile(r"AKIA[0-9A-Z]{32}")',  # 16→32：真 AKIA key 不再匹配
     "tests/test_adversarial.py",
     "SEC-001：放宽 AKIA 长度 → 真密钥漏报"),
    ("touchstone/review_provider.py",
     '"kind": "suggestion",',
     '"kind": "review",',
     "tests/test_review_provider.py",
     "parse_pr_agent：把 suggestion 误标 review → 解析分类错"),
    ("touchstone/learning_loop.py",
     "return json.loads(raw[i:j + 1])",
     "return raw",
     "tests/test_learning_loop.py",
     "_extract_json：不解析直接返串 → JSON 抽取失效"),
    ("touchstone/calibrate.py",
     'out = {"total": len(records),',
     'out = {"total": len(records) + 1,',
     "tests/test_loop_govern_calibrate.py",
     "aggregate：total 计数错 → 校准统计失真"),
    ("touchstone/loop.py",
     'return "escalate", "无推进',
     'return "continue", "无推进',
     "tests/test_loop_govern_calibrate.py",
     "loop_step：无推进不升级 → 抗博弈闸失效"),
]


def run_one(path, find, replace, test, note):
    full = os.path.join(ROOT, path)
    src = open(full, encoding="utf-8").read()
    if find not in src:
        return ("SKIP", f"锚点未找到（代码已变？）：{find[:40]}")
    open(full, "w", encoding="utf-8").write(src.replace(find, replace, 1))
    try:
        r = subprocess.run([PY, "-m", "pytest", "-q", os.path.join(ROOT, test)],
                           capture_output=True, text=True, timeout=180,
                           cwd=ROOT)
        caught = r.returncode != 0
        return ("CAUGHT" if caught else "SURVIVED",
                f"rc={r.returncode}；{note}")
    finally:
        open(full, "w", encoding="utf-8").write(src)   # 还原


def main():
    print("=== 变异测试审计：注入变异 → 跑测试 → 期望被抓住（CAUGHT）===\n")
    survived = []
    for path, find, replace, test, note in MUTATIONS:
        status, detail = run_one(path, find, replace, test, note)
        flag = "✅" if status == "CAUGHT" else ("⚠️ " if status == "SURVIVED" else "—")
        print(f"{flag} [{status}] {path}: {note}")
        print(f"     {detail}")
        if status == "SURVIVED":
            survived.append(note)
    print(f"\n汇总：{len(MUTATIONS) - len(survived)}/{len(MUTATIONS)} 变异被测试抓住。")
    if survived:
        print("存活的变异（测试未抓住 → 测试需加强）：")
        for s in survived:
            print(f"  - {s}")
        sys.exit(1)
    print("全部被抓住 → 关键路径测试是真护栏。")


if __name__ == "__main__":
    main()
