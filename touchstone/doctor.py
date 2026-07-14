#!/usr/bin/env python3
# ============================================================================
# touchstone/doctor.py  ——  健康度自检（一键红绿报告 + 上线门）
# ----------------------------------------------------------------------------
# preflight 回答"环境可达吗"（配置齐、端点通）；doctor 在其之上多回答一句
# "评审引擎现在真能跑通、产出裁决吗"——把 preflight 到不了的那一步（跑通一次评审）补上，
# 汇成一张红绿表，并用【退出码】表达这台机器现在能不能稳定上线跑 touchstone。
#
#   touchstone doctor              # 全检（配置 + 连通 + 自检评审）
#   touchstone doctor --no-net     # 跳过连通性（离线只检配置 + 自检评审）
#   touchstone doctor --json       # 机器可读 JSON（运维聚合 / CI 门用）
#   python -m touchstone.doctor    # 等价入口
#
# 退出码：0 = 可上线（无阻断项）；1 = 有阻断项，修正后再跑真评审。
#
# 概念（见 module-design）：
#   · 自检评审（smoke review）：用【合成 PR 上下文】在进程内跑一次真实评审主链
#     （orchestrator.review_pr），注入空 LLM 观察源 → 走确定性裁决链、零网络，
#     断言产出【合法裁决】。证明"引擎能产出裁决"，而非仅"环境可达"。
#     LLM/PR-Agent 端点的可达性由【连通性阶段】单独覆盖，二者互不拖累。
#   · 健康度报告（health report）：配置 / 连通 / 自检评审三阶段汇成红绿表 + 单一退出码。
# ============================================================================

import json
import os
import shutil
import sys
import tempfile

from touchstone import preflight


# 阻断集（✗ → 退出 1）：与 preflight 的 hard-fail 同源，另加 GitHub API 与自检评审。
# 其余 ok=False 项（如上下文窗口过小、LLM 端点不通）判 ⚠ 警告——可降级/可事后补，不拦上线门。
SMOKE_ROW = "自检评审（评审引擎跑通）"
BLOCKING = set(preflight.REQUIRED) | {"standards.yaml", "model-diversity", "GitHub API", SMOKE_ROW}

# 合成 PR：一行改动，触发确定性核对链但不依赖任何外部资源。
_SMOKE_DIFF = (
    "diff --git a/app/pay.py b/app/pay.py\n"
    "index 1111111..2222222 100644\n"
    "--- a/app/pay.py\n"
    "+++ b/app/pay.py\n"
    "@@ -1,2 +1,3 @@\n"
    " def charge(amount):\n"
    "+    log('charging', amount)\n"
    "     return amount\n"
)
_SMOKE_STANDARDS = {"rules": [
    {"id": "SPR-001", "title": "自检占位规则", "severity": "advisory",
     "machine_checkable": False, "description": "doctor smoke"},
]}


def smoke_review(env=None):
    """自检评审：合成 PR → 进程内跑 orchestrator.review_pr（注入空观察源 → 确定性链、零网络）
    → 断言产出合法裁决。返回 (ok, detail)。任何异常都判 ✗ 并如实报（never silent）。"""
    from touchstone import orchestrator
    prev_repo_dir = os.environ.get("REPO_DIR")
    tmp = tempfile.mkdtemp(prefix="ts_doctor_smoke_")
    os.environ["REPO_DIR"] = tmp                 # 隔离：不读客户真实仓的 .touchstone 配置
    try:
        pr_ctx = {"owner": "_doctor", "repo": "_smoke", "number": 0, "sha": "0" * 40,
                  "token": "", "diff": _SMOKE_DIFF, "standards": _SMOKE_STANDARDS}
        out = orchestrator.review_pr(pr_ctx, contract={}, standards=_SMOKE_STANDARDS,
                                     provider=lambda _pr: [])   # 空 LLM 观察源 → 确定性裁决链
        risk = out.get("risk")
        findings = out.get("findings")
        if isinstance(risk, dict) and "risk_band" in risk and isinstance(findings, list):
            return True, (f"引擎跑通：engine_status={out.get('engine_status')}，"
                          f"裁决 risk_band={risk['risk_band']}，findings={len(findings)} 条")
        return False, f"引擎未产出合法裁决：risk={risk!r} findings={type(findings).__name__}"
    except Exception as e:                        # noqa: BLE001 —— 自检必须捕获一切并如实报
        return False, f"引擎异常：{type(e).__name__}: {e}"
    finally:
        if prev_repo_dir is None:
            os.environ.pop("REPO_DIR", None)
        else:
            os.environ["REPO_DIR"] = prev_repo_dir
        shutil.rmtree(tmp, ignore_errors=True)


def collect(env, no_net=False):
    """跑三阶段，返回 [(stage_name, [(name, ok, detail), ...]), ...]。纯数据，供打印或 JSON。"""
    stages = [("配置", preflight.check_config(env) + preflight.check_standards(env))]
    if not no_net:
        stages.append(("连通性（从你的网络）", preflight.check_network(env)))
    ok, detail = smoke_review(env)
    stages.append(("自检评审", [(SMOKE_ROW, ok, detail)]))
    return stages


def _state(name, ok):
    """三态：pass / warn / fail。ok=False 且在阻断集 → fail；否则 warn。"""
    if ok:
        return "pass"
    return "fail" if name in BLOCKING else "warn"


def _report(stages):
    """把阶段折成机器可读报告 + 汇总计数 + 总体是否可上线。"""
    from touchstone import __version__
    out_stages, n = [], {"pass": 0, "warn": 0, "fail": 0}
    for sname, rows in stages:
        srows = []
        for name, ok, detail in rows:
            st = _state(name, ok)
            n[st] += 1
            srows.append({"name": name, "state": st, "detail": detail})
        out_stages.append({"stage": sname, "rows": srows})
    return {"version": __version__, "ok": n["fail"] == 0,
            "summary": n, "stages": out_stages}


def _print_human(report):
    mark = {"pass": "✓", "warn": "⚠", "fail": "✗"}
    print("\nTouchstone 健康度自检（doctor）")
    print("=" * 64)
    for stage in report["stages"]:
        print(f"\n— {stage['stage']} —")
        for r in stage["rows"]:
            print(f"  {mark[r['state']]} {r['name']:34} {r['detail']}")
    s = report["summary"]
    print("=" * 64)
    print(f"通过 {s['pass']}　警告 {s['warn']}　阻断 {s['fail']}")
    if report["ok"]:
        print("健康：可上线。下一步端到端试跑："
              "touchstone --repo O/R --pr N   （dry-run，确认后加 --post）")
    else:
        print("有阻断项（✗）——修正后再真跑。⚠ 为可降级/可事后补的警告，不拦门。")


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(
        prog="touchstone doctor",
        description="健康度自检：配置 + 连通 + 一次自检评审，红绿报告 + 退出码表达能否上线")
    ap.add_argument("--no-net", action="store_true", help="跳过连通性检查（离线只检配置 + 自检评审）")
    ap.add_argument("--json", action="store_true", help="输出机器可读 JSON（运维聚合 / CI 门用）")
    args = ap.parse_args(sys.argv[1:] if argv is None else argv)

    report = _report(collect(dict(os.environ), no_net=args.no_net))
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_human(report)
    sys.exit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
