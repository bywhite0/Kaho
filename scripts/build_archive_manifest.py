"""归档 manifest 生成与校验脚本。

用法：
    uv run python scripts/build_archive_manifest.py build <archive_root>
    uv run python scripts/build_archive_manifest.py verify <archive_root>
"""

import argparse
import hashlib
import json
import os
import sys

MANIFEST_NAME = "manifest.json"
CHUNK_SIZE = 1024 * 1024
PROGRESS_STEP = 500


def iter_files(root):
    # 遍历归档文件，跳过 manifest 自身
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in sorted(filenames):
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, root).replace(os.sep, "/")
            if rel == MANIFEST_NAME:
                continue
            yield rel, path


def hash_file(path):
    # 流式计算 SHA-256
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(CHUNK_SIZE), b""):
            h.update(chunk)
    return h.hexdigest()


def build(root):
    entries = {}
    total_size = 0
    for index, (rel, path) in enumerate(iter_files(root), start=1):
        size = os.path.getsize(path)
        entries[rel] = {"size": size, "sha256": hash_file(path)}
        total_size += size
        if index % PROGRESS_STEP == 0:
            print(f"已处理 {index} 个文件...")
    manifest = {
        "file_count": len(entries),
        "total_size": total_size,
        "files": entries,
    }
    manifest_path = os.path.join(root, MANIFEST_NAME)
    with open(manifest_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print(f"manifest 已生成: {manifest_path}")
    print(f"文件数: {len(entries)}, 总大小: {total_size / (1024 ** 3):.2f} GiB")
    return 0


def verify(root):
    manifest_path = os.path.join(root, MANIFEST_NAME)
    if not os.path.exists(manifest_path):
        print(f"缺少 manifest: {manifest_path}")
        return 1
    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)
    expected = manifest.get("files", {})
    actual = dict(iter_files(root))
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    corrupted = []
    checked = 0
    for rel, meta in expected.items():
        path = actual.get(rel)
        if path is None:
            continue
        if os.path.getsize(path) != meta["size"] or hash_file(path) != meta["sha256"]:
            corrupted.append(rel)
        checked += 1
        if checked % PROGRESS_STEP == 0:
            print(f"已校验 {checked}/{len(expected)} 个文件...")
    for label, items in (("缺失", missing), ("损坏", corrupted), ("多余", extra)):
        for rel in items:
            print(f"[{label}] {rel}")
    if missing or corrupted:
        print(f"校验失败: 缺失 {len(missing)}, 损坏 {len(corrupted)}, 多余 {len(extra)}")
        return 1
    print(f"校验通过: {len(expected)} 个文件, 多余 {len(extra)} 个")
    return 0


def main():
    parser = argparse.ArgumentParser(description="归档 manifest 生成与校验")
    sub = parser.add_subparsers(dest="command", required=True)
    p_build = sub.add_parser("build", help="生成 manifest")
    p_build.add_argument("root", help="归档根目录")
    p_verify = sub.add_parser("verify", help="按 manifest 校验")
    p_verify.add_argument("root", help="归档根目录")
    args = parser.parse_args()
    root = os.path.realpath(args.root)
    if not os.path.isdir(root):
        print(f"目录不存在: {root}")
        return 1
    if args.command == "build":
        return build(root)
    return verify(root)


if __name__ == "__main__":
    sys.exit(main())
