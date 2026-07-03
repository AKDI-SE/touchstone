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
