# Changelog

本文件记录 Touchstone 的发布版本。设计的逐版迭代历史见 `docs/touchstone-design.html` 的变更历史。

## v0.1.0 — 2026-06-23

首个版本。

- **评审主链**:复用 PR-Agent,做发现归一、风险分流、回贴(顾问式,默认不阻断)。
- **确定性门禁**:契约一致性核对 + 栈专项规则(机器可检,命中即阻断),聚合为单一总闸 `touchstone/gate`。
- **独立验证 verify(默认关)**:异模型盲测 + 改前/改后对比 + 充分性阶梯(覆盖/变异);Python 与 Java 双 runner(参考级)。
- **渐进自治 autonomy(默认关)**:仅对校准达标的变更类放行,熔断保障;自主边界 = 验证边界。
- **校准与离线学习**:与人审吻合度/噪声;经验蒸馏含计数式与 **TF-GRPO**(arXiv 2510.08191——策略冻结 + 组内语义优势蒸馏经验当 token prior;经注入 llm,离线假-llm 测试覆盖,生产需旗舰模型端点)。人类输入:`seed_experience` 手写种子、红线 `TOUCHSTONE_PROTECTED_TYPES`(受保护类型永不 suppress)、`locked`(人锁定经验不被回路改写/退役)、奖励权重可配；附 examples/seed_experiences.py（10 条手写种子案例，可直接跑）。
- **GitHub 集成**:三条工作流(touchstone / calibrate / govern)。
- 生产代码约 3427 行 / 17 模块;228 个离线测试全绿(无需 LLM / 网络 / 外部服务);行覆盖率 83%。
