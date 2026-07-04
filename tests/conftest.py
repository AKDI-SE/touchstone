import os
import sys

import pytest
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
# 未 pip install 时也可直接跑测试：仅插入仓库根目录（touchstone/、verify/ 均为其下的包）；
# tests/ 自身入 path 供 helpers 导入。模块一律以包形式导入（from touchstone import x），
# 与运行态同名同对象——不再出现"平铺导入与包导入各一份模块对象"的 monkeypatch 失配。
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)


@pytest.fixture(scope="session")
def rule_index():
    rules = yaml.safe_load(open(os.path.join(ROOT, ".touchstone", "standards.yaml")))["rules"]
    return {r["id"]: r for r in rules}


# #10 测试隔离：每个测试前重置已知的模块级可变全局，防止跨测试污染
# （本会话曾踩到：_PARSE_WARNING/_IX/_SESSION 残留影响后续测试）。
@pytest.fixture(autouse=True)
def _reset_module_globals():
    from touchstone import contract_check
    contract_check._PARSE_WARNING = None
    # pr_agent_runner / ghclient 可能尚未被 import（importorskip 等场景），容错
    try:
        from touchstone import pr_agent_runner
        pr_agent_runner._IX.clear()
    except Exception:
        pass
    try:
        from touchstone import ghclient
        ghclient._SESSION = None
    except Exception:
        pass
    yield

