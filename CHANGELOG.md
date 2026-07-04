# Changelog

本文件记录 Touchstone 的发布版本。设计的逐版迭代历史见 `docs/touchstone-design.html` 的变更历史。

## 未发布 — 2026-07-04（工程化加固·第二轮）

第一轮的两个"留作后续"项落地（lint 工具链、渲染层拆分），过程中又抓到并根治一类**被双重掩盖的运行期地雷**。测试 478 → **481**，ruff 全绿。

- **函数内平铺导入地雷（5 处）**：第一轮的包化改造只覆盖了顶层导入，函数体内还残留 5 处 sibling 平铺导入（orchestrator/loop/pr_agent_runner/review_provider 各 1-2 处）——移除 sys.path hack 后这些分支一执行必然 ModuleNotFoundError。它们此前不炸的原因有两层掩盖：①相关分支缺测试覆盖；②`test_integration_mock.py` 把 `touchstone/` 子目录插进了 sys.path，使全量测试里平铺名恰好可解析（单跑其他文件才炸）。本轮全部改为包导入、清除 path 污染，并新增 `tests/test_import_hygiene.py` 三条结构性守卫：静态扫描禁止 sibling 平铺导入（函数内也逃不掉）、禁止测试污染 sys.path、render 再导出兼容性。全部测试文件现可**逐个独立通过**（消除顺序依赖）。
- **渲染层拆分**：`_load_template`/`render_facts`/`render_findings`/`render_report`/`render_summary` 从 orchestrator（592 行）拆至新模块 `touchstone/render.py`；orchestrator 保留再导出，既有 `orchestrator.render_*` 引用路径与测试零改动兼容。上述地雷之一（render_findings 内的 `from llm_budget import`）随拆分根治为顶层包导入。
- **verify 执行环境的 token 落盘缺口（第一轮遗留的过度承诺，自查修复）**：verify_plan/verify_execute 未写 job 级 permissions，继承了 workflow 级 `checks: write`；且 actions/checkout 默认 `persist-credentials: true` 会把 GITHUB_TOKEN 写进 `.git/config`——verify_execute 里执行的 PR 代码读 `.git/config` 即可拿到足以**伪造 touchstone/gate 总闸**的 token（该缺口在拆分前的单 verify job 就存在，"GITHUB_TOKEN 已去掉"只去了 env 未去凭据落盘）。现两 job 权限降为 `contents: read` + checkout `persist-credentials: false`："执行环境零凭据"承诺至此才真正成立。
- **ruff 工具链（克制配置）**：pyproject 增加 `[tool.ruff]`——只选真缺陷规则（F/E7/E9/B/PLE），显式豁免 E701/E702/E731（单行紧凑写法是本仓刻意风格，不做格式化重排以免噪音淹没语义变更）。首跑 31 处命中，修复其中真缺陷：3 处死导入（含 orchestrator 拆分后彻底不用的 `re`）、3 处 `raise ... from e` 补异常因果链（排障时可见原始异常）、1 处 `zip(strict=True)` 把 rollout 同长不变式显式化、2 处无占位 f-string、测试侧重复导入/死变量各 1。CI 新增 lint job。

## 未发布 — 2026-07-04（工程化加固）

外部代码评审驱动的一轮工程卫生与安全边界修复。测试 109 → **478**，覆盖率 52% → **90%**（verify 0% → 81%）。

- **测试资产找回（P0）**：恢复 4ac2aaf 误删的 17 个测试文件（test_verify/test_learning_loop/test_autonomy/test_review_provider/test_checks/test_ghclient/属性测试等）——「命门」verify_change 与「差异化核心」learning_loop 此前处于零测试状态。恢复的属性测试当即抓到一个真回归并已修复：`parse_pr_agent` 对非 dict 输入崩溃（历史提交 9febc2e 声称加过的 isinstance 守卫实际不在代码里，现补齐顶层与条目两级形状守卫）。
- **verify 凭据隔离（P0，设计 §6.6 落地）**：`verify_change` 拆分为 `plan_verification`（持 LLM 凭据，只读接口 + 生成验收测试，**绝不执行 PR 代码**）与 `execute_verification`（真正执行 PR 代码，**不需要任何凭据**）；CLI 增加 `--phase plan|execute|all`，plan 产物 `acceptance-tests.json` 经 artifact 传递。workflow 的 verify job 相应拆为 verify_plan（持密不执行）/ verify_execute（执行零 secret）两个 job——恶意 PR 在执行环境中再无凭据可窃取。原单进程用法（`--phase all`）保留给可信环境，行为不变。新增 `tests/test_verify_phases.py` 固化三条不变式（plan 不执行代码 / plan 落盘回读与单进程判决等价 / execute 不接触凭据）。
- **自测 CI（P0）**：新增 `.github/workflows/ci.yml`——此前 5 个 workflow 没有一个跑本仓自己的 pytest。普通 pull_request 事件（无 secrets）+ Python 3.10/3.13 矩阵 + 覆盖率门槛（pyproject `fail_under = 85`，门槛对自己生效）。
- **打包与导入（P1）**：新增 `pyproject.toml`（`pip install -e .` 可装，`touchstone` CLI 入口）；`verify/` 包化；移除全部模块内 `sys.path.insert` hack，包内 sibling 导入统一为 `from touchstone import x`；运行方式统一为 `python -m touchstone.<module>`（workflow/README/RUNBOOK 已同步），`requirements.txt` 降级为指向 pyproject 的薄引用。
- **仓库卫生（P1）**：移除入库的构建产物——`mutants/`（mutmut 变异快照，约占仓库三分之一体量，其中还残留着已删测试的陈旧副本）与 `.coverage`；`.gitignore` 补全（coverage/pytest/hypothesis/mutants/egg-info/venv/运行产物）。
- **ghclient「唯一入口」承诺兑现（P1）**：`autonomy` 的 5 处裸 urllib 调用（check_base_fresh / update-branch / GraphQL 入队 / merge 执行 / marker 评论）全部迁至 ghclient——自动合并链路此前无任何重试与 Retry-After 处理；orchestrator 清理 urllib 残留 except 与死导入。
- **可排障性（P2）**：learning_loop 三处静默吞异常（LLM 调用回退 / 评审线程解析 / diff 取数）补 stderr 留痕；`gitcode_check` 的 `GITCODE_DIFF_CMD` 执行去 `shell=True`（改 shlex.split，管道需求需显式 `bash -c` 包裹，让 shell 语义成为明示选择）。

