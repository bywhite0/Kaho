import json
import os
import tempfile
import threading
from copy import deepcopy
from typing import Any


class FileDB:
    def __init__(self, path: str):
        self.path = os.path.abspath(path)
        self._data: dict[str, Any] = {}
        self._loaded = False
        self._lock = threading.RLock()

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    payload = json.load(f)
                if isinstance(payload, dict):
                    self._data = payload
                else:
                    self._data = {}
            except Exception:
                self._data = {}
            self._loaded = True

    def _walk(self, key: str, create: bool = False):
        parts = [p for p in key.split(".") if p]
        if not parts:
            return None, None
        node = self._data
        for part in parts[:-1]:
            nxt = node.get(part)
            if not isinstance(nxt, dict):
                if not create:
                    return None, None
                nxt = {}
                node[part] = nxt
            node = nxt
        return node, parts[-1]

    def get(self, key: str, default: Any = None) -> Any:
        self._ensure_loaded()
        with self._lock:
            node, last = self._walk(key, create=False)
            if node is None:
                return default
            return node.get(last, default)

    def get_copy(self, key: str, default: Any = None) -> Any:
        return deepcopy(self.get(key, default))

    def keys(self) -> list[str]:
        self._ensure_loaded()
        with self._lock:
            return list(self._data.keys())

    def set(self, key: str, value: Any) -> None:
        self._ensure_loaded()
        with self._lock:
            node, last = self._walk(key, create=True)
            if node is None:
                return
            node[last] = value
            self.save()

    def delete(self, key: str) -> None:
        self._ensure_loaded()
        with self._lock:
            node, last = self._walk(key, create=False)
            if node is None:
                return
            if last in node:
                del node[last]
                self.save()

    def clear(self) -> None:
        self._ensure_loaded()
        with self._lock:
            self._data = {}
            self.save()

    def save(self) -> None:
        self._ensure_loaded()
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        content = json.dumps(self._data, ensure_ascii=False, indent=2)
        fd, temp_path = tempfile.mkstemp(
            dir=os.path.dirname(self.path),
            prefix="filedb_",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
                f.write("\n")
            os.replace(temp_path, self.path)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
