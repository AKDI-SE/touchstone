# Touchstone · 两人分工与开发计划

> 基线：v0.1.0，生产代码 3427 行 / 17 模块，228 个离线测试全绿；设计文档、4+1 视图、PR-Agent 集成、学习回路文档均已就绪。verify 子系统为参考级、默认关；自治默认关。下一阶段目标是**在真实仓库上打通并逐步硬化**。

---

## 1. 分工总则

两人沿系统的**核心二分法**切：一人管 **AI 判断及其自我改进**（顾问侧），一人管 **客观验证·门禁·自治**（保障侧）。两块只经数据契约相接；各自内部用大模型怎么优化都行，前提是：① 自己那块测试全绿；② 不擅改层间契约。

**层间契约（冻结，改动须两人评审）**

| 方向 | 契约 |
|---|---|
| A → B | `Finding` · `RiskAssessment`（含 `verification_decision`）· `SubmissionContract` · `CalibrationRecord` |
| B → A | `VerificationResult` · 总闸 `touchstone/gate` · `AutonomyState` · 毕业类 `graduated-classes` |

**共有、改动须联审**：`tests/test_e2e_smoke.py`、`touchstone/run.py`、`.github/workflows/`、设计文档 §3 数据结构。

## 2. 两人职责与归属

### A · 评审判断与改进 —— 产出并改进顾问式判断
模块：`orchestrator.py` · `review_provider.py` · `stack_rules.py` · `contract_check.py` · `gen_best_practices.py` · `pr_agent_runner.py` · `loop.py` · `calibrate.py` · `learning_loop.py`
规模：活跃 ~1623 行
测试：`test_review_provider`(21)·`test_stack_rules`(17)·`test_contract`(18)·`test_gen_best_practices`(6)·`test_learning_loop`(11)·`test_loop_govern_calibrate` 的 loop+calibrate 部分
关键接口：`review_pr` / `normalize` / `map_verdict` / `route` / `check_stack_rules` / `check_contract_consistency` / `loop_step` / `record_calibration` / `distill_candidates`

### B · 验证·门禁·自治 —— 客观裁定准入与安全
模块：`verify/verify_change.py`（最大，701 行）· `checks.py` · `ghclient.py` · `preflight.py` · `govern.py` · `autonomy.py`
规模：活跃 ~1468 行
测试：`test_verify`(25)·`test_checks`(18)·`test_preflight`(3)·`test_autonomy`(17)·`test_loop_govern_calibrate` 的 govern 部分
关键接口：`verify_change` / `check_adequacy` / `resolve_acceptance_spec` / `select_runner` / `run_checks` / `aggregate_gate` / `post_gate` / `promote_to_gate` / `decide_auto_merge`

> **工作量与称重**：活跃代码 A≈B（1623 / 1468），大体均衡。称重上 B 含最关键的 verify（全仓最大模块、系统安全保证所在），难度最高；A 量稍大，但偏「软」的判断调优（信噪比、风险定级、规则、学习），收敛更难。两边各有一处重头，不偏废。

## 3. 初始化任务 0（开工前，先做）

先完成 [`github-setup.md`](github-setup.md)：把仓库放上 GitHub、配好让 Touchstone 在本仓 PR 上自动评审（纯顾问式打通），形成自我狗粮回路。完成其「完成判据」后再进入 M1。

## 4. 需求拆分到每人（P0 = 真实打通前置 / P1 = 硬化 / P2 = 演进）

### A · 评审判断与改进
- **A-P0-1** 接通真实 PR-Agent 端点：打通 `pr_agent_runner` → PR-Agent，确认 `pr-agent.yaml` 归一映射覆盖真实输出。
- **A-P0-2** 真实公开 PR 试跑：选 3–5 个真实 PR 跑 `review_pr`，人工核对 `map_verdict` 风险定级与 `Finding` 信噪比。
- **A-P0-3** calibrate 真实跑：用 A-P0-2 的评审 + 已合 PR 的人审裁决，经 `record_calibration`/`aggregate` 出**第一份吻合度/噪声报告**（供 B 的 govern/autonomy 当毕业依据）。
- **A-P1-1** 扩充栈专项确定性规则（补 Java/Spring + Go/Python 可机检规则），每条配 `test_stack_rules`。
- **A-P1-2** 打磨 `gen_best_practices`，让主观规则更有效喂 PR-Agent。
- **A-P1-3** learning_loop 离线蒸馏打通（计数式 + shadow A/B）；TF-GRPO 那条更强做法暂不实现。
- **A-P2-1** 反馈循环 `loop_step` 在真实 author-agent 上联调（收敛/升级判据）。

