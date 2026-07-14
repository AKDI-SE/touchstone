# Touchstone 故障排查 runbook（运维版）

> 面向对象：线上评审出异常时**定位并处置**的运维人员。按「症状 → 诊断 → 处置」组织。
> 与其它文档的分工：`docs/DEPLOYMENT.md` 是**部署前**一次性把环境配对；本文是**运行中**出故障时的排障手册；`SECURITY.md` 定义安全边界（本文的欺骗面条目引用它）。
> 锚点：v1.0.0（含 P0 可观测/配置强校验 + P1 doctor）。

## 0. 先跑这三样（多数故障能一步定位）

| 工具 | 命令 | 告诉你什么 |
|---|---|---|
| doctor | `touchstone doctor` | 配置齐否 / 端点通否 / 评审引擎能否产出裁决（红绿 + 退出码） |
| metrics 聚合 | `python -m touchstone.metrics touchstone-metrics.json` | 评审可信率、静默故障轮数、engine_status 分布、放行率 |
| 交互日志 | 看 artifact `pr-agent-interaction.log` | 本轮 LLM 真实请求/响应（是否真调了、错在哪） |

关键判据：metrics 的 `review_reliable_rate < 0.8`、`silent_failure_rounds > 0`、`engine_status` 非 `ok` 占比升高，都是排查信号。

---

## 1. LLM 静默故障（评审静默吞没）

**症状**：PR 评审给 0 条 AI 建议、看着"审过但没意见"；或可信率骤降，却没有任何报错。

**诊断**：metrics 中本轮 `review_reliable=false` 且 `engine_status == ok`——这正是静默故障的机器判据（聚合里计入 `silent_failure_rounds`：引擎自报正常却判不可信）。注意 `llm_failed`/`provider_failed` 是引擎**已检测到**的大声报错、不算静默（见 §3/§4/§5）。静默故障通常伴随 `ai_raw_count=0`。翻 `pr-agent-interaction.log` 确认 LLM 是否真被调用、返回是否为空/畸形。

**处置**：静默故障轮 `review_reliable=false` 时反馈循环**不会收敛**（不当绿灯，兜底见 loop/checklist）——先确认放行没被误触发。再按下面 §2/§3/§4 定位是裁空、超窗还是超时。把 `review_reliable_rate` 接监控告警（阈值 0.8）。历史上这类只能靠人追问才发现，现已由 metrics 主动可见。

## 2. diff 被裁空 → 0 建议（PR#44 类）

**症状**：较大的 PR 评审 0 建议，且 diff 像被清空。

**诊断**：`TOUCHSTONE_LLM_CONTEXT_TOKENS` 过小 → diff 被裁空喂给 LLM。`touchstone doctor` / `preflight` 会对过小值直接 WARN。

**处置**：按模型卡把 context tokens 调到模型真实上下文窗口；核对是否误把**输出上限**填成了上下文窗口。

## 3. 大 PR 被端点 400 拒（PR#47 类）

**症状**：评审轮报 HTTP 400 / 子进程失败，`engine_status` 为 `llm_failed`/`provider_failed`。

**诊断**：`TOUCHSTONE_LLM_CONTEXT_TOKENS` 设得**大于**模型真实窗口 → 输入超窗被端点拒。

**处置**：按模型真实窗口设 context tokens。对确实过大的 PR，设 `TOUCHSTONE_MAX_DIFF_LINES` 触发 SIZE-001（`engine_status=skipped_large_diff`），让系统输出"请拆分 PR"的 advisory 而非硬失败。

## 4. 慢模型子进程超时（PR#48 glm 类）

**症状**：本轮判"不可信"，或 pr-agent 子进程超时。

**诊断**：`TOUCHSTONE_PRAGENT_TIMEOUT` 偏小 + 慢模型（如 glm 单轮 360s+）。`preflight`/`doctor` 对 `< 180s` 直接 WARN。交互日志看是否卡在单次 LLM 调用。

**处置**：调大 `TOUCHSTONE_PRAGENT_TIMEOUT`（建议 ≥ 360，慢模型 3600）与 `TOUCHSTONE_LLM_CALL_TIMEOUT`。

## 5. 评审引擎降级（no_engine / provider_failed）

**症状**：评审只剩确定性核对（契约 + 栈规则）、没有 AI 建议，PR 评审评论里带**降级横幅**。

**诊断**：`engine_status=no_engine`（PR-Agent 未装）或 `provider_failed`（端点未配/不通）。**注意这是"降级非静默"**——有横幅、评审仍出确定性结论，不是故障 §1。

**处置**：把 PR-Agent 装到独立 venv（`TOUCHSTONE_PRAGENT_CMD` 指向它）、在 `.touchstone/pr-agent.yaml` 配好端点。降级期间确定性核对仍有效，可接受临时运行。

