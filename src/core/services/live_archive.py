import json
import os
import re
from datetime import datetime
from typing import Any, Optional

try:
    from nonebot import logger
except ImportError:
    import logging

    logger = logging.getLogger("LiveArchive")

LIVE_TYPE_NAMES = {1: "Fes×LIVE", 2: "With×MEETS"}

_UUID_URL_RE = re.compile(r"/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\.(\w+)$")
_COVER_EXTS = ("jpg", "png", "jpeg", "webp")


def _project_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def _default_data_dir() -> str:
    # 默认使用仓库内 submodule 的 data 目录
    path = os.path.join(_project_root(), "external", "linkura-live-data", "data")
    return path if os.path.isdir(path) else ""


def _parse_time(value: Any) -> Optional[datetime]:
    # 解析 ISO8601，兼容毫秒与 Z 后缀
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _load_json(path: str) -> Any:
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.warning(f"读取配信归档数据失败: {path} error={exc}")
        return None


class LiveArchiveService:
    """停服后配信归档数据的只读查询入口。

    数据源为 linkura-live-data 的 archive.json / archive-details.json，
    封面为本地 UUID 命名文件，弹幕数为离线预计算结果。
    """

    def __init__(
        self,
        data_dir: Optional[str] = None,
        covers_dir: Optional[str] = None,
        comment_counts_path: Optional[str] = None,
    ):
        root = _project_root()
        self.data_dir = (
            data_dir or os.getenv("LIVE_ARCHIVE_DATA_DIR", "") or _default_data_dir()
        )
        self.covers_dir = covers_dir or os.path.join(
            root, "cache", "game_api", "archive_covers"
        )
        self.comment_counts_path = comment_counts_path or os.path.join(
            root, "data", "llll", "comment_counts.json"
        )
        self._loaded = False
        self._archives: list[dict] = []
        self._by_id: dict[str, dict] = {}
        self._details: dict[str, dict] = {}
        self._comment_counts: dict[str, int] = {}

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self.data_dir:
            logger.info(
                "未找到配信归档数据目录（submodule 或 LIVE_ARCHIVE_DATA_DIR），功能不可用。"
            )
            return

        archives = _load_json(os.path.join(self.data_dir, "archive.json"))
        if not isinstance(archives, list):
            return
        details = _load_json(os.path.join(self.data_dir, "archive-details.json"))
        counts = _load_json(self.comment_counts_path)

        valid = [a for a in archives if isinstance(a, dict) and a.get("archives_id")]
        valid.sort(key=lambda a: a.get("live_start_time") or "", reverse=True)
        self._archives = valid
        self._by_id = {a["archives_id"]: a for a in valid}
        if isinstance(details, dict):
            self._details = {k: v for k, v in details.items() if isinstance(v, dict)}
        if isinstance(counts, dict):
            self._comment_counts = {
                k: v for k, v in counts.items() if isinstance(v, int)
            }
        logger.info(
            f"配信归档已加载: {len(self._archives)} 场, 详情 {len(self._details)} 条"
        )

    def available(self) -> bool:
        self._ensure_loaded()
        return bool(self._archives)

    def list_archives(
        self,
        live_type: Optional[int] = None,
        character_id: Optional[int] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
    ) -> list[dict]:
        # 返回按开始时间倒序的场次列表
        self._ensure_loaded()
        since_dt = _parse_time(since)
        until_dt = _parse_time(until)
        result = []
        for archive in self._archives:
            if live_type is not None and archive.get("live_type") != live_type:
                continue
            if since_dt or until_dt:
                start = _parse_time(archive.get("live_start_time"))
                if start is None:
                    continue
                if since_dt and start < since_dt:
                    continue
                if until_dt and start > until_dt:
                    continue
            if character_id is not None and character_id not in self.character_ids(
                archive["archives_id"]
            ):
                continue
            result.append(archive)
        return result

    def get_archive(self, archives_id: str) -> Optional[dict]:
        self._ensure_loaded()
        return self._by_id.get(archives_id)

    def get_detail(self, archives_id: str) -> Optional[dict]:
        self._ensure_loaded()
        return self._details.get(archives_id)

    def character_ids(self, archives_id: str) -> list[int]:
        # 登场角色以详情 characters 字段为准
        detail = self.get_detail(archives_id)
        if not detail:
            return []
        result = []
        for entry in detail.get("characters") or []:
            char_id = entry.get("character_id") if isinstance(entry, dict) else None
            if isinstance(char_id, int):
                result.append(char_id)
        return result

    def cover_path(self, archive: dict) -> Optional[str]:
        # 封面按 URL 中的 UUID 命中本地文件，禁止外部请求
        match = _UUID_URL_RE.search(archive.get("thumbnail_image_url") or "")
        if not match:
            return None
        uuid, url_ext = match.group(1), match.group(2).lower()
        for ext in dict.fromkeys((url_ext, *_COVER_EXTS)):
            path = os.path.join(self.covers_dir, f"{uuid}.{ext}")
            if os.path.exists(path):
                return path
        return None

    def comment_count(self, archives_id: str) -> Optional[int]:
        # 未统计到的场次返回 None，与 0 条区分
        self._ensure_loaded()
        return self._comment_counts.get(archives_id)


_service: Optional[LiveArchiveService] = None


def get_live_archive_service() -> LiveArchiveService:
    global _service
    if _service is None:
        _service = LiveArchiveService()
    return _service
