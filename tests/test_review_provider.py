"""PR-Agent 评审路径骨架（评审提供器 + 归一 + 裁决映射）。纯函数、离线；
PR-Agent 真实端点为接缝，测试经 pr_ctx['pr_agent_output'] 注入原始输出。"""
import json

import pytest

import review_provider as RP


# 一份贴近 PR-Agent improve+review 输出的样例
_RAW = {
    "code_suggestions": [
        {"relevant_file": "src/auth.py", "relevant_lines_start": 12, "relevant_lines_end": 14,
         "one_sentence_summary": "Validate token before use", "improved_code": "if not token: raise ...",
         "label": "security"},
        {"relevant_file": "src/util.py", "relevant_lines_start": 30, "relevant_lines_end": 30,
         "one_sentence_summary": "Rename variable for clarity", "improved_code": "user_count = ...",
         "label": "maintainability"},
        {"relevant_file": "src/calc.py", "relevant_lines_start": 7, "relevant_lines_end": 9,
         "one_sentence_summary": "Off-by-one in loop bound", "improved_code": "range(n+1)",
         "label": "possible bug"},
    ],
    "review": {
        "key_issues_to_review": [
            {"relevant_file": "src/calc.py", "start_line": 7, "end_line": 9,
             "issue_header": "Edge case", "issue_content": "n=0 not handled", "label": "possible issue"},
        ],
    },
}


# ---------------- 解析 ----------------
def test_parse_pr_agent_suggestions_and_review():
    items = RP.parse_pr_agent(_RAW)
    assert len(items) == 4
    sug = [i for i in items if i["kind"] == "suggestion"]
    rev = [i for i in items if i["kind"] == "review"]
    assert len(sug) == 3 and len(rev) == 1
    assert sug[0]["file"] == "src/auth.py" and sug[0]["line_start"] == 12 and sug[0]["label"] == "security"
    assert rev[0]["summary"] == "Edge case" and rev[0]["tool"] == "review"


def test_parse_empty_is_empty():
    assert RP.parse_pr_agent({}) == []
    assert RP.parse_pr_agent(None) == []


# ---------------- 归一 ----------------
def test_normalize_maps_label_to_category_and_agent():
    findings = RP.normalize(RP.parse_pr_agent(_RAW))
    cats = {f["file"]: f["category"] for f in findings}
    assert cats["src/auth.py"] == "security"
    assert cats["src/util.py"] == "convention"        # maintainability → convention
    # possible bug → correctness；possible issue → correctness_suspect（弱信号、不升 high）
    calc_cats = {f["category"] for f in findings if f["file"] == "src/calc.py"}
    assert calc_cats == {"correctness", "correctness_suspect"}
    # 顾问式：一律 warn，不产 block_candidate；agent 记来源
    assert all(f["severity"] == "warn" for f in findings)
    assert all(f["agent"].startswith("pr-agent:") for f in findings)
    assert all(f["rule_id"].startswith("PRA-") for f in findings)


def test_normalize_respects_discard():
    nmap = dict(RP._DEFAULT_NMAP, discard_labels=["maintainability"])
    findings = RP.normalize(RP.parse_pr_agent(_RAW), nmap)
    assert "src/util.py" not in {f["file"] for f in findings}   # 被丢弃
    assert len(findings) == 3


def test_normalize_unknown_label_falls_to_default_category():
    items = [{"kind": "suggestion", "file": "x.py", "line_start": 1, "label": "wat", "summary": "?"}]
    f = RP.normalize(items)[0]
    assert f["category"] == "convention"               # default_category


# ---------------- 裁决映射 ----------------
def test_map_verdict_security_is_high():
    _, risk = RP.map_verdict(RP.normalize(RP.parse_pr_agent(_RAW)))
    assert risk["risk_band"] == "high"                 # 含 security/correctness
    assert "security_surface" in risk["blast_radius"]
    assert risk["verification_decision"] == "full_suite"   # 高 + 影响面严重(security_surface) → 最强一档


def test_map_verdict_only_convention_is_mid():
    items = [{"kind": "suggestion", "file": "a.py", "line_start": 1, "label": "typo", "summary": "x"}]
    _, risk = RP.map_verdict(RP.normalize(items))
    assert risk["risk_band"] == "mid" and risk["verification_decision"] == "cheap_only"


def test_map_verdict_empty_is_low():
    _, risk = RP.map_verdict([])
    assert risk["risk_band"] == "low" and risk["human_action"] == "skip"


def test_map_verdict_confidence_floor_filters():
    findings = [{"category": "security", "confidence": 0.2}]   # 低于 conf_min=0.5
    kept, risk = RP.map_verdict(findings)
    assert kept == [] and risk["risk_band"] == "low"


