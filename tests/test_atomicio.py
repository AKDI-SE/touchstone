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
