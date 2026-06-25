#!/usr/bin/env python3
# ============================================================================
# touchstone/checks.py —— 可插拔"必须通过"检查框架
# ----------------------------------------------------------------------------
# 设计要点：
#   • 策略全在 .touchstone/checks.yaml（挂哪些检查、哪几个 required、阈值）——不散在
#     GitHub 设置里；改"哪个必须绿"只改这个文件。
#   • 对外只发【一个】总闸状态(默认 touchstone/gate)：当且仅当所有 required 且启用
#     的检查都通过时为 success。GitHub 那边只需一次性要求这一个状态即可（人点合并场景）。
#   • 三种插件：
#       builtin —— 进程内函数（如 touchstone 自带确定性规则、verify 深检）
#       relay   —— 读某个【已有】GitHub check-run 的结论（工具在自己的 CI 里跑过）
#       service —— POST PR 上下文到一个 HTTP 服务，拿回结果（未来自建服务的挂点）
#   • Touchstone 不发明关卡：质量保障来自现成工具/未来服务，这里只提供挂载与汇总。
# ============================================================================

import os

import requests
import yaml

import ghclient

DEFAULT_GATE = "touchstone/gate"
_RELAY_OK = {"success", "neutral", "skipped"}
_BUILTINS = {}        # name -> fn(pr_ctx, cfg) -> (passed: bool|None, summary: str)


def builtin(name):
    """注册一个内置检查插件。fn 返回 (passed, summary)；passed=None 表示中性/跳过。"""
    def deco(fn):
        _BUILTINS[name] = fn
        return fn
    return deco


class CheckResult:
    def __init__(self, name, passed, summary="", required=False):
        self.name = name
        self.passed = passed          # True 通过 / False 失败 / None 中性·跳过·未知
        self.summary = summary
        self.required = required


