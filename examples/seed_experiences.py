#!/usr/bin/env python3
"""案例：人手写的 10 条评审经验「种子」（seed_experience 的用法）。

这些是「规矩」——会注入 PR-Agent 的提示词，让评审多盯紧某些问题、少挑某些噪声。
不依赖 TF-GRPO、不需模型端点，可立刻用（冷启动）。

照着改：
  • 把 finding_type 换成你们 PR-Agent 实际输出的类型名（下面的 PRA-* 是示意）；
  • 把 repo/stack 换成你们的；
  • 规则原文写英文（PR-Agent 提示词是英文环境，模型执行更准）。

约束：一条经验对应一个（动作 × finding_type）。同一类型表达多点，就合并进一条文字，
      不要写两条同 (kind, finding_type)——后写的会覆盖先写的。

用法：
  python examples/seed_experiences.py          # 写入经验库（路径见 TOUCHSTONE_EXPERIENCE）
  # 或在代码里：
  import learning_loop as L
  store = L.load_store(); apply_seeds(store); L.save_store(store)
安全类记得同时设：export TOUCHSTONE_PROTECTED_TYPES=PRA-SEC-AUTHZ,PRA-SEC-SQLI,PRA-SEC-SECRET-LOG
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "touchstone"))
import learning_loop as L  # noqa: E402

# (finding_type, 动作, 规则原文, stack) —— 前 8 条 emphasize（多盯紧），后 2 条 suppress（别烦人）
SEEDS = [
    ("PRA-SPRING-TX",          "emphasize",
     "Flag @Transactional on private or self-invoked methods; Spring proxies won't apply the transaction.", "java"),
    ("PRA-ERROR-SWALLOW",      "emphasize",
     "Flag empty catch blocks, or catch blocks that only log and swallow the exception.", "java"),
    ("PRA-PY-MUTABLE-DEFAULT", "emphasize",
     "Flag mutable default arguments like def f(x=[]) or x={}; they are shared across calls.", "python"),
    ("PRA-GO-ERRCHECK",        "emphasize",
     "Flag returned errors that are ignored (assigned to _ or not checked).", "go"),
    ("PRA-SEC-AUTHZ",          "emphasize",
     "Flag new HTTP handlers or endpoints added without an auth/authorization check.", ""),
    ("PRA-SEC-SQLI",           "emphasize",
     "Flag SQL built by string concatenation or formatting with request data; require parameterized queries.", ""),
    ("PRA-SEC-SECRET-LOG",     "emphasize",
     "Flag logging or printing of secrets, tokens, passwords, or full request bodies.", ""),
    ("PRA-RELIABILITY-TIMEOUT", "emphasize",
     "Flag outbound network or DB calls created without an explicit timeout.", ""),
    ("PRA-STYLE-IMPORT",       "suppress",
     "Do not raise import-ordering or formatting nits; the formatter/linter already handles them.", ""),
    ("PRA-DOC-PRIVATE",        "suppress",
     "Do not ask for docstrings on short private helper functions in this repo.", ""),
]

# 安全类红线：这些类型永不许被学习回路 suppress（配进 TOUCHSTONE_PROTECTED_TYPES）
PROTECTED = ["PRA-SEC-AUTHZ", "PRA-SEC-SQLI", "PRA-SEC-SECRET-LOG"]


def apply_seeds(store, repo="acme/pay", seeds=SEEDS):
    """把种子写进经验库：默认 active + locked —— 立刻生效注入评审，且回路不得改写/退役。"""
    for ftype, kind, text, stack in seeds:
        L.seed_experience(store, ftype, kind, text, repo=repo, stack=stack)
    return store


def main():
    store = L.load_store()
    apply_seeds(store)
    L.save_store(store)
    print(f"已写入 {len(SEEDS)} 条种子经验到 {L.STORE_PATH}")
    print(f"建议同时设：export TOUCHSTONE_PROTECTED_TYPES={','.join(PROTECTED)}")


if __name__ == "__main__":
    main()
