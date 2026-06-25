# Touchstone

**给 AI 时代的代码合入装一把试金石。** Touchstone 在 GitHub PR 上做评审,默认只给建议;是否准予合入,交给一道客观、可复现、可审计的质量门禁,而不是 AI 的判断。

## 它是什么 / 它不是什么

**它是**:一个挂在 PR 上的评审与门禁系统。它把现成的 AI 评审(复用 [PR-Agent](https://github.com/qodo-ai/pr-agent))接进来,补上 PR-Agent 没有的那部分——发现归一、风险分流、确定性契约核对、栈专项规则、单一总闸,以及可选的独立验证与渐进自治。

**它不是**:一个"让 AI 替你点合并"的工具。自动合并是**可选、默认关闭**的能力;打开后,它的放行边界也被牢牢限制在"机器能验证的范围"之内。默认形态下,合入由人点,Touchstone 只提供建议与一道硬门禁。

## 为什么需要它 —— 核心理念

AI 写的代码越来越多,但 AI 评审有两个绕不开的弱点:

1. **似是而非的错误。** 大模型会给出读起来很合理、实则错误的判断。这类错误恰恰最难靠"再看一眼"发现。
2. **同源盲点。** 用来评审的模型,往往和写这段代码的模型是同一类。写错的地方,复审多半也看不出来——人审之所以可靠,部分正因为人和 AI 不同源。

结论很简单:**判断可以来自 AI,但"准予合入"这个决定不能押在判断上。** Touchstone 把准入权交给客观、可复现、可审计的机制——测试是否真的通过、确定性规则是否被触犯——而不是任何一段自然语言意见。

一条贯穿全系统的红线:**自主边界 = 验证边界。** Touchstone 能自动做到哪一步,取决于它能客观验证到哪一步;验证不到的,就只建议、由人决定。即使 AI 判错,只要它不进入前两类(正确性、红线契约)的准入裁决,它的错误也越不过质量门禁。

## 三类判定

Touchstone 把一个 PR 上要回答的问题分成三类,各用各的依据:

| 判定 | 问的是 | 靠什么定 | 能否阻断合入 |
|---|---|---|---|
| **正确性** | 改动真的对吗 | 机器:独立生成验收测试并真实执行(verify) | 能(开启 verify 时) |
| **红线契约** | 是否触犯硬性约定 | 机器:确定性规则与契约核对(无 LLM) | 能 |
| **质量** | 写得好不好 | Touchstone 的判断(复用 PR-Agent) | **不能,仅建议** |

只有前两类(可被机器客观裁定的)才有资格阻断合入;第三类质量判断永远只是建议。

## 一个 PR 会发生什么(默认形态)

1. PR 打开或更新,`touchstone.yml` 触发。
2. Touchstone 调用 PR-Agent 做评审,把它的输出**归一**成内部统一的 `Finding`,并据此做**风险分流**(`RiskAssessment`:风险档 + 影响面 → 是否需要验证、需要哪一档)。
3. 跑**确定性核对**:契约一致性(`contract_check`)与栈专项规则(`stack_rules`),这些不依赖 LLM,命中即为红线。
4. 把评审建议与发现**回贴**到 PR(advisory)。
5. 所有"必须通过才能合"的检查折进**单一总闸** `touchstone/gate`;它绿,才满足分支保护。是否点合并,由人决定。

开启可选能力后,在第 3 步与第 5 步之间会多出独立验证(verify),在第 5 步之后可由 autonomy 在达标类上替人点合并——两者默认都关。

## 默认形态与可选能力

- **评审(默认开)** —— 顾问式,只产建议与发现,不阻断。
- **确定性门禁(默认开)** —— 契约与栈规则 + SEC-001 密钥扫描,机器可检。`severity=block_candidate` 的规则(CTR-001/SPR-TX-001/JAVA-EQ-001/SEC-001)命中即阻断;`warn` 规则经校准固化(`enforced`)后升级为阻断。SEC-002(注入)依赖外部 SAST。
- **独立验证 verify(默认关)** —— 用**异于评审的模型**、盲于实现地生成验收测试,在 git worktree 上对改动前/改动后两版分别执行,要求"改后通过 ∧ 改前失败 ∧ 覆盖/变异达标 ∧ 回归绿"才判正确。是 Touchstone 的核心,分量也最重。
- **渐进自治 autonomy(默认关)** —— 仅对经校准证明"放行靠谱"的变更类,才开自动合并,且有熔断保障。自主边界严格等于验证边界。
- **学习回路 learning_loop(离线,Touchstone 的差异化核心)** —— 评审引擎复用的是开源 PR-Agent,所以真正属于 Touchstone 的创造,是这条让评审越用越准的回路:统计"人最终采纳了哪些发现、忽略了哪些",把规律写成自然语言经验,加进给 PR-Agent 的提示词里。它分两档:当前实际跑的是**计数式做法**(不训练模型、不改权重,只统计采纳率,已实现);更强的 **TF-GRPO**(取自 arXiv 2510.08191)**也已实现、离线可测**(机制见 `docs/learning-loop-design.html` 第 3 节;生产需一个参数固定的旗舰模型端点)。整条回路都离线跑、和评审分开(它出问题不影响评审);经验只用来调建议,绝不参与合入判定;新经验还要先用真实 PR 做 shadow A/B 对照,达标了才正式启用。

无论开关如何,所有检查都**聚合成一道总闸**对外暴露,分支保护只认这一个状态。

## 复用而非重造

Touchstone **不自己实现通用代码评审**——那部分复用成熟的 PR-Agent(跑在独立 venv,经子进程调用,不进本仓依赖)。Touchstone 只做 PR-Agent 没有的事:把不同来源的评审**归一**、把意见**映射**成风险档、确定性的**契约/栈规则**核对、**单一总闸**、**独立验证**、**自治**、以及**校准与学习**。其中**让评审越用越准的学习回路(TF-GRPO)是 Touchstone 最有差异化价值的一块**——评审引擎本身是复用的,自我改进才是 Touchstone 自己的创造(机制设计见 `docs/learning-loop-design.html` 第 3 节)。PR-Agent 没装时,评审优雅降级为只跑契约核对 + 栈规则。

## 快速开始

```bash
# 1. 依赖
pip install -r requirements.txt

# 2. 起步自检(配置 / 端点 / 权限)
python -m touchstone.preflight

# 3. 对任意 PR 跑一次评审(默认 dry-run,只打印不回贴)
python -m touchstone.run --repo owner/name --pr 314

# 4. 真回贴评论/check
python -m touchstone.run --repo owner/name --pr 314 --post
```

可选参数:`--repo-dir`(给定已 checkout 的 PR head,跳过自动 clone)、`--standards`(指定 `standards.yaml` 路径)。

> 所有测试与确定性核对**离线可跑**,无需 LLM、网络或外部服务。只有 PR-Agent 评审与可选的 verify 才需要 LLM 端点。

## 配置(`.touchstone/`,随仓库版本化)

| 文件 | 作用 |
|---|---|
| `standards.yaml` | **单一事实源规范**:同一份既喂 author 生成端,也喂评审端,两端不漂移 |
| `pr.yaml` | 提交契约模板:author 每个 PR 按此生成 `SubmissionContract` |
| `checks.yaml` | 可插拔检查闸配置:哪些检查折进总闸、哪些必须通过 |
| `pr-agent.yaml` | PR-Agent 原始输出 → 内部 `Finding` 的归一映射 |
| `best_practices.md` | 主观规则库,作为喂 PR-Agent 评审侧的 prompt 素材 |
| `acceptance.yaml.example` | 人核准验收规格样例(verify 用,可选) |

## GitHub 集成

三条工作流:

- `touchstone.yml` —— PR 触发:评审 + 高风险时的 verify → 回贴 + 汇总成总闸。
- `calibrate.yml` —— 定时:从已合 PR 重建"与人审吻合度 / 噪声"报告。
- `govern.yml` —— 定时:把复发的发现固化为硬门禁、按 revert/hotfix 信号做熔断校准。

分支保护设为 **Require `touchstone/gate`**,即可让这道总闸成为合入的硬前提。仓库需放开工作流的写权限以便回贴评论/check。

## 仓库结构

```
.
├── .touchstone/                # 仓内策略(随仓库版本化,离线生效)
│   ├── standards.yaml          # 单一事实源规范(喂 author 与评审两端)
│   ├── pr.yaml                 # 提交契约模板
│   ├── checks.yaml             # 可插拔检查闸配置
│   ├── pr-agent.yaml           # PR-Agent 输出 → Finding 归一映射
│   ├── best_practices.md       # 主观规则库(评审 prompt 素材)
│   └── acceptance.yaml.example # 人核准验收规格样例(verify 用)
├── touchstone/                 # 评审判断 + 门禁/集成 + 闭环/治理 + 入口
│   ├── orchestrator.py            # 主编排:评审归一 → 裁决映射/风险分流 → 回贴(advisory)
│   ├── review_provider.py      # 评审来源适配(PR-Agent / 优雅降级)
│   ├── pr_agent_runner.py      # PR-Agent 调用(独立 venv,子进程)
│   ├── stack_rules.py          # 栈专项确定性规则(DI/事务/equals/异常/日志/路径契约)
│   ├── contract_check.py       # 确定性契约一致性核对(无 LLM)
│   ├── gen_best_practices.py   # 主观规则 → PR-Agent prompt 素材
│   ├── loop.py                 # 反馈循环 loop_step(有界、防震荡、可升级)
│   ├── calibrate.py            # 影子校准:与人审吻合度 / 噪声
│   ├── learning_loop.py        # 离线学习:从校准记录蒸馏候选
│   ├── checks.py               # 可插拔检查闸聚合 → 单一 touchstone/gate
│   ├── govern.py               # 治理:固化提案(发现→硬门禁)+ 熔断
│   ├── autonomy.py             # 渐进开放自动合并(可选、默认关)
│   ├── ghclient.py             # GitHub REST/GraphQL 客户端(连接池 + 退避)
│   ├── preflight.py            # 起步自检
│   └── run.py                  # 独立入口:python -m touchstone.run --pr N
├── verify/
│   └── verify_change.py        # 质量门禁的核心:独立验收测试 + 改前/改后对比 + 充分性阶梯
├── tests/                      # 245 个离线用例(无需 LLM / 网络 / 外部服务)
└── .github/workflows/          # touchstone.yml · calibrate.yml · govern.yml
```

生产代码约 3578 行 / 17 个模块;测试 245 个用例 / 12 个文件,全绿、离线;行覆盖率 83%(核心逻辑模块 85–100%;GitHub API / 子进程 / LLM / CLI 等集成层经 mock 覆盖)。

## 状态与边界(诚实交代)

- **评审 + 确定性门禁**:已实现、可跑。
- **verify(独立验证)**:参考级实现,**默认关、尚未规模化实跑**。Python(pytest + coverage)与 Java(Maven + JaCoCo + PIT)双 runner;Python 侧变异为自写 AST,生产应换 mutmut/cosmic-ray;需要一个异于评审的 LLM 端点(离线测试以桩覆盖)。
- **autonomy(自治)**:默认关,需要足够的校准数据证明某变更类"放行靠谱"后才逐步开放。
- **学习回路 / TF-GRPO**:两档都已实现、离线可跑——计数式蒸馏,以及核心的 **TF-GRPO**(策略冻结 + 组内语义优势把经验蒸馏成注入提示词的 token prior,取自 arXiv 2510.08191,机制见 `docs/learning-loop-design.html` 第 3 节)。TF-GRPO 经注入的 `llm` 调用旗舰模型,离线用假 llm 覆盖测试;生产需配置一个参数固定的旗舰模型端点(`LLM_BASE_URL`/`LLM_API_KEY`/`TOUCHSTONE_FLAGSHIP_MODEL`)与一份历史 PR 真值集。出于稳健,新经验先 shadow A/B 达标才注入、且只影响建议不碰合入。因为经验是人能读写的自然语言,**人能直接读写它学到的东西**:手写种子(`seed_experience`)、审校候选、立红线(受保护类型永不 suppress、`locked` 经验不被回路改写/退役)、调奖励权重——见 `docs/learning-loop-design.html` 第 6 节。蒸馏器**可插拔**:`register_distiller` 注册自有实现、env `TOUCHSTONE_DISTILLER` 按名切换,`_distill_via_llm` 的 rollout/score/distill 三步也可单独注入——整体或局部换成你们自己的实现都行。
- 还有一些预留的可替换实现(比如内网 embedding、不同语言的测试 runner),默认都不启用,确认依赖就绪后再接入。

## 设计文档

- `docs/touchstone-design.html` —— 详细设计(自包含离线 HTML,含内联 SVG)
- `docs/touchstone-arch-4plus1.html` —— 4+1 架构视图
- `docs/touchstone-index.html` —— 模块与交付物索引
- `docs/touchstone-slides.html` —— 评审用 slides
- `docs/touchstone-on-pr-agent.html` —— 与 PR-Agent 的复用边界
- `docs/learning-loop-design.html` —— 学习回路设计

## 名称由来

试金石是古人辨真金与愚人金的器物:不听成色的说辞,把东西在石上一划,真假立现。它也指"评判事物的标准"。这两层意思正是本系统的立身之本——**对似是而非的判断,不信表象,只认那道客观的标尺。**
