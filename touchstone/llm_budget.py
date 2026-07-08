"""LLM 上下文/输出 token 预算的单一事实源。

设计原则：
  • 真实模型规格经 env 声明（部署方按模型卡填，如 GitHub secret）——不再硬编码魔法数字：
      TOUCHSTONE_LLM_CONTEXT_TOKENS — 模型上下文窗口（token），0 = 未知/不限。
      TOUCHSTONE_LLM_OUTPUT_TOKENS  — 模型最大输出（token），默认 4096。
  • token 计数用启发式估计（无模型分词器时的近似；量级够用，精确预算需真实 tokenizer，
    如 GLM 自有分词器——可日后替换 est_tokens 实现）。优先用 tiktoken（cl100k 近似），
    不可用时退化为字符数/3（代码+中文混合的经验值）。

注意：touchstone 侧的 diff 截断只用于【显示/摘要/内联锚定】（受 GitHub 评论 65536 字符限），
确定性核对（SEC-001 密钥扫描等）跑【全文 diff】——安全保证不随体量打折扣。LLM 的实际上下文
由 pr-agent 自己管理（它取全文 PR + 用 output_tokens() 做 max_tokens）。"""
import os

_ENC = None
def _enc():
    global _ENC
    if _ENC is None:
        try:
            import tiktoken
            _ENC = tiktoken.get_encoding("cl100k_base")
        except Exception:
            _ENC = False        # 无 tiktoken → 用字符启发式
    return _ENC


def context_tokens():
    """模型上下文窗口（token）。0 = 未声明/不限。"""
    try:
        return int(os.environ.get("TOUCHSTONE_LLM_CONTEXT_TOKENS", "0") or 0)
    except ValueError:
        return 0


def output_tokens():
    """模型最大输出（token）。pr-agent 的 custom_model_max_tokens 用它。"""
    try:
        v = int(os.environ.get("TOUCHSTONE_LLM_OUTPUT_TOKENS", "4096") or 4096)
        return v if v > 0 else 4096
    except ValueError:
        return 4096


def est_tokens(text):
    """文本 token 数估计（近似）。tiktoken(cl100k) 优先，否则字符/3。"""
    text = text or ""
    enc = _enc()
    if enc:
        return len(enc.encode(text))
    # 启发式：CJK 约 1 字符/token、ASCII 代码约 3-4 字符/token → 折中 3
    return max(1, len(text) // 3)


def llm_diff_token_budget(reserve_output=True, prompt_overhead=2000):
    """喂给 LLM 的 diff token 预算 = 上下文 −（系统/prompt 开销 + 输出预留）。
    上下文未声明（0）时返回 0（= 不主动截断，交 pr-agent 自管）。"""
    ctx = context_tokens()
    if ctx <= 0:
        return 0
    out = output_tokens() if reserve_output else 0
    return max(0, ctx - prompt_overhead - out)


def truncate_to_tokens(text, max_tokens, marker="\n... [diff truncated]"):
    """把 text 截到估计 token 数 ≤ max_tokens（增量校验，留余量）。max_tokens<=0 → 不截断。
    用于喂 LLM 的上下文（如 TF-GRPO 真值 diff）。注意：这是近似（见 est_tokens 说明）。"""
    if max_tokens <= 0 or not text:
        return text
    if est_tokens(text) <= max_tokens:
        return text
    ratio = max_tokens / max(1, est_tokens(text))
    cut = max(100, int(len(text) * ratio * 0.95))      # 留 5% 余量给 marker
    while est_tokens(text[:cut] + marker) > max_tokens and cut > 100:
        cut = int(cut * 0.9)
    return text[:cut] + marker


# 显示/摘要侧（非 LLM）：GitHub PR 评论 65536 字符硬限。留 marker + 表头余量。
COMMENT_CHAR_LIMIT = 60000
MAX_FINDINGS_IN_SUMMARY = 50        # 摘要里最多列这么多条，超出折叠为"另有 N 条"
