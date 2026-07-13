#!/usr/bin/env python3
# ============================================================================
# touchstone/preflight.py  ——  真跑前自检（#2）
# ----------------------------------------------------------------------------
# 真跑(run.py / orchestrator.py)前先跑这个：体检环境变量、规范可解析、
# GitHub / LLM / GraphQL 端点是否从【你的网络】可达。逐项 ✓/✗，便于定位连通性问题。
#   python -m touchstone.preflight              # 全检
#   python -m touchstone.preflight --no-net     # 只检配置(不打网络)
# ============================================================================

import json
import os
import sys
import urllib.request



REQUIRED = ["GITHUB_TOKEN"]
# LLM_* 仅 verify（独立验收测试，异模型）需要；评审走 PR-Agent（自有端点配置见 .touchstone/pr-agent.yaml），
# 不需要这些。故不列入 REQUIRED——缺失不阻断 preflight。
OPTIONAL = ["LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL", "LLM_TEST_MODEL",
            "GITHUB_REPOSITORY", "GITHUB_API_URL", "GITHUB_GRAPHQL_URL", "HTTP_PROXY", "HTTPS_PROXY"]


def check_config(env):
    """纯函数：返回 [(name, ok, detail)]。不打网络。"""
    rows = []
    for k in REQUIRED:
        v = env.get(k)
        rows.append((k, bool(v), "已设置" if v else "缺失（必需）"))
    # LLM_* 仅 verify 用；未设不阻断（评审走 PR-Agent），仅给提示
    missing_llm = [k for k in ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL") if not env.get(k)]
    if missing_llm:
        rows.append(("LLM（verify 用）", True,
                     f"未设置 {missing_llm}——评审不受影响；启用 verify（独立验收测试）时再设"))
    tm = env.get("LLM_TEST_MODEL")
    rows.append(("LLM_TEST_MODEL", True,
                 tm or "未设置（verify 独立验收测试将回落 LLM_MODEL；建议设为异模型）"))
    # touchstone 模型不应等于 author 模型（异模型是独立验收测试的前提）
    if env.get("LLM_MODEL") and tm and env["LLM_MODEL"] == tm:
        rows.append(("model-diversity", False, "LLM_MODEL == LLM_TEST_MODEL（应不同，避免同源盲点）"))
    # 常见坑：经代理访问公网时代理未配好会 407/挂起
    if env.get("HTTPS_PROXY") or env.get("HTTP_PROXY"):
        rows.append(("proxy", True, "检测到代理变量——若经代理访问公网，确认 *_PROXY/NO_PROXY 配置正确"))

    # 「不设就撞默认坑」的配置强校验（运维成熟度）——这些不设不会立刻报错，但会在真实
    # 运行中触发已知故障，preflight 必须提前 WARN 并说明后果，而非等线上撞坑再排查：
    #
    # TOUCHSTONE_LLM_CONTEXT_TOKENS 未按模型卡设置 → 回退 32768；若模型真实窗口 < 32768
    # 会超窗被端点 400 拒（大 PR 触发），> 32768 则没吃满上下文。是 PR #47 被拒的根因类别。
    ctx = env.get("TOUCHSTONE_LLM_CONTEXT_TOKENS")
    if not ctx:
        rows.append(("LLM 上下文窗口", True,
                     "未设 TOUCHSTONE_LLM_CONTEXT_TOKENS → 回退 32768。强烈建议按模型卡显式设置："
                     "过小端点会因输入超窗拒绝大 PR，过大则浪费上下文（见 SECURITY/CHANGELOG）"))
    else:
        try:
            _c = int(ctx)
            if _c < 8192:
                rows.append(("LLM 上下文窗口", False,
                             f"TOUCHSTONE_LLM_CONTEXT_TOKENS={_c} 过小——diff 极易被裁空致 LLM 0 建议"
                             "（PR #44 类故障）。请核对是否误填了输出上限而非上下文窗口"))
            else:
                rows.append(("LLM 上下文窗口", True, f"{_c} tokens（已按模型卡声明）"))
        except ValueError:
            rows.append(("LLM 上下文窗口", False, f"TOUCHSTONE_LLM_CONTEXT_TOKENS={ctx!r} 非整数"))

    # VERIFY_ENABLED 开启但缺 LLM 凭据 → verify 阶段必挂
    if env.get("VERIFY_ENABLED") == "true" and missing_llm:
        rows.append(("verify 前置", False,
                     f"VERIFY_ENABLED=true 但缺 {missing_llm}——verify 的 plan 阶段会因缺凭据失败"))

    # PRAGENT 超时过小 + 慢模型（如 glm）→ 子进程超时（PR #48 类）
    _to = env.get("TOUCHSTONE_PRAGENT_TIMEOUT")
    if _to:
        try:
            if int(_to) < 180:
                rows.append(("PR-Agent 超时", False,
                             f"TOUCHSTONE_PRAGENT_TIMEOUT={_to}s 偏小——慢模型（如 glm）易超时致本轮不可信；"
                             "建议 ≥ 360s"))
        except ValueError:
            rows.append(("PR-Agent 超时", False, f"TOUCHSTONE_PRAGENT_TIMEOUT={_to!r} 非整数"))
    return rows


def _ping(url, headers=None, data=None, timeout=15):
    try:
        req = urllib.request.Request(url, data=data, headers=headers or {},
                                     method="POST" if data else "GET")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return True, f"HTTP {r.status}"
    except Exception as e:                      # 网络自检：任何异常都如实报
        return False, f"{type(e).__name__}: {e}"


def check_network(env):
    rows = []
    api = env.get("GITHUB_API_URL", "https://api.github.com")
    tok = env.get("GITHUB_TOKEN", "")
    ok, d = _ping(api + "/rate_limit", {"Authorization": "Bearer " + tok,
                                        "User-Agent": "touchstone"})
    rows.append(("GitHub API", ok, d))
    base = (env.get("LLM_BASE_URL") or "").rstrip("/")
    if base:
        body = json.dumps({"model": env.get("LLM_MODEL", ""),
                           "messages": [{"role": "user", "content": "ping"}],
                           "max_tokens": 1}).encode()
        ok, d = _ping(base + "/chat/completions",
                      {"Authorization": "Bearer " + env.get("LLM_API_KEY", ""),
                       "Content-Type": "application/json"}, data=body, timeout=30)
        rows.append(("LLM 端点", ok, d))
    gql = env.get("GITHUB_GRAPHQL_URL", "https://api.github.com/graphql")
    ok, d = _ping(gql, {"Authorization": "Bearer " + tok, "Content-Type": "application/json",
                        "User-Agent": "touchstone"},
                  data=json.dumps({"query": "{viewer{login}}"}).encode())
    rows.append(("GitHub GraphQL（finding 级采纳用）", ok, d))
    return rows


def main():
    no_net = "--no-net" in sys.argv
    rows = [("— 配置 —", True, "")] + check_config(dict(os.environ))
    # 规范可解析
    try:
        import yaml
        sp = os.environ.get("TOUCHSTONE_STANDARDS", ".touchstone/standards.yaml")
        std = yaml.safe_load(open(sp))
        rows.append(("standards.yaml", bool(std and std.get("rules")),
                     f"{len(std.get('rules', []))} 条规则" if std else "解析失败"))
    except Exception as e:
        rows.append(("standards.yaml", False, str(e)))
    if not no_net:
        rows.append(("— 连通性（从你的网络）—", True, ""))
        rows += check_network(dict(os.environ))

    print("\nTouchstone 真跑预检")
    print("=" * 60)
    hard_fail = False
    for name, ok, detail in rows:
        if name.startswith("—"):
            print(f"\n{name}")
            continue
        mark = "✓" if ok else "✗"
        print(f"  {mark} {name:34} {detail}")
        if not ok and name in REQUIRED + ["standards.yaml", "model-diversity"]:
            hard_fail = True
    print("=" * 60)
    if hard_fail:
        print("有必需项未通过——修正后再真跑。")
        sys.exit(1)
    print("配置就绪。下一步：python -m touchstone.run --repo O/R --pr N   （dry-run，确认后加 --post）")


if __name__ == "__main__":
    main()
