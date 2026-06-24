# Touchstone 真跑示例（PR-Agent 路径）

两个**真实公开 PR** 上跑 touchstone 的实际输出。目的：让团队直观看到"它到底产出什么、按什么格式、给谁看"。评审层已复用开源 PR-Agent（自研委员会退役），下面是 PR-Agent 路径的真跑。

## 这两次跑的边界（诚实标注）

- **评审层 = PR-Agent；本次"评审 LLM"由 Claude 经注入入口充当**：真实 PR-Agent 端点（`review_provider._invoke_endpoint`）需在你的环境实现并配置，本次未配置,故评审发现由我（读完真实 diff 后）按 PR-Agent 的 `improve` schema 产出，经 `pr_ctx['pr_agent_output']` 注入。这正是该注入入口的用途；接上真实 PR-Agent 后，这一环换成它的 LLM，发现的**形状不变**（同样 file/line/category/severity），仅来源不同。
- **diff 是真从 GitHub 取的**：经 `git clone` + `fetch` 算出真实 unified diff（沙箱无 token，REST API 未认证配额也已耗尽，故走 git 而非 API；你的环境有 token 时 `get_pr_diff` 走 API 即可）。
- **确定性机器是真跑的**：`parse_diff` / `check_untested_code`（契约核对）/ `normalize` / `map_verdict`（按 category 定风险等级，**不做共识**）/ 反馈循环 / `change_class` / `decide_auto_merge` / `anchor_inline`，全是仓里代码真实执行。
- **示例 1 的风险等级是 `NormalizationMap` 校准后的结果**：PR-Agent 的 `possible issue` 默认映射到 `correctness_suspect`（弱信号、不升 high），故落 `mid`；`possible bug`/`critical bug`/`security` 仍升 `high`（见示例 2）。映射写在 `.touchstone/pr-agent.yaml`，可继续按真跑调。
- **verify（质量门禁层）未跑**：高风险时路由*建议* `targeted_tests`，但真跑它需要 Java 构建 + 异模型出独立验收测试，示例环境没有；这次只到"建议触发"。
- **未回贴**：dry-run（无写权限 token，也不应往他人公开 PR 贴 AI 评论）。touchstone **永不拦截合入**：review 一律 `event=COMMENT`，check 一律 `neutral`，与人审并行。

---

## 示例 1 · 重构 PR —— [spring-ai-ascend#314](https://github.com/chaosxingxc-orion/spring-ai-ascend/pull/314)

`refactor(openjiuwen): extract memory runtime rail`

**改动**：把内部类 `MemoryRuntimeRail` 抽成顶层类、瘦身 `OpenJiuwenAgentRuntimeHandler`、同步测试与文档。6 文件 +257/-232。

**touchstone 判定**

| 项 | 值 |
|---|---|
| 风险等级 | **MID**（`correctness_suspect` 不升 high；详见边界第 4 条） |
| 建议动作 | `read`（人过目） |
| 验证建议 | `cheap_only` |
| 反馈循环 | `continue`（待 author 自改 2 项） |
| 变更分类 | `mid\|mixed\|convention,correctness_suspect\|none` |
| 自治决策 | `disabled`（开关默认关 → 回落到人） |

**发现 2 条**

> `PRA-POSSIBLE_ISSUE` [warn] conf=0.70 · pr-agent:suggestion · `…/openjiuwen/MemoryRuntimeRail.java:25`
> 抽出后的 `MemoryRuntimeRail` 由 `public static` 嵌套类变为**包级私有**顶层类。若该类型曾作为对外 API 被外部包引用/继承，则为破坏性收窄；若确为内部兼容 rail，建议在 PR 说明里点明意图。
> 建议：确认无外部消费者依赖；若属公开库 API，走 `@Deprecated` 转发或 changelog 标 breaking，而非静默收窄。

