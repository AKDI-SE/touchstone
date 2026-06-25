# RUNBOOK —— 真跑一次（#2）

沙箱没有实时的 GitHub token 与 LLM API 凭据，也没有目标仓库，所以"真跑"在你的环境做。本手册给确切命令。
顺序：**预检 → dry-run → --post → （高风险才）verify → （以后）影子自治 → 真自治**。
每步都可单独停下，前一步绿了再进下一步。

## 0. 前置
```bash
pip install -r requirements.txt          # pyyaml / pytest / coverage
python -m pytest tests/ -q               # 应全绿（离线，无需网络/LLM）
```
环境变量（touchstone 本身不再需要 LLM_*：评审复用 PR-Agent，端点配置见 .touchstone/pr-agent.yaml）：
```bash
export GITHUB_TOKEN=...                   # repo 读 + （--post 时）评论/check 写
# 评审引擎 PR-Agent 的端点在 PR-Agent 侧/_invoke_endpoint 配置（不经下面这些变量）。
# 下面 LLM_* 仅供（可选）verify 子系统用：
export LLM_BASE_URL=...                   # OpenAI 兼容 /chat/completions 的 base（verify 用）
export LLM_API_KEY=...                     # （verify 用）
export LLM_TEST_MODEL=...                  # verify 独立验收测试模型，建议异于 author 模型
# 内部 GitHub（如非 github.com）：
# export GITHUB_API_URL=https://your.ghe/api/v3
# export GITHUB_GRAPHQL_URL=https://your.ghe/api/graphql
```

## 1. 预检（一键体检）
```bash
python -m touchstone.preflight             # 配置 + GitHub/LLM/GraphQL 连通性，逐项 ✓/✗
python -m touchstone.preflight --no-net    # 只检配置（不打网络）
```
必需项有 ✗ 就先修；连通性 ✗ 多半是代理/端点配置问题（见 §5）。

## 2. Dry-run（只读，不动 PR）
```bash
python -m touchstone.run --repo OWNER/NAME --pr 123
```
经 API 取**完整 diff** + 浅 clone，跑 PR-Agent 评审归一 → 契约核对 → 裁决映射 → 反馈循环，
打印风险等级/发现/闭环决策。**不回贴**。先在一个真实 PR 上看输出是否合理。

## 3. 真跑（回贴 advisory）
```bash
python -m touchstone.run --repo OWNER/NAME --pr 123 --post
```
回贴：摘要评论（含隐藏 result marker）+ 尽力内联评论（每条带 `touchstone-finding` 标记）
+ 中性 check run（**永不 failure**，advisory）。绝不 REQUEST_CHANGES、绝不合并。
对你不拥有的外部 PR，别加 `--post`。

## 4. 高风险才跑的客观验证（质量门禁）
裁决映射把 `verification_decision` 置为 `targeted_tests` 时（高风险），才需要 verify。
CI 里由 `touchstone.yml` 的 verify job 触发；本地手动：
```bash
export GITHUB_EVENT_PATH=...              # PR 事件 JSON（含 pull_request.number/head.sha）
python verify/verify_change.py            # 异模型独立验收测试 + 充分性阶梯（改动行覆盖/哨兵/变异）
```
Java 仓需 `mvn` 可用（JaCoCo 出改动行覆盖、PIT 出变异）；Python 用 coverage.py + 内置变异。

## 5. 网络注记（自托管 runner / 经代理访问公网）
- **代理**：自托管 runner 若经代理访问公网，确保 `*_PROXY`/`NO_PROXY` 配置正确，否则 407/挂起；公有 runner 通常直连。
- **pip 加速**：可选用私有或就近的 PyPI 镜像。
- **CI runner**：`touchstone.yml` 各 job 注释处已标网络相关替换点（代理、可选镜像）。
- **GraphQL**：finding 级采纳（calibrate）走 GraphQL，内部 GitHub 设 `GITHUB_GRAPHQL_URL`。

## 6. Actions 闭环（CI 自动跑，默认只到 advisory）
- `touchstone.yml`：PR 触发 → touchstone(advisory) + verify(高风险) 两 job，**不拦不合**。
- `calibrate.yml` / `govern.yml`：定时。govern 跑 calibrate→govern→`autonomy --graduate`，
  发布并提交 `.touchstone/graduated-classes.json`（**经验层**，仅 `vars.AUTONOMY_ENABLED=true` 时提交）。