## 未发布 — 2026-07-04

2026-06-25 技术方案评审已采纳意见（1–7、10）的落地实现（意见 8、9、11 明确不采纳）。修订设计与数据结构-流程锚定矩阵见 `docs/touchstone-design-revision.html`。

- **范围事实 ScopeFacts（意见 7）**：`contract_check.scope_facts()`——确定性修改范围（每文件增删/hunk 结构）+ 仓级路径规则命中（新增 `.touchstone/scope-rules.yaml`，human_curated）+ 内容指纹。`map_verdict` 接收 scope_facts：影响面推导 = 路径规则命中（确定性）∪ 类别推导（模型补充），敏感路径命中但模型零发现时影响面照样点亮；评审报告新增「确定性事实区」呈现机器实测修改范围。
- **Finding 方向化（意见 1、2）**：模型来源只给 `fix_direction`（方向）+ `fix_reasoning`（依据），PR-Agent 的 improved_code 补丁在归一时降级、不再进任何建议字段；`deterministic_patch` 通道仅确定性来源保留。每条发现附 `done_criteria` 达成判据（deterministic=规则复检 / review=定向复核问题）。`loop.author_actionable` 门槛改为「有 fix_direction」（suggested_fix 作过渡别名仍受理）。
- **收敛清单（意见 3）**：新模块 `touchstone/checklist.py`——逐项销项清单（open/done/waived/split 状态机），置顶评论 task list（人可读）+ 隐藏 JSON marker（权威状态，沿用 trusted_bodies 防篡改）双载体，每轮快照写入 `checklist-round-N.json`。author 经 ```touchstone-ack``` 代码块申报；申报是输入信号，评审方按达成判据复核后才销项（done 需复检不再命中，waived 需理由，split 需链接）。`loop_step` 清单语义：收敛=清单全部销项且无新增可自改发现；无推进=销项率连续为零且无 waived/split 申报（覆盖假修）。
- **轮次台账（意见 10）**：新模块 `touchstone/lineage.py`——记账主体从 PR 号改为内容指纹（文件集 Jaccard≥0.8 且 hunk 结构相似≥0.6 双阈值）。同源的「关旧开新」继承历史轮次消耗与未销项清单（从关闭 PR 的机器人评论重建，不新增存储；已合入的关闭不入台账），余额为零直接升级人工；`rounds-reset` label 人工授权重置。author 伪造历史 marker 不被采信（[bot] 过滤）。
- **版面模板（意见 4）**：评审报告七段版面抽出为 `touchstone/templates/review_report.md`（一等设计资产，代码只填充不定义版面）：①声明与风险横幅 ②总结 ③确定性事实 ④逐条发现（定位·方向·依据·达成判据）⑤收敛清单 ⑥验证结果 ⑦机器 marker。
- **加固**：`parse_diff`/`scope_facts` 对 unidiff 在畸形输入上抛出的库内异常（UnboundLocalError 等）按解析失败处理并显式标注（防静默故障约定不变，此前会打断评审主链）。
- **主设计文档回灌**：修订内容合并入 `docs/touchstone-design.html` 正文——§2.1 四个新概念、§3.2 Finding 字段改造、新增 §3.9 ScopeFacts / §3.10 ConvergenceChecklist / §3.11 RoundLedger / **§3.12 数据结构-流程锚定矩阵**（含内生控制变量单列，新增结构须同步矩阵行）、§4.8 反馈质量与收敛机制接口 + 七段版面定义、§5 一致性校验补记已解决冲突与有意接受的遗留项、§7 变更历史「阶段八」。
- **全流程可视化** `docs/touchstone-visualization.html`（自包含离线，无外部依赖）：8 节点可交互流程图 + 两轮切换，每节点展示真实中间状态（ScopeFacts / 归一前后 Finding / RiskAssessment / RoundLedger / 两轮清单 / loop marker / 七段报告实际正文 / ack 申报与解析）+ 内生控制变量当次取值。数据由真实模块逐环节执行采集（PR-Agent 输出与关闭 PR 检索为注入桩），页面自带验收标准声明。
- **真实数据回放发现并修复一处缺陷**：台账继承的种子清单（round=0）曾使同源新 PR 的第 1 轮被误判「无推进」直接升级（author 尚未获得修改机会）——`checklist.no_progress` 增加第 0 轮闸 + 回归测试。这正是意见 6「用真实数据核对中间状态」的预期收益。
- 测试 444 → **469**（+25：`tests/test_revision_items.py` 覆盖范围事实/字段改造/清单状态机与复核/台账同源与伪造防御/版面七段/种子清单回归），全绿、离线。

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
