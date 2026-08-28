"""画廊图片元数据持久化。

元数据是用户数据（上传者、标签、备注等），必须存放在数据目录而非缓存目录，
与可重建的哈希索引分离；结构对齐 GalleryImageIndex：相对路径做键 + 原子写 + 锁保护。
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from threading import RLock
from typing import Callable

from pydantic import BaseModel, ValidationError

from ._atomic import atomic_write_text

logger = logging.getLogger(__name__)

META_INDEX_FILE_NAME = "picture_meta_v1.json"


class PictureMeta(BaseModel):
    """单张图片的元数据；字段全部可选，保证旧数据向后兼容"""

    uploader_id: str | None = None
    """上传者用户 ID"""

    uploader_name: str | None = None
    """上传者昵称"""

    added_at: datetime | None = None
    """入库时间"""

    tags: list[str] = []
    """标签"""

    note: str | None = None
    """备注"""

    source: str | None = None
    """来源说明（URL 或文字）"""


class PictureMetaIndex:
    """相对路径 -> 元数据 的持久化索引"""

    def __init__(self, root: Path):
        self._lock = RLock()
        self._root = root.resolve()
        self._entries: dict[str, dict] = {}
        self._load()

    def _index_path(self) -> Path:
        return self._root / META_INDEX_FILE_NAME

    def _load(self) -> None:
        try:
            data = json.loads(self._index_path().read_text(encoding="utf-8"))
            if data.get("version") == 1 and isinstance(data.get("entries"), dict):
                self._entries = data["entries"]
        except FileNotFoundError:
            pass
        except (OSError, ValueError, TypeError) as e:
            logger.warning(f"无法加载图片元数据索引 {self._index_path()}，将使用空索引：{e}")

    def _relative(self, path: Path) -> str:
        return path.resolve().relative_to(self._root).as_posix()

    def get(self, path: Path) -> PictureMeta:
        with self._lock:
            return self._get_locked(path)

    def _get_locked(self, path: Path) -> PictureMeta:
        entry = self._entries.get(self._relative(path))
        if entry is None:
            return PictureMeta()
        try:
            return PictureMeta.model_validate(entry)
        except ValidationError:
            logger.warning(f"图片元数据损坏，已回退为默认值：{self._relative(path)}")
            return PictureMeta()

    def record_many(self, paths: list[Path], meta: PictureMeta) -> None:
        """批量记录新入库图片的元数据"""
        with self._lock:
            for path in paths:
                self._entries[self._relative(path)] = meta.model_dump(mode="json")
            self._save()

    def update(
        self,
        path: Path,
        transform: Callable[[PictureMeta], PictureMeta],
    ) -> PictureMeta:
        """在锁内完成单个图片元数据的读改写"""
        with self._lock:
            meta = transform(self._get_locked(path))
            self._entries[self._relative(path)] = meta.model_dump(mode="json")
            self._save()
            return meta

    def remove(self, path: Path) -> None:
        with self._lock:
            try:
                relative = self._relative(path)
            except ValueError:
                return
            if self._entries.pop(relative, None) is not None:
                self._save()

    def remove_gallery(self, name: str) -> None:
        with self._lock:
            prefix = f"{Path(name).as_posix()}/"
            removed = False
            for relative in tuple(self._entries):
                if relative.startswith(prefix):
                    removed = self._entries.pop(relative, None) is not None or removed
            if removed:
                self._save()

    def find_by_tags(self, tags: list[str]) -> list[Path]:
        """返回同时含有所有指定标签且文件仍存在的图片路径（AND 语义）"""
        wanted = set(tags)
        if not wanted:
            return []

        with self._lock:
            items = tuple(self._entries.items())

        result: list[Path] = []
        for relative, entry in items:
            try:
                meta = PictureMeta.model_validate(entry)
            except ValidationError:
                continue
            if wanted <= set(meta.tags):
                path = self._root / relative
                if path.is_file():
                    result.append(path)
        return result

    def _save(self) -> None:
        try:
            atomic_write_text(
                self._index_path(),
                json.dumps(
                    {"version": 1, "entries": self._entries},
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            )
        except OSError as e:
            logger.warning(f"无法保存图片元数据索引：{e}")


_picture_meta_index: PictureMetaIndex | None = None


def get_picture_meta_index() -> PictureMetaIndex:
    global _picture_meta_index
    if _picture_meta_index is None:
        from .config import cfg

        _picture_meta_index = PictureMetaIndex(cfg.data_dir_path)
    return _picture_meta_index
