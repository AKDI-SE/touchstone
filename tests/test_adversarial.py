"""#3 对抗/安全测试：Touchstone 是门禁，必被攻击。验证伪造 marker、密钥规避、
经验投毒绕门禁、marker 注入等都能被挡。"""
import json
import os
import re

from touchstone import contract_check
from touchstone import loop


def _rule_index():
    import yaml
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    rules = yaml.safe_load(open(os.path.join(root, ".touchstone", "standards.yaml"), encoding="utf-8"))["rules"]
    return {r["id"]: r for r in rules}


# ---------------- 伪造 marker：author 可控的评论不得污染 loop 状态 ----------------
def test_forged_loop_marker_from_human_is_ignored():
    """author 在评论里塞伪造的 loop marker（洗掉震荡/无推进闸）→ 必须被 trusted_bodies 丢弃。"""
    forged = loop.render_marker(loop.LoopState(2, [], None))    # 同轮次+空 history（洗闸）
    comments = [
        {"user": {"login": "attacker"}, "body": forged},        # 人发的伪造
        {"user": {"login": "github-actions[bot]"},              # 真机器人发的
         "body": loop.render_marker(loop.LoopState(2, [["A"], ["A"]], None))},
    ]
    # bot_login 已知 → 精确过滤；未知 → 按 [bot] 后缀过滤。两种都只取 bot 的。
    for bot in ("github-actions[bot]", None):
        bodies = loop.trusted_bodies(comments, bot)
        st = loop.parse_latest_state(bodies)
        assert st.history == [["A"], ["A"]]                     # 伪造的空 history 没生效


# ---------------- SEC-001：真密钥必抓、占位符跳过、不得被"伪装"规避 ----------------
def test_sec001_real_aws_key_caught():
    ridx = _rule_index()
    added = {"src/config.py": [(1, 'AWS_KEY = "AKIAABCDEFGHIJKLMNOP"')]}
    f = contract_check.check_secrets(added, ridx)
    assert any(x["rule_id"] == "SEC-001" for x in f)


def test_sec001_placeholder_value_skipped():
    ridx = _rule_index()
    # 密钥模式匹配到值，但值是占位词（changeme）→ _PLACEHOLDER 命中 → 跳过（防误报）
    added = {"src/config.py": [(1, 'password = "changeme12345678901234567890abc"')]}
    assert contract_check.check_secrets(added, ridx) == []


def test_sec001_genuine_key_not_evasionable_by_context():
    """真泄漏的 key 即便周围写满 'example' 字样，仍被抓——占位符过滤只看匹配串本身，
    不被前后文欺骗。"""
    ridx = _rule_index()
    added = {"src/config.py": [(1, '# example sample placeholder\nAWS = "AKIAABCDEFGHIJKLMNOP"')]}
    f = contract_check.check_secrets(added, ridx)
    assert any(x["rule_id"] == "SEC-001" for x in f)


def test_sec001_skips_test_fixtures():
    """测试文件里的密钥是夹具，不据此阻断（真实泄密由外部 SAST 兜底）。"""
    ridx = _rule_index()
    added = {"tests/test_x.py": [(1, 'key = "AKIAABCDEFGHIJKLMNOP"')]}
    assert contract_check.check_secrets(added, ridx) == []


# ---------------- 经验投毒：active 经验的 suppress 不能绕过确定性门禁 ----------------
def test_experience_suppress_cannot_remove_deterministic_block():
    """即便经验库有一条 suppress 安全类型的 active 经验，SEC-001 等确定性 block_candidate
    发现仍照样产出（经验只调建议、绝不进/绕门禁）。"""
    from touchstone import orchestrator as orc
    import yaml
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    standards = yaml.safe_load(open(os.path.join(root, ".touchstone", "standards.yaml"), encoding="utf-8"))
    # 经验库投毒：试图 suppress security
    os.environ["TOUCHSTONE_EXPERIENCE_ENABLED"] = "true"
    pr = {"owner": "o", "repo": "r", "number": 1, "sha": "s", "token": "t",
          "diff": 'diff --git a/c.py b/c.py\n--- a/c.py\n+++ b/c.py\n@@ -0,0 +1 @@\n+K="AKIAABCDEFGHIJKLMNOP"\n',
          "pr_agent_output": {"code_suggestions": [], "review": {"key_issues_to_review": []}}}
    out = orc.review_pr(pr, {}, standards)
    sec = [f for f in out["findings"] if f.get("rule_id") == "SEC-001"]
    assert sec and sec[0]["severity"] == "block_candidate"     # 仍阻断级，未被经验抹掉


# ---------------- marker 完整性：对抗内容不得破坏机读 marker ----------------
def test_result_marker_remains_parseable_with_quotes_in_content(monkeypatch):
    """finding rationale 含引号/特殊字符 → result marker 仍是合法 JSON（json.dumps 转义）。"""
    from touchstone import orchestrator as orc
    posted = {}
    monkeypatch.setattr(orc, "gh",
                        lambda m, p, t, data=None, **k: posted.update(body=data["body"])
                        if (m == "POST" and p.endswith("/comments")) else None)
    risk = {"risk_band": "low", "human_action": "skip", "verification_decision": "cheap_only",
            "blast_radius": []}
    findings = [{"rule_id": "PRA-X", "agent": "pr-agent:review", "severity": "warn",
                 "confidence": 0.7, "file": "a.py", "line": 1,
                 "rationale": 'he said "hi\" and } { --> ', "suggested_fix": "x"}]
    orc.post_results("o", "r", 1, "s", "t", risk, findings)
    m = re.search(r"<!-- touchstone-result: (.*?) -->", posted["body"], re.S)
    parsed = json.loads(m.group(1))                            # 必须可解析
    assert parsed["findings"][0]["rule_id"] == "PRA-X"
