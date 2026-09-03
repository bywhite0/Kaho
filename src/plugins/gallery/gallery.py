import json
import shutil
from dataclasses import dataclass, field
from functools import cache, lru_cache
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from threading import RLock

from emoji import emoji_list
from nonebot import logger
from PIL import Image, ImageDraw, ImageFont, ImageOps

from .compat import atomic_write_text
from .config import cfg, gallery_name_data
from .image_hash import ImageHashes, calculate_image_hashes, perceptual_distances
from .names import DEFAULT_MODE, MODE_LABELS, GalleryMode


@dataclass(frozen=True)
class DuplicatePicture:
    candidate_index: int
    candidate_path: Path
    existing_path: Path
    reason: str


@dataclass(frozen=True)
class AddPicturesResult:
    added_count: int
    duplicates: list[DuplicatePicture]
    duplicate_image: bytes | None = None
    saved_paths: list[Path] = field(default_factory=list)

    def summary(self, gallery_name: str) -> str:
        lines: list[str] = []
        if self.duplicates:
            lines.append(f"检测到 {len(self.duplicates)} 张重复图片，已跳过。")
            lines.append("如需跳过查重强制添加，请在添加图片命令末尾加上 force 参数。")
        lines.append(f"成功添加 {self.added_count} 张图片到画廊 {gallery_name}。")
        return "\n".join(lines)


@dataclass(frozen=True)
class GalleryOverviewItem:
    name: str
    aliases: list[str]
    picture_count: int
    cover_path: Path | None
    mode: GalleryMode = DEFAULT_MODE


def get_gallery_name(name_or_alias: str) -> str | None:
    """根据名称或别名获取画廊名称"""
    v = gallery_name_data.instance
    if name_or_alias in v.name_to_aliases:
        return name_or_alias
    return v.alias_to_name.get(name_or_alias)


def get_picture_by_id(pic_id: int) -> Path | None:
    """根据图片id获取图片文件路径"""
    return _gallery_index.get_picture_by_id(pic_id)


def get_gallery_mode(name: str) -> GalleryMode:
    """读取画廊模式；缺失或被手工改坏的值一律回退到默认模式"""
    raw = gallery_name_data.instance.name_to_mode.get(name)
    return raw if raw in MODE_LABELS else DEFAULT_MODE


def set_gallery_mode(name: str, mode: GalleryMode) -> None:
    """设置画廊模式；等于默认值时删除条目，保持索引文件精简"""
    v = gallery_name_data.instance
    if mode == DEFAULT_MODE:
        v.name_to_mode.pop(name, None)
    else:
        v.name_to_mode[name] = mode
    gallery_name_data.save_to_file()
    invalidate_gallery_render_cache()


def is_gallery_hidden(name: str) -> bool:
    """off 模式的画廊对非超级用户完全不可见"""
    return get_gallery_mode(name) == "off"


def is_gallery_writable(name: str) -> bool:
    """只有 edit 模式允许非超级用户增删图片与别名"""
    return get_gallery_mode(name) == "edit"


def set_gallery_cover(name: str, pic_id: int) -> None:
    gallery_name_data.instance.name_to_cover[name] = pic_id
    gallery_name_data.save_to_file()
    invalidate_gallery_render_cache()


def clear_gallery_cover(name: str) -> None:
    if gallery_name_data.instance.name_to_cover.pop(name, None) is not None:
        gallery_name_data.save_to_file()
        invalidate_gallery_render_cache()


def _picture_id_of(path: Path) -> int | None:
    """图片文件名即其 id；无法解析的文件（如手工放入的杂项）返回 None"""
    try:
        return int(path.stem)
    except ValueError:
        return None


def list_picture_ids(*, include_hidden: bool = False) -> list[int]:
    """按升序返回全部图片 id，供负数索引（看 -1 取最新一张）使用"""
    ids: list[int] = []
    for name in gallery_name_data.instance.name_to_aliases:
        if not include_hidden and is_gallery_hidden(name):
            continue
        gallery_dir = cfg.data_dir_path / name
        if not gallery_dir.is_dir():
            continue
        for path in gallery_dir.iterdir():
            if path.is_file() and (pic_id := _picture_id_of(path)) is not None:
                ids.append(pic_id)
    ids.sort()
    return ids


def resolve_picture_index(index: int, *, include_hidden: bool = False) -> int | None:
    """把负数索引换算为真实图片 id：-1 是最新入库的一张"""
    if index >= 0:
        return index
    ids = list_picture_ids(include_hidden=include_hidden)
    if not ids or index < -len(ids):
        return None
    return ids[index]


