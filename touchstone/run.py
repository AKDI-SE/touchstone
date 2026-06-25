#!/usr/bin/env python3
# ============================================================================
# touchstone/run.py  ——  独立运行入口（Actions 之外，对任意 PR 端到端跑评审）
# ----------------------------------------------------------------------------
#   python -m touchstone.run --repo owner/name --pr 314 [--post] [--repo-dir DIR] [--standards PATH]
#
# 与 Actions 版的区别：
#   • 经 GitHub API 取【完整 diff】(消除手搓 diff 的截断假阳性)
#   • 浅 clone + checkout 到 PR head（供读取仓内 .touchstone 配置）
#   • 默认 dry-run 只打印；--post 才回贴评论/check（对不拥有的外部 PR 默认不动它）
# 评审复用 PR-Agent（review_provider）；真实端点在 review_provider._invoke_endpoint。
# token 走环境变量 GITHUB_TOKEN；PR-Agent 端点配置见 .touchstone/pr-agent.yaml。
# ============================================================================

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import urlparse

from touchstone import orchestrator as C   # 触发 orchestrator.py 的同目录加固导入


def _gh_host():
    """clone 用的 Git host：GITHUB_HOST 优先；否则从 GITHUB_API_URL 推（企业 GHE 的 api 在 <host>/api/v3）。
    公有 github 的 api host api.github.com → 还原为 github.com。"""
    h = os.environ.get("GITHUB_HOST")
    if h:
        return h
    host = urlparse(os.environ.get("GITHUB_API_URL", "https://api.github.com")).hostname
    return "github.com" if host in (None, "api.github.com") else host


def _checkout(repo, head_sha, token):
    """浅 clone 到 PR head；返回 (repo_dir, created?)。"""
    d = tempfile.mkdtemp(prefix="touchstone_pr_")
    host = _gh_host()
    url = f"https://{token}@{host}/{repo}.git" if token else f"https://{host}/{repo}.git"
    try:
        subprocess.run(["git", "init", "-q", d], check=True, capture_output=True)
        subprocess.run(["git", "-C", d, "remote", "add", "origin", url],
                       check=True, capture_output=True)
        subprocess.run(["git", "-C", d, "fetch", "--depth", "1", "-q", "origin", head_sha],
                       check=True, capture_output=True)
        subprocess.run(["git", "-C", d, "checkout", "-q", "FETCH_HEAD"],
                       check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        shutil.rmtree(d, ignore_errors=True)
        sys.exit(f"checkout 失败: {e.stderr.decode('utf-8','replace')[:300] if e.stderr else e}")
    return d, True


def main():
    ap = argparse.ArgumentParser(prog="touchstone.run", description="对任意 PR 跑 Touchstone 评审")
    ap.add_argument("--repo", required=True, help="owner/name")
    ap.add_argument("--pr", required=True, type=int)
    ap.add_argument("--post", action="store_true", help="回贴评论/check(默认 dry-run 只打印)")
    ap.add_argument("--repo-dir", help="已有的 PR head checkout(给则不自动 clone)")
    ap.add_argument("--standards", help="standards.yaml 路径(默认用 checkout 内的 .touchstone/standards.yaml)")
    args = ap.parse_args()

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        sys.exit("缺 GITHUB_TOKEN（环境变量）")
    owner, name = args.repo.split("/", 1)
    print("[run] 评审复用 PR-Agent（review_provider）；端点未配置则仅跑确定性契约核对。", file=sys.stderr)

    pr = C.gh("GET", f"/repos/{args.repo}/pulls/{args.pr}", token)
    head_sha = (pr.get("head") or {}).get("sha")
    print(f"[run] PR #{args.pr} {pr.get('title','')}  head={head_sha[:9] if head_sha else '?'}  "
          f"模式={'POST' if args.post else 'DRY-RUN'}")

    repo_dir, created = (args.repo_dir, False) if args.repo_dir else _checkout(args.repo, head_sha, token)
    try:
        std_path = args.standards or os.path.join(repo_dir, ".touchstone/standards.yaml")
        standards = C.load_yaml(std_path)
        if not standards:
            sys.exit(f"未找到规范 {std_path}（用 --standards 指定你自己的）")
        rule_index = {r["id"]: r for r in standards.get("rules", [])}
        contract = C.load_yaml(os.path.join(repo_dir, ".touchstone/pr.yaml"))

        diff = C.get_pr_diff(owner, name, args.pr, token)
        pr_ctx = {"owner": owner, "repo": name, "number": args.pr, "sha": head_sha,
                  "token": token, "diff": diff, "standards": standards}
        # 评审主链（§4.1）：PR-Agent 归一 + 契约核对 + 栈专项确定性规则 → 裁决映射
        # （review_pr 内部对 PR-Agent 端点未配置已做降级：仅跑确定性核对）
        out = C.review_pr(pr_ctx, contract, standards)
        findings, risk = out["findings"], out["risk"]
        dec, reason, new_state = C.loop.loop_step(findings, rule_index, C.loop.LoopState())

        print("\n=== 结果 ===")
        print(f"风险等级={risk['risk_band']}  人={risk['human_action']}  "
              f"验证={risk['verification_decision']}  blast={risk['blast_radius']}")
        print(f"反馈循环={dec} ({reason})")
        print(f"发现 {len(findings)} 条:")
        for f in findings:
            print(f"  · {f['rule_id']} [{f.get('severity','')}] conf={f['confidence']:.2f} "
                  f"{f.get('agent','contract-check')} {f.get('file','?')}:{f.get('line','?')}\n"
                  f"      {f.get('rationale','')}")

        if args.post:
            loop_info = (dec, reason, C.loop.render_marker(new_state))
            C.post_results(owner, name, args.pr, head_sha, token, risk, findings, loop_info, diff=diff)
            print("\n[run] 已回贴到 PR。")
        else:
            print("\n[run] DRY-RUN：未回贴。确认无误后加 --post。")
    finally:
        if created:
            shutil.rmtree(repo_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
