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


def _ping_llm(base, key, model):
    """直接探测 LLM 端点（1-token 请求），确认 base/key/model 可用。失败抛异常（带真实错误）。
    抽成函数便于测试 monkeypatch（离线测试不真发请求）。"""
    import openai
    c = openai.OpenAI(base_url=base, api_key=key, timeout=30)
    c.chat.completions.create(model=model,
                              messages=[{"role": "user", "content": "ping"}], max_tokens=1)


# 本次 run() 的交互轨迹（关键节点日志），main() 据此 + 返回结果写完整交互日志（artifact）。
# 单进程单线程，模块级即可。
_IX = []


def _ix(msg):
    _IX.append(msg)


def _write_interaction_log(out):
    """把本次 LLM 交互的完整轨迹 + pr-agent 原始输出写到 TOUCHSTONE_INTERACTION_LOG（供 workflow
    上传为 artifact、评审评论里贴链接）。失败不影响主流程。"""
    path = os.environ.get("TOUCHSTONE_INTERACTION_LOG")
    if not path:
        return
    try:
        import json as _json
        parts = ["# PR-Agent / LLM 完整交互日志", "(api_key 已脱敏，不记录)"]
        parts += list(_IX)
        parts += ["", "---- 返回结果（pr-agent 完整输出 / 降级原因）----",
                  _json.dumps(out, ensure_ascii=False, indent=2)[:20000]]
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(parts))
    except Exception as e:
        try:
            print(f"[pr-agent] 交互日志写入失败: {e}", file=sys.stderr)
        except Exception:
            pass


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
    _IX.clear()
    _ix(f"pr_url={pr_url} mode={mode} extra_instructions={len(extra_instructions or '')} 字符")
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
        _ix(f"阶段=import 失败(no_engine): {e}")
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
        # pr-agent 的 get_max_tokens(model) 要求模型在内置 MAX_TOKENS 表里，否则报
        # "Model ... is not defined in MAX_TOKENS ... no custom_model_max_tokens is set"
        # 直接判"Failed to generate prediction"（glm-5.2 等自定义模型不在表里——这是多日"0 建议"的真根因之一）。
        #
        # 【输入侧预算，非输出 max_tokens】pr-agent 0.37 的 get_max_tokens() 把此值当作
        # 【整个上下文窗口】用于内部 diff 裁剪预算（pr_processing.get_pr_diff 的 token 上限），
        # 而它实际向 LLM API 发起的 chat_completion【并不传 max_tokens】（litellm_ai_handler
        # 构造的 kwargs 无 max_tokens 字段，仅 extended_thinking 路径才设）——由端点用默认输出上限。
        # 故此值必须填【模型上下文窗口】(context_tokens)，绝不能填【输出】(output_tokens=默认4096)：
        # 填 4096 = 告诉 pr-agent"整个窗口只有 4096"→ 改动 diff 被裁成空 → LLM 拿到空 diff → 0 建议。
        # 这正是 PR #44（及 #42 收敛的运气成分）"LLM 没给意见"的真根因：output_tokens 语义用反。
        # 部署方用 secret TOUCHSTONE_LLM_CONTEXT_TOKENS 按模型卡声明上下文窗口；未声明时回退
        # 128000（现代模型典型窗口）而非 4096——宁可让 LLM 看全 diff，不可裁空。
        try:
            from touchstone.llm_budget import context_tokens
            ctx = context_tokens()
            s.config.custom_model_max_tokens = ctx if ctx > 0 else 128000
        except Exception:
            s.config.custom_model_max_tokens = 128000
        # 清空 fallback_models：默认 fallback（gpt-5.4-mini 等）发到我们的 base 会返回"模型不存在"，徒增失败噪音。
        try:
            s.config.fallback_models = []
        except Exception:
            pass
    if extra_instructions:
        s.pr_code_suggestions.extra_instructions = extra_instructions
        s.pr_reviewer.extra_instructions = extra_instructions
    # 压一压 LiteLLM 的 stdout 噪音（"LiteLLM.Info / Give Feedback" 等 print），减少 stderr 干扰。
    # 需排查"LLM 到底被调了没"时设 TOUCHSTONE_LITELLM_VERBOSE=true，litellm 会把请求打到 stderr。
    try:
        import litellm
        litellm.suppress_debug_info = True
        litellm.set_verbose = os.environ.get("TOUCHSTONE_LITELLM_VERBOSE", "").lower() in ("1", "true", "yes")
    except Exception:
        pass

    # 【关键节点】LLM 配置日志 + 预检 ping：用同样的 base/key/model 直接发一个 1-token 请求，
    # 确认端点可达、凭据有效（成功会出现在 LLM 服务端请求日志里）。这是回答"LLM key 是否被调用"
    # 的决定性观测点——否则 pr-agent 可能在内部静默跳过 LLM、返回空建议，我们无从得知。
    _base = os.environ.get("OPENAI_API_BASE") or os.environ.get("LLM_BASE_URL")
    _key = os.environ.get("OPENAI_API_KEY") or os.environ.get("LLM_API_KEY")
    _ix(f"LLM 配置: model={model_override!r} base_url={_base!r} api_key={'已设' if _key else '缺失'}")
    print(f"[pr-agent] LLM 配置：model={model_override!r} base_url={_base!r} "
          f"api_key={'已设' if _key else '缺失'}", file=sys.stderr)
    if not (_base and _key and model_override):
        _ix("阶段=LLM 配置不全 → llm_failed")
        return {"_degraded": "llm_failed",
                "reason": (f"LLM 配置不全：需 LLM_BASE_URL/LLM_API_KEY/LLM_MODEL 都设"
                           f"（model={model_override!r}, base={'有' if _base else '无'}, "
                           f"key={'有' if _key else '无'}）")}
    try:
        _ping_llm(_base, _key, model_override)
        _ix("LLM 预检 ping: 成功（端点可达、凭据有效）")
        print("[pr-agent] LLM 预检 ping 成功（端点可达、凭据有效）", file=sys.stderr)
    except Exception as e:
        _ix(f"LLM 预检 ping: 失败 → llm_failed ({type(e).__name__}: {e})")
        return {"_degraded": "llm_failed",
                "reason": f"LLM 端点探测失败（{type(e).__name__}: {e}）—— base={_base} model={model_override}"}

    out = {"code_suggestions": [], "review": {"key_issues_to_review": []}}
    tools = set(mode.split("+"))
    _ix(f"阶段=pr-agent 工具执行: tools={sorted(tools)}")
    # pr-agent/LiteLLM 运行期会把 Info/调试信息 print 到 stdout，污染我们最后打印的 JSON
    # （曾导致 review_provider json.loads 失败、误判 no_engine）。这里在 fd 级把 stdout
    # 重定向到 stderr：库的任何 print（含 C 级写）都进 stderr（被 _invoke_endpoint 当诊断捕获），
    # 只有 main() 最后的 json.dump 走真正的 stdout。防 stdout 污染导致的静默故障。
    sys.stdout.flush()
    _saved_stdout_fd = os.dup(1)
    os.dup2(2, 1)
    try:
        # 阶段一：构造 provider + 取 PR（pre-LLM）。构造时即拉取 PR diff，失败归 provider_failed。
        instances = {}
        try:
            if "improve" in tools:
                instances["cs"] = PRCodeSuggestions(pr_url)
            if "review" in tools:
                instances["rv"] = PRReviewer(pr_url)
            _ix("取 PR / 构造 provider: 成功")
        except Exception as e:
            _ix(f"取 PR / 构造 provider: 失败 → provider_failed ({type(e).__name__}: {e})")
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
            _ix(f"工具执行完成: code_suggestions={len(out['code_suggestions'])} "
                f"key_issues={len(out['review']['key_issues_to_review'])}")
        except Exception as e:   # LLM 端点/鉴权/超时/解析失败等 —— 不静默吞掉，上报为 llm_failed
            _ix(f"工具执行: 失败 → llm_failed ({type(e).__name__}: {e})")
            return {"_degraded": "llm_failed", "reason": f"{type(e).__name__}: {e}"}
        return out
    finally:
        sys.stdout.flush()
        os.dup2(_saved_stdout_fd, 1)
        os.close(_saved_stdout_fd)


def main():
    ap = argparse.ArgumentParser(prog="pr_agent_runner",
                                 description="调 PR-Agent（不发评论）并打印 JSON 供 touchstone 解析")
    ap.add_argument("--pr-url", required=True)
    ap.add_argument("--mode", default="improve+review", help="improve / review / improve+review")
    ap.add_argument("--extra-instructions-file")
    a = ap.parse_args()
    out = run(a.pr_url, a.mode, _read(a.extra_instructions_file))
    _write_interaction_log(out)   # 写完整 LLM 交互日志（TOUCHSTONE_INTERACTION_LOG，供 artifact + 评审链接）
    json.dump(out, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