def save_pictures(name: str, pic_paths: list[Path]) -> list[Path]:
    """保存图片文件到画廊目录"""
    gallery_dir = cfg.data_dir_path / name
    gallery_dir.mkdir(parents=True, exist_ok=True)

    v = gallery_name_data.instance
    saved_paths: list[Path] = []
    for pic_path in pic_paths:
        # 生成图片文件名
        pic_id = v.iota + 1
        v.iota = pic_id
        suffix = pic_path.suffix
        new_pic_path = gallery_dir / f"{pic_id}{suffix}"
        shutil.copy(pic_path, new_pic_path)
        saved_paths.append(new_pic_path)

    if saved_paths:
        _gallery_index.record_many(saved_paths)

    gallery_name_data.save_to_file()
    if saved_paths:
        invalidate_gallery_render_cache()
        invalidate_gallery_render_cache(name)
    return saved_paths


def add_pictures(
    name: str,
    pic_paths: list[Path],
    *,
    force: bool = False,
) -> AddPicturesResult:
    """Add pictures, skipping and rendering matches already in the gallery."""
    if force:
        saved_paths = save_pictures(name, pic_paths)
        return AddPicturesResult(
            added_count=len(saved_paths),
            duplicates=[],
            saved_paths=saved_paths,
        )

    unique_paths, duplicates = find_duplicate_pictures(name, pic_paths)
    saved_paths = save_pictures(name, unique_paths)
    duplicate_image = render_duplicate_comparisons(duplicates) if duplicates else None
    return AddPicturesResult(
        added_count=len(saved_paths),
        duplicates=duplicates,
        duplicate_image=duplicate_image,
        saved_paths=saved_paths,
    )


def find_duplicate_pictures(
    name: str,
    candidate_paths: list[Path],
) -> tuple[list[Path], list[DuplicatePicture]]:
    """Compare candidate pictures with files that already exist in a gallery."""
    existing_hashes = _gallery_index.hashes_for_gallery(name)
    exact_hashes: dict[str, Path] = {}
    for existing_path, hashes in existing_hashes:
        exact_hashes.setdefault(hashes.file_hash, existing_path)

    unique_paths: list[Path] = []
    duplicates: list[DuplicatePicture] = []
    for candidate_index, candidate_path in enumerate(candidate_paths, start=1):
        try:
            candidate_hashes = calculate_image_hashes(candidate_path)
        except (OSError, ValueError) as e:
            logger.warning(f"无法计算待添加图片 {candidate_path} 的哈希，将正常添加：{e}")
            unique_paths.append(candidate_path)
            continue

        if existing_path := exact_hashes.get(candidate_hashes.file_hash):
            duplicates.append(
                DuplicatePicture(
                    candidate_index=candidate_index,
                    candidate_path=candidate_path,
                    existing_path=existing_path,
                    reason="文件完全一致",
                )
            )
            continue

        best_match: tuple[int, Path, tuple[int, int, int]] | None = None
        for existing_path, hashes in existing_hashes:
            distances = perceptual_distances(candidate_hashes, hashes)
            if distances is None:
                continue
            score = sum(distances)
            if best_match is None or score < best_match[0]:
                best_match = (score, existing_path, distances)

        if best_match is None:
            unique_paths.append(candidate_path)
            continue

        _, existing_path, distances = best_match
        similar_hashes = [
            hash_name
            for hash_name, distance, threshold in zip(
                ("dHash", "pHash", "aHash"),
                distances,
                (8, 2, 2),
            )
            if distance < threshold
        ]
        duplicates.append(
            DuplicatePicture(
                candidate_index=candidate_index,
                candidate_path=candidate_path,
                existing_path=existing_path,
                reason=f"感知哈希相似：{'、'.join(similar_hashes)}",
            )
        )

    return unique_paths, duplicates


HASH_INDEX_FILE_NAME = "image_index_v2.json"
"""哈希算法变更时递增版本号：索引里缓存着按旧算法算出的哈希值，
沿用旧文件会让新旧指纹混在同一次比较里，查重结果不可预测。"""

HASH_INDEX_VERSION = 2


def _cleanup_stale_hash_index() -> None:
    """删除旧版本的哈希索引文件，避免在缓存目录里留下永不再读的孤儿文件"""
    try:
        for entry in cfg.cache_dir_path.glob("image_index_v*.json"):
            if entry.name == HASH_INDEX_FILE_NAME or not entry.is_file():
                continue
            entry.unlink()
            logger.info(f"已清理旧哈希索引文件：{entry}")
    except OSError as e:
        logger.warning(f"清理旧哈希索引失败：{e}")


