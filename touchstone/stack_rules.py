# touchstone/stack_rules.py
"""§4.1 确定性 touchstone-rules 的【分栈】部分。

standards.yaml 里 machine_checkable=true 的栈专项规则，按 applies_to 只在对应栈的 PR 上跑，
对【新增行】做正则/模式检测，产出顾问式 Finding（severity=warn；可经 govern.promote_to_gate
固化为 enforced 后拦截）。通用确定性检查（SCOPE-001/TEST-001/DUP-001）在 contract_check；
本模块只补"栈专项"那批（CTR-001 / SPR-DI-001 / SPR-TX-001 / JAVA-EQ-001 / JAVA-EXC-001 /
JAVA-LOG-001）。

检测是行级 best-effort（会有少量漏判/误判）——给线索而非判决；
准入仍只由质量门禁（verify/总闸）把关。machine_checkable=false 的主观栈规则（如 SPR-VAL-001）
不在此，而是经 gen_best_practices 进 best_practices.md 供 PR-Agent。
"""
import re
import fnmatch

import contract_check


# ---- applies_to / 栈判定 ------------------------------------------------------
def _stack_of(path):
    return "java" if path.endswith(".java") else None


def _on(rule_index, rid):
    """该栈规则是否生效：在册 且 machine_checkable=true（false 的归 best_practices，不在此跑）。"""
    r = rule_index.get(rid)
    return bool(r and r.get("machine_checkable"))


def _ctr_path_match(rule, path):
    ap = rule.get("applies_to") or ""
    pats = [p.strip() for p in str(ap).split(",") if p.strip()]
    for p in pats:
        if fnmatch.fnmatch(path, p) or fnmatch.fnmatch(path, "*/" + p.lstrip("*/")):
            return True
        seg = p.strip("*/ ")            # 形如 **/api/**  → 子串 api
        if seg and ("/" + seg + "/") in ("/" + path + "/"):
            return True
    return False


def _mk(rule_id, rule_index, path, lineno, why):
    r = rule_index.get(rule_id, {})
    # severity 取自规则：block_candidate（CTR-001/SPR-TX-001/JAVA-EQ-001）立即具备拦截级；
    # warn 类（SPR-DI/JAVA-EXC/JAVA-LOG）仅在被 govern 固化(enforced=true)后才升为 block_candidate。
    severity = "block_candidate" if r.get("enforced") else r.get("severity", "warn")
    return {
        "rule_id": rule_id,
        "category": r.get("category", "convention"),
        "severity": severity,
        "confidence": 0.8,                  # 行级正则 best-effort，非确定 1.0
        "file": path, "line": lineno, "line_start": lineno, "line_end": lineno,
        "agent": "touchstone-rules",
        "consumable_by": "both",
        "rationale": f"确定性栈规则 {rule_id}：{why}（{r.get('description','')[:60]}）",
    }


# ---- 行级检测器 ---------------------------------------------------------------
_RE_DI_ANNO   = re.compile(r"@(Autowired|Resource|Inject)\b")
_RE_FIELD     = re.compile(r"^\s*(private|protected|public)?\s*(static\s+|final\s+)*[\w$.<>\[\],\s]+\s+\w+\s*(=|;)")
_RE_TX        = re.compile(r"@Transactional\b")
_RE_NONPUB_M  = re.compile(r"\b(private|protected)\s+[\w$.<>\[\],\s]+\s+\w+\s*\(")
_RE_EQ_STR    = re.compile(r'(==|!=)\s*"|"\s*(==|!=)')          # 与字符串字面量用 ==/!= 比较
_RE_EMPTY_CAT = re.compile(r"catch\s*\([^)]*\)\s*\{\s*\}")       # 单行空 catch
_RE_CATCH_OPN = re.compile(r"catch\s*\([^)]*\)\s*\{?\s*$")       # catch (...) { 行尾
_RE_ONLY_CLS  = re.compile(r"^\s*\}\s*$")                        # 仅一个 }
_RE_LOG       = re.compile(r"\.printStackTrace\s*\(|System\.(out|err)\.")


def check_stack_rules(diff_text, rule_index):
    """对新增行跑【在册且 machine_checkable】的栈专项规则。返回 Finding[]（与 contract_check 同构）。"""
    findings = []
    _, added = contract_check.parse_diff(diff_text or "")

    # CTR-001：路径型契约影响（改了 api/schema/proto 即提示评估下游兼容）
    if _on(rule_index, "CTR-001"):
        rule = rule_index["CTR-001"]
        for path, lines in added.items():
            if _ctr_path_match(rule, path):
                first = lines[0][0] if lines else 0
                findings.append(_mk("CTR-001", rule_index, path, first,
                                    "改动触及对外契约（API/schema/proto），需评估下游兼容"))

    # Java 行级：逐文件按新增行顺序扫描
    for path, lines in added.items():
        if _stack_of(path) != "java":
            continue
        pend_di = pend_tx = pend_catch = False
        for lineno, text in lines:
            t = text

            if _on(rule_index, "SPR-DI-001"):
                anno = bool(_RE_DI_ANNO.search(t))
                field = bool(_RE_FIELD.search(t)) and "(" not in t
                if anno and field:
                    findings.append(_mk("SPR-DI-001", rule_index, path, lineno, "字段注入（应改构造器注入）"))
                    pend_di = False
                elif pend_di and field:
                    findings.append(_mk("SPR-DI-001", rule_index, path, lineno, "字段注入（应改构造器注入）"))
                    pend_di = False
                else:
                    pend_di = anno

            if _on(rule_index, "SPR-TX-001"):
                tx = bool(_RE_TX.search(t))
                nonpub = bool(_RE_NONPUB_M.search(t))
                if tx and nonpub:
                    findings.append(_mk("SPR-TX-001", rule_index, path, lineno,
                                        "@Transactional 标在非 public 方法上（代理不生效）"))
                    pend_tx = False
                elif pend_tx and nonpub:
                    findings.append(_mk("SPR-TX-001", rule_index, path, lineno,
                                        "@Transactional 标在非 public 方法上（代理不生效）"))
                    pend_tx = False
                else:
                    pend_tx = tx

            if _on(rule_index, "JAVA-EQ-001") and _RE_EQ_STR.search(t):
                findings.append(_mk("JAVA-EQ-001", rule_index, path, lineno,
                                    "用 ==/!= 比较字符串内容（应用 equals）"))

            if _on(rule_index, "JAVA-EXC-001"):
                if _RE_EMPTY_CAT.search(t):
                    findings.append(_mk("JAVA-EXC-001", rule_index, path, lineno, "空 catch 吞异常"))
                    pend_catch = False
                elif pend_catch and _RE_ONLY_CLS.match(t):
                    findings.append(_mk("JAVA-EXC-001", rule_index, path, lineno, "空 catch 吞异常"))
                    pend_catch = False
                elif _RE_CATCH_OPN.search(t):
                    pend_catch = True
                elif pend_catch and t.strip():
                    pend_catch = False        # catch 体有内容，不判（best-effort）

            if _on(rule_index, "JAVA-LOG-001") and _RE_LOG.search(t):
                findings.append(_mk("JAVA-LOG-001", rule_index, path, lineno,
                                    "用 printStackTrace/System.out 而非日志框架"))

    return findings
