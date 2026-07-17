#!/usr/bin/env python3
# ============================================================================
# tests/test_atomicio.py —— 状态文件原子写回归锁
# ----------------------------------------------------------------------------
# atomic_write_* 是喂 auto-merge 判据的状态文件（经验库/毕业类/自治态/findings/
# calibration）的落盘保证。本测试锁三件事：① 正常写入内容正确；② 写完不留临时
# 文件；③ 序列化中途抛异常时，既不产生目标文件、也不留半个临时文件——读方永不见
# 截断态（这正是原子写要防的失败模式）。
# ============================================================================

import json
import os

import pytest

from touchstone.atomicio import atomic_write_json, atomic_write_text


def test_write_json_roundtrip(tmp_path):
    p = tmp_path / "sub" / "state.json"          # 父目录不存在也应自动建
    atomic_write_json(str(p), {"graduated_classes": ["a", "b"], "n": 3})
    assert json.loads(p.read_text(encoding="utf-8")) == {
        "graduated_classes": ["a", "b"], "n": 3}


def test_no_temp_leftover(tmp_path):
    p = tmp_path / "state.json"
    atomic_write_json(str(p), {"x": 1})
    leftovers = [n for n in os.listdir(tmp_path) if n.startswith(".ts_tmp_")]
    assert leftovers == [], f"残留临时文件: {leftovers}"


def test_overwrite_is_atomic_replace(tmp_path):
    p = tmp_path / "state.json"
    atomic_write_json(str(p), {"v": 1})
    atomic_write_json(str(p), {"v": 2})          # 覆盖走 os.replace
    assert json.loads(p.read_text())["v"] == 2
    assert len(list(tmp_path.iterdir())) == 1    # 只剩目标文件，无临时残留


def test_serialize_failure_leaves_no_partial(tmp_path):
    """序列化中途失败：不得留下目标文件，也不得留下半个临时文件。
    用不可 JSON 序列化的对象触发 json.dumps 抛错——此时目标路径必须仍不存在
    （旧文件若存在则保持旧内容，绝不出现截断的新文件）。"""
    p = tmp_path / "state.json"
    with pytest.raises(TypeError):
        atomic_write_json(str(p), {"bad": object()})
    assert not p.exists()
    assert [n for n in os.listdir(tmp_path) if n.startswith(".ts_tmp_")] == []


def test_serialize_failure_preserves_prior_content(tmp_path):
    """已有完整旧文件时，新写入序列化失败不得破坏旧文件（读方回退到旧完整态）。"""
    p = tmp_path / "state.json"
    atomic_write_json(str(p), {"good": 1})
    with pytest.raises(TypeError):
        atomic_write_json(str(p), {"bad": object()})
    assert json.loads(p.read_text()) == {"good": 1}   # 旧内容完好


def test_write_text_roundtrip(tmp_path):
    p = tmp_path / "note.txt"
    atomic_write_text(str(p), "hello\n世界")
    assert p.read_text(encoding="utf-8") == "hello\n世界"


# ============ round-2 闭环锁：权限保持（F1）+ 目录 fsync（F2） ============
def test_atomic_write_preserves_existing_file_mode(tmp_path):
    """F1 权限保持：mkstemp 给 0o600，os.replace 会把源 inode 权限带过去——必须
    显式恢复目标既有权限，否则每个被重写的状态文件都静默变 0o600，破坏"同签名同效果"。"""
    p = tmp_path / "state.json"
    p.write_text("{}", encoding="utf-8")
    os.chmod(p, 0o640)                          # 模拟既有文件的非默认权限
    atomic_write_text(str(p), '{"x": 1}')
    assert (os.stat(p).st_mode & 0o777) == 0o640   # 沿用既有，未被 mkstemp 的 0o600 覆盖


def test_atomic_write_new_file_default_mode_is_0o644(tmp_path):
    """F1 新建文件默认 0o644（=旧 open('w') 按 umask 的常见默认），非 mkstemp 的 0o600。"""
    p = tmp_path / "fresh.json"                 # 目标不存在
    atomic_write_text(str(p), "hi")
    assert (os.stat(p).st_mode & 0o777) == 0o644


def test_atomic_write_fsyncs_parent_directory(tmp_path, monkeypatch):
    """F2 目录 fsync：os.replace 后须 fsync 父目录，让 rename 断电后也持久。pytest
    无法模拟断电，故 spy 内部 _fsync_dir 锁定"确实对父目录做了 fsync"（否则 remove
    该行即静默丢失耐久保证，无人察觉）。"""
    import touchstone.atomicio as aio
    seen = []
    monkeypatch.setattr(aio, "_fsync_dir", lambda d: seen.append(d))
    aio.atomic_write_text(str(tmp_path / "state.json"), "data")
    assert seen, "os.replace 后未对父目录 fsync（F2 未落地）"
    assert os.path.samefile(seen[0], str(tmp_path))   # fsync 的是父目录，非别处
