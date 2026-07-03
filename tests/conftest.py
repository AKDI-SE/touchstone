import os
import sys

import pytest
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
# 顺序：最后 insert(0) 的在最前 → touchstone/ 在最前，使 `import orchestrator` 解析到 orchestrator.py 模块
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "verify"))
sys.path.insert(0, os.path.join(ROOT, "touchstone"))


@pytest.fixture(scope="session")
def rule_index():
    rules = yaml.safe_load(open(os.path.join(ROOT, ".touchstone", "standards.yaml")))["rules"]
    return {r["id"]: r for r in rules}


# #10 测试隔离：每个测试前重置已知的模块级可变全局，防止跨测试污染
# （本会话曾踩到：_PARSE_WARNING/_IX/_SESSION 残留影响后续测试）。
@pytest.fixture(autouse=True)
def _reset_module_globals():
    import contract_check
    contract_check._PARSE_WARNING = None
    # pr_agent_runner / ghclient 可能尚未被 import（importorskip 等场景），容错
    try:
        import pr_agent_runner
        pr_agent_runner._IX.clear()
    except Exception:
        pass
    try:
        import ghclient
        ghclient._SESSION = None
    except Exception:
        pass
    yield

