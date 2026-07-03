"""gitcode_check.py 的离线测试（GitCode 平台的确定性门禁入口）。无网络、无 git。"""
import os
import sys

import gitcode_check as gc


# ---------------- load_yaml ----------------
def test_load_yaml_missing_returns_default(tmp_path):
    assert gc.load_yaml(str(tmp_path / "nope.yaml"), "DEF") == "DEF"


def test_load_yaml_reads_file(tmp_path):
    p = tmp_path / "s.yaml"
    p.write_text("rules:\n  - id: X\n", encoding="utf-8")
    assert gc.load_yaml(str(p)) == {"rules": [{"id": "X"}]}


# ---------------- _format_finding ----------------
def test_format_finding_severity_icons():
    base = {"rule_id": "R", "agent": "a", "confidence": 0.5,
            "file": "f.py", "line": 9, "rationale": "why", "suggested_fix": "do"}
    for sev, icon in [("block_candidate", "🚫"), ("warn", "⚠️"), ("info", "ℹ️"), ("wat", "•")]:
        out = gc._format_finding(dict(base, severity=sev), 1)
        assert icon in out and "R" in out and "f.py:9" in out


def test_format_finding_truncates_long_fields():
    out = gc._format_finding(
        {"rule_id": "R", "severity": "warn", "agent": "a", "confidence": 0.1,
         "file": "f", "line": 1, "rationale": "x" * 500, "suggested_fix": "y" * 500}, 2)
    assert "…" not in out  # 仅切片不附加省略号；确认不崩、含截断后内容
    assert len(out) < 700


# ---------------- get_diff_from_git ----------------
class _R:
    def __init__(self, rc, out):
        self.returncode, self.stdout, self.stderr = rc, out, ""


def test_get_diff_first_working_cmd_wins(monkeypatch):
    seen = []
    def fake(cmd, **k):
        seen.append(cmd)
        return _R(0, "diff --git" if len(seen) == 1 else "")
    monkeypatch.setattr(gc.subprocess, "run", fake)
    assert gc.get_diff_from_git("main") == "diff --git"
    assert len(seen) == 1                      # 命中第一条即返回


def test_get_diff_skips_empty_then_none(monkeypatch):
    # 第一条 rc=0 但空、第二条非空 → 取第二条
    seq = [_R(0, "   "), _R(0, "real")]
    monkeypatch.setattr(gc.subprocess, "run", lambda *a, **k: seq.pop(0))
    assert gc.get_diff_from_git("main") == "real"


def test_get_diff_all_fail_returns_none(monkeypatch):
    monkeypatch.setattr(gc.subprocess, "run", lambda *a, **k: _R(1, ""))
    assert gc.get_diff_from_git("main") is None


def test_get_diff_subprocess_exception_returns_none(monkeypatch):
    import subprocess as sp
    def boom(*a, **k):
        raise sp.TimeoutExpired(cmd=a[0], timeout=1)
    monkeypatch.setattr(gc.subprocess, "run", boom)
    assert gc.get_diff_from_git("main") is None


# ---------------- main() ----------------
def _std(tmp_path):
    """写一份最小 standards.yaml。"""
    p = tmp_path / "standards.yaml"
    p.write_text("rules:\n  - id: CTR-001\n    severity: block_candidate\n", encoding="utf-8")
    return str(p)


def test_main_no_diff_passes(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(gc, "get_diff_from_git", lambda base: None)
    monkeypatch.delenv("GITCODE_DIFF_CMD", raising=False)
    assert gc.main() == 0
    assert "无可检查内容" in capsys.readouterr().out


def test_main_missing_standards_returns_1(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "argv", ["gitcode_check", "--diff", "something"])
    monkeypatch.setenv("TOUCHSTONE_STANDARDS", str(tmp_path / "absent.yaml"))
    monkeypatch.setenv("TOUCHSTONE_CONTRACT", str(tmp_path / "c.yaml"))
    assert gc.main() == 1


def test_main_diff_from_stdin(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "argv", ["gitcode_check", "--diff", "-"])
    monkeypatch.setattr(sys, "stdin", _Stdin("--- a/x\n+++ b/x\n@@ +1,1 +1,1 @@\n+x\n"))
    monkeypatch.setenv("TOUCHSTONE_STANDARDS", _std(tmp_path))
    monkeypatch.setenv("TOUCHSTONE_CONTRACT", str(tmp_path / "c.yaml"))
    # 打桩确定性检查：返回空 → GATE PASS
    monkeypatch.setattr(gc.contract_check, "check_contract_consistency", lambda *a: [])
    monkeypatch.setattr(gc.stack_rules, "check_stack_rules", lambda *a: [])
    assert gc.main() == 0


def test_main_diff_inline_arg(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "argv", ["gitcode_check", "--diff", "inline-diff", "--base", "dev"])
    monkeypatch.setenv("TOUCHSTONE_STANDARDS", _std(tmp_path))
    monkeypatch.setenv("TOUCHSTONE_CONTRACT", str(tmp_path / "c.yaml"))
    monkeypatch.setattr(gc.contract_check, "check_contract_consistency", lambda *a: [])
    monkeypatch.setattr(gc.stack_rules, "check_stack_rules", lambda *a: [])
    assert gc.main() == 0


def test_main_gitcode_diff_cmd_env(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "argv", ["gitcode_check"])
    monkeypatch.setenv("GITCODE_DIFF_CMD", "echo hello-diff")
    monkeypatch.setenv("TOUCHSTONE_STANDARDS", _std(tmp_path))
    monkeypatch.setenv("TOUCHSTONE_CONTRACT", str(tmp_path / "c.yaml"))
    monkeypatch.setattr(gc.contract_check, "check_contract_consistency", lambda *a: [])
    monkeypatch.setattr(gc.stack_rules, "check_stack_rules", lambda *a: [])
    assert gc.main() == 0


def test_main_block_finding_fails_gate(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(sys, "argv", ["gitcode_check", "--diff", "x"])
    monkeypatch.setenv("TOUCHSTONE_STANDARDS", _std(tmp_path))
    monkeypatch.setenv("TOUCHSTONE_CONTRACT", str(tmp_path / "c.yaml"))
    block = [{"rule_id": "CTR-001", "severity": "block_candidate", "agent": "contract-check",
              "confidence": 1.0, "file": "a.py", "line": 3, "rationale": "bad", "suggested_fix": "fix"}]
    monkeypatch.setattr(gc.contract_check, "check_contract_consistency", lambda *a: block)
    monkeypatch.setattr(gc.stack_rules, "check_stack_rules", lambda *a: [])
    assert gc.main() == 1
    assert "GATE FAILURE" in capsys.readouterr().out


def test_main_warn_finding_passes_gate(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(sys, "argv", ["gitcode_check", "--diff", "x"])
    monkeypatch.setenv("TOUCHSTONE_STANDARDS", _std(tmp_path))
    monkeypatch.setenv("TOUCHSTONE_CONTRACT", str(tmp_path / "c.yaml"))
    warn = [{"rule_id": "W", "severity": "warn", "agent": "stack", "confidence": 0.5,
             "file": "a.py", "line": 1, "rationale": "meh", "suggested_fix": "optional"}]
    monkeypatch.setattr(gc.contract_check, "check_contract_consistency", lambda *a: [])
    monkeypatch.setattr(gc.stack_rules, "check_stack_rules", lambda *a: warn)
    assert gc.main() == 0
    out = capsys.readouterr().out
    assert "警告级: 1 条" in out and "GATE PASS" in out


class _Stdin:
    def __init__(self, text):
        self.text = text
    def read(self):
        return self.text
