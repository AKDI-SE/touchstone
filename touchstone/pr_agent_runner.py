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
#   • 真调需本进程环境：① LLM（OPENAI_API_KEY 等，pr-agent 经 LiteLLM 调）② GITHUB_TOKEN。
#     这两样是任何 AI 评审器固有的，经 env 透传；本脚本不持有、不打印任何密钥。
#   • PR-Agent 是 pip 包、不是要部署的服务——这里就是 import 它、调用、拿结果。
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
import sys

# review 解析用的 keys_fix_yaml，与 pr-agent PRReviewer._prepare_pr_review 一致
_REVIEW_KEYS_FIX = ["key_issues_to_review:", "relevant_file:", "relevant_line:", "suggestion:"]


def _read(path):
    if not path:
        return None
    with open(path, encoding="utf-8") as f:
        return f.read()


def run(pr_url, mode, extra_instructions=None):
    try:
        from pr_agent.algo.utils import load_yaml
        from pr_agent.config_loader import get_settings
        from pr_agent.tools.pr_code_suggestions import PRCodeSuggestions
        from pr_agent.tools.pr_reviewer import PRReviewer
    except ImportError as e:
        sys.exit(f"未安装 pr-agent：请在本子进程环境 `pip install pr-agent`。原始错误：{e}")

    s = get_settings()
    s.config.publish_output = False           # 关键：不往 PR 发评论，只取结构化结果
    s.config.publish_output_progress = False
    if extra_instructions:
        s.pr_code_suggestions.extra_instructions = extra_instructions
        s.pr_reviewer.extra_instructions = extra_instructions

    out = {"code_suggestions": [], "review": {"key_issues_to_review": []}}
    tools = set(mode.split("+"))

    if "improve" in tools:
        cs = PRCodeSuggestions(pr_url)
        asyncio.run(cs.run())                 # 结果落在 cs.data = {"code_suggestions": [...]}
        out["code_suggestions"] = (getattr(cs, "data", None) or {}).get("code_suggestions") or []

    if "review" in tools:
        rv = PRReviewer(pr_url)
        asyncio.run(rv.run())                 # rv.prediction 是原始 YAML 串；自行解析
        data = load_yaml((rv.prediction or "").strip(),
                         keys_fix_yaml=_REVIEW_KEYS_FIX,
                         first_key="review", last_key="security_concerns") or {}
        out["review"]["key_issues_to_review"] = (data.get("review") or {}).get("key_issues_to_review") or []

    json.dump(out, sys.stdout, ensure_ascii=False)


def main():
    ap = argparse.ArgumentParser(prog="pr_agent_runner",
                                 description="调 PR-Agent（不发评论）并打印 JSON 供 touchstone 解析")
    ap.add_argument("--pr-url", required=True)
    ap.add_argument("--mode", default="improve+review", help="improve / review / improve+review")
    ap.add_argument("--extra-instructions-file")
    a = ap.parse_args()
    run(a.pr_url, a.mode, _read(a.extra_instructions_file))


if __name__ == "__main__":
    main()
