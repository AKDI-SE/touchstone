# ============================================================================
# tests/test_hygiene_silent_except.py —— "never silent" 纪律的机器闸
#
# 扫描 touchstone/*.py：任何 `except ...:` + 紧邻 `pass` 的静默吞异常点，其近旁
# （except 前 3 行 + pass 行及其后 1 行）必须存在下列信号之一：
#   • 可见性动作：log / print / _ix / stderr（异常已被记录）
#   • 显式豁免标记：`静默豁免`（附理由的正当静默——清理 best-effort、扫描协议等）
# 新增静默点要么补日志，要么写明豁免理由；两者都没有 → 本测试红。
# 背景：商用审计 P2-1，14 处无信号静默点（与仓库自身防静默故障纪律矛盾）已清零。
# ============================================================================
import glob
import os
import re

ROOT = os.path.join(os.path.dirname(__file__), "..", "touchstone")


def _silent_sites():
    sites = []
    for f in sorted(glob.glob(os.path.join(ROOT, "*.py"))):
        src = open(f, encoding="utf-8").read().splitlines()
        for i, l in enumerate(src):
            if re.match(r"\s*except.*:\s*$", l) and i + 1 < len(src) \
                    and re.match(r"\s*pass\s*(#.*)?$", src[i + 1]):
                ctx = "\n".join(src[max(0, i - 3):min(len(src), i + 3)])
                if not re.search(r"log|print|_ix|stderr|静默豁免", ctx, re.I):
                    sites.append(f"{os.path.basename(f)}:{i + 1}")
    return sites


def test_no_unmarked_silent_except_pass():
    sites = _silent_sites()
    assert not sites, (
        "发现无信号的静默 except-pass（补日志或加『静默豁免：<理由>』注释）: "
        + ", ".join(sites))
