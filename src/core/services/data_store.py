import hashlib
import json
import os
import sqlite3

import yaml
from sqlalchemy import bindparam, delete, select, text, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from src.core.services.db import (
    Base,
    MetaKV,
    MusicChart,
    YamlCache,
    YamlRow,
    create_session_factory,
    create_sqlite_engine,
)

try:
    from nonebot import logger
except ImportError:
    import logging

    logger = logging.getLogger("DataStore")
    logging.basicConfig(level=logging.INFO)


class DataStore:
    def __init__(self, data_dir):
        self.data_dir = os.path.realpath(data_dir)
        self.db_path = self._resolve_db_path()
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        self._migrate_legacy_db(self._resolve_legacy_db_path(), self.db_path)
        self._engine = create_sqlite_engine(self.db_path)
        self._session_factory = create_session_factory(self._engine)
        self._init_db()
        logger.info(f"数据库已初始化: {self.db_path}")

    def _project_root(self):
        return os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..")
        )

    def _resolve_db_path(self):
        env_path = os.getenv("KAHO_DB_PATH", "").strip()
        if env_path:
            return os.path.abspath(os.path.expanduser(env_path))
        return os.path.join(self._project_root(), "data", "llll", "data.db")

    def _resolve_legacy_db_path(self):
        return os.path.join(self._project_root(), "localstore", "llll", "data.db")

    def _migrate_legacy_db(self, legacy_path, target_path):
        if os.path.exists(target_path):
            return
        if not os.path.exists(legacy_path):
            return
        target_dir = os.path.dirname(target_path)
        if target_dir:
            os.makedirs(target_dir, exist_ok=True)
        with sqlite3.connect(legacy_path) as src_conn:
            with sqlite3.connect(target_path) as dst_conn:
                src_conn.backup(dst_conn)
        logger.info(f"检测到旧数据库，已自动迁移到: {target_path}")

    def _init_db(self):
        Base.metadata.create_all(self._engine)
        with self._engine.begin() as conn:
            table_info = conn.execute(text("PRAGMA table_info(yaml_cache)")).fetchall()
            columns = [row[1] for row in table_info]
            if "file_hash" not in columns:
                conn.execute(
                    text("ALTER TABLE yaml_cache ADD COLUMN file_hash TEXT DEFAULT ''")
                )

    def save_music_chart(self, music_id, data):
        data_json = json.dumps(data, ensure_ascii=False, default=str)
        stmt = sqlite_insert(MusicChart).values(music_id=music_id, data_json=data_json)
        stmt = stmt.on_conflict_do_update(
            index_elements=[MusicChart.music_id],
            set_={"data_json": stmt.excluded.data_json},
        )
        with self._session_factory() as session:
            with session.begin():
                session.execute(stmt)

    def get_music_chart(self, music_id):
        with self._session_factory() as session:
            row = session.get(MusicChart, music_id)
            if not row:
                return None
            return json.loads(row.data_json)

    def load_yaml_file(self, filename, sanitizer=None, session=None):
        path = os.path.join(self.data_dir, filename)
        if not os.path.exists(path):
            return None
        mtime = os.path.getmtime(path)
        if session is None:
            with self._session_factory() as local_session:
                with local_session.begin():
                    return self._load_yaml_file_impl(
                        local_session, filename, path, mtime, sanitizer
                    )
        return self._load_yaml_file_impl(session, filename, path, mtime, sanitizer)

    def _load_yaml_file_impl(self, session, filename, path, mtime, sanitizer=None):
        cached = self._get_cache(session, filename, mtime)
        if cached is not None:
            return cached
        file_hash = self._compute_file_hash(path)
        cached_by_hash = self._get_cache_by_hash(session, filename, file_hash)
        if cached_by_hash is not None:
            self._update_cache_mtime(session, filename, mtime)
            return cached_by_hash
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        if sanitizer:
            content = sanitizer(content)
        data = yaml.safe_load(content)
        data_json = json.dumps(data, ensure_ascii=False, default=str)
        stmt = sqlite_insert(YamlCache).values(
            filename=filename,
            mtime=mtime,
            data_json=data_json,
            file_hash=file_hash,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[YamlCache.filename],
            set_={
                "mtime": stmt.excluded.mtime,
                "data_json": stmt.excluded.data_json,
                "file_hash": stmt.excluded.file_hash,
            },
        )
        session.execute(stmt)
        return data

    def _get_cache(self, session, filename, mtime):
        data_json = session.execute(
            select(YamlCache.data_json).where(
                YamlCache.filename == filename, YamlCache.mtime == mtime
            )
        ).scalar_one_or_none()
        if data_json is None:
            return None
        return json.loads(data_json)

    def _get_cache_by_hash(self, session, filename, file_hash):
        data_json = session.execute(
            select(YamlCache.data_json).where(
                YamlCache.filename == filename, YamlCache.file_hash == file_hash
            )
        ).scalar_one_or_none()
        if data_json is None:
            return None
        return json.loads(data_json)

    def _update_cache_mtime(self, session, filename, mtime):
        session.execute(
            update(YamlCache)
            .where(YamlCache.filename == filename)
            .values(mtime=mtime)
        )

    def _compute_file_hash(self, path):
        h = hashlib.md5()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    def get_meta(self, key):
        with self._session_factory() as session:
            return session.execute(
                select(MetaKV.value).where(MetaKV.key == key)
            ).scalar_one_or_none()

    def set_meta(self, key, value):
        stmt = sqlite_insert(MetaKV).values(key=key, value=value)
        stmt = stmt.on_conflict_do_update(
            index_elements=[MetaKV.key], set_={"value": stmt.excluded.value}
        )
        with self._session_factory() as session:
            with session.begin():
                session.execute(stmt)

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
        changed = self._sync_yaml_rows(sanitizer)
        self.set_meta("current_version", version)
        logger.info(f"版本已更新: {version}，变更行数: {changed}")
        return True

    def rebuild(self, version_path, sanitizer=None):
        logger.info("开始重建数据库...")
        with self._session_factory() as session:
            with session.begin():
                session.execute(delete(YamlCache))
                session.execute(delete(YamlRow))
        if os.path.exists(version_path):
            with open(version_path, "r", encoding="utf-8") as f:
                version = f.read().strip()
            self.set_meta("current_version", version)
            logger.info(f"重建版本设置为: {version}")
        else:
            self.set_meta("current_version", "")
            logger.warning(f"版本文件不存在: {version_path}")
        changed = self._sync_yaml_rows(sanitizer)
        logger.info(f"重建完成，变更行数: {changed}")
        return changed

    def _sync_yaml_rows(self, sanitizer=None):
        total_changed = 0
        yaml_files = [
            f
            for f in os.listdir(self.data_dir)
            if f.lower().endswith((".yaml", ".yml"))
        ]
        with self._session_factory() as session:
            with session.begin():
                total_changed += self._cleanup_removed_yaml_files(session, set(yaml_files))
                session.execute(
                    text(
                        "CREATE TEMP TABLE IF NOT EXISTS sync_yaml_ids (id INTEGER PRIMARY KEY)"
                    )
                )
                for filename in sorted(yaml_files):
                    data = self.load_yaml_file(filename, sanitizer, session=session)
                    rows = []
                    ids = []
                    if isinstance(data, list):
                        for entry in data:
                            if not isinstance(entry, dict):
                                continue
                            if "Id" not in entry:
                                continue
                            try:
                                entry_id = int(entry["Id"])
                            except Exception:
                                continue
                            rows.append(
                                {
                                    "filename": filename,
                                    "id": entry_id,
                                    "data_json": json.dumps(
                                        entry, ensure_ascii=False, default=str
                                    ),
                                }
                            )
                            ids.append({"id": entry_id})
                    before = self._get_total_changes(session)
                    if rows:
                        insert_stmt = sqlite_insert(YamlRow)
                        upsert_stmt = insert_stmt.on_conflict_do_update(
                            index_elements=[YamlRow.filename, YamlRow.id],
                            set_={"data_json": insert_stmt.excluded.data_json},
                            where=YamlRow.data_json != insert_stmt.excluded.data_json,
                        )
                        session.execute(upsert_stmt, rows)
                    session.execute(text("DELETE FROM sync_yaml_ids"))
                    if ids:
                        for chunk in self._chunked(ids, 2000):
                            session.execute(
                                text(
                                    "INSERT OR IGNORE INTO sync_yaml_ids (id) VALUES (:id)"
                                ),
                                chunk,
                            )
                        session.execute(
                            text(
                                """
                                DELETE FROM yaml_rows
                                WHERE filename = :filename
                                  AND id NOT IN (SELECT id FROM sync_yaml_ids)
                                """
                            ),
                            {"filename": filename},
                        )
                    else:
                        session.execute(
                            text("DELETE FROM yaml_rows WHERE filename = :filename"),
                            {"filename": filename},
                        )
                    after = self._get_total_changes(session)
                    total_changed += after - before
        return total_changed

    def _cleanup_removed_yaml_files(self, session, yaml_file_set):
        if not yaml_file_set:
            rows_deleted = self._safe_rowcount(
                session.execute(text("DELETE FROM yaml_rows"))
            )
            cache_deleted = self._safe_rowcount(
                session.execute(text("DELETE FROM yaml_cache"))
            )
            return rows_deleted + cache_deleted
        filenames = sorted(yaml_file_set)
        rows_stmt = text("DELETE FROM yaml_rows WHERE filename NOT IN :filenames")
        rows_stmt = rows_stmt.bindparams(bindparam("filenames", expanding=True))
        cache_stmt = text("DELETE FROM yaml_cache WHERE filename NOT IN :filenames")
        cache_stmt = cache_stmt.bindparams(bindparam("filenames", expanding=True))
        rows_deleted = self._safe_rowcount(
            session.execute(rows_stmt, {"filenames": filenames})
        )
        cache_deleted = self._safe_rowcount(
            session.execute(cache_stmt, {"filenames": filenames})
        )
        return rows_deleted + cache_deleted

    def _safe_rowcount(self, result):
        count = result.rowcount
        if count is None or count < 0:
            return 0
        return count

    def _get_total_changes(self, session):
        return int(session.execute(text("SELECT total_changes()")).scalar_one())

    def _chunked(self, values, size):
        for i in range(0, len(values), size):
            yield values[i : i + size]
