import asyncio
import os

from src.core.data_manager import DataManager

_dm = None
_dm_lock = asyncio.Lock()


async def init_dm():
    global _dm
    if _dm is not None:
        return _dm
    async with _dm_lock:
        if _dm is None:
            root_dir = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "..", "..", "..")
            )
            data_dir = os.path.join(root_dir, "masterdata")
            version_path = os.path.join(root_dir, "cache", "currentVersion.txt")
            _dm = DataManager(data_dir)
            await asyncio.to_thread(_dm.sync_version_cache, version_path)
    return _dm


def get_dm():
    return _dm


def get_paths():
    root_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..")
    )
    data_dir = os.path.join(root_dir, "masterdata")
    version_path = os.path.join(root_dir, "cache", "currentVersion.txt")
    return root_dir, data_dir, version_path
