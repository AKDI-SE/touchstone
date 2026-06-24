#!/usr/bin/env bash
# ============================================================================
# push-to-github.sh —— 一键把本仓推送到一个【新建的】 GitHub 仓库
# ----------------------------------------------------------------------------
# 做三件事：① 用 GitHub API 新建仓库（或用已登录的 gh CLI）② 配置 origin
#           ③ 推送当前分支 + 所有 tag。token 不写进 .git/config（用一次性 URL 推）。
#
# 前提：
#   • 一个有 repo 权限的 GitHub Personal Access Token：
#       - 经典 token：勾 “repo”
#       - 细粒度 token：Administration=Read&Write + Contents=Read&Write
#     放进环境变量 GITHUB_TOKEN，或用 --token 传，或运行时按提示输入。
#   • 华为内网访问 github.com（公网）需走代理：加 --huawei 即可。
#
# 用法：
#   GITHUB_TOKEN=ghp_xxx  ./push-to-github.sh touchstone --private --huawei
#   ./push-to-github.sh touchstone --public --org my-team --desc "试金石"
#   ./push-to-github.sh touchstone --dry-run            # 只打印步骤，不真执行
# ============================================================================
set -euo pipefail

HOST="github.com"
API="https://api.github.com"
VIS="private"
ORG=""
DESC="Touchstone (试金石) — AI PR review-and-gate with a training-free self-improving loop"
TOKEN="${GITHUB_TOKEN:-}"
PROXY="${HTTPS_PROXY:-${https_proxy:-}}"
USE_GH=0
DRYRUN=0
REPO=""
HUAWEI_PROXY='http://z00:Zjf%3B@proxy.huawei.com:8080'   # 华为内网公网出口代理（见 huawei-internal-network）

usage() {
  sed -n '2,/^set -euo/p' "$0" | grep '^#' | sed 's/^# \{0,1\}//'
  exit "${1:-0}"
}

# ---- 解析参数 --------------------------------------------------------------
while [ $# -gt 0 ]; do
  case "$1" in
    --public)  VIS="public" ;;
    --private) VIS="private" ;;
    --org)     ORG="${2:?--org 需要值}"; shift ;;
    --desc)    DESC="${2:?--desc 需要值}"; shift ;;
    --token)   TOKEN="${2:?--token 需要值}"; shift ;;
    --proxy)   PROXY="${2:?--proxy 需要值}"; shift ;;
    --huawei)  PROXY="$HUAWEI_PROXY" ;;
    --host)    HOST="${2:?--host 需要值}"; shift ;;
    --api)     API="${2:?--api 需要值}"; shift ;;
    --gh)      USE_GH=1 ;;
    --dry-run) DRYRUN=1 ;;
    -h|--help) usage 0 ;;
    -*)        echo "未知选项：$1" >&2; usage 1 ;;
    *)         [ -z "$REPO" ] && REPO="$1" || { echo "多余参数：$1" >&2; usage 1; } ;;
  esac
  shift
done

say()  { printf '\033[1;36m[push]\033[0m %s\n' "$*"; }
err()  { printf '\033[1;31m[push] 错误：\033[0m %s\n' "$*" >&2; exit 1; }
run()  { if [ "$DRYRUN" = 1 ]; then printf '  (dry-run) %s\n' "$*"; else eval "$@"; fi; }

[ -n "$REPO" ] || { echo "缺少仓库名。" >&2; usage 1; }
command -v git >/dev/null || err "未找到 git。"
git rev-parse --git-dir >/dev/null 2>&1 || err "当前目录不是 git 仓库。请在仓库根目录运行。"
git rev-parse HEAD >/dev/null 2>&1 || err "仓库还没有任何提交。"

BRANCH="$(git branch --show-current 2>/dev/null || echo main)"
[ -n "$BRANCH" ] || BRANCH="main"

# 工作区有未提交改动时提醒（不阻断，只推已提交内容）
if [ -n "$(git status --porcelain)" ]; then
  say "提醒：工作区有未提交改动，本次只推送【已提交】的内容。"
fi

# ---- 代理（github.com 是公网；内网下必须走代理）----------------------------
if [ -n "$PROXY" ]; then
  export https_proxy="$PROXY" http_proxy="$PROXY" HTTPS_PROXY="$PROXY" HTTP_PROXY="$PROXY"
  say "使用代理：$PROXY"
else
  say "未设代理（若在华为内网访问 github.com 会卡住/超时，请加 --huawei）。"
fi

