import json
import os
import tempfile
from typing import Any


class MusicChartCache:
    def __init__(self, cache_dir: str):
        self.cache_dir = os.path.realpath(cache_dir)
        os.makedirs(self.cache_dir, exist_ok=True)

    def get(self, music_id: int):
        path = self._chart_path(music_id)
        if not os.path.exists(path):
            return None
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def set(self, music_id: int, data: Any) -> None:
        path = self._chart_path(music_id)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        content = json.dumps(data, ensure_ascii=False, default=str)
        fd, temp_path = tempfile.mkstemp(
            dir=os.path.dirname(path),
            prefix="music_chart_",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
                f.write("\n")
            os.replace(temp_path, path)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def clear(self) -> None:
        if not os.path.isdir(self.cache_dir):
            return
        for name in os.listdir(self.cache_dir):
            path = os.path.join(self.cache_dir, name)
            if os.path.isfile(path) and name.endswith(".json"):
                os.remove(path)

    def _chart_path(self, music_id: int) -> str:
        return os.path.join(self.cache_dir, f"{int(music_id)}.json")
