"""PR-Agent 评审路径骨架（评审提供器 + 归一 + 裁决映射）。纯函数、离线；
PR-Agent 真实端点为接缝，测试经 pr_ctx['pr_agent_output'] 注入原始输出。"""
import json

import pytest

from touchstone import review_provider as RP


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


def test_run_link_from_actions_env(monkeypatch):
    # 评审评论里贴的"完整 LLM 交互日志"链接，由 Actions env 构造；非 Actions 环境为空
    from touchstone import orchestrator as orc
    monkeypatch.setenv("GITHUB_RUN_ID", "12345")
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
    monkeypatch.setenv("GITHUB_SERVER_URL", "https://github.com")
    assert orc._run_link() == "https://github.com/o/r/actions/runs/12345"
    monkeypatch.delenv("GITHUB_RUN_ID", raising=False)
    assert orc._run_link() == ""


def test_runner_imports_without_pr_agent():
    # 适配器模块本身可被导入、不在导入期触碰 pr-agent（pr-agent 只在 run() 内 import）
    from touchstone import pr_agent_runner as R
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
    import importlib
    from touchstone import learning_loop
    from touchstone import review_provider as rp
    store = tmp_path / "exp.json"
    store.write_text('{"experiences": [{"id": "e:::T", "finding_type": "T", "kind": "emphasize",'
                     '"text": "FLAG-T", "status": "active", "updated_at": 1}]}', encoding="utf-8")
    monkeypatch.setenv("TOUCHSTONE_STORE_PATH", str(store))
    from touchstone import experience_store
    importlib.reload(experience_store)   # STORE_PATH 在 experience_store 导入期求值
    importlib.reload(learning_loop)      # 门面再导出随后同步
    try:
        monkeypatch.setenv("TOUCHSTONE_EXPERIENCE_ENABLED", "true")
        monkeypatch.delenv("TOUCHSTONE_EXPERIENCE_REF", raising=False)
        monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
        assert rp._experience_injection(".") == ""              # PR 无受信 ref：拒注入
        monkeypatch.setenv("GITHUB_EVENT_NAME", "schedule")
        assert "FLAG-T" in rp._experience_injection(".")        # 非 PR：正常注入（证明非空转）
    finally:
        monkeypatch.delenv("TOUCHSTONE_STORE_PATH", raising=False)
        importlib.reload(experience_store); importlib.reload(learning_loop)


# ---------------- review_reliable：引擎健康度判据 ----------------
def test_review_reliable_ok_with_suggestions():
    assert RP.review_reliable("ok", ai_raw_count=3, added_lines=500) is True


def test_review_reliable_ok_small_diff_zero_suggestions():
    # 改动小（<阈值）且 0 建议 -> 合理，可靠
    assert RP.review_reliable("ok", ai_raw_count=0, added_lines=5) is True


def test_review_reliable_suspicious_empty_large_diff_zero_suggestions():
    # 改动不小（>=阈值）却 0 原始建议 -> 可疑空收敛（PR #44 真根因：diff 被裁空）-> 不可靠
    assert RP.review_reliable("ok", ai_raw_count=0, added_lines=25) is False
    assert RP.review_reliable("ok", ai_raw_count=0, added_lines=20) is False  # 边界


def test_review_reliable_engine_degraded():
    # 引擎降级各态 -> 不可靠（0 建议是缺审，非审完无问题）
    for st in ("no_engine", "provider_failed", "llm_failed", "skipped_large_diff"):
        assert RP.review_reliable(st, ai_raw_count=0, added_lines=5) is False


# ---------------- review_reliable engaged 逃生口（PR #51：审完无问题 ≠ 裁空/吞没）----------------
def test_review_reliable_engaged_clean_is_reliable():
    # glm 审完无问题：engine ok、改动不小、0 建议、但 engaged（多段实质性评审）-> 可靠。
    # 这是 PR #51 的真场景：干净 PR 被旧逻辑误判可疑空收敛。
    assert RP.review_reliable("ok", ai_raw_count=0, added_lines=61, engaged=True) is True
    assert RP.review_reliable("ok", ai_raw_count=0, added_lines=20, engaged=True) is True  # 边界


def test_review_reliable_not_engaged_large_still_suspicious():
    # 未 engaged（_rv 近乎空，如 diff 被裁空）+ 大改动 + 0 建议 -> 仍可疑（guard 不削弱）
    assert RP.review_reliable("ok", ai_raw_count=0, added_lines=61, engaged=False) is False


def test_review_reliable_engaged_default_false_preserves_old_behavior():
    # 不传 engaged（老调用/autonomy）-> 默认 False -> 大改动 0 建议仍可疑（向后兼容）
    assert RP.review_reliable("ok", ai_raw_count=0, added_lines=61) is False


