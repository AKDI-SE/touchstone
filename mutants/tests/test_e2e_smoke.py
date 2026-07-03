"""离线端到端冒烟 —— #2「真跑一次」的可在沙箱执行的代理。

评审复用 PR-Agent：这里把 PR-Agent 的原始输出经 pr_ctx['pr_agent_output'] 注入（替代真实端点），
其余全真：真 git 仓 + 真 unified diff + 真规范，跑通
  评审提供器(fetch) → 发现归一(normalize) → 裁决映射(map_verdict) + 确定性契约核对
  → 反馈循环 → 变更分类 → 自治决策(默认关→不放行)。
验证编排链本身无误；在你的环境接上真实 PR-Agent 端点(_invoke_endpoint)即为真跑。
"""
import os
import subprocess

import yaml

import autonomy
import orchestrator  # noqa: F401  （触发同目录 sys.path 加固，使下面裸 import 可解析）
import contract_check
import loop
import review_provider


def _git(repo, *args):
    subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True)


def _make_pr_repo(tmp_path):
    repo = str(tmp_path)
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    os.makedirs(os.path.join(repo, "lib"))
    with open(os.path.join(repo, "lib", "util.py"), "w") as f:
        f.write("def shared_helper(a, b):\n    return a + b\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    # “PR”改动：新增一个与已有能力重复的 helper，且没加测试
    os.makedirs(os.path.join(repo, "app"))
    with open(os.path.join(repo, "app", "new.py"), "w") as f:
        f.write("def add_two(x, y):\n    return x + y\n")
    _git(repo, "add", "-A")
    diff = subprocess.run(["git", "-C", repo, "diff", "--cached"],
                          capture_output=True, text=True).stdout
    return repo, diff


def test_e2e_pipeline_offline(tmp_path):
    repo, diff = _make_pr_repo(tmp_path)
    assert "app/new.py" in diff

    standards = yaml.safe_load(open(os.path.join(
        os.path.dirname(orchestrator.__file__), "..", ".touchstone", "standards.yaml")))
    rule_index = {r["id"]: r for r in standards["rules"]}
    contract = {"intent": "add helper", "scope": ["app/**"], "acceptance_criteria": ["加法正确"]}

    # 注入一份 PR-Agent 评审输出（替代真实端点）：报一条"与已有 helper 重复"的建议
    pr_agent_output = {"code_suggestions": [{
        "relevant_file": "app/new.py", "relevant_lines_start": 1, "relevant_lines_end": 2,
        "one_sentence_summary": "Reuse existing shared_helper",
        "improved_code": "from lib.util import shared_helper", "label": "maintainability"}]}
    pr_ctx = {"owner": "o", "repo": "r", "number": 1, "sha": "deadbeef",
              "diff": diff, "standards": standards, "pr_agent_output": pr_agent_output}

    # —— 真实编排链（与 orchestrator.main / run.py 同路径）——
    review_findings = review_provider.normalize(review_provider.fetch(pr_ctx))
    contract_findings = contract_check.check_contract_consistency(diff, contract, rule_index)
    findings, risk = review_provider.map_verdict(review_findings + contract_findings)
    decision, _, _ = loop.loop_step(findings, rule_index, loop.LoopState())
    changed_files, _ = contract_check.parse_diff(diff)
    cls = autonomy.change_class(risk, findings, sorted(changed_files), rule_index)

    # 编排产物连贯
    assert any(f["agent"].startswith("pr-agent") for f in findings)   # PR-Agent 评审被归一保留
    assert any(f["rule_id"] == "TEST-001" for f in findings)          # 无测试 → 确定性契约核对命中
    assert risk["risk_band"] in ("low", "mid", "high")
    assert decision in ("converged", "continue", "escalate")
    assert cls.count("|") == 3 and cls.startswith(risk["risk_band"])  # 变更分类签名成形
    assert "code" in cls                                              # app/new.py 是 code 画像

    # 自治决策：默认关 → 一定不放行（边界在端到端下成立）
    co = {"pr": 1, "sha": "deadbeef", "risk": risk, "findings": findings,
          "changed_files": sorted(changed_files), "loop_decision": decision,
          "change_class": cls, "gate": "success"}
    d = autonomy.build_decision_inputs(co, {"tripped": False}, [cls])
    dec = autonomy.decide_auto_merge(d["risk"], d["findings"], d["loop_decision"],
                                     d["gate"], d["autonomy_state"],
                                     set(d["graduated_classes"]), d["cls"],
                                     enabled=False)
    assert dec["merge"] is False and dec["mode"] == "disabled"