# ============================================================================
# 路线 A：gh CLI（已 gh auth login 时最省事）
# ============================================================================
if [ "$USE_GH" = 1 ]; then
  command -v gh >/dev/null || err "--gh 需要安装并登录 gh CLI（gh auth login）。"
  TARGET="${ORG:+$ORG/}$REPO"
  say "用 gh 新建并推送：$TARGET（$VIS）"
  run "gh repo create '$TARGET' --$VIS --source=. --remote=origin --push --description '$DESC'"
  say "完成 → https://$HOST/${ORG:-<你的账号>}/$REPO"
  exit 0
fi

# ============================================================================
# 路线 B：GitHub API（curl）新建 + git 推送（无需额外工具）
# ============================================================================
[ "$DRYRUN" = 1 ] || [ -n "$TOKEN" ] || { read -rsp "请输入 GitHub PAT（输入不回显）：" TOKEN; echo; }
[ "$DRYRUN" = 1 ] || [ -n "$TOKEN" ] || err "未提供 token。"
command -v curl >/dev/null || err "未找到 curl。"
command -v python3 >/dev/null || err "未找到 python3（用于解析 API 返回的 JSON）。"

# 小工具：调 GitHub API，打印 HTTP 状态码到 stderr、响应体到 stdout
gh_api() {  # gh_api METHOD PATH [JSON_BODY]
  local method="$1" path="$2" body="${3:-}"
  local args=(-sS -X "$method" -H "Authorization: Bearer $TOKEN"
              -H "Accept: application/vnd.github+json"
              -H "X-GitHub-Api-Version: 2022-11-28" -w '\n%{http_code}')
  [ -n "$body" ] && args+=(-d "$body")
  curl "${args[@]}" "$API$path"
}

# 1) 解析 owner（建在本人账号下时取登录名）
if [ -n "$ORG" ]; then
  OWNER="$ORG"
else
  if [ "$DRYRUN" = 1 ]; then
    OWNER="<你的账号>"
  else
    say "查询当前账号 ……"
    resp="$(gh_api GET /user)"; code="$(printf '%s' "$resp" | tail -n1)"
    [ "$code" = "200" ] || err "取账号失败（HTTP $code）。token 是否有效/有 repo 权限？"
    OWNER="$(printf '%s' "$resp" | sed '$d' | python3 -c 'import sys,json;print(json.load(sys.stdin)["login"])')"
  fi
fi
say "目标仓库：$OWNER/$REPO（$VIS）  分支：$BRANCH"

# 2) 新建仓库（已存在则继续，不报错）
PRIVATE_JSON=$([ "$VIS" = "private" ] && echo true || echo false)
BODY=$(python3 -c 'import json,sys;print(json.dumps({"name":sys.argv[1],"private":sys.argv[2]=="true","description":sys.argv[3],"auto_init":False}))' "$REPO" "$PRIVATE_JSON" "$DESC")
CREATE_PATH=$([ -n "$ORG" ] && echo "/orgs/$ORG/repos" || echo "/user/repos")
if [ "$DRYRUN" = 1 ]; then
  say "将创建仓库：POST $API$CREATE_PATH  body=$BODY"
else
  say "创建仓库 ……"
  resp="$(gh_api POST "$CREATE_PATH" "$BODY")"; code="$(printf '%s' "$resp" | tail -n1)"
  case "$code" in
    201) say "已创建。" ;;
    422) say "仓库似乎已存在，跳过创建、直接推送。" ;;
    *)   err "创建失败（HTTP $code）：$(printf '%s' "$resp" | sed '$d' | head -c 400)" ;;
  esac
fi

# 3) 配置 origin（存清洁 URL，不含 token）
CLEAN_URL="https://$HOST/$OWNER/$REPO.git"
if git remote get-url origin >/dev/null 2>&1; then
  run "git remote set-url origin '$CLEAN_URL'"
else
  run "git remote add origin '$CLEAN_URL'"
fi

# 4) 推送当前分支 + 所有 tag（用一次性带 token 的 URL，token 不写进 .git/config）
PUSH_URL="https://x-access-token:${TOKEN}@$HOST/$OWNER/$REPO.git"
say "推送分支 $BRANCH 与全部 tag ……"
if [ "$DRYRUN" = 1 ]; then
  say "将执行：git push <带token的URL> $BRANCH --tags（token 不落盘）"
else
  git push "$PUSH_URL" "refs/heads/$BRANCH:refs/heads/$BRANCH"
  git push "$PUSH_URL" --tags
  git branch --set-upstream-to="origin/$BRANCH" "$BRANCH" >/dev/null 2>&1 || true
fi

say "完成 ✅  仓库：https://$HOST/$OWNER/$REPO"
say "（origin 已设为不含 token 的地址；以后 git push 会用你的凭据助手或再次提示登录。）"