- `auto_merge` job：**默认关**（`vars.AUTONOMY_ENABLED != 'true'` 直接不跑）。

## 7. 启用自治（务必按序，先影子）

> **前提（务必先建立习惯）：人核准的验收规格。**
> 走独立验收测试验证的 PR（高风险/功能型），自治的「可信绿」**只认人核准的验收规格** `.touchstone/acceptance.yaml`（`human_curated`）。author 在 `.touchstone/pr.yaml` 里写的 `acceptance_criteria` **仅作建议**（`author_proposed`），其独立验收测试绿**不足以**支撑自动放行——`floor_passed` 会拒掉，这类 PR 一律回落到人（安全，但不自治）。
> 含义：**想让正确性敏感的改动也能自治，团队必须先养成「人写/人核准验收规格」的习惯**（模板见 `.touchstone/acceptance.yaml.example`，每条写成一句可判定的验收点）。这是"人被前移"的角色——把精力从"逐行读 PR"挪到"事前定义什么算对"。纯重构/低风险 PR 不需要（走回归或 cheap_only，无需人写规格）。

1. 先让 touchstone 在真实 PR 上 advisory 跑一两周，攒校准数据。
2. 看 `calibration-report.md`：风险等级是否 high≫low、有无噪声 agent/rule、finding 级采纳率。
3. **影子模式**：设 `vars.AUTONOMY_ENABLED=true` 且 `vars.AUTONOMY_SHADOW=true`。
   此时 `decide_auto_merge` 只记"本会合并吗"、**不真合**；对照人审看决策对不对。
4. 影子稳了再 `vars.AUTONOMY_SHADOW=false` 真合——且只有**达标的变更分类**(govern 发布)
   且**各闸全过**(质量门禁绿/无阻断否决/闭环收敛/契约净/未熔断/类已达标/总开关)才合。
   注：「质量门禁绿」对独立验收测试路径=**可信绿**（须 `human_curated` 规格）；author 自报规格的绿在此不算数。
5. 熔断：govern 检测到回滚率超阈会写 `autonomy-state.json`（tripped），据此关 `AUTONOMY_ENABLED`。
6. 强烈建议：分支保护把 verify 设为 required check（Phase 1 合入闸），自治才有确定性门禁保障。

## 8. 示范：Touchstone 审自身 PR（dogfooding，证明门禁真能拦）

> 本仓的 PR #2（让确定性门禁真正生效那次修复）就是用 Touchstone 审 Touchstone 自己——
> 结果总闸先判 **failure**，逼出修复后再判 **success**。这条闭环本身就是「试金石」生效的活证据。

发生了什么：
1. 初版 PR 推上去 → `touchstone/gate = failure`：内置 SEC-001 密钥扫描把
   `tests/test_contract.py` 里**测扫描器用的密钥夹具**（`ghp_…`/`AIza…`/PEM）当真实泄密拦了。
2. 诊断：扫描器工作正常（确实检出了），但**不该把测试夹具当泄密来阻断**——
   违背扫描器自己声明的「确定性扫描宁可漏不误拦」。
3. 修复：`check_secrets` 跳过 `_is_test(path)` 的文件（真实泄密仍由外部 SAST 兜底）+ 1 条锁定测试。
4. 重跑 → `touchstone/gate = success`（`✓ touchstone-rules：22 条建议、无拦截级`）。

含义：门禁**拦下了「看着对、实则误拦」的提交**（似是而非的反面），逼出正确修复后再放行——
正是系统的立身之本。接入后，拿一个**故意带缺陷**的 PR 跑一遍，看总闸是否如预期 failure，
是验证你这套 `checks.yaml` + `standards.yaml` 真生效的最快办法。

## 排错
- touchstone 不再需要 LLM_*（评审走 PR-Agent）。`缺少 LLM_BASE_URL/...` 仅可能来自（可选）verify——启用 verify 时再设这些变量。
- 内联评论降级（行不在 diff 内）属正常，不影响摘要与 marker。
- `autonomy` 打印 `no-op（默认不放行）`：缺 touchstone-findings.json 或总开关没开——预期行为。