## 6. author 自证销项企图闭环放行（欺骗面）

**症状**：PR 意见"全部销项"却没有真实代码修改，就触发了收敛 / 自动放行。

**诊断**：metrics `unverified_claims > 0` 却仍收敛，即为异常。销项分 `VERIFIED`（机器复核）与 `CLAIMED`（author 自证 waived/split）；后者绝不该触发收敛/放行。

**处置**：确认 VERIFIED/CLAIMED 拆分生效——存在未核准的 CLAIMED 时 loop 回落 continue/escalate、不收敛。任何绕过此边界的路径按**高危漏洞**处理（`SECURITY.md` 边界 1，走披露流程）。

## 7. 伪造 loop marker 洗掉抗博弈闸

**症状**：明显在震荡或"只加不减"无推进的 PR，却一直 `continue` 不升级。

**诊断**：loop marker 只认**机器人自己**发的评论（`trusted_bodies` 过滤）；author 可能伪造"同轮次 + 空 history"的 marker 洗掉震荡/无推进闸。检查 bot_login 过滤是否生效。

**处置**：确认 marker 过滤按 bot 账号（`[bot]` 后缀）严格生效；无推进/震荡必须升级（无推进升级已由 `test_loop_escalate_on_no_progress_legacy` 守住，见 `docs/mutation-baseline.md`）。

## 8. 凭据泄露 / 门禁状态伪造（verify_execute）

**症状**：执行不可信 PR 代码的 job 里出现 secret，或 PR 代码能写 checks/伪造门禁状态。

**诊断**：检查 workflow `verify_execute` job 权限是否降为 `contents: read`、是否零凭据（无 secret、`.git/config` 无 token）。

**处置**：恢复零凭据隔离（`SECURITY.md` 边界 2）。任何让 PR 代码窃取凭据或伪造门禁状态的路径按高危漏洞处理。

## 9. 连接 407 / 挂起（代理）

**症状**：GitHub / LLM 端点连接 407 或长时间卡住。

**诊断**：经代理访问外网但 `HTTP_PROXY`/`HTTPS_PROXY`/`NO_PROXY` 未配好。`preflight` 检测到代理变量会提示核对。

**处置**：正确配置 `*_PROXY` / `NO_PROXY`。

## 10. GHE 上 API 404

**症状**：企业版 GitHub 上取 PR / 回贴报 404。

**诊断**：用了公有 github 的 API 地址。

**处置**：设 `GITHUB_API_URL=https://<host>/api/v3`、`GITHUB_GRAPHQL_URL=https://<host>/api/graphql`。

## 11. 跑完变异测试后单元测试"假失败"（开发/CI 排障）

**症状**：跑过 `mutmut run` 或 `python tests/mutation_audit.py` 后，一批测试（尤其 SEC-001 等）莫名失败，但 `git status` 显示源码干净、`git diff` 为空。

**诊断**：变异测试会**就地变异源码再还原**；过程中子进程把**变异版**编进了 `__pycache__/*.pyc`，还原 `.py` 后陈旧 `.pyc` 仍被加载，导致行为像被变异过。git 看不到，因为 `.pyc` 与 `mutants/` 都被 gitignore。

**处置**：清缓存后重跑——
```bash
find . -name __pycache__ -type d -exec rm -rf {} +
rm -rf mutants mutmut-stats.json .mutmut-cache .hypothesis
python -m pytest -q
```

---

## 附：故障 → 主要信号速查

| 故障 | engine_status | metrics 信号 | 一线处置 |
|---|---|---|---|
| 静默故障(§1) | ok | review_reliable=false（通常 ai_raw_count=0） | 查端点/超时，不当绿灯 |
| 裁空(§2) | ok | ai_raw_count=0 | 调大 context tokens |
| 超窗(§3) | llm_failed/provider_failed | — | 按真实窗口设 tokens |
| 超时(§4) | llm_failed | review_reliable=false | 调大 PRAGENT/CALL 超时 |
| 降级(§5) | no_engine/provider_failed | findings_ai=0 | 装/配 PR-Agent（有横幅，非静默） |
| 自证放行(§6) | — | unverified_claims>0 却收敛 | 查 VERIFIED/CLAIMED 拆分 |

## 变更历史

| 日期 | 变更内容 | 原因 |
|---|---|---|
| 2026-07-13 | 首版故障排查 runbook | 把散在 CHANGELOG 的踩坑（裁空/超窗/超时/静默故障/欺骗面/变异测试缓存）集中为「症状→诊断→处置」手册，接上 doctor/metrics/交互日志诊断抓手 |
