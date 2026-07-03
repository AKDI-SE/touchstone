#!/usr/bin/env python3
# ============================================================================
# touchstone/pr_agent_runner.py  ——  PR-Agent 子进程适配器
#
# 在【装了 pr-agent 的环境】里调 PR-Agent（improve / review），不往 PR 发评论，
# 把结果打成 review_provider.parse_pr_agent 期望的 JSON 打到 stdout：
#     {"code_suggestions": [...], "review": {"key_issues_to_review": [...]}}
#
# 设计要点：
#   • Touchstone 本体【不依赖】pr-agent；pr-agent 只装在跑本脚本的子进程环境里（依赖隔离）。
#   • LLM 配置经 LLM_* env 映射成 pr-agent/LiteLLM 认的键（见 run() docstring），不在本仓
#     workflow 里重复散落凭据；GITHUB_TOKEN 经 env 透传给 pr-agent 取 PR。本脚本不持有、不打印密钥。
#   • PR-Agent 是 pip 包、不是要部署的服务——这里就是 import 它、调用、拿结果。
#   • 【防静默故障】引擎层失败（pr-agent 没装 / LLM 调用失败）一律不抛、不非零退出，而是返回
#     {"_degraded": "no_engine"|"llm_failed", "reason": ...}；review_provider 转成
#     ReviewEngineDegraded，orchestrator 把它写进贴到 PR 的人可见评审说明（见 docs/touchstone-on-pr-agent.html）。
#
# 已对 pr-agent 0.37.0 验证下列 API（improve 结果在 self.data；review 需自行 load_yaml
# 解析 self.prediction；extra_instructions/publish_output 为真实配置键）。其它版本若有差异，
# 这是【你拥有的适配器】，按你的版本对齐即可。沙箱无凭据无法真跑，只验 API 表面。
#
# best_practices.md 不经本脚本注入：pr-agent 的本地 best_practices 是【文件式】——把
# gen_best_practices.py 生成的 best_practices.md 放到被审 PR 的仓库根，pr-agent 自动识别。
# 本脚本只负责 extra_instructions（学习回路 active 经验 / 主观强调）的注入。
# ============================================================================

import argparse
import asyncio
import json
import os
import sys

# review 解析用的 keys_fix_yaml，与 pr-agent PRReviewer._prepare_pr_review 一致
_REVIEW_KEYS_FIX = ["key_issues_to_review:", "relevant_file:", "relevant_line:", "suggestion:"]


def _read(path):
    if not path:
        return None
    with open(path, encoding="utf-8") as f:
        return f.read()


