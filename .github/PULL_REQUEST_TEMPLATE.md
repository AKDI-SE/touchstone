<!-- ══ 提交前两读（写给 agent 与人；本注释不渲染）═══════════════════════════
  ① .touchstone/pr.yaml —— 本 PR 的提交契约：必填三件 intent / acceptance_criteria /
     scope，其余字段按价值递减选填（文件头有逐字段说明与示例）。
     每个声明都会被独立核对（scope 外改动=SCOPE-001、申报测试不实=TEST-001、
     复用申报对不上=DUP-001）——写漂亮骗不过 touchstone，只会烧你自己的修改轮次。
  ② CLAUDE.md（=AGENTS.md）—— 写代码的硬性规矩：四条铁律、按层可动范围、DoD 自检。
  收到 Touchstone 评审意见后：销项规程在仓内 skills/touchstone-ack/SKILL.md
  （agent 可安装为 skill 或直接参考；含申报格式与时序）。
════════════════════════════════════════════════════════════════════════ -->

## 改动说明

<!-- 做什么 + 为什么（与 .touchstone/pr.yaml 的 intent 一致，偏离即 SCOPE-001） -->

## 验证

<!-- 跑了哪些测试/检查，贴真实输出关键行；如 python3 -m pytest tests/test_xxx.py -q -->

## 残余

<!-- 没做完的 / stub / 已知风险；没有写「无」 -->
