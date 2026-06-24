# 初始化任务 0 · 上 GitHub 并开始自我狗粮

> 这是开工前的第一个初始化任务：把仓库放上 GitHub，配好让 Touchstone 在本仓 PR 上自动评审（advisory），形成"自己评审自己"的狗粮回路。**先做到纯顾问式打通**，再逐步打开 verify 与自治。
> 关联：人分工见 [`dev-plan-2people.md`](dev-plan-2people.md)；大模型须遵守仓库根 `CLAUDE.md`。

负责人：______　预计：半天　完成判据见文末。

---

## 1. 推仓库
- 新建 GitHub 仓库（私有/公开均可），把整个仓库 push 上去；`.github/workflows/` 一并上去即生效。
- `requirements.txt` 已就绪（pyyaml / requests / unidiff / openai / pytest / coverage）。
- 推之前本地自检一次：`python -m touchstone.preflight`（逐项 ✓/✗ 检查配置与 GitHub/LLM 连通性，见 `RUNBOOK.md`）。

## 2. 配 Secrets
`Settings → Secrets and variables → Actions → Secrets`：

| Secret | 何时需要 | 说明 |
|---|---|---|
| `LLM_BASE_URL` · `LLM_API_KEY` · `LLM_MODEL` | 必填 | touchstone 评审用的 LLM；模型应**不弱于** author 用的 |
| `LLM_TEST_MODEL` | 仅开 verify 时 | 独立验收测试作者，须异于 touchstone |
| `GITHUB_TOKEN` | 不用建 | Actions 自带；权限见 §4 |

## 3. 配 Variables（功能开关 —— 起步全默认 = 纯顾问式）
同页 `Variables` 标签：

| Variable | 起步值 | 作用 |
|---|---|---|
| `VERIFY_ENABLED` | 不设（默认关） | 设 `true` 才跑 verify 深检（需 `LLM_TEST_MODEL` + `acceptance.yaml`） |
| `AUTONOMY_ENABLED` | 不设（默认关） | 自动合并；**起步别开**，等校准数据够再说 |

> 起步什么开关都不设：touchstone 只产出评审意见 + 发一个总闸，不跑验证、不自动合 —— 最稳的狗粮起点。

## 4. 放开 Actions 写权限（关键）
`Settings → Actions → General → Workflow permissions`：
- 选 **"Read and write permissions"** —— 否则 `GITHUB_TOKEN` 默认只读，touchstone 发不出 check run 和 PR 评论。
- 将来开 auto_merge 时再勾 "Allow GitHub Actions to create and approve pull requests"。

## 5. PR-Agent（评审引擎）—— 起步可暂缓
当前 workflow 只 `pip install -r requirements.txt`，**未安装 PR-Agent**。直接跑时 `review_pr` 会**优雅降级：只跑确定性的契约核对 + 栈规则，不出 PR-Agent 的评审建议**（不报错，只是评审广度少一块）。
- **建议**：第一阶段就用"契约 + 栈规则"狗粮（零额外配置、稳）。
- 接 PR-Agent 是下一步，对应 `dev-plan-2people.md` 的 **A-P0-1**：在 touchstone job 加一步装 pr-agent（独立 venv），让 `pr_agent_runner` 调到它。

## 6. 分支保护（想让总闸真拦再设）
`Settings → Branches`（或 Rulesets）给 `main` 加规则 → **Require status checks to pass** → 选 **`touchstone/gate`**（对外那一个总闸）。
- 纯顾问式狗粮可先不设（gate 是中性建议，不挡合并）。
- 要让它成为"必须通过才能合"的硬闸时再加；开了 verify 后建议把它设为 required。

## 7. 跑起来（狗粮回路）
1. 开一个对 `main` 的 PR —— **用本仓分支，不要用 fork**（fork PR 的 token 只读，GitHub 安全限制，发不了 check；自己狗粮用同仓分支没问题）。
2. `touchstone.yml` 在 `pull_request`（opened/synchronize/reopened）触发 → touchstone 评审 → gate 发那**一个** `touchstone/gate` 总闸 + 行内/总结评论。
3. 照常 review、合并。
4. 定时任务自动跑：`calibrate.yml`（每周一）从已合 PR 重建"与人审吻合度/噪声"报告；`govern.yml`（随后）固化复发发现/校准熔断。

## 8. 内部 GitHub（GHE）/ 自托管 runner（按需）
- 用 GitHub Enterprise：设 `GITHUB_API_URL` / `GITHUB_GRAPHQL_URL`（见 `touchstone.yml` 注记与 `RUNBOOK.md`）。
- 自托管 runner 经代理访问公网或 LLM：按需配 `*_PROXY` / `NO_PROXY`，可选私有/就近 PyPI 镜像加速 `pip install`。

---

## 完成判据
- [ ] 仓库已推上 GitHub，四条 workflow 在 Actions 页可见。
- [ ] Secrets（LLM 三件）+ Variables（起步全默认）已配；`Read and write permissions` 已开。
- [ ] 开一个测试 PR，`touchstone.yml` 跑绿，PR 上出现 `touchstone/gate` 总闸 + 评审评论。
- [ ] `python -m touchstone.preflight` 本地全 ✓。
- [ ] （可选）`main` 分支保护已要求 `touchstone/gate`。

完成后即进入 `dev-plan-2people.md` 的 M1：两人各自的 P0。
