import preflight


def _rows_to_map(rows):
    return {name: (ok, detail) for name, ok, detail in rows}


def test_check_config_flags_missing_required():
    rows = _rows_to_map(preflight.check_config({}))
    assert rows["GITHUB_TOKEN"][0] is False                 # 唯一必需项缺失 → ✗
    # LLM_* 不再必需（评审走 PR-Agent）：缺失时只给 advisory 行（ok=True），不再逐项判 ✗
    assert rows["LLM（verify 用）"][0] is True


def test_check_config_all_required_ok():
    env = {"GITHUB_TOKEN": "t", "LLM_BASE_URL": "http://x", "LLM_API_KEY": "k",
           "LLM_MODEL": "m-review", "LLM_TEST_MODEL": "m-test"}
    rows = _rows_to_map(preflight.check_config(env))
    assert rows["GITHUB_TOKEN"][0] is True
    assert "model-diversity" not in rows          # 异模型 → 不报
    assert "LLM（verify 用）" not in rows          # LLM_* 齐全 → 无 advisory


def test_check_config_flags_same_review_and_test_model():
    env = {"GITHUB_TOKEN": "t", "LLM_BASE_URL": "http://x", "LLM_API_KEY": "k",
           "LLM_MODEL": "same", "LLM_TEST_MODEL": "same"}
    rows = _rows_to_map(preflight.check_config(env))
    assert rows["model-diversity"][0] is False     # 同源 → 报盲点风险