> `PRA-MAINTAINABILITY` [warn] conf=0.70 · pr-agent:suggestion · `…/openjiuwen/MemoryRuntimeRail.java:47`
> 4 段几乎相同的 `LOGGER.warn(... tenantId/sessionId/taskId/errorClass/message ...)` 样板，建议抽一个 `warnMemory(stage, error)` 公共方法。

**值得注意**：这是个高质量重构——构造器注入 + `Objects.requireNonNull`、SLF4J 而非 printStackTrace、测试与文档全同步，所以那批 Java/Spring 规则一条没踩、没有硬凑问题。两条都是"看一眼"级别，不是 bug——这也正是把 `possible issue` 从 high 软化到 mid 的理由：行为不变的纯重构不该被判 high。

---

## 示例 2 · bug-fix PR —— spring-ai-ascend `2ba12b7`

`fix(financial): paginate 天天基金 NAV (pageSize capped at 20)`

**改动**：把 NAV 历史接口从单页改成分页拉取（接口对 pageSize 有 20 上限）。`EastMoneyFundDataSource.java` +33/-18，**未带测试**。

**touchstone 判定**

| 项 | 值 |
|---|---|
| 风险等级 | **HIGH**（含 `correctness` 发现 → 升 high） |
| 建议动作 | `read+arbitrate` |
| 验证建议 | `targeted_tests` |
| 反馈循环 | `continue`（待 author 自改 1 项） |
| 变更分类 | `high\|code\|correctness,weak_test\|none` |

**发现 2 条**

> `PRA-POSSIBLE_BUG` [warn] conf=0.70 · pr-agent:suggestion · `…/eastmoney/EastMoneyFundDataSource.java:106`
> 末页判定 `if (added < PAGE) break;` 用的是**过滤后计数**（只数 `LJJZ > 0` 的行）。若某**整页**含无效行（LJJZ 缺失/≤0），`added` 会 `< 20` 被误判末页提前退出，**静默漏掉后续页的 NAV**。
> 建议：用原始返回条数判断末页（`list.size() < PAGE` 才 break），过滤（`v > 0`）只用于累积、不用于翻页终止。

> `TEST-001` [warn] conf=0.90 · contract-check · 改动包含代码文件，但 diff 中无任何测试文件改动（疑似缺测试）。

**值得注意**：`PRA-POSSIBLE_BUG` 是**作者在这次修复里新引入的真实缺陷**——把过滤计数当翻页终止条件，遇含无效行的整页确实会漏数据。PR-Agent 把这类逻辑错标 `possible bug`，归一为 `correctness` → 升 `high`、路由 `targeted_tests`，与示例 1 的纯重构形成对照：**软化的是含糊的 `possible issue`，真缺陷信号照常升 high**。`TEST-001` 来自无需 manifest 的纯 diff 事实检查（改了代码却零测试）。两条都不是硬凑。

---

## 一份发现如何喂两个消费者

同一份归一后的发现，按消费者渲染两种形状：

- **人类评审（并行人审）**：顶层摘要评论（散文 advisory）+ 底部状态 check。读、判、仲裁。
- **AI author agent（反馈循环输入）**：内联评论（锚在 `file:line`、带 `suggested_fix` + 机读标记 `<!-- touchstone-finding -->`）+ `touchstone-findings.json` + 闭环指令（`continue` → 程序化自改后重提）。

> 内联锚定：发现指向被删代码/超界行时，`anchor_inline` 就近锚到同文件最近新增行（注明原行）或降级只进摘要——避免 GitHub 因评论行不在 diff 内整条 review 被拒。PR 级事实（如 `TEST-001` 无具体行）只进摘要、不内联。

## 怎么自己跑一遍

见仓库根 `RUNBOOK.md`：`preflight → dry-run（只读）→ --post（回贴 advisory）`。touchstone 本身**不需要 LLM_***（评审走 PR-Agent，端点配置见 `.touchstone/pr-agent.yaml` 与 `review_provider._invoke_endpoint`）；真跑需在你的环境接上真实 PR-Agent 端点 + GitHub token。
