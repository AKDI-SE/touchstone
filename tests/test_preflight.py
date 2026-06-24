import preflight


def _rows_to_map(rows):
    return {name: (ok, detail) for name, ok, detail in rows}


def test_check_config_flags_missing_required():
    rows = _rows_to_map(preflight.check_config({}))
    for k in ("GITHUB_TOKEN", "LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL"):
        assert rows[k][0] is False


def test_check_config_all_required_ok():
    env = {"GITHUB_TOKEN": "t", "LLM_BASE_URL": "http://x", "LLM_API_KEY": "k",
           "LLM_MODEL": "m-review", "LLM_TEST_MODEL": "m-test"}
    rows = _rows_to_map(preflight.check_config(env))
    for k in ("GITHUB_TOKEN", "LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL"):
        assert rows[k][0] is True
    assert "model-diversity" not in rows          # 异模型 → 不报


def test_check_config_flags_same_review_and_test_model():
    env = {"GITHUB_TOKEN": "t", "LLM_BASE_URL": "http://x", "LLM_API_KEY": "k",
           "LLM_MODEL": "same", "LLM_TEST_MODEL": "same"}
    rows = _rows_to_map(preflight.check_config(env))
    assert rows["model-diversity"][0] is False     # 同源 → 报盲点风险
