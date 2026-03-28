import hashlib
import json
import os
import tempfile
from typing import Any, Callable, Optional

import yaml

from .file_db import FileDB


class MasterDataCacheManager:
    def __init__(self, data_dir: str, cache_dir: str, state_db: FileDB):
        self.data_dir = os.path.realpath(data_dir)
        self.cache_dir = os.path.realpath(cache_dir)
        self.state_db = state_db
        self._index_cache: dict[str, dict[int, dict[str, Any]]] = {}
        os.makedirs(self.cache_dir, exist_ok=True)

    def load_yaml_file(
        self,
        filename: str,
        sanitizer: Optional[Callable[[str], str]] = None,
    ):
        path = os.path.join(self.data_dir, filename)
        if not os.path.exists(path):
            return None
        mtime = os.path.getmtime(path)
        files_state = self._get_files_state()
        state = files_state.get(filename) or {}
        cache_path = self._cache_path(filename)

        if state.get("mtime") == mtime:
            cached = self._read_cached_json(cache_path)
            if cached is not None:
                self._build_index(filename, cached)
                return cached

        file_hash = self._compute_file_hash(path)
        if state.get("file_hash") == file_hash:
            cached = self._read_cached_json(cache_path)
            if cached is not None:
                state["mtime"] = mtime
                files_state[filename] = state
                self._save_files_state(files_state)
                self._build_index(filename, cached)
                return cached

        parsed = self._parse_yaml(path, sanitizer)
        self._write_cached_json(cache_path, parsed)
        row_count = self._count_rows(parsed)
        files_state[filename] = {
            "mtime": mtime,
            "file_hash": file_hash,
            "row_count": row_count,
        }
        self._save_files_state(files_state)
        self._build_index(filename, parsed)
        return parsed

    def sync_incremental(
        self,
        sanitizer: Optional[Callable[[str], str]] = None,
    ) -> int:
        total_changed = 0
        files_state = self._get_files_state()
        yaml_files = self._list_yaml_files()
        yaml_set = set(yaml_files)

        removed_files = [name for name in files_state.keys() if name not in yaml_set]
        for filename in removed_files:
            row_count = int((files_state.get(filename) or {}).get("row_count") or 0)
            total_changed += row_count
            files_state.pop(filename, None)
            self._index_cache.pop(filename, None)
            self._remove_cache_file(filename)
        self._save_files_state(files_state)

        for filename in yaml_files:
            before = files_state.get(filename) or {}
            before_hash = before.get("file_hash")
            before_rows = int(before.get("row_count") or 0)

            data = self.load_yaml_file(filename, sanitizer=sanitizer)
            if data is None:
                continue
            after = self._get_files_state().get(filename) or {}
            after_hash = after.get("file_hash")
            after_rows = int(after.get("row_count") or 0)
            files_state = self._get_files_state()

            if before_hash != after_hash:
                if before_hash is None:
                    total_changed += after_rows
                else:
                    total_changed += max(before_rows, after_rows)

        self._save_files_state(files_state)
        return total_changed

    def rebuild_all(
        self,
        sanitizer: Optional[Callable[[str], str]] = None,
    ) -> int:
        self.clear()
        total_changed = 0
        files_state: dict[str, dict[str, Any]] = {}
        for filename in self._list_yaml_files():
            data = self.load_yaml_file(filename, sanitizer=sanitizer)
            if data is None:
                continue
            state = self._get_files_state().get(filename) or {}
            files_state[filename] = state
            total_changed += int(state.get("row_count") or 0)
        self._save_files_state(files_state)
        return total_changed

    def clear(self) -> None:
        files_state = self._get_files_state()
        for filename in list(files_state.keys()):
            self._remove_cache_file(filename)
        self._index_cache = {}
        self._save_files_state({})

    def get_index(self, filename: str) -> dict[int, dict[str, Any]]:
        return self._index_cache.get(filename, {})

    def _get_files_state(self) -> dict[str, dict[str, Any]]:
        files = self.state_db.get_copy("masterdata.files", {})
        if not isinstance(files, dict):
            return {}
        result: dict[str, dict[str, Any]] = {}
        for key, value in files.items():
            if isinstance(key, str) and isinstance(value, dict):
                result[key] = value
        return result

    def _save_files_state(self, files_state: dict[str, dict[str, Any]]) -> None:
        self.state_db.set("masterdata.files", files_state)

    def _list_yaml_files(self) -> list[str]:
        if not os.path.isdir(self.data_dir):
            return []
        return sorted(
            f
            for f in os.listdir(self.data_dir)
            if f.lower().endswith((".yaml", ".yml"))
        )

    def _cache_path(self, filename: str) -> str:
        return os.path.join(self.cache_dir, f"{filename}.json")

    def _remove_cache_file(self, filename: str) -> None:
        cache_path = self._cache_path(filename)
        if os.path.exists(cache_path):
            os.remove(cache_path)

    def _parse_yaml(
        self,
        path: str,
        sanitizer: Optional[Callable[[str], str]] = None,
    ):
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        if sanitizer:
            content = sanitizer(content)
        return yaml.safe_load(content)

    def _write_cached_json(self, cache_path: str, payload: Any) -> None:
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        content = json.dumps(payload, ensure_ascii=False, default=str)
        fd, temp_path = tempfile.mkstemp(
            dir=os.path.dirname(cache_path),
            prefix="md_cache_",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
                f.write("\n")
            os.replace(temp_path, cache_path)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def _read_cached_json(self, cache_path: str):
        if not os.path.exists(cache_path):
            return None
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def _compute_file_hash(self, path: str) -> str:
        h = hashlib.md5()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    def _count_rows(self, data: Any) -> int:
        if not isinstance(data, list):
            return 0
        count = 0
        for entry in data:
            if not isinstance(entry, dict):
                continue
            if "Id" not in entry:
                continue
            try:
                int(entry["Id"])
            except Exception:
                continue
            count += 1
        return count

    def _build_index(self, filename: str, data: Any) -> None:
        index: dict[int, dict[str, Any]] = {}
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
                index[entry_id] = entry
        self._index_cache[filename] = index
