#!/usr/bin/env bash
# ============================================================================
# push-guard.sh —— git pre-push 钩子：拦「推送到已关闭/已合并 PR 的分支」
# ----------------------------------------------------------------------------
# 动机（2026-08-17 实付学费）：PR 合并后其分支的推送 GitHub 静默接受——push 报
# 成功、提交却不评审、不进 main，纯作废。写进 skill §7 的坑被 skill 作者本人
# 在规则合入 5 分钟内踩中，证明纪律靠自觉不可靠，要靠机器闸。
#
# 拦截逻辑：对每个待推送分支——
#   1. 远端同名分支有【开着的】 PR（state=open 且非 draft）→ 放行
#   2. 远端同名分支的 PR 已 merged/closed，且本次推送含新提交 → 拒绝并提示
#      「开新分支 cherry-pick」
#   3. 远端无 PR（未开过 PR 的分支，如个人开发分支）→ 放行
#
# 安装（一次性）：
#   cp scripts/push-guard.sh .git/hooks/pre-push && chmod +x .git/hooks/pre-push
#   （或 git config core.hooksPath .githooks 后放入该目录——随仓版本化时用）
#
# 依赖：curl；GITHUB_TOKEN（PAT）或 GH_TOKEN。无 token 时降级为提示（不拦截），
#       避免离线/未配环境被卡。--no-verify 可绕过（明知故犯时）。
# ============================================================================
set -euo pipefail

GITHUB_TOKEN="${GITHUB_TOKEN:-${GH_TOKEN:-}}"
# 兜底：本机惯例 ~/github.token（仅本地开发便利；CI/他人环境用 env）
[ -z "$GITHUB_TOKEN" ] && [ -f "$HOME/github.token" ] && GITHUB_TOKEN="$(tr -d '\n' < "$HOME/github.token")"

# pre-push 钩子从 stdin 读：每行 "<local ref> <local sha> <remote ref> <remote sha>"
while read -r local_ref local_sha remote_ref remote_sha; do
  [ "$local_sha" = "0000000000000000000000000000000000000000" ] && continue  # 删分支，不拦
  case "$remote_ref" in refs/heads/*) ;; *) continue ;; esac                 # 只管分支
  branch="${remote_ref#refs/heads/}"

  # 从仓库 remote 推断 owner/repo（取 origin 的 URL）
  url="$(git remote get-url origin 2>/dev/null || true)"
  slug=""
  if echo "$url" | grep -qE 'github\.com[:/].+/.+'; then
    slug="$(echo "$url" | sed -E 's#.*github\.com[:/]##; s#\.git$##; s#^x-access-token:[^@]*@##; s#https?://##')"
  fi
  [ -n "$slug" ] || { echo "[push-guard] 非 GitHub remote 或无法解析仓坐标，跳过检查。"; continue; }

  if [ -z "$GITHUB_TOKEN" ]; then
    echo "[push-guard] ⚠️ 未设 GITHUB_TOKEN/GH_TOKEN，无法查 PR state（降级提示，不拦截）。"
    continue
  fi

  # 查该分支的 PR（含关闭的）。列表端点无 merged 字段：先列表取 state+number，
  # closed 时再查单 PR 端点取 merged（区分「已合并」与「关闭未合并」）。
  resp="$(curl -sS -H "Authorization: Bearer $GITHUB_TOKEN" \
        "https://api.github.com/repos/$slug/pulls?head=${slug%%/*}:$branch&state=all" 2>/dev/null || echo '[]')"
  state="$(printf '%s' "$resp" | python3 -c '
import sys, json
try:
    ps = json.load(sys.stdin)
except Exception:
    print("parse-fail"); sys.exit()
if not ps: print("none"); sys.exit()
p = ps[0]
if p["state"] != "closed": print(p["state"], "x"); sys.exit()
print("closed", p["number"])' 2>/dev/null || echo parse-fail)"

  if printf '%s' "$state" | grep -q '^open'; then
    echo "[push-guard] ✓ $branch 的 PR 仍 open，放行。"
    continue
  elif printf '%s' "$state" | grep -q '^closed [0-9]'; then
    pr_num="$(printf '%s' "$state" | awk '{print $2}')"
    one="$(curl -sS -H "Authorization: Bearer $GITHUB_TOKEN" \
         "https://api.github.com/repos/$slug/pulls/$pr_num" 2>/dev/null || echo '{}')"
    merged="$(printf '%s' "$one" | python3 -c '
import sys, json
try: print("merged" if json.load(sys.stdin).get("merged") else "not-merged")
except Exception: print("unknown")' 2>/dev/null || echo unknown)"
    if [ "$merged" = "merged" ]; then
      echo "[push-guard] ❌ $branch 的 PR #$pr_num 已【合并】，推送不会进任何 PR/main——纯作废！" >&2
      echo "            正确做法：从最新 main 切新分支 cherry-pick，重开 PR。" >&2
      echo "            （明知故犯绕过：git push --no-verify）" >&2
      exit 1
    fi
    echo "[push-guard] ❌ $branch 的 PR #$pr_num 已【关闭未合并】，推送不评审不进 main——作废！" >&2
    echo "            若要继续此工作：重开 PR，或从最新 main 切新分支。" >&2
    echo "            （明知故犯绕过：git push --no-verify）" >&2
    exit 1
  elif false; then
    echo "[push-guard] ❌ $branch 的 PR 已【合并】，推送不会进任何 PR/main——纯作废！" >&2
    echo "            正确做法：从最新 main 切新分支 cherry-pick，重开 PR。" >&2
    echo "            （明知故犯绕过：git push --no-verify）" >&2
    exit 1
  elif [ "$state" = "none" ]; then
    echo "[push-guard] ✓ $branch 从未开过 PR（个人分支），放行。"
    continue
  else
    echo "[push-guard] ⚠️ PR state 查询异常（$state），不拦截仅提示——请人工确认 $branch 的 PR 状态。"
    continue
  fi
done

exit 0
