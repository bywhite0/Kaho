import hashlib
import json
import os
import sqlite3

import yaml
try:
    from nonebot import logger
except ImportError:
    import logging
    logger = logging.getLogger("DataStore")
    logging.basicConfig(level=logging.INFO)

class DataStore:
    def __init__(self, data_dir):
        self.data_dir = data_dir
        self.db_path = self._resolve_db_path()
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._conn = None
        self._init_db()
        logger.info(f"LocalStore 数据库已初始化: {self.db_path}")

    def _resolve_db_path(self):
        base_dir = None
        try:
            from nonebot_plugin_localstore import get_data_dir
            base_dir = str(get_data_dir("llll"))
        except Exception:
            base_dir = os.path.join(os.getcwd(), "localstore", "llll")
        return os.path.join(base_dir, "data.db")

    def _connect(self):
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _init_db(self):
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute(
                "CREATE TABLE IF NOT EXISTS yaml_cache (filename TEXT PRIMARY KEY, mtime REAL, data_json TEXT)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS yaml_rows (filename TEXT, id INTEGER, data_json TEXT, PRIMARY KEY (filename, id))"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS music_charts (music_id INTEGER PRIMARY KEY, data_json TEXT)"
            )
            # Migrate: add file_hash column if not exists
            try:
                conn.execute("ALTER TABLE yaml_cache ADD COLUMN file_hash TEXT DEFAULT ''")
            except sqlite3.OperationalError:
                pass  # Column already exists

    def save_music_chart(self, music_id, data):
        data_json = json.dumps(data, ensure_ascii=False, default=str)
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO music_charts (music_id, data_json) VALUES (?, ?)",
                (music_id, data_json),
            )
            
    def get_music_chart(self, music_id):
        with self._connect() as conn:
            row = conn.execute(
                "SELECT data_json FROM music_charts WHERE music_id = ?",
                (music_id,),
            ).fetchone()
            if not row:
                return None
            return json.loads(row["data_json"])

    def load_yaml_file(self, filename, sanitizer=None):
        path = os.path.join(self.data_dir, filename)
        if not os.path.exists(path):
            return None
        mtime = os.path.getmtime(path)
        # Fast path: mtime unchanged -> cache hit
        cached = self._get_cache(filename, mtime)
        if cached is not None:
            return cached
        # mtime changed or no cache: compute hash for content-level check
        file_hash = self._compute_file_hash(path)
        cached_by_hash = self._get_cache_by_hash(filename, file_hash)
        if cached_by_hash is not None:
            # Content unchanged (mtime changed, e.g. after git pull), update mtime only
            self._update_cache_mtime(filename, mtime)
            return cached_by_hash
        # True cache miss: parse YAML
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        if sanitizer:
            content = sanitizer(content)
        data = yaml.safe_load(content)
        data_json = json.dumps(data, ensure_ascii=False, default=str)
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO yaml_cache (filename, mtime, data_json, file_hash) VALUES (?, ?, ?, ?)",
                (filename, mtime, data_json, file_hash),
            )
        return data

    def _get_cache(self, filename, mtime):
        with self._connect() as conn:
            row = conn.execute(
                "SELECT data_json FROM yaml_cache WHERE filename = ? AND mtime = ?",
                (filename, mtime),
            ).fetchone()
            if not row:
                return None
            return json.loads(row["data_json"])

    def _get_cache_by_hash(self, filename, file_hash):
        """Check cache by file content hash (fallback when mtime changed)."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT data_json FROM yaml_cache WHERE filename = ? AND file_hash = ?",
                (filename, file_hash),
            ).fetchone()
            if not row:
                return None
            return json.loads(row["data_json"])

    def _update_cache_mtime(self, filename, mtime):
        """Update mtime without re-parsing (content unchanged)."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE yaml_cache SET mtime = ? WHERE filename = ?",
                (mtime, filename),
            )

    def _compute_file_hash(self, path):
        """Compute MD5 hash of file content."""
        h = hashlib.md5()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    def get_meta(self, key):
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value FROM meta WHERE key = ?",
                (key,),
            ).fetchone()
            return row["value"] if row else None

    def set_meta(self, key, value):
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                (key, value),
            )

    def sync_version(self, version_path, sanitizer=None):
        if not os.path.exists(version_path):
            logger.warning(f"版本文件不存在: {version_path}")
            return False
        with open(version_path, "r", encoding="utf-8") as f:
            version = f.read().strip()
        stored = self.get_meta("current_version")
        logger.info(f"读取当前版本: db={stored or '-'} file={version or '-'}")
        if stored == version:
            logger.info("版本未变化，跳过更新。")
            return False
        self.set_meta("current_version", version)
        inserted = self._sync_yaml_rows(sanitizer)
        logger.info(f"版本已更新: {version}，新增行数: {inserted}")
        return True

    def rebuild(self, version_path, sanitizer=None):
        logger.info("开始重建数据库...")
        with self._connect() as conn:
            conn.execute("DELETE FROM yaml_cache")
            conn.execute("DELETE FROM yaml_rows")
        if os.path.exists(version_path):
            with open(version_path, "r", encoding="utf-8") as f:
                version = f.read().strip()
            self.set_meta("current_version", version)
            logger.info(f"重建版本设置为: {version}")
        else:
            self.set_meta("current_version", "")
            logger.warning(f"版本文件不存在: {version_path}")
        inserted = self._sync_yaml_rows(sanitizer)
        logger.info(f"重建完成，新增行数: {inserted}")
        return inserted

    def _sync_yaml_rows(self, sanitizer=None):
        total_inserted = 0
        yaml_files = [
            f for f in os.listdir(self.data_dir)
            if f.lower().endswith((".yaml", ".yml"))
        ]
        conn = self._connect()
        conn.execute("BEGIN")
        try:
            for filename in sorted(yaml_files):
                data = self.load_yaml_file(filename, sanitizer)
                if not isinstance(data, list):
                    continue
                rows = []
                for entry in data:
                    if not isinstance(entry, dict):
                        continue
                    if "Id" not in entry:
                        continue
                    try:
                        entry_id = int(entry["Id"])
                    except Exception:
                        continue
                    rows.append((entry_id, entry))
                if not rows:
                    continue
                rows.sort(key=lambda x: x[0])
                max_id = self._get_max_id(filename)
                new_rows = []
                for entry_id, entry in rows:
                    if max_id is not None and entry_id <= max_id:
                        continue
                    new_rows.append((filename, entry_id, json.dumps(entry, ensure_ascii=False, default=str)))
                if new_rows:
                    conn.executemany(
                        "INSERT OR IGNORE INTO yaml_rows (filename, id, data_json) VALUES (?, ?, ?)",
                        new_rows,
                    )
                    total_inserted += len(new_rows)
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        return total_inserted

    def _get_max_id(self, filename):
        with self._connect() as conn:
            row = conn.execute(
                "SELECT MAX(id) AS max_id FROM yaml_rows WHERE filename = ?",
                (filename,),
            ).fetchone()
            return row["max_id"] if row else None