class GalleryImageIndex:
    """可重建的画廊路径和图片哈希索引。"""

    def __init__(self) -> None:
        self._lock = RLock()
        self._root: Path | None = None
        self._entries: dict[str, dict[str, int | str | None]] = {}
        self._picture_ids: dict[str, str] = {}

    def _ensure_loaded(self) -> None:
        root = cfg.data_dir_path.resolve()
        if root == self._root:
            return
        self._root = root
        self._entries = {}
        self._picture_ids = {}
        try:
            data = json.loads(self._index_path().read_text(encoding="utf-8"))
            if data.get("version") == HASH_INDEX_VERSION and isinstance(data.get("entries"), dict):
                self._entries = data["entries"]
                self._picture_ids = {
                    Path(relative).stem: relative for relative in self._entries
                }
        except FileNotFoundError:
            pass
        except (OSError, ValueError, TypeError) as e:
            logger.warning(f"无法加载画廊图片索引，将自动重建：{e}")

    def _index_path(self) -> Path:
        return cfg.cache_dir_path / HASH_INDEX_FILE_NAME

    def _relative(self, path: Path) -> str:
        assert self._root is not None
        return path.resolve().relative_to(self._root).as_posix()

    @staticmethod
    def _metadata(path: Path) -> tuple[int, int]:
        stat = path.stat()
        return stat.st_size, stat.st_mtime_ns

    def _entry_for(self, path: Path) -> dict[str, int | str | None]:
        relative = self._relative(path)
        size, mtime_ns = self._metadata(path)
        entry = self._entries.get(relative)
        if entry is None or entry.get("size") != size or entry.get("mtime_ns") != mtime_ns:
            entry = {
                "size": size,
                "mtime_ns": mtime_ns,
                "file_hash": None,
                "dhash": None,
                "phash": None,
                "ahash": None,
            }
            self._entries[relative] = entry
        self._picture_ids[path.stem] = relative
        return entry

    def _remove_relative(self, relative: str) -> bool:
        if self._entries.pop(relative, None) is None:
            return False
        picture_id = Path(relative).stem
        if self._picture_ids.get(picture_id) == relative:
            self._picture_ids.pop(picture_id, None)
        return True

    def record_many(self, paths: list[Path]) -> None:
        with self._lock:
            self._ensure_loaded()
            for path in paths:
                try:
                    self._entry_for(path)
                except OSError as e:
                    logger.warning(f"无法记录画廊图片 {path}：{e}")
            self._save()

    def remove(self, path: Path) -> None:
        with self._lock:
            self._ensure_loaded()
            try:
                relative = self._relative(path)
            except ValueError:
                return
            if self._remove_relative(relative):
                self._save()

    def remove_gallery(self, name: str) -> None:
        with self._lock:
            self._ensure_loaded()
            prefix = f"{Path(name).as_posix()}/"
            removed = False
            for relative in tuple(self._entries):
                if relative.startswith(prefix):
                    removed = self._remove_relative(relative) or removed
            if removed:
                self._save()

    def get_picture_by_id(self, pic_id: int) -> Path | None:
        with self._lock:
            self._ensure_loaded()
            assert self._root is not None
            target = str(pic_id)
            changed = False

            if relative := self._picture_ids.get(target):
                path = self._root / relative
                if path.is_file():
                    return path
                changed = self._remove_relative(relative)

            if not self._root.is_dir():
                if changed:
                    self._save()
                return None
            for path in self._root.rglob(f"{target}.*"):
                if path.is_file():
                    self._entry_for(path)
                    self._save()
                    return path
            if changed:
                self._save()
            return None

    def hashes_for_gallery(self, name: str) -> list[tuple[Path, ImageHashes]]:
        with self._lock:
            self._ensure_loaded()
            assert self._root is not None
            gallery_dir = self._root / name
            if not gallery_dir.is_dir():
                return []

            current_paths = [path for path in gallery_dir.iterdir() if path.is_file()]
            current_relatives = {self._relative(path) for path in current_paths}
            prefix = f"{Path(name).as_posix()}/"
            changed = False
            for relative in tuple(self._entries):
                if relative.startswith(prefix) and relative not in current_relatives:
                    changed = self._remove_relative(relative) or changed

            result: list[tuple[Path, ImageHashes]] = []
            for path in current_paths:
                try:
                    entry = self._entry_for(path)
                    if entry["file_hash"] is None:
                        hashes = calculate_image_hashes(path)
                        entry.update(
                            file_hash=hashes.file_hash,
                            dhash=hashes.dhash,
                            phash=hashes.phash,
                            ahash=hashes.ahash,
                        )
                        changed = True
                    result.append(
                        (
                            path,
                            ImageHashes(
                                file_hash=str(entry["file_hash"]),
                                dhash=int(entry["dhash"]),
                                phash=int(entry["phash"]),
                                ahash=(int(entry["ahash"]) if entry["ahash"] is not None else None),
                            ),
                        )
                    )
                except (OSError, ValueError, TypeError) as e:
                    logger.warning(f"无法计算画廊图片 {path} 的哈希，已跳过：{e}")
            if changed:
                self._save()
            return result

    def clear_hashes(self, name: str) -> None:
        """清空某个画廊已缓存的哈希，强制下次比较时重算"""
        with self._lock:
            self._ensure_loaded()
            prefix = f"{Path(name).as_posix()}/"
            changed = False
            for relative, entry in self._entries.items():
                if relative.startswith(prefix) and entry.get("file_hash") is not None:
                    entry.update(file_hash=None, dhash=None, phash=None, ahash=None)
                    changed = True
            if changed:
                self._save()

    def _save(self) -> None:
        index_path = self._index_path()
        try:
            atomic_write_text(
                index_path,
                json.dumps(
                    {"version": HASH_INDEX_VERSION, "entries": self._entries},
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            )
        except OSError as e:
            logger.warning(f"无法保存画廊图片索引 {index_path}：{e}")


_cleanup_stale_hash_index()

_gallery_index = GalleryImageIndex()


def remove_picture_from_index(path: Path) -> None:
    _gallery_index.remove(path)


def remove_gallery_from_index(name: str) -> None:
    _gallery_index.remove_gallery(name)


def find_duplicate_groups(name: str, *, rehash: bool = False) -> list[list[int]]:
    """扫描画廊内已存在的重复图片，每组返回一串图片 id（首项是最早入库的那张）。

    入库查重只挡得住"当时可比"的图片：阈值调整、哈希算法升级、force 强制入库
    都会在库里留下漏网的重复，需要这样一次全量补扫。
    """
    if rehash:
        _gallery_index.clear_hashes(name)

    ordered: list[tuple[int, ImageHashes]] = []
    for path, hashes in _gallery_index.hashes_for_gallery(name):
        if (pic_id := _picture_id_of(path)) is not None:
            ordered.append((pic_id, hashes))
    ordered.sort(key=lambda item: item[0])

    # 贪心分组：每张图与已有各组的代表比较，命中即归入该组
    representatives: list[tuple[ImageHashes, list[int]]] = []
    for pic_id, hashes in ordered:
        for rep_hashes, members in representatives:
            same_file = rep_hashes.file_hash == hashes.file_hash
            if same_file or perceptual_distances(hashes, rep_hashes) is not None:
                members.append(pic_id)
                break
        else:
            representatives.append((hashes, [pic_id]))
    return [members for _, members in representatives if len(members) > 1]


GALLERY_COLUMNS = 10
THUMBNAIL_SIZE = (100, 75)
GALLERY_PADDING = 16
GALLERY_GAP = 8
LABEL_HEIGHT = 24

OVERVIEW_COLUMNS = 5
OVERVIEW_CELL_WIDTH = 220
OVERVIEW_COVER_SIZE = (200, 200)
OVERVIEW_HEADER_HEIGHT = 58
OVERVIEW_TEXT_GAP = 6

DUPLICATE_COLUMNS = 2
DUPLICATE_THUMBNAIL_SIZE = (180, 135)
DUPLICATE_CELL_WIDTH = 408
DUPLICATE_CELL_HEIGHT = 200
DUPLICATE_HEADER_HEIGHT = 80

RENDER_CACHE_DIR_NAME = "rendered_v2"
"""渲染逻辑（字体、布局等）变更时递增版本号，旧目录会在插件加载时被清理"""
OVERVIEW_CACHE_FILE_NAME = "overview.png"
OVERVIEW_ALL_CACHE_FILE_NAME = "overview_all.png"
"""总览按可见范围分两份缓存：普通用户看不到 off 画廊，超级用户要看到全部"""


def _cleanup_stale_render_cache() -> None:
    """删除旧版本的渲染缓存目录，避免渲染逻辑变更后继续发送旧图"""
    try:
        for entry in cfg.cache_dir_path.glob("rendered_v*"):
            if entry.name == RENDER_CACHE_DIR_NAME or not entry.is_dir():
                continue
            shutil.rmtree(entry)
            logger.info(f"已清理旧渲染缓存目录：{entry}")
    except OSError as e:
        logger.warning(f"清理旧渲染缓存失败：{e}")


_cleanup_stale_render_cache()


def _render_cache_path(name: str | None = None, *, include_hidden: bool = False) -> Path:
    cache_dir = cfg.cache_dir_path / RENDER_CACHE_DIR_NAME
    if name is None:
        if include_hidden:
            return cache_dir / OVERVIEW_ALL_CACHE_FILE_NAME
        return cache_dir / OVERVIEW_CACHE_FILE_NAME
    cache_key = sha256(name.encode()).hexdigest()
    return cache_dir / f"gallery_{cache_key}.png"


def _read_render_cache(cache_path: Path) -> bytes | None:
    try:
        return cache_path.read_bytes()
    except FileNotFoundError:
        return None
    except OSError as e:
        logger.warning(f"无法读取画廊渲染缓存 {cache_path}，将重新渲染：{e}")
        return None


def _write_render_cache(cache_path: Path, image: bytes) -> None:
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(image)
    except OSError as e:
        logger.warning(f"无法写入画廊渲染缓存 {cache_path}：{e}")


def invalidate_gallery_render_cache(name: str | None = None) -> None:
    """Invalidate the overview cache or one gallery's thumbnail cache."""
    if name is None:
        cache_paths = [
            _render_cache_path(include_hidden=False),
            _render_cache_path(include_hidden=True),
        ]
    else:
        cache_paths = [_render_cache_path(name)]
    for cache_path in cache_paths:
        try:
            cache_path.unlink(missing_ok=True)
        except OSError as e:
            logger.warning(f"无法删除画廊渲染缓存 {cache_path}：{e}")


def render_gallery_thumbnails(name: str, pic_files: list[Path]) -> bytes:
    """按图片 ID 排序并渲染画廊缩略图。"""
    cache_path = _render_cache_path(name)
    if (cached_image := _read_render_cache(cache_path)) is not None:
        return cached_image

    numbered_files: list[tuple[int, Path]] = []
    for pic_file in pic_files:
        if (pic_id := _picture_id_of(pic_file)) is None:
            logger.warning(f"画廊目录中的 {pic_file} 不是以图片 id 命名的文件，已跳过")
            continue
        numbered_files.append((pic_id, pic_file))

    thumbnails: list[tuple[int, Image.Image]] = []
    for pic_id, pic_file in sorted(numbered_files):
        try:
            thumbnails.append((pic_id, _load_thumbnail(pic_file, THUMBNAIL_SIZE)))
        except OSError as e:
            logger.warning(f"无法读取画廊图片 {pic_file}，已跳过：{e}")

    if not thumbnails:
        return b""

    columns = min(GALLERY_COLUMNS, len(thumbnails))
    rows = (len(thumbnails) + columns - 1) // columns
    cell_width = THUMBNAIL_SIZE[0]
    cell_height = THUMBNAIL_SIZE[1] + LABEL_HEIGHT
    canvas_width = GALLERY_PADDING * 2 + columns * cell_width + (columns - 1) * GALLERY_GAP
    canvas_height = GALLERY_PADDING * 2 + rows * cell_height + (rows - 1) * GALLERY_GAP
    canvas = Image.new("RGB", (canvas_width, canvas_height), "white")
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default(size=24)

    for index, (pic_id, thumbnail) in enumerate(thumbnails):
        row, column = divmod(index, columns)
        cell_x = GALLERY_PADDING + column * (cell_width + GALLERY_GAP)
        cell_y = GALLERY_PADDING + row * (cell_height + GALLERY_GAP)
        image_x = cell_x + (cell_width - thumbnail.width) // 2
        image_y = cell_y + (THUMBNAIL_SIZE[1] - thumbnail.height) // 2
        canvas.paste(thumbnail, (image_x, image_y), thumbnail)

        label = str(pic_id)
        label_box = draw.textbbox((0, 0), label, font=font)
        label_width = label_box[2] - label_box[0]
        label_x = cell_x + (cell_width - label_width) // 2
        label_y = cell_y + THUMBNAIL_SIZE[1] + 4
        draw.text((label_x, label_y), label, fill="black", font=font)

    output = BytesIO()
    canvas.save(output, format="PNG")
    image = output.getvalue()
    _write_render_cache(cache_path, image)
    return image


def get_gallery_overview_items(*, include_hidden: bool = False) -> list[GalleryOverviewItem]:
    """Collect cover and metadata for every gallery in index order."""
    items: list[GalleryOverviewItem] = []
    cover_ids = gallery_name_data.instance.name_to_cover
    for name, aliases in gallery_name_data.instance.name_to_aliases.items():
        mode = get_gallery_mode(name)
        if not include_hidden and mode == "off":
            continue
        gallery_dir = cfg.data_dir_path / name
        if not gallery_dir.is_dir():
            logger.warning(f"画廊索引中存在画廊名称 {name}，但对应的目录不存在：{gallery_dir}")
            items.append(GalleryOverviewItem(name, list(aliases), 0, None, mode))
            continue

        picture_paths: dict[int, Path] = {}
        for path in gallery_dir.iterdir():
            if path.is_file() and (pic_id := _picture_id_of(path)) is not None:
                picture_paths[pic_id] = path

        cover_path = picture_paths.get(cover_ids.get(name, -1))
        if cover_path is None and picture_paths:
            # 未指定封面（或指定的图已被删除）时退回 id 最小的一张，保证结果稳定
            cover_path = picture_paths[min(picture_paths)]
        items.append(
            GalleryOverviewItem(
                name=name,
                aliases=list(aliases),
                picture_count=len(picture_paths),
                cover_path=cover_path,
                mode=mode,
            )
        )
    return items


def render_gallery_overview(*, include_hidden: bool = False) -> bytes:
    """Render all gallery covers and metadata as an image."""
    cache_path = _render_cache_path(include_hidden=include_hidden)
    if (cached_image := _read_render_cache(cache_path)) is not None:
        return cached_image

    items = get_gallery_overview_items(include_hidden=include_hidden)
    if not items:
        return b""

    title_font = _load_font(25, bold=True)
    name_font = _load_font(20, bold=True)
    detail_font = _load_font(15)
    columns = min(OVERVIEW_COLUMNS, len(items))
    text_width = OVERVIEW_COVER_SIZE[0]

    measure_canvas = Image.new("RGB", (1, 1))
    measure_draw = ImageDraw.Draw(measure_canvas)
    prepared_items: list[tuple[GalleryOverviewItem, list[str], list[str], int]] = []
    for item in items:
        name_lines = _wrap_text(measure_draw, item.name, name_font, 20, text_width)
        aliases = "、".join(item.aliases) if item.aliases else "无"
        alias_lines = _wrap_text(
            measure_draw,
            f"别名：{aliases}",
            detail_font,
            15,
            text_width,
        )
        if item.mode != DEFAULT_MODE:
            alias_lines.append(f"状态：{MODE_LABELS[item.mode]}")
        cell_height = (
            OVERVIEW_COVER_SIZE[1]
            + OVERVIEW_TEXT_GAP
            + len(name_lines) * 27
            + 22
            + len(alias_lines) * 21
            + 8
        )
        prepared_items.append((item, name_lines, alias_lines, cell_height))

    row_heights = [
        max(prepared[3] for prepared in prepared_items[index : index + columns])
        for index in range(0, len(prepared_items), columns)
    ]
    canvas_width = GALLERY_PADDING * 2 + columns * OVERVIEW_CELL_WIDTH + (columns - 1) * GALLERY_GAP
    canvas_height = (
        OVERVIEW_HEADER_HEIGHT
        + sum(row_heights)
        + (len(row_heights) - 1) * GALLERY_GAP
        + GALLERY_PADDING
    )
    canvas = Image.new("RGB", (canvas_width, canvas_height), "white")
    draw = ImageDraw.Draw(canvas)
    draw.text(
        (GALLERY_PADDING, GALLERY_PADDING),
        f"画廊一览  共 {len(items)} 个",
        fill="#202124",
        font=title_font,
    )

    row_y = OVERVIEW_HEADER_HEIGHT
    for index, (item, name_lines, alias_lines, _) in enumerate(prepared_items):
        row, column = divmod(index, columns)
        if column == 0 and row > 0:
            row_y += row_heights[row - 1] + GALLERY_GAP
        cell_x = GALLERY_PADDING + column * (OVERVIEW_CELL_WIDTH + GALLERY_GAP)
        cover_x = cell_x + (OVERVIEW_CELL_WIDTH - OVERVIEW_COVER_SIZE[0]) // 2
        _paste_gallery_cover(canvas, draw, item.cover_path, cover_x, row_y, detail_font)

        text_x = cover_x
        text_y = row_y + OVERVIEW_COVER_SIZE[1] + OVERVIEW_TEXT_GAP
        for line in name_lines:
            _draw_text_with_emoji(
                canvas,
                draw,
                (text_x, text_y),
                line,
                name_font,
                20,
                fill="#202124",
            )
            text_y += 27
        draw.text(
            (text_x, text_y),
            f"图片：{item.picture_count} 张",
            fill="#5f6368",
            font=detail_font,
        )
        text_y += 22
        for line in alias_lines:
            _draw_text_with_emoji(
                canvas,
                draw,
                (text_x, text_y),
                line,
                detail_font,
                15,
                fill="#5f6368",
            )
            text_y += 21

    output = BytesIO()
    canvas.save(output, format="PNG")
    image = output.getvalue()
    _write_render_cache(cache_path, image)
    return image


def _paste_gallery_cover(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    cover_path: Path | None,
    x: int,
    y: int,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
) -> None:
    background = Image.new("RGB", OVERVIEW_COVER_SIZE, "#f1f3f4")
    canvas.paste(background, (x, y))
    if cover_path is not None:
        try:
            thumbnail = _load_cover(cover_path, OVERVIEW_COVER_SIZE)
        except OSError as e:
            logger.warning(f"无法读取画廊封面 {cover_path}，将显示占位图：{e}")
        else:
            canvas.paste(thumbnail, (x, y), thumbnail)
            return

    placeholder = "暂无图片"
    box = draw.textbbox((0, 0), placeholder, font=font)
    text_width = box[2] - box[0]
    text_height = box[3] - box[1]
    draw.text(
        (
            x + (OVERVIEW_COVER_SIZE[0] - text_width) // 2,
            y + (OVERVIEW_COVER_SIZE[1] - text_height) // 2 - box[1],
        ),
        placeholder,
        fill="#80868b",
        font=font,
    )


def _wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    font_size: int,
    max_width: int,
) -> list[str]:
    lines: list[str] = []
    current_line = ""
    for text_unit in _iter_text_units(text):
        candidate = current_line + text_unit
        if current_line and _text_length(draw, candidate, font, font_size) > max_width:
            lines.append(current_line)
            current_line = text_unit
        else:
            current_line = candidate
    if current_line or not lines:
        lines.append(current_line)
    return lines


