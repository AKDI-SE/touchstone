"""测试公用助手。"""
import os


def make_repo(base, files):
    """files: {relpath: content} → 写入 base 目录，返回 base 路径(str)。"""
    base = str(base)
    for rel, content in files.items():
        p = os.path.join(base, rel)
        os.makedirs(os.path.dirname(p) or base, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(content)
    return base


def hunk(path, added, new=True):
    """构造一个文件的 unified diff 片段（added: 新增行列表）。"""
    head = "--- /dev/null\n" if new else "--- a/" + path + "\n"
    return ("diff --git a/" + path + " b/" + path + "\n" + head + "+++ b/" + path + "\n"
            + "@@ -0,0 +1," + str(len(added)) + " @@\n"
            + "".join("+" + l + "\n" for l in added))


def build_diff(parts):
    """parts: [(path, added_lines, is_new)] → 合并 diff 字符串。"""
    return "".join(hunk(p, a, new) for p, a, new in parts)
