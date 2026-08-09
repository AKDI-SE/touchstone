# tests/test_seed_loader.py —— .touchstone/seeds.yaml 加载器纯函数契约
import os
import textwrap

from touchstone import seed_loader


def _seed_path(repo_dir):
    return os.path.join(repo_dir, ".touchstone", "seeds.yaml")


def _write(repo_dir, body):
    p = _seed_path(repo_dir)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(textwrap.dedent(body))


def test_no_file_returns_empty(tmp_path):
    assert seed_loader.load_seed_injection(str(tmp_path)) == ""


def test_empty_file_returns_empty(tmp_path):
    _write(str(tmp_path), "")
    assert seed_loader.load_seed_injection(str(tmp_path)) == ""


def test_empty_list_returns_empty(tmp_path):
    _write(str(tmp_path), "[]")
    assert seed_loader.load_seed_injection(str(tmp_path)) == ""


def test_valid_emphasize_and_suppress(tmp_path):
    _write(str(tmp_path), """
        - finding_type: PRA-ERROR-SWALLOW
          kind: emphasize
          text: Flag empty catch blocks.
        - finding_type: PRA-NIT
          kind: suppress
          text: Skip formatting nits.
    """)
    out = seed_loader.load_seed_injection(str(tmp_path))
    assert "Team seed rules" in out
    assert "[PRA-ERROR-SWALLOW] Prioritize surfacing: Flag empty catch blocks." in out
    assert "[PRA-NIT] Do not raise: Skip formatting nits." in out


def test_stack_filter_seed_with_matching_stack_included(tmp_path):
    _write(str(tmp_path), """
        - finding_type: PRA-X
          kind: emphasize
          stack: python
          text: py only
    """)
    out = seed_loader.load_seed_injection(str(tmp_path), stack="python")
    assert "PRA-X" in out


def test_stack_filter_seed_with_nonmatching_stack_excluded(tmp_path):
    _write(str(tmp_path), """
        - finding_type: PRA-X
          kind: emphasize
          stack: python
          text: py only
    """)
    out = seed_loader.load_seed_injection(str(tmp_path), stack="go")
    assert out == ""                                # 唯一一条被栈过滤掉 → 空


def test_stack_no_field_applies_to_all_stacks(tmp_path):
    """没标 stack 的种子对所有栈生效（通用规范）。"""
    _write(str(tmp_path), """
        - finding_type: PRA-UNIVERSAL
          kind: emphasize
          text: applies everywhere
    """)
    for st in ("python", "go", "rust", "anything"):
        assert "PRA-UNIVERSAL" in seed_loader.load_seed_injection(str(tmp_path), stack=st)


def test_malformed_yaml_returns_empty(tmp_path):
    _write(str(tmp_path), "not: valid: yaml: [\n")
    assert seed_loader.load_seed_injection(str(tmp_path)) == ""


def test_top_level_dict_returns_empty(tmp_path):
    _write(str(tmp_path), """
        finding_type: PRA-X
        kind: emphasize
        text: wrong shape
    """)
    assert seed_loader.load_seed_injection(str(tmp_path)) == ""


def test_bad_items_skipped_individually_good_kept(tmp_path):
    """格式不对的条目逐条跳过、不整体失败；合法条目保留。"""
    _write(str(tmp_path), """
        - finding_type: PRA-GOOD
          kind: emphasize
          text: keep
        - finding_type: PRA-BAD
          kind: weird
          text: bad kind
        - text: no finding_type
        - finding_type: PRA-NOTEXT
          kind: emphasize
        - "plain string item"
        - 42
    """)
    out = seed_loader.load_seed_injection(str(tmp_path))
    assert "PRA-GOOD" in out
    assert "PRA-BAD" not in out
    assert "PRA-NOTEXT" not in out
    assert "plain string" not in out
    # 只剩一条合法
    lines = [l for l in out.splitlines() if l.startswith("- [")]
    assert len(lines) == 1


def test_kind_case_insensitive(tmp_path):
    _write(str(tmp_path), """
        - finding_type: PRA-A
          kind: EMPHASIZE
          text: upper
        - finding_type: PRA-B
          kind: Suppress
          text: mixed
    """)
    out = seed_loader.load_seed_injection(str(tmp_path))
    assert "PRA-A" in out and "Prioritize surfacing" in out
    assert "PRA-B" in out and "Do not raise" in out


def test_text_and_finding_type_required(tmp_path):
    """缺 text 或 finding_type 的条目跳过（空 text 也算缺）。"""
    _write(str(tmp_path), """
        - finding_type: PRA-A
          kind: emphasize
          text: "  "
        - kind: emphasize
          text: no ftype
    """)
    assert seed_loader.load_seed_injection(str(tmp_path)) == ""