# ---- 配置 -------------------------------------------------------------------
def load_config(repo_dir):
    path = os.environ.get("TOUCHSTONE_CHECKS",
                          os.path.join(repo_dir, ".touchstone", "checks.yaml"))
    try:
        data = yaml.safe_load(open(path, encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        data = {}
    data.setdefault("gate", {}).setdefault("status_name", DEFAULT_GATE)
    data.setdefault("checks", [])
    return data


# ---- 各类插件运行器 ---------------------------------------------------------
def _gh(pr, method, path):
    base = os.environ.get("GITHUB_API_URL", "https://api.github.com")
    return ghclient.request(method, base + path, pr["token"])


def _run_relay(pr, cfg):
    """读某个已有 check-run 的结论（工具在自己的 CI 跑过，这里只转达）。"""
    src = cfg.get("source_check")
    data = _gh(pr, "GET", f"/repos/{pr['owner']}/{pr['repo']}/commits/{pr['sha']}/check-runs")
    runs = [r for r in (data.get("check_runs") or []) if r.get("name") == src]
    if not runs:
        return None, f"未找到检查 {src}"
    if any(r.get("status") != "completed" for r in runs):
        return None, f"{src} 未完成"
    bad = [r for r in runs if r.get("conclusion") not in _RELAY_OK]
    return (not bad), f"{src}=" + ",".join(r.get("conclusion") or "?" for r in runs)


def _run_service(pr, cfg):
    """POST PR 上下文到一个 HTTP 服务（未来自建质量服务的挂点）。"""
    r = requests.post(cfg["url"], json={
        "owner": pr["owner"], "repo": pr["repo"], "sha": pr["sha"],
        "files": pr.get("files", [])}, timeout=cfg.get("timeout", 60))
    r.raise_for_status()
    d = r.json()
    return bool(d.get("passed")), str(d.get("summary", ""))


def _run_builtin(pr, cfg):
    fn = _BUILTINS.get(cfg.get("plugin", cfg.get("name")))
    if fn is None:
        return None, f"未注册的内置插件 {cfg.get('plugin', cfg.get('name'))}"
    return fn(pr, cfg)


_RUNNERS = {"builtin": _run_builtin, "relay": _run_relay, "service": _run_service}


# ---- 编排：跑检查 → 汇总总闸 → 发一个状态 -----------------------------------
def run_checks(config, pr):
    results = []
    for cfg in config.get("checks", []):
        if not cfg.get("enabled", True):
            continue
        name = cfg.get("name", "?")
        required = bool(cfg.get("required", False))
        runner = _RUNNERS.get(cfg.get("type", "builtin"))
        if runner is None:
            results.append(CheckResult(name, None, f"未知插件类型 {cfg.get('type')}", required))
            continue
        try:
            passed, summary = runner(pr, cfg)
        except Exception as e:        # 插件隔离：单个插件失败不拖垮总闸计算，记为中性
            passed, summary = None, f"插件异常: {e}"
        results.append(CheckResult(name, passed, summary, required))
    return results


def aggregate_gate(results):
    """总闸：所有【required】检查都必须 passed=True；任一 required 非通过 → 总闸 failure。
    非 required 的结果只作信息展示，不影响总闸。无 required 检查 → success（空策略不挡）。"""
    required = [r for r in results if r.required]
    if any(r.passed is not True for r in required):
        return "failure"
    return "success"


def post_gate(pr, config, results):
    """把汇总后的总闸发成【一个】GitHub check-run；明细列在 summary 里。"""
    gate = aggregate_gate(results)
    name = config["gate"]["status_name"]
    mark = {True: "✓", False: "✗", None: "–"}
    lines = [f"{mark[r.passed]} {r.name}{'（必须）' if r.required else ''}: {r.summary}"
             for r in results]
    base = os.environ.get("GITHUB_API_URL", "https://api.github.com")
    ghclient.request("POST", base + f"/repos/{pr['owner']}/{pr['repo']}/check-runs",
                     pr["token"], data={
                         "name": name, "head_sha": pr["sha"], "status": "completed",
                         "conclusion": gate,
                         "output": {"title": f"Touchstone 总闸：{gate}",
                                    "summary": "\n".join(lines) or "（无启用的检查）"}})
    return gate, results


# ---- 内置插件：touchstone 自带的确定性规则 -----------------------------------
@builtin("touchstone-rules")
def _check_touchstone_rules(pr, cfg):
    """通过 = 确定性检查（contract-check + touchstone-rules）无拦截级发现。
    拦截级 = severity == block_candidate（含被 enforce 固化升级的）或 category == contract。
    severity 由各检查器按规则 severity 计算：block_candidate 规则立即拦截，warn 规则仅 enforced 后拦截。"""
    findings = pr.get("contract_findings") or []
    block = [f for f in findings
             if f.get("severity") == "block_candidate" or f.get("category") == "contract"]
    if block:
        ids = ",".join(sorted({f.get("rule_id", "?") for f in block}))
        return False, f"确定性规则拦截：{ids}"
    return True, f"{len(findings)} 条建议、无拦截级"


# ---- 内置插件：verify 正确性深检（默认关；算力够时在 checks.yaml 里开）----------
@builtin("verify")
def _check_verify(pr, cfg):
    """折入 verify 深检结果：verify_change 作为独立/按需 job 跑、写 verify-result.json，
    本插件只把它的结论折进总闸。未跑则记中性（不挡）。"""
    import json
    path = cfg.get("result_file", "verify-result.json")
    try:
        d = json.load(open(path, encoding="utf-8"))
    except (OSError, ValueError):
        return None, "verify 未运行（无结果文件）"
    # 可信绿：author 自报规格(author_proposed)的绿不构成正确性认证，不算通过（此规则由 autonomy.floor 搬来）
    passed = bool(d.get("passed")) and d.get("spec_source") != "author_proposed"
    return passed, f"verify passed={d.get('passed')} spec={d.get('spec_source')}"


# ---- CLI：独立发总闸（CI 的 gate job 在 touchstone(+ 可选 verify) 之后聚合并发布）----
def main():
    """读 cwd 的 touchstone-findings.json（+ 若 verify 跑过则有 verify-result.json）→ 跑检查
    → 发对外那【一个】总闸 → 把最终结论写回 touchstone-findings.json（供 autonomy 读到含 verify 的总闸）。"""
    import json
    try:
        co = json.load(open("touchstone-findings.json", encoding="utf-8"))
    except (OSError, ValueError):
        print("[gate] 无 touchstone-findings.json；no-op")
        return
    owner, _, name = os.environ.get("GITHUB_REPOSITORY", "/").partition("/")
    findings = co.get("findings", [])
    pr = {"owner": owner, "repo": name, "sha": co.get("sha"),
          "token": os.environ.get("GITHUB_TOKEN", ""),
          "files": co.get("changed_files", []),
          # 确定性发现 = contract-check（含 SEC-001 密钥）+ touchstone-rules（CTR/SPR/JAVA）
          "contract_findings": [f for f in findings
                                if f.get("agent") in ("contract-check", "touchstone-rules")]}
    cfg = load_config(os.environ.get("REPO_DIR", "."))
    gate, _ = post_gate(pr, cfg, run_checks(cfg, pr))
    co["gate"] = gate
    with open("touchstone-findings.json", "w", encoding="utf-8") as f:
        json.dump(co, f, ensure_ascii=False, indent=2)
    print(f"[gate] 总闸={gate}（已写回 touchstone-findings.json）")


if __name__ == "__main__":
    main()
