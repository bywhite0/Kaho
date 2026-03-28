import os

from src.core.services.file_db import FileDB
from src.core.services.masterdata_cache import MasterDataCacheManager
from src.core.services.music_chart_cache import MusicChartCache

try:
    from nonebot import logger
except ImportError:
    import logging

    logger = logging.getLogger("DataStore")
    logging.basicConfig(level=logging.INFO)


class DataStore:
    def __init__(self, data_dir):
        self.data_dir = os.path.realpath(data_dir)
        self.project_root = self._resolve_project_root()
        self.store_dir = os.path.join(self.project_root, "data", "llll")
        self.state_path = os.path.join(self.store_dir, "state.json")
        self.masterdata_cache_dir = os.path.join(self.store_dir, "masterdata", "cache")
        self.music_chart_cache_dir = os.path.join(self.store_dir, "music_charts")

        os.makedirs(self.store_dir, exist_ok=True)
        self._state_db = FileDB(self.state_path)
        self._masterdata_cache = MasterDataCacheManager(
            self.data_dir,
            self.masterdata_cache_dir,
            self._state_db,
        )
        self._music_chart_cache = MusicChartCache(self.music_chart_cache_dir)
        logger.info(f"文件存储已初始化: {self.store_dir}")

    def close(self):
        self._state_db.save()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    def _resolve_project_root(self):
        return os.path.abspath(os.path.join(self.data_dir, ".."))

    def save_music_chart(self, music_id, data):
        self._music_chart_cache.set(int(music_id), data)

    def get_music_chart(self, music_id):
        return self._music_chart_cache.get(int(music_id))

    def load_yaml_file(self, filename, sanitizer=None):
        return self._masterdata_cache.load_yaml_file(filename, sanitizer=sanitizer)

    def get_meta(self, key):
        return self._state_db.get(f"meta.{key}")

    def set_meta(self, key, value):
        self._state_db.set(f"meta.{key}", value)

    def sync_version(self, version_path, sanitizer=None):
        if not os.path.exists(version_path):
            logger.warning(f"版本文件不存在: {version_path}")
            return False
        with open(version_path, "r", encoding="utf-8") as f:
            version = f.read().strip()
        stored = self.get_meta("current_version")
        logger.info(f"读取当前版本: cache={stored or '-'} file={version or '-'}")
        if stored == version:
            logger.info("版本未变化，跳过更新。")
            return False
        changed = self._masterdata_cache.sync_incremental(sanitizer=sanitizer)
        self.set_meta("current_version", version)
        self.set_meta("last_sync_changed", changed)
        logger.info(f"版本已更新: {version}，变更行数: {changed}")
        return True

    def rebuild(self, version_path, sanitizer=None):
        logger.info("开始重建缓存...")
        if os.path.exists(version_path):
            with open(version_path, "r", encoding="utf-8") as f:
                version = f.read().strip()
            self.set_meta("current_version", version)
            logger.info(f"重建版本设置为: {version}")
        else:
            self.set_meta("current_version", "")
            logger.warning(f"版本文件不存在: {version_path}")
        changed = self._masterdata_cache.rebuild_all(sanitizer=sanitizer)
        self.set_meta("last_rebuild_changed", changed)
        logger.info(f"重建完成，变更行数: {changed}")
        return changed
