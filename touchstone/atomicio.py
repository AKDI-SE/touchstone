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


def atomic_write_text(path, text, encoding="utf-8"):
    """把 text 原子写入 path。父目录不存在则创建。写失败不留半文件。"""
    d = os.path.dirname(path) or "."
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".ts_tmp_", dir=d)
    try:
        with os.fdopen(fd, "w", encoding=encoding) as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())          # 元数据+数据落盘，防 replace 后仍是脏页
        os.replace(tmp, path)             # 原子改名：读方永不见截断态
        tmp = None
    finally:
        if tmp is not None and os.path.exists(tmp):
            try:
                os.unlink(tmp)            # 写/replace 失败 → 清理临时文件，不留垃圾
            except OSError:
                pass


def atomic_write_json(path, obj, *, ensure_ascii=False, indent=2):
    """原子写 JSON。与散落各处的 json.dump(obj, open(path,"w")) 同签名同效果，但原子。"""
    atomic_write_text(path, json.dumps(obj, ensure_ascii=ensure_ascii, indent=indent))