def test_review_reliable_engaged_does_not_rescue_degraded():
    # 引擎降级时 engaged 无效——降级优先，0 建议是缺审不是审完
    assert RP.review_reliable("llm_failed", ai_raw_count=0, added_lines=61, engaged=True) is False
    assert RP.review_reliable("no_engine", ai_raw_count=0, added_lines=61, engaged=True) is False


def test_review_reliable_engaged_irrelevant_when_findings_present():
    # 有原始建议时本就可靠，engaged 无关
    assert RP.review_reliable("ok", ai_raw_count=2, added_lines=61, engaged=False) is True


def test_extract_engaged_reads_runner_signal():
    # runner 在 review 段写 _engaged；离线注入/老协议/非 dict -> False（保守）
    assert RP._extract_engaged({"review": {"_engaged": True, "key_issues_to_review": []}}) is True
    assert RP._extract_engaged({"review": {"_engaged": False}}) is False
    assert RP._extract_engaged({"review": {"key_issues_to_review": []}}) is False  # 无 _engaged 键
    assert RP._extract_engaged({"code_suggestions": []}) is False                  # 无 review 段
    assert RP._extract_engaged(None) is False                                      # 非 dict


def test_extract_engaged_truthy_nondict_review_is_false():
    # 闭环 PR #52 advisory（PRA-POSSIBLE_ISSUE）：review 为 truthy 非 dict（malformed/legacy
    # 字符串/列表/数）时，`data.get("review") or {}` 短路返回该非 dict 值，旧实现 .get("_engaged")
    # 会抛 AttributeError。守卫后须安全落到 False，且不抛。
    assert RP._extract_engaged({"review": "some string"}) is False
    assert RP._extract_engaged({"review": ["a", "b"]}) is False
    assert RP._extract_engaged({"review": 42}) is False
    # 正常 dict 仍工作（回归保护）
    assert RP._extract_engaged({"review": {"_engaged": True}}) is True


# ---------------- prediction_swallowed_failure：pr-agent 吞掉的 LLM 失败检测 ----------------
def test_prediction_swallowed_failure_empty_with_sig():
    # round-3 / #46 真场景：失败串在 stderr + 本轮 0 原始建议 -> 吞没失败
    data = {"code_suggestions": [], "review": {"key_issues_to_review": []}}
    stderr = "...WARNING Failed to generate prediction with openai/glm-5.2\nERROR Failed to generate...with any model"
    assert RP.prediction_swallowed_failure(data, stderr) is True


def test_prediction_swallowed_failure_with_real_issues_not_swallowed():
    # round-2 场景：improve 工具失败（stderr 有串）但 review 成功给了 key_issues -> 不算吞没
    data = {"code_suggestions": [], "review": {"key_issues_to_review": [{"relevant_file": "x.py"}]}}
    assert RP.prediction_swallowed_failure(data, "Failed to generate prediction") is False


def test_prediction_swallowed_failure_clean_success():
    # 正常成功：无失败串 -> 不算吞没
    data = {"code_suggestions": [{"a": 1}], "review": {"key_issues_to_review": []}}
    assert RP.prediction_swallowed_failure(data, "all good, no errors") is False


def test_invoke_endpoint_swallowed_failure_raises_llm_failed(monkeypatch):
    # pr-agent 退出码 0、无 _degraded、空 findings、stderr 含失败串 -> 抛 ReviewEngineDegraded("llm_failed")
    # （此前的 _degraded 字段检查漏过这种吞没；本检测是 review_reliable 主判据的来源）
    monkeypatch.setattr(RP.subprocess, "run", lambda a, **k: _Proc(
        0, out=json.dumps({"code_suggestions": [], "review": {"key_issues_to_review": []}}),
        err="...Failed to generate prediction with openai/glm-5.2\nFailed to generate...any model"))
    monkeypatch.setattr(RP, "_experience_injection", lambda d: "")
    with pytest.raises(RP.ReviewEngineDegraded) as ei:
        RP.fetch({"owner": "o", "repo": "r", "number": 3})
    assert ei.value.degraded == "llm_failed"
    assert "Failed to generate prediction" in ei.value.reason


def test_invoke_endpoint_partial_success_not_degraded(monkeypatch):
    # improve 工具失败（stderr 有串）但 review 给了 key_issues -> 不降级（仍拿到真实评审）
    monkeypatch.setattr(RP.subprocess, "run", lambda a, **k: _Proc(
        0, out=json.dumps({"code_suggestions": [],
                           "review": {"key_issues_to_review": [{"relevant_file": "x.py"}]}}),
        err="Failed to generate prediction with openai/glm-5.2"))
    monkeypatch.setattr(RP, "_experience_injection", lambda d: "")
    items = RP.fetch({"owner": "o", "repo": "r", "number": 3})
    assert len(items) == 1                                    # review 的 1 条意见照常返回


