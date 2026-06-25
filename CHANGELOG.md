# Changelog

本文件记录 Touchstone 的发布版本。设计的逐版迭代历史见 `docs/touchstone-design.html` 的变更历史。

## v0.2.0 — 2026-06-25

审查后修复：让「确定性红线门禁」真正生效，并接通若干悬空的安全机制（均不改冻结契约字段、marker 仅追加、测试只增不削）。

- **门禁生效（P0）**：`stack_rules`/`contract_check` 的 severity 改为取自规则（不再硬编码 warn），`enforced` 固化标志接入运行时——block_candidate 规则（CTR-001/SPR-TX-001/JAVA-EQ-001）立即阻断，warn 规则经固化后阻断。门禁输入纳入 `touchstone-rules` 发现（此前仅 contract-check，且 orchestrator 误引未定义变量）。内置 **SEC-001 离线密钥扫描器**（高精度正则 + 占位符过滤）；SEC-002（注入）仍标注为外部 SAST。SEC-001 **豁免测试文件**（密钥夹具是故意的，不据此阻断——兑现「宁可漏不误拦」；本条由 Touchstone 审自身 PR 时抓到）。
- **安全机制接通（P1）**：`loop` 按 category 排除 correctness（修 PR-Agent 源 PRA-* 漏网）；熔断改读真实 `auto_handled` marker（不再用低风险代理，hotfix 检测留作未来）；学习回路 `graduate` 接入 `main()`、result marker 追加 `injected_types`（candidate→active 自动达标需积累 A/B 数据，此前由人写 seed 驱动）。
- **配置/开箱（P2）**：`checks.yaml` 的 unit-tests 默认非必填（修开箱总闸恒红）；`preflight` 把 LLM_* 降为可选（评审走 PR-Agent，仅 verify 需要）；`run.py` clone 支持 GHE；`select_runner` 非 Python/Java 返回 None（不再误生成 pytest）；`calibrate.aggregate` 别名容错 + `main()` 经 `record_calibration` 构造记录。
- **清理（P3）**：删 `_SEVERE_BLAST` 死项、修 `review_provider` 过时 docstring、文档对齐。
- **契约检查精度**：`check_scope` 跳过 `<...>` 占位符 scope（未填的 pr.yaml 模板）——不再对每条 PR 刷假阳性 SCOPE-001（与 SEC-001 豁免测试文件同类；亦由审自身 PR 时 bot 报的 23 条 SCOPE-001 触发）。
- 测试 228 → 245（+17 锁定行为），全绿、离线。
- **dogfooding 验证**：PR #2 用 Touchstone 审自身——初版被总闸判 failure（SEC-001 误拦测试夹具），定位修复后判 success（见 RUNBOOK §8）。门禁拦下「看着对、实则误拦」、逼出正确修复的能力，在本仓自己身上得到证实。

## v0.1.0 — 2026-06-23

首个版本。

- **评审主链**:复用 PR-Agent,做发现归一、风险分流、回贴(顾问式,默认不阻断)。
- **确定性门禁**:契约一致性核对 + 栈专项规则(机器可检,命中即阻断),聚合为单一总闸 `touchstone/gate`。
- **独立验证 verify(默认关)**:异模型盲测 + 改前/改后对比 + 充分性阶梯(覆盖/变异);Python 与 Java 双 runner(参考级)。
- **渐进自治 autonomy(默认关)**:仅对校准达标的变更类放行,熔断保障;自主边界 = 验证边界。
- **校准与离线学习**:与人审吻合度/噪声;经验蒸馏含计数式与 **TF-GRPO**(arXiv 2510.08191——策略冻结 + 组内语义优势蒸馏经验当 token prior;经注入 llm,离线假-llm 测试覆盖,生产需旗舰模型端点)。人类输入:`seed_experience` 手写种子、红线 `TOUCHSTONE_PROTECTED_TYPES`(受保护类型永不 suppress)、`locked`(人锁定经验不被回路改写/退役)、奖励权重可配；附 examples/seed_experiences.py（10 条手写种子案例，可直接跑）。
- **GitHub 集成**:三条工作流(touchstone / calibrate / govern)。
- 生产代码约 3427 行 / 17 模块;228 个离线测试全绿(无需 LLM / 网络 / 外部服务);行覆盖率 83%。