def _iter_text_units(text: str):
    """Yield normal characters and whole emoji sequences as wrapping units."""
    emoji_matches = emoji_list(text)
    match_index = 0
    character_index = 0
    while character_index < len(text):
        if (
            match_index < len(emoji_matches)
            and character_index == emoji_matches[match_index]["match_start"]
        ):
            match = emoji_matches[match_index]
            yield match["emoji"]
            character_index = match["match_end"]
            match_index += 1
            continue
        yield text[character_index]
        character_index += 1


def _text_segments(text: str) -> list[tuple[str, bool]]:
    """Split text into normal-font and emoji-font runs."""
    matches = emoji_list(text)
    if not matches:
        return [(text, False)]

    segments: list[tuple[str, bool]] = []
    start = 0
    for match in matches:
        match_start = match["match_start"]
        if match_start > start:
            segments.append((text[start:match_start], False))
        segments.append((match["emoji"], True))
        start = match["match_end"]
    if start < len(text):
        segments.append((text[start:], False))
    return segments


def _text_length(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    font_size: int,
) -> float:
    width = 0.0
    for segment, is_emoji in _text_segments(text):
        if is_emoji and (emoji_image := _render_emoji(segment, font_size)) is not None:
            width += emoji_image.width
        else:
            width += draw.textlength(segment, font=font)
    return width