# ---------------- 子进程 stdout 噪音容错（litellm/pr-agent 延迟 print 污染；PR #49 no_engine 真根因）----------------
# runner（pr_agent_runner._emit_json）用 _JSON_BEGIN/_JSON_END 哨兵包裹 JSON；父进程 _extract_json
# 按哨兵提取、无哨兵则 raw_decode 兜底。模拟各种 litellm async 延迟 print 场景，确保不误判 no_engine。
def test_invoke_endpoint_json_with_trailing_litellm_noise(monkeypatch):
    # 〔本次 bug〕哨兵包裹的 JSON 后跟 litellm "Logging Details LiteLLM-Async Success Call"
    # （async 回调晚于 runner fd 级 dup2 重定向恢复才落盘）→ 父进程按哨兵提取，不 no_engine。
    noisy = (RP._JSON_BEGIN + json.dumps(_RAW) + RP._JSON_END +
             "\nLogging Details LiteLLM-Async Success Call, cache_hit=None")
    monkeypatch.setattr(RP.subprocess, "run", lambda a, **k: _Proc(0, out=noisy))
    monkeypatch.setattr(RP, "_experience_injection", lambda d: "")
    assert len(RP.fetch({"owner": "o", "repo": "r", "number": 3})) == 4


def test_invoke_endpoint_json_with_leading_noise(monkeypatch):
    # litellm 噪音在哨兵之前（回调早于 main 的 _emit_json）也能按哨兵提取。
    noisy = ("LiteLLM.Info: Give Feedback ...\n" + RP._JSON_BEGIN +
             json.dumps(_RAW) + RP._JSON_END)
    monkeypatch.setattr(RP.subprocess, "run", lambda a, **k: _Proc(0, out=noisy))
    monkeypatch.setattr(RP, "_experience_injection", lambda d: "")
    assert len(RP.fetch({"owner": "o", "repo": "r", "number": 3})) == 4


def test_invoke_endpoint_json_with_noise_both_sides(monkeypatch):
    noisy = ("preamble\n" + RP._JSON_BEGIN + json.dumps(_RAW) + RP._JSON_END + "\ntrailing")
    monkeypatch.setattr(RP.subprocess, "run", lambda a, **k: _Proc(0, out=noisy))
    monkeypatch.setattr(RP, "_experience_injection", lambda d: "")
    assert len(RP.fetch({"owner": "o", "repo": "r", "number": 3})) == 4


def test_invoke_endpoint_sentinel_absent_raw_decode_fallback(monkeypatch):
    # 无哨兵（老协议 runner / 哨兵缺失）：JSON 后跟噪音 → raw_decode 取首个对象兜底，
    # 不再 "Extra data" 崩成 no_engine（这正是 PR #49 修复前的失败模式）。
    noisy = json.dumps(_RAW) + "\nLogging Details LiteLLM-Async Success Call"
    monkeypatch.setattr(RP.subprocess, "run", lambda a, **k: _Proc(0, out=noisy))
    monkeypatch.setattr(RP, "_experience_injection", lambda d: "")
    assert len(RP.fetch({"owner": "o", "repo": "r", "number": 3})) == 4


def test_extract_json_unit():
    # 纯函数直接测 _extract_json 三分支：哨兵提取 / raw_decode 兜底 / 纯噪音抛。
    payload = {"code_suggestions": [], "review": {"key_issues_to_review": []}}
    raw = json.dumps(payload)
    assert RP._extract_json(RP._JSON_BEGIN + raw + RP._JSON_END + "trailing") == payload
    assert RP._extract_json("leading" + RP._JSON_BEGIN + raw + RP._JSON_END) == payload
    assert RP._extract_json(raw + " trailing noise") == payload          # raw_decode 兜底
    with pytest.raises(json.JSONDecodeError):
        RP._extract_json("not json at all")                              # 纯噪音无 JSON → 抛


def test_swallowed_failure_ignores_litellm_success_log():
    # 〔举一反三·stderr 侧〕litellm 正常成功日志不含 _PRED_FAILURE_SIGS；即便 findings 空
    # （glm 真审了认为没问题）也不应误判吞没。锁死：成功日志不命中失败签名。
    data = {"code_suggestions": [], "review": {"key_issues_to_review": []}}
    assert RP.prediction_swallowed_failure(data, "Logging Details LiteLLM-Async Success Call") is False


