"""LLM 预算收敛 + 大 diff 安全扫描回归测试。
核心：确定性核对（SEC-001）跑【全文 diff】，截断只施加在显示/LLM 侧——
大 PR 不能把泄漏的凭据藏在截断点之后绕过密钥门禁。"""
import os

import llm_budget as LB


# ---------------- llm_budget 单一来源 ----------------
def test_context_tokens_from_env(monkeypatch):
    monkeypatch.setenv("TOUCHSTONE_LLM_CONTEXT_TOKENS", "128000")
    assert LB.context_tokens() == 128000


def test_context_tokens_unknown_is_zero(monkeypatch):
    monkeypatch.delenv("TOUCHSTONE_LLM_CONTEXT_TOKENS", raising=False)
    assert LB.context_tokens() == 0


def test_output_tokens_default_and_env(monkeypatch):
    monkeypatch.delenv("TOUCHSTONE_LLM_OUTPUT_TOKENS", raising=False)
    assert LB.output_tokens() == 4096
    monkeypatch.setenv("TOUCHSTONE_LLM_OUTPUT_TOKENS", "8192")
    assert LB.output_tokens() == 8192


def test_output_tokens_bad_env_falls_back(monkeypatch):
    monkeypatch.setenv("TOUCHSTONE_LLM_OUTPUT_TOKENS", "garbage")
    assert LB.output_tokens() == 4096


def test_est_tokens_positive_and_monotone():
    assert LB.est_tokens("") == 1                     # 空串给 1（避免 0 除）
    assert LB.est_tokens("a") > 0
    assert LB.est_tokens("a" * 1000) > LB.est_tokens("a")
    assert LB.est_tokens("hello world code") <= LB.est_tokens("hello world code " * 10)


def test_llm_diff_budget_derives_from_context(monkeypatch):
    monkeypatch.setenv("TOUCHSTONE_LLM_CONTEXT_TOKENS", "128000")
    monkeypatch.setenv("TOUCHSTONE_LLM_OUTPUT_TOKENS", "4096")
    # 128000 - 2000(overhead) - 4096(output) = 121904
    assert LB.llm_diff_token_budget() == 121904


def test_llm_diff_budget_zero_when_context_unknown(monkeypatch):
    monkeypatch.delenv("TOUCHSTONE_LLM_CONTEXT_TOKENS", raising=False)
    assert LB.llm_diff_token_budget() == 0            # 不声明 → 不主动截断


def test_truncate_to_tokens_respects_budget():
    big = "x" * 100000
    out = LB.truncate_to_tokens(big, 100)             # 截到约 100 token
    assert LB.est_tokens(out) <= 100
    assert out.endswith("... [diff truncated]") or len(out) < len(big)


def test_truncate_to_tokens_zero_means_no_truncation():
    assert LB.truncate_to_tokens("anything", 0) == "anything"


# ---------------- 大 diff：SEC-001 跑全文，密钥在尾部也抓得到（回归）----------------
def _rule_index():
    import yaml
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    rules = yaml.safe_load(open(os.path.join(root, ".touchstone", "standards.yaml"), encoding="utf-8"))["rules"]
    return {r["id"]: r for r in rules}


def test_sec001_catches_secret_beyond_old_truncation_point(monkeypatch):
    """构造一个 > 原 DIFF_BUDGET(60K) 的大 diff，AKIA 密钥放在 60K 字符之后。
    全文扫描前：截断 → 漏检（本会话实测过）；全文扫描后：SEC-001 必须命中。
    这条测试锁住"安全扫描跑全文、不被大 diff 绕过"。"""
    import contract_check as cc
    ridx = _rule_index()
    # 前面塞 65000 字符的普通改动（> 旧 60K 预算），末尾藏真密钥
    pad = "".join(f"diff --git a/p{i}.py b/p{i}.py\n--- a/p{i}.py\n+++ b/p{i}.py\n@@ -0,0 +1 @@\n+x{i}\n"
                  for i in range(4000))
    assert len(pad) > 60000
    diff = pad + 'diff --git a/secret.py b/secret.py\n--- a/secret.py\n+++ b/secret.py\n' \
                '@@ -0,0 +1 @@\n+K="AKIAABCDEFGHIJKLMNOP"\n'
    f = cc.check_contract_consistency(diff, {}, ridx)
    assert any(x["rule_id"] == "SEC-001" for x in f), "密钥在 60K 之后仍必须被 SEC-001 抓到（全文扫描）"