### B · 验证·门禁·自治
- **B-P0-1** verify 真实实跑（Python）：在一个真实 Python 仓库打通「改前 FAIL / 改后 PASS / 改动行覆盖 / 回归绿」判决链。
- **B-P0-2** 接通异模型 LLM 端点做 `generate_spec_blind_tests`（异于 touchstone 模型）。
- **B-P1-1** 变异换生产级：Python 侧自写 AST 变异 → mutmut/cosmic-ray；Java 侧在真实 Maven 项目上验证 PIT。
- **B-P1-2** 总闸真实联调：`checks` 的 builtin/relay/service 聚合成单一 `touchstone/gate`。
- **B-P1-3** govern 固化通道 + 熔断校准：读 A 的 `CalibrationRecord` → `promote_to_gate` / `update_autonomy`，在真实 revert/hotfix 信号上校准阈值。
- **B-P1-4** autonomy 影子模式：`decide_auto_merge` 全程 dry-run，记录「若开启会放行哪些」，先不真合。
- **B-P2-1** 充分性阶梯调参：覆盖/变异阈值按风险档（cheap/targeted/full）定标。
- **B-P2-2** 多语言 runner：按需扩 Go / JS（`select_runner` + 覆盖/变异适配）。

## 5. 里程碑

- **M1 · 真实打通**：A 评审在真实 PR 上出 `Finding` + calibrate 出首份吻合度报告；B verify 在一个真实 Python 仓库打通判决链。**出口门槛**：两块在 ≥1 个真实仓库端到端串起来（**影子，不自动合**）；`test_e2e_smoke` 绿。
- **M2 · 硬化与规模化**：A 栈规则扩充 + 学习蒸馏；B 变异换生产级、总闸联调、govern 固化 + 熔断校准、autonomy 影子。**出口门槛**：多个真实仓库稳定跑；校准数据足以判断「哪些变更类可放行」。
- **M3 · 自治开放**：B 对校准达标的变更类开自动合并（熔断保障）。**红线**：自主边界 = 验证边界。

## 6. 协作流程

1. **契约冻结**：改 §3 任一数据结构或总闸状态名，须两人评审 + 同步更新设计文档 §3/§4，再改代码。
2. **测试即护栏**：用大模型优化实现随便改，但**提交前自己那块测试全绿、契约未动**才能合——这正是 Touchstone 自己的哲学（「验证通过才算数」）用在我们自己的开发上。
3. **联合集成闸**：`test_e2e_smoke` + `run.py` + workflows 改动须联审；e2e 一红即说明契约边界被碰，两人一起看。
4. **建议先做的整理**：把 `test_loop_govern_calibrate.py`（30 例）按 loop+calibrate（A）/ govern（B）拆成两个文件，让测试归属与代码归属对齐。

## 7. 跨人依赖（需协调）

- **A-P0-3（calibrate）→ B 的 govern/autonomy**：B 的固化与毕业读 A 产出的 `CalibrationRecord`；M1 内 A 先产出。
- **B 总闸 + verify → A**：A 的 loop/calibrate 可读 B 的总闸结论。
- **`verification_decision` 档位**：A 的 `route` 产档、B 的 `verify_change` 按档跑——这条 A↔B 共用，改档位定义须两人对齐。

---

> **配套**：写代码的大模型须遵守仓库根 `CLAUDE.md`（开发与验证铁律，已同步为两层 A/B）。本计划面向人、定分工与节奏；`CLAUDE.md` 面向大模型、定不可瞎写的硬约束。