def _draw_text_with_emoji(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    position: tuple[int, int],
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    font_size: int,
    *,
    fill: str,
) -> None:
    x, y = position
    for segment, is_emoji in _text_segments(text):
        emoji_image = _render_emoji(segment, font_size) if is_emoji else None
        if emoji_image is not None:
            emoji_y = y + max(0, (font_size + 4 - emoji_image.height) // 2)
            canvas.paste(emoji_image, (round(x), emoji_y), emoji_image)
            x += emoji_image.width
            continue
        draw.text((x, y), segment, fill=fill, font=font)
        x += draw.textlength(segment, font=font)


@lru_cache(maxsize=256)
def _render_emoji(text: str, font_size: int) -> Image.Image | None:
    font = _load_emoji_font(font_size)
    if font is None:
        return None

    try:
        box = font.getbbox(text)
        width = box[2] - box[0]
        height = box[3] - box[1]
        if width <= 0 or height <= 0:
            return None
        source = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        ImageDraw.Draw(source).text(
            (-box[0], -box[1]),
            text,
            font=font,
            embedded_color=True,
        )
    except (OSError, ValueError):
        return None

    target_height = font_size + 4
    target_width = max(1, round(width * target_height / height))
    return source.resize((target_width, target_height), Image.Resampling.LANCZOS)


@cache
def _load_emoji_font(font_size: int) -> ImageFont.FreeTypeFont | None:
    font_names = (
        "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
        "/usr/local/share/fonts/NotoColorEmoji.ttf",
        "NotoColorEmoji.ttf",
        "seguiemj.ttf",
    )
    for font_name in font_names:
        for size in (font_size, 109, 128, 160):
            try:
                return ImageFont.truetype(font_name, size=size)
            except OSError:
                continue
    return None


def _load_font(
    size: int,
    *,
    bold: bool = False,
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    # 裸文件名由 PIL 在系统字体目录中搜索（Windows: C:\Windows\Fonts，Linux: XDG 字体目录）
    # 优先 Noto/思源系与国产厂商字体，微软雅黑、黑体作为 Windows 最后回退
    font_names = (
        (
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
            "NotoSansCJK-Bold.ttc",
            "NotoSansSC-Bold.ttf",
            "SourceHanSansSC-Bold.otf",
            "HarmonyOS_Sans_SC_Bold.ttf",
            "MiSans-Bold.ttf",
            "msyhbd.ttc",
            "simhei.ttf",
        )
        if bold
        else (
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "NotoSansCJK-Regular.ttc",
            "NotoSansSC-Regular.ttf",
            "SourceHanSansSC-Regular.otf",
            "HarmonyOS_Sans_SC_Regular.ttf",
            "MiSans-Regular.ttf",
            "msyh.ttc",
            "simhei.ttf",
        )
    )
    for font_name in font_names:
        try:
            return ImageFont.truetype(font_name, size=size)
        except OSError:
            continue
    logger.warning("未找到 CJK 字体，回退到 PIL 默认字体，中文将无法正常渲染")
    return ImageFont.load_default(size=size)


def _load_thumbnail(image_path: Path, size: tuple[int, int]) -> Image.Image:
    with Image.open(image_path) as source:
        source = ImageOps.exif_transpose(source)
        thumbnail = ImageOps.contain(
            source.convert("RGBA"),
            size,
            Image.Resampling.LANCZOS,
        )
        return thumbnail.copy()


def _load_cover(image_path: Path, size: tuple[int, int]) -> Image.Image:
    with Image.open(image_path) as source:
        source = ImageOps.exif_transpose(source)
        cover = ImageOps.fit(
            source.convert("RGBA"),
            size,
            Image.Resampling.LANCZOS,
        )
        return cover.copy()


def render_duplicate_comparisons(duplicates: list[DuplicatePicture]) -> bytes:
    """Render candidate and existing pictures side by side."""
    if not duplicates:
        return b""

    columns = min(DUPLICATE_COLUMNS, len(duplicates))
    rows = (len(duplicates) + columns - 1) // columns
    canvas_width = GALLERY_PADDING * 2 + columns * DUPLICATE_CELL_WIDTH
    canvas_height = DUPLICATE_HEADER_HEIGHT + GALLERY_PADDING + rows * DUPLICATE_CELL_HEIGHT
    canvas = Image.new("RGB", (canvas_width, canvas_height), "white")
    draw = ImageDraw.Draw(canvas)
    title_font = _load_font(24, bold=True)
    label_font = _load_font(17, bold=True)
    detail_font = _load_font(14)
    draw.text(
        (GALLERY_PADDING, GALLERY_PADDING),
        f"检测到 {len(duplicates)} 张重复图片",
        fill="#202124",
        font=title_font,
    )
    draw.text(
        (GALLERY_PADDING, GALLERY_PADDING + 32),
        "如需跳过查重，请在添加图片命令末尾加上 force 参数",
        fill="#5f6368",
        font=detail_font,
    )

    for index, duplicate in enumerate(duplicates):
        row, column = divmod(index, columns)
        cell_x = GALLERY_PADDING + column * DUPLICATE_CELL_WIDTH
        cell_y = DUPLICATE_HEADER_HEIGHT + row * DUPLICATE_CELL_HEIGHT
        if column:
            draw.line(
                (cell_x, cell_y, cell_x, cell_y + DUPLICATE_CELL_HEIGHT - 12),
                fill="#dadce0",
                width=1,
            )

        left_x = cell_x + 8
        right_x = cell_x + 220
        image_y = cell_y + 28
        _paste_comparison_thumbnail(canvas, duplicate.candidate_path, left_x, image_y)
        _paste_comparison_thumbnail(canvas, duplicate.existing_path, right_x, image_y)
        draw.text(
            (left_x, cell_y + 2),
            f"待添加 #{duplicate.candidate_index}",
            fill="#202124",
            font=label_font,
        )
        existing_id = duplicate.existing_path.stem
        draw.text(
            (right_x, cell_y + 2),
            f"画廊已有 #{existing_id}",
            fill="#202124",
            font=label_font,
        )
        draw.text(
            (cell_x + 198, image_y + 54),
            "=",
            fill="#d93025",
            font=title_font,
        )
        draw.text(
            (left_x, image_y + DUPLICATE_THUMBNAIL_SIZE[1] + 5),
            duplicate.reason,
            fill="#5f6368",
            font=detail_font,
        )

    output = BytesIO()
    canvas.save(output, format="PNG")
    return output.getvalue()


def _paste_comparison_thumbnail(
    canvas: Image.Image,
    image_path: Path,
    x: int,
    y: int,
) -> None:
    thumbnail = _load_thumbnail(image_path, DUPLICATE_THUMBNAIL_SIZE)
    background = Image.new("RGB", DUPLICATE_THUMBNAIL_SIZE, "#f1f3f4")
    background_x = x
    background_y = y
    canvas.paste(background, (background_x, background_y))
    image_x = x + (DUPLICATE_THUMBNAIL_SIZE[0] - thumbnail.width) // 2
    image_y = y + (DUPLICATE_THUMBNAIL_SIZE[1] - thumbnail.height) // 2
    canvas.paste(thumbnail, (image_x, image_y), thumbnail)
