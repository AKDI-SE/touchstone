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


def test_map_verdict_contract_category_path():
    """contract 类发现 → blast 含 cross_module_contract。
    注意：contract 不在默认 high_categories → band=mid → cheap_only（当前行为）；
    高风险升级需配 high_categories 纳入 contract，或改 route() 逻辑。此处锁定现状。"""
    findings = [{"category": "contract", "confidence": 0.9, "rule_id": "CTR-001",
                 "agent": "touchstone-rules", "severity": "block_candidate"}]
    _, risk = RP.map_verdict(findings)
    assert "cross_module_contract" in risk["blast_radius"]
    assert risk["risk_band"] == "mid"          # 当前：contract 不在 high_categories
    assert risk["verification_decision"] == "cheap_only"   # 因 band != high


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


def test_invoke_endpoint_degraded_json_raises_typed(monkeypatch):
    # 适配器结构化降级：子进程退出 0 但 JSON 带 _degraded → 抛 ReviewEngineDegraded（带 degraded/reason）
    monkeypatch.setattr(RP.subprocess, "run", lambda a, **k:
                        _Proc(0, out=json.dumps({"_degraded": "llm_failed", "reason": "AuthError: 401"})))
    monkeypatch.setattr(RP, "_experience_injection", lambda d: "")
    with pytest.raises(RP.ReviewEngineDegraded) as ei:
        RP.fetch({"owner": "o", "repo": "r", "number": 3})
    assert ei.value.degraded == "llm_failed"
    assert "401" in ei.value.reason


def test_engine_banner():
    from touchstone import orchestrator as orc
    assert "AI 评审未运行" in orc._engine_banner("no_engine")
    assert "LLM 调用失败" in orc._engine_banner("llm_failed")
    assert orc._engine_banner("ok") == ""


def test_review_pr_engine_status_on_degradation(monkeypatch):
    # fetch 抛 ReviewEngineDegraded → review_pr 仍返回确定性核对结果，但 engine_status 标降级
    from touchstone import orchestrator as orc

    def _degrade(pr, provider=None):
        raise RP.ReviewEngineDegraded("no_engine", "pr-agent 未安装")
    monkeypatch.setattr(RP, "fetch", _degrade)
    out = orc.review_pr({"diff": ""}, {}, {})
    assert out["engine_status"] == "no_engine"
    assert out["findings"] == []                       # 降级：无评审发现，仅确定性核对（空 diff→空）


def test_parse_diff_malformed_sets_warning():
    # C：unidiff 解析失败 → 返回空 + 置 _PARSE_WARNING（供 orchestrator 显式标注，防静默）
    from touchstone import contract_check as cc
    cc._PARSE_WARNING = None
    # hunk 内出现非法行首（=badline）→ unidiff 抛 UnidiffParseError
    files, added = cc.parse_diff("--- a/x.py\n+++ b/x.py\n@@ -1,1 +1,1 @@\n=badline\n")
    assert files == set() and added == {}
    assert cc._PARSE_WARNING and "解析失败" in cc._PARSE_WARNING
    # 正常 diff 应回到无告警
    files, added = cc.parse_diff("--- a/x.py\n+++ b/x.py\n@@ -0,0 +1,1 @@\n+pass\n")
    assert cc._PARSE_WARNING is None


def test_review_pr_det_warning_on_bad_diff(monkeypatch):
    # C：坏 diff → review_pr 返回 det_warning；确定性核对空转不再被读成"干净"
    from touchstone import orchestrator as orc
    monkeypatch.setattr(RP, "fetch", lambda ctx, provider=None: [])
    out = orc.review_pr({"diff": "--- a/x.py\n+++ b/x.py\n@@ -1,1 +1,1 @@\n=badline\n"}, {}, {})
    assert out["det_warning"]                           # 非空告警
    assert out["findings"] == []                        # 坏 diff → 确定性核对 0 发现（但已显式标注）


def test_engine_banner_combines_det_warning():
    # post_results 把 det_warning 也拼进 banner——这里直接验 _engine_banner 与拼接逻辑的存在
    from touchstone import orchestrator as orc
    assert "AI 评审未运行" in orc._engine_banner("no_engine")
    assert orc._engine_banner("ok") == ""


def test_clean_review_trace_disambiguates_zero_findings():
    # 0 发现时溯源：让人区分"LLM 真审了没问题" vs "没真审"（防静默故障）
    from touchstone import orchestrator as orc
    # 引擎正常 + 改动小 + 0 原始建议 → 合理（非空回）
    t = orc._clean_review_trace("ok", ai_raw_count=0, added_lines=3, n_changed=1)
    assert "已端到端运行" in t and "0 条原始建议" in t and "合理" in t
    # 引擎正常 + 改动大 + 0 原始建议 → 可疑，提示人工扫一眼
    t2 = orc._clean_review_trace("ok", ai_raw_count=0, added_lines=120, n_changed=8)
    assert "人工扫一眼" in t2
    # 引擎正常 + pr-agent 真有返回 → 不可疑（归一后 0 是被过滤）
    t3 = orc._clean_review_trace("ok", ai_raw_count=5, added_lines=120, n_changed=8)
    assert "5 条原始建议" in t3 and "人工扫一眼" not in t3
    # 降级时不输出溯源（由 _engine_banner 负责）
    assert orc._clean_review_trace("llm_failed", 0, 0, 0) == ""


