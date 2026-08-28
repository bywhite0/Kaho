"""离线统计配信弹幕数量。

用法：
    uv run python scripts/build_comment_counts.py <batched_dir> [输出路径]

batched_dir 为弹幕归档的 batched 目录，其下为 type_*/<archives_id>/*_comments.json。
输出默认写入 data/llll/comment_counts.json，键为 archives_id，值为主文件弹幕条数。
"""

import json
import os
import sys

# 带阶段中缀的文件是直播过程弹幕，主文件为回放弹幕
_STAGE_MARKS = ("][live][", "][lobby][")


def pick_main_file(dir_path):
    candidates = []
    for name in os.listdir(dir_path):
        if not name.endswith("_comments.json"):
            continue
        path = os.path.join(dir_path, name)
        is_stage = any(mark in name for mark in _STAGE_MARKS)
        candidates.append((is_stage, -os.path.getsize(path), path))
    if not candidates:
        return None
    # 优先非阶段文件，同类取最大
    candidates.sort()
    return candidates[0][2]


def count_comments(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return len(data) if isinstance(data, list) else 0


def main():
    if len(sys.argv) < 2:
        print(__doc__.strip())
        return 1
    batched_dir = os.path.realpath(sys.argv[1])
    if not os.path.isdir(batched_dir):
        print(f"目录不存在: {batched_dir}")
        return 1
    default_out = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data",
        "llll",
        "comment_counts.json",
    )
    out_path = os.path.realpath(sys.argv[2]) if len(sys.argv) > 2 else default_out

    counts = {}
    errors = []
    type_dirs = sorted(
        d for d in os.listdir(batched_dir) if d.startswith("type_")
    )
    for type_dir in type_dirs:
        type_path = os.path.join(batched_dir, type_dir)
        archive_ids = sorted(os.listdir(type_path))
        for index, archives_id in enumerate(archive_ids, start=1):
            dir_path = os.path.join(type_path, archives_id)
            if not os.path.isdir(dir_path):
                continue
            main_file = pick_main_file(dir_path)
            if main_file is None:
                errors.append(f"{archives_id}: 无弹幕文件")
                continue
            try:
                counts[archives_id] = count_comments(main_file)
            except Exception as exc:
                errors.append(f"{archives_id}: {exc}")
            if index % 50 == 0:
                print(f"{type_dir}: 已处理 {index}/{len(archive_ids)}")

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(counts, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")
    print(f"已统计 {len(counts)} 场，输出: {out_path}")
    for line in errors:
        print(f"[异常] {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
