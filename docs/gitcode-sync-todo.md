# Gitcode 同步 TODO

> GitHub **AKDI-SE/touchstone** 是主仓库；gitcode akdi-distribution/touchstone 是镜像（2026-07-03 起以 AKDI-SE main 为唯一基准）。
> 本文件记录 gitcode 侧需要跟进的修改（从 AKDI-SE main 同步时需注意的差异点）。

## 已在 GitHub main 但 gitcode 侧可能缺或不同的

| 项 | GitHub main 状态 | gitcode 侧需做 | 优先 |
|---|---|---|---|
| **确定性 blast-radius**（`review_provider.deterministic_blast`） | ✅ 已有 | 同步 | 高 |
| **第七道闸·基线新鲜度**（`autonomy.check_base_fresh`） | ✅ 已有 | 同步 | 高 |
| **经验库投毒防护**（`TOUCHSTONE_EXPERIENCE_REF` + `_read_store_text`） | ✅ 已有 | 同步 | 高 |
| **作者自-resolve 过滤**（`thread_findings(pr_author=)`） | ✅ 已有 | 同步 | 高 |
| **loop marker 防伪造**（`loop.trusted_bodies`） | ✅ 已有（Leo 版） | gitcode 有 `_is_trusted_marker_author`（MR #7），需合并两种方案 | 中 |
| **required relay fail-closed** | ✅ 已有 | 同步 | 中 |
| **外部变异命令**（`TOUCHSTONE_MUTATION_CMD`） | ✅ 已有 | gitcode 有内置 15 类 AST 变异（MR #18），两者可共存 | 低 |
| **reviewdog rdjson 导出**（`to_rdjson`） | ✅ 已有 | 同步 | 低 |
| **GitHub 原生 merge queue**（`enqueue_auto_merge`） | ✅ 已有 | 同步 | 低 |
| **SEC 规则冻结 + gitleaks relay** | ✅ Leo 版冻结 7 类 | gitcode 扩展到 12 类（MR #20）→ 取 gitcode 的扩展版 + 加 gitleaks relay | 低 |
| **_exp_id 含 repo/stack** | ✅ `kind:repo:stack:ftype` | gitcode 用 `kind:ftype`（MR 注释说单仓）→ **取 GitHub 版** | 中 |
| **active_ids 格式** | ✅ 带 repo/stack | gitcode 版不带 → 取 GitHub 版 | 中 |
| **I2 epoch 迭代** | ✅ Leo 版 | gitcode 版（`_conditioning_text`）思路一致但实现不同 → 取一版 | 中 |
| **I3 冲突消解** | ✅ `_resolve_conflicts`（保留 updated_at 新的） | gitcode 版（drop both）→ 可讨论 | 低 |

## 同步方式

```bash
# gitcode 侧从 AKDI-SE 拉
git remote add akdi git@github.com:AKDI-SE/touchstone.git
git fetch akdi main
git checkout main
git merge akdi/main  # 解冲突（取 AKDI-SE 版为主）
git push origin main
```
