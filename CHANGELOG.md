# Changelog

本文件记录 Touchstone 的发布版本。设计的逐版迭代历史见 `docs/touchstone-design.html` 的变更历史。

## 未发布 — 2026-07-03

v0.2.1 之后的积累：基准仓收敛到 **AKDI-SE/touchstone** main（PR #16 合入），并补齐文档与代码的一致性。

- **新增模块** `touchstone/gitcode_check.py`（GitCode 平台适配的可插拔检查闸）。生产代码 3840 → **4445 行**（17 模块）。
- **TF-GRPO 生产化差距**：`docs/learning-loop-design.html` 新增 §3.6，列出论文实现（~185 行）与生产落地之间的差距（奖励质量 / 蒸馏质量 / 收敛性 / 规模 / ground-truth 清理）——明确为建议性、与 `VERIFY_ENABLED`/`AUTONOMY_ENABLED` 无关。
- **workflow 加固**：`learn.yml` 的 `TOUCHSTONE_EXPERIENCE_REF`（经验库从受信任引用读取，防工作树投毒）+ 4 条回归测试。
- **文档对齐（本次）**：README / index / slides / 4+1 的「生产代码行数 / 测试用例数 / 工作流条数 / 功能区行数」全部更新到当前真实值（**4445 行 / 276 用例 / 14 测试文件 / 5 条 workflow**）；补回遗漏的 `gitcode_check` 模块；`gitcode-sync-todo.md` 的基准仓从 1587 改为 AKDI-SE。
- 测试 268 → **276**（+8：经验引用受信读取、TF-GRPO 生产化回归等），全绿、离线、无新增运行时依赖。

## v0.2.1 — 2026-07-02

架构审查后的安全加固与文档对齐（不改冻结契约字段、marker 仅追加、测试只增不削）。

- **确定性影响面兜底（P0，最关键）**：`map_verdict` 除按 category 定级外，新增 `review_provider.deterministic_blast`——直接从改动文件【路径】判定影响面（migration/`*.sql`/`*.proto`/schema → cross_module_contract；auth/crypto/secrets 等路径 → security_surface），与评审侧结果保守取并；命中严重影响面即【无视 LLM 类别】抬到 high → full_suite，并触发（可选的）自动合并否决。此前 blast 仅由 PR-Agent 给的 category 推导，评审侧漏判类别时高危改动会被误走 cheap_only、自动合并下仅凭 CI 绿放行——本条把主设计 §5 承诺的「确定性兜底」真正落地。
- **经验 provenance 到 id 级（P1）**：result marker 追加 `injected_experience_ids`（`learning_loop.active_ids`），使坏经验可【单条】归因与回退（此前仅 `injected_types` 类型级，见数据采集设计 取舍 2）。
- **文档对齐**：4+1 / index / slides 的「生产代码行数」「测试用例数」更新到当前值（3840 行 / 254 用例）；主设计 §5 该遗留项改为「已落地」。
- **loop marker 防伪造（P0）**：loop 状态此前从 PR 的【全部】评论解析——评论任何人都能发，author 可伪造 marker（同轮次+空 history）洗掉震荡/无推进等抗博弈闸。现只解析机器人自己发的评论（`loop.trusted_bodies` 按发帖人过滤，orchestrator 经 `GET /user` 确认身份；无法确认时降级全量并告警）。
- **required 接力检查 fail-closed（P0）**：`_run_relay` 此前把 skipped/neutral 一律算过——author 用 [skip ci]/路径过滤让源 CI 跳过即可绿总闸，自动合并下会放行未经验证的代码。现 required 的 relay 只认 success；非 required 保持宽松（兼容既有流水线）；确需放宽对该检查设 `allow_skipped: true`。
- **第七道闸·基线新鲜度（P0，对照 bors/merge queue）**：`decide_auto_merge` 新增 `base_fresh` 闸——CI 绿是对旧 main 算的就不自动合（两个各自绿的 PR 合在一起可能语义冲突，即 merge skew；`sha` 参数只防 head 再 push、不防基线过期）。live 执行前 `check_base_fresh` 比对 PR base sha 与 base 分支当前 head；过期则调 GitHub update-branch 带上最新 main、CI 重绿后下轮再判；评估失败仅记 None 不误拦，评出过期必拦。长期演进建议改用 GitHub 原生 merge queue（见主设计 §2.6），不自建合并执行器。
- **SEC-\* 规则冻结（P1）**：内置 SEC-001 只作离线兜底、不再新增模式——完整密钥扫描经 checks.yaml 的 relay 挂 gitleaks/semgrep（主设计 §4.7 已加示例行）。
- **成熟工具接缝三件（P1/P2）**：① 变异测试可经 `TOUCHSTONE_MUTATION_CMD` 换用 mutmut/cosmic-ray（外部命令，stdout 末尾数字作击杀率，失败回退内置 AST 变异）；② `AUTONOMY_MERGE_MODE=queue` 经 GraphQL enablePullRequestAutoMerge 走 GitHub 原生 merge queue/auto-merge（不自建合并执行器，direct 保留兜底）；③ 设 `TOUCHSTONE_RDJSON_PATH` 导出 Reviewdog rdjson，行内评论锚定长尾可交 reviewdog。
- **TF-GRPO 加固重施（P0，专项复检）**：审查发现 I1–I4 加固未曾合入 main，而新自学习代码把多仓真值采集接通后，I1（经验 id 不含仓·栈，多仓同类型互相覆盖）已成实际缺陷。现重施于新基线：`_exp_id` 含 `kind:repo:stack:finding_type`（I1）；`_distill_via_llm` 每轮用已蒸出候选重渲染注入 E（I2，真 multi-epoch）；`render_injection` 前 `_resolve_conflicts` 消解同 仓·栈·类型 的 emphasize/suppress 矛盾（I3）；`distill_semantic_advantage` 退化组（组内奖励无差异）跳过、并对【整组】带分对比归纳替代 top-2/bottom-2（I4，贴合论文、降小组取样方差）。
- 测试 251 → 268（+17：确定性 blast 按路径 / 评审漏判仍被路径抬级 / active_ids / 伪造 marker 过滤 / required-relay skipped 拒过 ×2 / base_fresh 闸 / is_base_fresh 纯判定 / 变异输出解析 / 外部变异命令 / rdjson 导出），全绿、离线。

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