def test_map_verdict_possible_issue_alone_is_mid():
    # 弱信号 correctness_suspect 单独出现 → mid（不升 high）；这是 possible issue 调映射后的目标行为
    items = [{"kind": "review", "file": "a.py", "line_start": 1, "label": "possible issue", "summary": "maybe"}]
    findings = RP.normalize(items)
    assert findings[0]["category"] == "correctness_suspect"
    _, risk = RP.map_verdict(findings)
    assert risk["risk_band"] == "mid" and risk["verification_decision"] == "cheap_only"


def test_map_verdict_possible_bug_still_high():
    # 真缺陷信号照常升 high（只软化 possible issue，不动 possible bug/critical bug）
    items = [{"kind": "suggestion", "file": "a.py", "line_start": 1, "label": "possible bug", "summary": "off by one"}]
    _, risk = RP.map_verdict(RP.normalize(items))
    assert risk["risk_band"] == "high"


def test_map_verdict_high_categories_configurable():
    # high_categories 可配：把 correctness_suspect 纳入 → possible issue 也升 high
    nmap = dict(RP._DEFAULT_NMAP, high_categories=["security", "correctness", "correctness_suspect"])
    items = [{"kind": "review", "file": "a.py", "line_start": 1, "label": "possible issue", "summary": "m"}]
    _, risk = RP.map_verdict(RP.normalize(items, nmap), nmap)
    assert risk["risk_band"] == "high"


# ---------------- 评审提供器 fetch（注入 vs 子进程集成）----------------
def test_fetch_with_injected_output():
    items = RP.fetch({"pr_agent_output": _RAW})
    assert len(items) == 4


def test_build_pr_url_from_owner_repo_number():
    assert RP._build_pr_url({"owner": "o", "repo": "r", "number": 7}).endswith("/o/r/pull/7")
    assert RP._build_pr_url({"owner": "o", "repo": "r"}) == ""        # 缺 number → 空


class _Proc:
    def __init__(self, rc, out="", err=""):
        self.returncode, self.stdout, self.stderr = rc, out, err


def test_invoke_endpoint_subprocess_success(monkeypatch):
    captured = {}

    def fake_run(args, **kw):
        captured["args"] = args
        return _Proc(0, out=json.dumps(_RAW))
    monkeypatch.setattr(RP.subprocess, "run", fake_run)
    monkeypatch.setattr(RP, "_experience_injection", lambda d: "")     # 隔离学习回路
    items = RP.fetch({"owner": "o", "repo": "r", "number": 3})
    assert len(items) == 4                                            # 子进程 JSON → 解析成 ReviewItem
    assert "--pr-url" in captured["args"] and "--mode" in captured["args"]


def test_invoke_endpoint_nonzero_raises(monkeypatch):
    monkeypatch.setattr(RP.subprocess, "run", lambda a, **k: _Proc(2, err="boom-detail"))
    monkeypatch.setattr(RP, "_experience_injection", lambda d: "")
    with pytest.raises(RuntimeError, match="boom-detail"):
        RP.fetch({"owner": "o", "repo": "r", "number": 3})


def test_invoke_endpoint_bad_json_raises(monkeypatch):
    monkeypatch.setattr(RP.subprocess, "run", lambda a, **k: _Proc(0, out="not json"))
    monkeypatch.setattr(RP, "_experience_injection", lambda d: "")
    with pytest.raises(RuntimeError, match="JSON"):
        RP.fetch({"owner": "o", "repo": "r", "number": 3})


def test_invoke_endpoint_missing_runner_raises(monkeypatch):
    def boom(a, **k):
        raise FileNotFoundError("no such cmd")
    monkeypatch.setattr(RP.subprocess, "run", boom)
    monkeypatch.setattr(RP, "_experience_injection", lambda d: "")
    with pytest.raises(RuntimeError, match="pip install pr-agent"):
        RP.fetch({"owner": "o", "repo": "r", "number": 3})


def test_invoke_endpoint_no_pr_url_raises(monkeypatch):
    monkeypatch.setattr(RP, "_experience_injection", lambda d: "")
    with pytest.raises(RuntimeError, match="PR URL"):
        RP.fetch({"sha": "s"})                                       # 无 pr_url / owner-repo-number


def test_runner_imports_without_pr_agent():
    # 适配器模块本身可被导入、不在导入期触碰 pr-agent（pr-agent 只在 run() 内 import）
    import pr_agent_runner as R
    assert R._read(None) is None
    assert callable(R.run) and callable(R.main)


def test_fetch_unknown_provider():
    with pytest.raises(ValueError):
        RP.fetch({"pr_agent_output": _RAW}, provider="nope")