def run(pr_url, mode, extra_instructions=None):
    """调 PR-Agent（不发评论）→ 返回 dict 供 touchstone 解析。

    LLM 配置经 LLM_* env 映射成 PR-Agent/LiteLLM 认的键（方案 b，集中在本适配器，
    不把凭据重复散落到 workflow 明文 env）：
      LLM_API_KEY  → OPENAI_API_KEY（LiteLLM openai provider 在调用时读）
      LLM_BASE_URL → OPENAI_API_BASE
      LLM_MODEL    → get_settings().config.model = "openai/<model>"（LiteLLM provider 前缀，走 OpenAI 兼容端点）

    GitHub 凭据：从 GITHUB_TOKEN（workflow 透传、subprocess 继承）注入 pr-agent 的
    settings.github.user_token，并显式 git_provider="github"——否则 pr-agent 取不到 PR
    （GitProviderFactory 报 "Failed to get git provider"），连 LLM 都调不到。

    任何引擎层失败都【不抛异常、不非零退出】，而是返回带 `_degraded` 的 dict，由 review_provider
    转成 ReviewEngineDegraded、再由 orchestrator 写进人可见的评审说明（防静默故障）：
      _degraded="no_engine"      —— pr-agent 未安装 / 导入失败
      _degraded="provider_failed"—— pr-agent 已导入但取 PR/git provider 失败（凭据/网络，pre-LLM）
      _degraded="llm_failed"     —— PR 已取到、但 LLM 调用失败（端点/鉴权/超时/解析等）
    """
    # 先把 LLM_* 映射成 LiteLLM 认的 env（必须在 import/调用 pr-agent 前注入）
    if os.environ.get("LLM_API_KEY") and not os.environ.get("OPENAI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = os.environ["LLM_API_KEY"]
    if os.environ.get("LLM_BASE_URL") and not os.environ.get("OPENAI_API_BASE"):
        os.environ["OPENAI_API_BASE"] = os.environ["LLM_BASE_URL"]
    model_override = os.environ.get("LLM_MODEL")

    try:
        from pr_agent.algo.utils import load_yaml
        from pr_agent.config_loader import get_settings
        from pr_agent.tools.pr_code_suggestions import PRCodeSuggestions
        from pr_agent.tools.pr_reviewer import PRReviewer
    except ImportError as e:
        return {"_degraded": "no_engine",
                "reason": f"pr-agent 未安装：请在本子进程环境 `pip install pr-agent`。原始错误：{e}"}

    s = get_settings()
    s.config.publish_output = False           # 关键：不往 PR 发评论，只取结构化结果
    s.config.publish_output_progress = False
    s.config.git_provider = "github"          # 显式：headless 运行时避免 provider 自动探测失败
    gh_tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GITHUB_USER_TOKEN")
    if gh_tok:
        s.github.user_token = gh_tok          # pr-agent 取 PR 需要 GitHub token
    if model_override:
        s.config.model = f"openai/{model_override}"   # LiteLLM：openai 前缀走 OpenAI 兼容端点
    if extra_instructions:
        s.pr_code_suggestions.extra_instructions = extra_instructions
        s.pr_reviewer.extra_instructions = extra_instructions

    out = {"code_suggestions": [], "review": {"key_issues_to_review": []}}
    tools = set(mode.split("+"))
    # 阶段一：构造 provider + 取 PR（pre-LLM）。构造时即拉取 PR diff，失败归 provider_failed。
    instances = {}
    try:
        if "improve" in tools:
            instances["cs"] = PRCodeSuggestions(pr_url)
        if "review" in tools:
            instances["rv"] = PRReviewer(pr_url)
    except Exception as e:
        return {"_degraded": "provider_failed",
                "reason": f"取 PR / git provider 失败（pre-LLM）：{type(e).__name__}: {e}"}
    # 阶段二：跑工具（LLM 调用）+ 解析。失败归 llm_failed。
    try:
        if "cs" in instances:
            asyncio.run(instances["cs"].run())           # 结果落在 cs.data = {"code_suggestions": [...]}
            out["code_suggestions"] = (getattr(instances["cs"], "data", None) or {}).get("code_suggestions") or []
        if "rv" in instances:
            asyncio.run(instances["rv"].run())           # rv.prediction 是原始 YAML 串；自行解析
            data = load_yaml((instances["rv"].prediction or "").strip(),
                             keys_fix_yaml=_REVIEW_KEYS_FIX,
                             first_key="review", last_key="security_concerns") or {}
            out["review"]["key_issues_to_review"] = (data.get("review") or {}).get("key_issues_to_review") or []
    except Exception as e:   # LLM 端点/鉴权/超时/解析失败等 —— 不静默吞掉，上报为 llm_failed
        return {"_degraded": "llm_failed", "reason": f"{type(e).__name__}: {e}"}
    return out


def main():
    ap = argparse.ArgumentParser(prog="pr_agent_runner",
                                 description="调 PR-Agent（不发评论）并打印 JSON 供 touchstone 解析")
    ap.add_argument("--pr-url", required=True)
    ap.add_argument("--mode", default="improve+review", help="improve / review / improve+review")
    ap.add_argument("--extra-instructions-file")
    a = ap.parse_args()
    json.dump(run(a.pr_url, a.mode, _read(a.extra_instructions_file)), sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