def test_render_summary_caps_findings_to_avoid_comment_overflow():
    """大 PR 产出大量发现 → 摘要封顶列出，超出折叠，避免超 GitHub 65536 字符限。"""
    import orchestrator as orc
    risk = {"risk_band": "low", "human_action": "skip", "verification_decision": "cheap_only",
            "blast_radius": []}
    findings = [{"rule_id": f"R{i}", "agent": "a", "severity": "warn", "confidence": 0.5,
                 "file": "a.py", "line": i, "rationale": "x", "suggested_fix": "y"}
                for i in range(500)]
    body = orc.render_summary(risk, findings)
    assert "另有" in body and "仅列前" in body
    assert len(body) < 65536                        # 评论体不超限
    assert body.count("`R") <= LB.MAX_FINDINGS_IN_SUMMARY + 1   # 列出的不超过封顶


# ---------------- 体量门禁（SIZE-001）----------------
def test_size_gate_blocks_large_diff(monkeypatch):
    """超过 TOUCHSTONE_MAX_DIFF_LINES → 不调 LLM，直接产 SIZE-001 block_candidate。"""
    import orchestrator as orc, review_provider as rp
    monkeypatch.setenv("TOUCHSTONE_MAX_DIFF_LINES", "5")        # 只许 5 行
    # 10 行新增 → 超限
    diff = "".join(f"diff --git a/f{i}.py b/f{i}.py\n--- a/f{i}.py\n+++ b/f{i}.py\n@@ -0,0 +1 @@\n+x{i}\n"
                   for i in range(10))
    pr = {"diff": diff, "pr_agent_output": {"SHOULD_NOT_BE_USED": True}}
    out = orc.review_pr(pr, {}, {})
    size = [f for f in out["findings"] if f.get("rule_id") == "SIZE-001"]
    assert size and size[0]["severity"] == "block_candidate"     # block 级
    assert out["engine_status"] == "skipped_large_diff"          # LLM 被跳过
    assert out["ai_raw_count"] == 0                              # 没调 pr-agent


def test_size_gate_allows_within_limit(monkeypatch):
    """未超限 → 正常调 LLM，不产 SIZE-001。"""
    import orchestrator as orc
    monkeypatch.setenv("TOUCHSTONE_MAX_DIFF_LINES", "100")      # 上限 100，diff 只 2 行
    diff = "diff --git a/f.py b/f.py\n--- a/f.py\n+++ b/f.py\n@@ -0,0 +1,2 @@\n+a\n+b\n"
    pr = {"diff": diff, "pr_agent_output": {"code_suggestions": [], "review": {"key_issues_to_review": []}}}
    out = orc.review_pr(pr, {}, {})
    assert out["engine_status"] == "ok"
    assert not any(f.get("rule_id") == "SIZE-001" for f in out["findings"])


def test_size_gate_disabled_by_default(monkeypatch):
    """未设 TOUCHSTONE_MAX_DIFF_LINES → 门禁关（不拦）。"""
    import orchestrator as orc
    monkeypatch.delenv("TOUCHSTONE_MAX_DIFF_LINES", raising=False)
    diff = "".join(f"diff --git a/f{i}.py b/f{i}.py\n+++ b/f{i}.py\n@@ -0,0 +1 @@\n+x\n" for i in range(200))
    pr = {"diff": diff, "pr_agent_output": {"code_suggestions": [], "review": {"key_issues_to_review": []}}}
    out = orc.review_pr(pr, {}, {})
    assert out["engine_status"] == "ok"
    assert not any(f.get("rule_id") == "SIZE-001" for f in out["findings"])
