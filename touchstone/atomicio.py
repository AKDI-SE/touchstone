#!/usr/bin/env python3
# ============================================================================
# touchstone/atomicio.py —— 状态文件原子写（write-to-temp + os.replace）
# ----------------------------------------------------------------------------
# 为什么需要：本仓多处状态文件（经验库、毕业类、自治熔断状态、清单快照、学习报告）
# 直接喂 auto-merge 的毕业判据与校准归因。若写到一半进程被杀（CI runner 超时杀进程
# 是常态），open(...,"w") 会在磁盘留下【被截断的半个 JSON】——下次 load 要么抛
# JSONDecodeError（好些的分支会兜成空），要么更糟地被解析成偏斜的部分状态，让授权
# 自动放行的判据建立在残缺数据上。
#
# 原子写保证：同目录建临时文件写全 → flush+fsync 落盘 → os.replace 原子改名。
# os.replace 在同一文件系统上是原子的（POSIX rename 语义），读方要么看到旧的完整
# 文件、要么看到新的完整文件，永不会看到中间态。临时文件同目录建（跨文件系统的
# /tmp → 目标 会退化成非原子的 copy+unlink），异常时清理。
# ============================================================================

import json
import os
import tempfile


def _fsync_dir(path):
    """fsync 父目录：os.replace 在页缓存里原子，但 rename 的目录项不保证落盘——
    断电后可能丢掉这次 rename（回退到旧完整文件，core "不截断"承诺仍成立，但最新一次写会丢）。
    补一次目录 fsync 让 rename 持久。某些 FS（tmpfs/网络盘）不支持目录 fsync → 静默跳过
    （非致命：原子承诺不依赖它，只是少一档断电耐久）。"""
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass    # 静默豁免：目录 fsync 是崩溃持久性加固（best-effort），失败不影响数据
                # 正确性；本模块是无日志依赖的底层库，且不能让加固失败冒充写失败。
    finally:
        # os.close 失败不得上抛：调用方此时 os.replace 已完成、数据已落盘，
        # 是【成功的原子写】的尾收尾。若目录 fd 关闭失败（NFS EIO 等罕见但真实）
        # 被向上传播，一次成功落盘会被误判为写失败——破坏"成功不冒失败"契约。
        # 仍尝试 close（防 fd 泄漏），但吞掉 OSError（与上面 fsync 同纪律）。
        try:
            os.close(fd)
        except OSError:
            pass    # 静默豁免：见上方注释——close 失败不得冒充写失败，fd 泄漏由进程退出兜底。


def atomic_write_text(path, text, encoding="utf-8"):
    """把 text 原子写入 path。父目录不存在则创建。写失败不留半文件。

    权限保持（与旧 ``open(path, "w")`` 同效果）：mkstemp 默认建 0o600（仅属主），而
    os.replace 携带源 inode 的权限——若照搬，每个被重写的状态文件都会静默变 0o600，
    破坏"同签名同效果"。故 replace 前 chmod：目标已存在→沿用其当前权限（=旧 open('w')
    截断写保持权限）；新建→0o644（=旧 open('w') 按 umask 的常见默认）。"""
    d = os.path.dirname(path) or "."
    os.makedirs(d, exist_ok=True)
    # 目标权限：存在则沿用既有（旧 open('w') 截断保持权限），新建则 0o644（旧 open('w') 默认）
    try:
        mode = os.stat(path).st_mode & 0o777
    except FileNotFoundError:
        mode = 0o644
    fd, tmp = tempfile.mkstemp(prefix=".ts_tmp_", dir=d)
    try:
        with os.fdopen(fd, "w", encoding=encoding) as f:
            f.write(text)
            f.flush()
            # 权限须在 fsync【前】经 fchmod 写到 fd：fsync 只持久化【调用前】已写入的元数据。
            # 原实现先 fsync 再 chmod——fsync 落盘的是 mkstemp 的 0o600，chmod 的元数据改动
            # 在 fsync 之后、未被持久 → 崩溃后回退 0o600（#86 round-3 finding）。fchmod 早于
            # fsync，单次 fsync 即把数据 + 正确权限一起落盘。
            os.fchmod(f.fileno(), mode)
            os.fsync(f.fileno())          # 元数据+数据（含正确权限）落盘，防 replace 后仍是脏页
        os.replace(tmp, path)             # 原子改名：读方永不见截断态
        _fsync_dir(d)                     # 目录 fsync：让 rename 断电后也持久
        tmp = None
    finally:
        if tmp is not None and os.path.exists(tmp):
            try:
                os.unlink(tmp)            # 写/replace 失败 → 清理临时文件，不留垃圾
            except OSError:
                pass    # 静默豁免：清理是 best-effort，主错误已在上方传播/记录。


def atomic_write_json(path, obj, *, ensure_ascii=False, indent=2):
    """原子写 JSON。与散落各处的 json.dump(obj, open(path,"w")) 同签名同效果，但原子。"""
    atomic_write_text(path, json.dumps(obj, ensure_ascii=ensure_ascii, indent=indent))
