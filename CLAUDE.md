# 开发与验证原则 · 给写代码的大模型

> 这份是给**正在改这个仓库的大模型**看的硬性规矩，会被编码 agent 自动加载到上下文（Claude Code 读仓库根的 `CLAUDE.md`；其它工具读 `AGENTS.md`，已软链到本文件）。
> 你正在开发的系统（Touchstone）本身就是用来挡住"AI 写的、看着对其实错"的代码的。**别在开发它的时候，犯它要抓的那些错。**
> 任何一条规矩与具体任务冲突时：**停下，问人，不要自作主张。**

---

## 0. 一句话

你可以用任何方式重写/优化你负责那一层的实现——**前提是：不动层间契约、本层测试全绿、不编造、不把测试改弱来骗过**。做不到就如实说做不到，不要伪装成功。

---

## 1. 四条铁律（违反即视为瞎写，直接拒绝合入）

1. **不动契约。** 层间数据结构是冻结的——`Finding`、`RiskAssessment`（含 `verification_decision`）、`SubmissionContract`、`VerificationResult`、`CalibrationRecord`、总闸状态名 `touchstone/gate`。**不许增删改它们的字段、类型、含义。** 若任务看起来非改契约不可：**停下，向人说明，等两人评审**，不要"顺手"改了。

2. **测试不可削弱。** 不许删测试、不许放宽断言、不许写恒真断言（`assert True`、断言永远成立的东西）来让代码"通过"。**测试是行为的定义**，不是你要绕过的障碍。改不动就报告卡点，不要做假。
   —— 讽刺提醒：本系统的"空实现哨兵"和"变异检查"就是专门抓这种假绿的。你要是这么干，等于亲手示范了它要拦的反面教材。

3. **待在自己那一层。** 只改你归属的模块（见 §4）。**不许擅自动**别人的模块、也不许动共有文件：`touchstone/run.py`、`.github/workflows/`、`tests/test_e2e_smoke.py`、设计文档 §3 的数据结构。要动这些 → 先标记、走联审。

4. **不编造。** 不许凭空发明接口名、文件路径、函数、库的行为、配置项。**拿不准某东西是否存在/怎么用，就去读源码、跑一下确认**，不要猜。**不许在没真跑测试的情况下声称"测试通过"。** 不许引用你没核实过的文档章节或数据。

---

## 2. "完成"的定义（DoD）—— 提交前逐条自检

一个任务只有满足**全部**下列条件，才算完成：

- [ ] 代码改完，且**真的运行过**本层相关测试：`python -m pytest tests/<本层测试文件> -q` —— **全绿**。
- [ ] 端到端冒烟未被破坏：`python -m pytest tests/test_e2e_smoke.py -q` —— **绿**。
- [ ] **没有改任何层间契约**（§1.1）；若确需改，已停下并取得人的批准。
- [ ] 没有新增不必要的依赖（如有，PR 里已说明理由与替代方案对比）；仓库须保持**离线可跑**（测试不依赖 LLM / 网络 / 外部服务）。
- [ ] 改动若涉及设计文档里描述过的具名接口或行为，**已同步更新文档**（或已明确标记需更新）。
- [ ] **CI 烟测（防"实现了却没跑通"）**：动了 `.github/workflows/` 或依赖/环境相关时，不只验 YAML 语法——要确认它在**目标 runner + Python 版本**上真能装依赖、跑通到结束。**坑**：`pull_request_target` 出于安全取 **base 分支（main）的 workflow**，**PR 改不动自己 workflow 的 check**——这类改动在本 PR 无法自证，合入后必须用下一个 PR 或空 commit 重触发来回归（曾因此把"装 pr-agent"盲合进 main、Python 3.14 下 tiktoken 编译失败而无人发现）。涉及原生编译包（tiktoken/pydantic-core/PyO3 等）尤其要确认目标 Python 有预编译 wheel，否则钉到有 wheel 的版本。
- [ ] 如实写明本次改动**还遗留什么没做 / 哪里是 stub**，不夸大、不把"接缝"说成"已实现"。

**任何一项打不上勾，就不要说"做完了"。** 说清楚卡在哪一项。

---

## 3. 写代码时的具体规矩

- **小步、可验证。** 一次改一小块、跑一次测试确认，再继续。不要一口气抛出大段没验证过的重写。
- **重构保行为。** 优化/重写实现时，对外可观察的行为必须保持不变（除非任务明确要改）；改完所有本层测试 + e2e 必须仍绿。
- **诚实标 gap。** 遇到可选/未实现的东西（TF-GRPO 那条更强做法、默认关的 verify/autonomy），描述时就如实说它是可选/未实现，**不要写成"现行能力"**。文档里"把休眠当现行说"已被多次清理过，别再制造。
- **复用成熟开源组件。** 尽可能复用成熟、经过社区验证的开源库，不要重复造轮子。现有核心依赖：`unidiff` / `requests` / `openai` / `pyyaml` / `pytest` / `coverage`。测试用 `unittest.mock`（stdlib，零额外依赖）。引入新依赖时在 PR 里说明理由与替代方案对比。PR-Agent 在**独立 venv、不进仓库**，只经 `pr_agent_runner.py` 子进程调用——不要把它的包塞进本仓依赖。
- **遇到这些信号立刻停下问人**：要删东西、要改契约/共有文件、要碰安全/凭据相关、跨层改动、或你发现自己在"为了让测试过而修改测试"。

---

## 4. 按层的可动范围（你只动属于你的那一格）

| 你是 | 可改 | 本层测试（提交前必绿） | 绝不擅自动 |
|---|---|---|---|
| **A 评审判断与改进** | `orchestrator.py`·`review_provider.py`·`stack_rules.py`·`contract_check.py`·`gen_best_practices.py`·`pr_agent_runner.py`·`loop.py`·`calibrate.py`·`learning_loop.py` | `test_review_provider`·`test_stack_rules`·`test_contract`·`test_gen_best_practices`·`test_learning_loop`·`test_loop_govern_calibrate`(loop+calibrate 部分) | B 的模块、契约结构、`run.py`、workflows、e2e |
| **B 验证·门禁·自治** | `verify/verify_change.py`·`checks.py`·`ghclient.py`·`preflight.py`·`govern.py`·`autonomy.py` | `test_verify`·`test_checks`·`test_preflight`·`test_autonomy`·`test_loop_govern_calibrate`(govern 部分) | A 的模块、契约结构、`run.py`、workflows、e2e |

> 跨层只允许经数据契约相接（A→B 给 `Finding`+`RiskAssessment`+`SubmissionContract`+`CalibrationRecord`；B→A 给 `VerificationResult`+总闸+`AutonomyState`+毕业类）。需要对方配合的，提出来联审，不要直接伸手改对方代码。

---

## 5. 你交回结果时，必须说清的三件事

1. **改了什么**：动了哪些文件、哪些函数，对外行为有没有变。
2. **验证了什么**：跑了哪些测试、结果（贴真实输出，别凭印象）；契约有没有动。
3. **还差什么**：本次没做完的、绕过的、留作 stub 的，逐条列出——**宁可显得"没做完"，也不要假装"全做好了"**。

---

**总则重申**：本仓的精神是"自主边界 = 验证边界"。对你（写代码的大模型）同样成立——**你能改多少、改得能不能信，取决于测试覆盖到哪、契约守没守住，而不是取决于你自己觉得写得多好。**
