# Touchstone best practices

<!-- 本文件由 touchstone/gen_best_practices.py 从 .touchstone/standards.yaml 生成；请勿手改——改 standards.yaml 后重新生成。 -->
<!-- 仅含主观规则（machine_checkable=false）；可机检规则由 touchstone-rules / contract_check 确定性处理。 -->

若 PR 代码违反下列任一 pattern，请生成一条建议（将被标为 “Organization best practice”）。聚焦项目特有判断，不重复通用且 AI 已知的常识。

## 通用 (all languages)

Pattern 1 (DUP-001, applies: all languages): 新增的工具/辅助函数与代码库已有能力重复或高度相似。
- Why: agent 未检索已有代码即自行实现，造成重复实现、维护分裂。
- Do: 新增任何 util/helper 前，先在已有代码地图(repo_index)中检索同义能力； 若存在，复用并在提交契约 reused_components 中声明，而非另写一份。

Pattern 2 (CONV-002, applies: all languages): 注释/文档须与代码实际行为一致，不得是 AI 生成的"看起来合理"但与实现不符的描述。
- Why: AI 易产出漂亮但与代码不符的注释，误导后续读者与评审。
- Do: 注释只描述代码真实做的事；改了实现必须同步改注释。

Pattern 3 (OE-001, applies: all languages): 引入与任务规模不相称的抽象层、配置项或泛化（YAGNI 违例）。
- Why: agent 倾向"40 行能解决写成 400 行"，凭空加抽象，增加复杂度与维护面。
- Do: 用满足 acceptance_criteria 的最小改动；不为"将来可能"提前泛化。

Pattern 4 (ERR-001, applies: all languages): 外部边界(IO/网络/解析/用户输入)缺校验，或异常被静默吞掉。
- Why: AI 常给出 happy-path 实现，忽略错误路径与边界。
- Do: 对所有外部输入与可失败调用显式处理错误；不写空 catch、不静默吞异常。

Pattern 5 (COR-001, applies: all languages): 使用了未经核实的 API/方法/字段（疑似幻觉或签名记错）。
- Why: AI 易调用不存在的接口或记错参数顺序/语义。
- Do: 只用已确认存在的 API；不确定的先查文档/类型定义。

Pattern 6 (COR-002, applies: all languages): 共享状态/并发路径缺同步，或对外部响应结构做了未验证假设。
- Why: 此类语义错误"看着对、能跑"，只有执行/特定输入才暴露。
- Do: 并发访问共享状态需显式同步；对外部响应先校验结构再使用。

Pattern 7 (SCOPE-001, applies: all languages): diff 触及与提交契约 intent 无关的文件/区域，或捆绑了不相关改动。
- Why: agent 易顺手改动声明范围之外的东西，放大评审与风险面。
- Do: 一个 PR 只做一件事；与 intent 无关的改动拆成独立 PR。

## **/*test*, **/*spec*

Pattern 8 (TEST-002, applies: **/*test*, **/*spec*): 测试 mock 掉了被测对象本身，或只测桩而非真实逻辑。
- Why: 过度 mock 让测试通过却未验证真实行为。
- Do: 只 mock 外部依赖，不 mock 被测单元本身。

## java

Pattern 9 (SPR-VAL-001, applies: java): 控制器入参（@RequestBody/@RequestParam/@PathVariable）未做校验（缺 @Valid/@Validated 或显式校验）。
- Why: 外部输入是信任边界；不校验直接进业务/落库，放大注入与脏数据风险。
- Do: 给 @RequestBody DTO 加约束注解并在入参标 @Valid；@RequestParam 关键约束显式校验。