def test_runner_imports_without_pr_agent():
    # 适配器模块本身可被导入、不在导入期触碰 pr-agent（pr-agent 只在 run() 内 import）
    import pr_agent_runner as R
    assert R._read(None) is None
    assert callable(R.run) and callable(R.main)


def test_fetch_unknown_provider():
    with pytest.raises(ValueError):
        RP.fetch({"pr_agent_output": _RAW}, provider="nope")


# ============ 确定性影响面（不依赖 LLM 类别）·安全兜底回归 ============
def test_deterministic_blast_by_path():
    from touchstone import review_provider as rp
    assert "cross_module_contract" in rp.deterministic_blast(["db/migrations/0007_add.sql"])
    assert "cross_module_contract" in rp.deterministic_blast(["api/user.proto"])
    assert "security_surface" in rp.deterministic_blast(["svc/auth/login.py"])
    assert rp.deterministic_blast(["svc/pay/charge.py", "README.md"]) == []   # 普通路径不误报


def test_llm_missed_category_still_elevated_by_path():
    """评审侧【漏判】类别（category 不含 security/contract）时，
    改动却触及 migration/安全面 → 确定性 blast 仍把它抬到 high → full_suite。"""
    from touchstone import review_provider as rp
    findings = [{"rule_id": "PRA-STYLE", "category": "style", "severity": "warn", "confidence": 0.9}]
    # 不给 changed_files：沿用旧行为（低风险）
    _, risk0 = rp.map_verdict(list(findings))
    assert risk0["risk_band"] != "high"
    # 给出触及 schema 迁移的改动文件：即便 LLM 只报了 style，也被抬到 high + full_suite
    _, risk1 = rp.map_verdict(list(findings), changed_files=["db/migrations/0007_add.sql"])
    assert risk1["risk_band"] == "high"
    assert "cross_module_contract" in risk1["blast_radius"]
    assert risk1["verification_decision"] == "full_suite"


def test_to_rdjson_reviewdog_backend():
    """rdjson 导出：行内评论可交 reviewdog（成熟锚定后端），severity 正确映射。"""
    from touchstone import review_provider as rp
    d = rp.to_rdjson([{"rule_id": "SCOPE-001", "file": "m.sql", "line": 1,
                       "severity": "block_candidate", "rationale": "超出 scope"}])
    diag = d["diagnostics"][0]
    assert d["source"]["name"] == "touchstone"
    assert diag["severity"] == "ERROR" and diag["location"]["path"] == "m.sql"
    assert diag["code"]["value"] == "SCOPE-001"


def test_to_rdjson_shape():
    rd = RP.to_rdjson([{"rule_id": "SCOPE-001", "file": "a.sql", "line": 3,
                       "severity": "block_candidate", "rationale": "超出 scope"},
                      {"rule_id": "PRA-STYLE", "file": "b.py", "severity": "warn"}])
    d = rd["diagnostics"]
    assert rd["source"]["name"] == "touchstone" and len(d) == 2
    assert d[0]["severity"] == "ERROR" and d[0]["location"]["range"]["start"]["line"] == 3
    assert d[1]["severity"] == "WARNING" and d[1]["location"]["range"]["start"]["line"] == 1


def test_injection_disabled_switch(monkeypatch):
    from touchstone import review_provider as rp
    monkeypatch.setenv('TOUCHSTONE_EXPERIENCE_ENABLED', 'false')
    assert rp._experience_injection('.') == ''

def test_injection_skipped_in_pr_without_trusted_ref(monkeypatch, tmp_path):
    """PR 事件且未配受信 ref → 即便经验库真实存在也不注入（非空转验证：防投毒 fail-safe）。"""
    import importlib, learning_loop
    from touchstone import review_provider as rp
    store = tmp_path / "exp.json"
    store.write_text('{"experiences": [{"id": "e:::T", "finding_type": "T", "kind": "emphasize",'
                     '"text": "FLAG-T", "status": "active", "updated_at": 1}]}', encoding="utf-8")
    monkeypatch.setenv("TOUCHSTONE_STORE_PATH", str(store))
    importlib.reload(learning_loop)
    try:
        monkeypatch.setenv("TOUCHSTONE_EXPERIENCE_ENABLED", "true")
        monkeypatch.delenv("TOUCHSTONE_EXPERIENCE_REF", raising=False)
        monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
        assert rp._experience_injection(".") == ""              # PR 无受信 ref：拒注入
        monkeypatch.setenv("GITHUB_EVENT_NAME", "schedule")
        assert "FLAG-T" in rp._experience_injection(".")        # 非 PR：正常注入（证明非空转）
    finally:
        monkeypatch.delenv("TOUCHSTONE_STORE_PATH", raising=False)
        importlib.reload(learning_loop)