# ---------------- 检测器盲区回归（对 pr-agent 0.37 源码核实的分层失败串）----------------
def test_swallowed_failure_detects_review_parse_layer():
    """review 工具的空 content 失败发生在 retry 圈外的解析层，stderr 不含
    'Failed to generate prediction'——旧单签名检测器在此漏检（小 PR 上
    added_lines 启发式也兜不住）。信号集合必须逐个能触发。"""
    from touchstone import review_provider as rp
    empty = {"code_suggestions": [], "review": {"key_issues_to_review": []}}
    for sig in ("Failed to parse AI prediction after fallbacks",
                "Failed to parse review data",
                "Failed to review PR: argument of type 'NoneType' is not iterable",
                "Failed to generate prediction with openai/glm-5.2"):
        assert rp.prediction_swallowed_failure(empty, f"WARNING ... {sig} ...") is True, sig


def test_swallowed_failure_still_requires_zero_output():
    """有真实评审产出时，即便 stderr 含失败串（如仅 improve 挂了），不算吞没。"""
    from touchstone import review_provider as rp
    data = {"code_suggestions": [], "review": {"key_issues_to_review": [{"issue_header": "x"}]}}
    assert rp.prediction_swallowed_failure(
        data, "Failed to parse review data") is False


def test_swallowed_failure_clean_stderr_negative():
    from touchstone import review_provider as rp
    empty = {"code_suggestions": [], "review": {"key_issues_to_review": []}}
    assert rp.prediction_swallowed_failure(empty, "all good, 0 suggestions") is False


# ---------------- 静默故障系统排查（2026-07-09）：部分降级与截断修复可见化 ----------------
def test_partial_tool_failure_improve_down_review_up():
    """S1：improve 挂、review 正常——整轮仍可信（不触发降级），但必须归因可见。"""
    from touchstone import review_provider as rp
    data = {"code_suggestions": [],
            "review": {"key_issues_to_review": [{"issue_header": "x"}]}}
    assert rp.partial_tool_failure(
        data, "ERROR Failed to generate code suggestions for PR, error: ...") == "improve"
    assert rp.partial_tool_failure(
        data, "[runner] improve produced no data（run() 内部已吞异常）") == "improve"


def test_partial_tool_failure_review_down_improve_up():
    from touchstone import review_provider as rp
    data = {"code_suggestions": [{"suggestion_content": "x"}],
            "review": {"key_issues_to_review": []}}
    assert rp.partial_tool_failure(data, "[runner] review prediction malformed（...）") == "review"
    assert rp.partial_tool_failure(data, "Failed to review PR: boom") == "review"


def test_partial_tool_failure_negative_cases():
    from touchstone import review_provider as rp
    both = {"code_suggestions": [{"s": 1}], "review": {"key_issues_to_review": [{"i": 1}]}}
    none_ = {"code_suggestions": [], "review": {"key_issues_to_review": []}}
    assert rp.partial_tool_failure(both, "Failed to review PR:") is None   # 两侧都有产出
    assert rp.partial_tool_failure(none_, "clean") is None                 # 无失败串
    # 两侧全空 + 失败串 -> 归 swallowed（整轮不可信），不算部分降级
    assert rp.partial_tool_failure(none_, "Failed to review PR:") is None


def test_runner_markers_included_in_swallowed_sigs():
    """runner 外化的三个工具级标记必须能触发整轮吞没检测（两侧全空时）。"""
    from touchstone import review_provider as rp
    empty = {"code_suggestions": [], "review": {"key_issues_to_review": []}}
    for sig in ("[runner] improve produced no data",
                "[runner] review produced empty prediction",
                "[runner] review prediction malformed"):
        assert rp.prediction_swallowed_failure(empty, sig) is True, sig


def test_invoke_meta_repaired_parses_counted(monkeypatch):
    """S3：截断/畸形被 try_fix_yaml 修复的次数经 meta 通道透出。"""
    import json as _j
    import subprocess
    from touchstone import review_provider as rp
    out = _j.dumps({"code_suggestions": [{"suggestion_content": "x", "relevant_file": "a.py",
                                          "language": "python", "existing_code": "",
                                          "improved_code": "", "one_sentence_summary": "s",
                                          "label": "possible bug"}],
                    "review": {"key_issues_to_review": []}})
    err = ("WARNING Initial failure to parse AI prediction: bad yaml\n"
           "WARNING Initial failure to parse AI prediction: bad yaml again\n")
    monkeypatch.setattr(rp.subprocess, "run",
                        lambda *a, **k: subprocess.CompletedProcess(a[0], 0, stdout=out, stderr=err))
    items = rp.fetch({"pr_url": "https://github.com/o/r/pull/1"})
    assert items and rp.invoke_meta()["repaired_parses"] == 2
    assert rp.invoke_meta()["partial_tool_failure"] is None
