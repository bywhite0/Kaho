"""插件加载冒烟测试：验证完整 import 链、matcher 注册与权限文件创建"""

import importlib
import os
import sys
import tempfile
from pathlib import Path

tmp = Path(tempfile.mkdtemp(prefix="gallery_smoke_"))
os.environ["LOCALSTORE_DATA_DIR"] = str(tmp / "data")
os.environ["LOCALSTORE_CACHE_DIR"] = str(tmp / "cache")
os.environ["LOCALSTORE_CONFIG_DIR"] = str(tmp / "config")

# 插件包名跟随目录名，Kaho 内为 gallery，独立仓库为 nonebot_plugin_gallery
_PKG_NAME = Path(__file__).resolve().parents[1].name
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import nonebot

nonebot.init(driver="~none", superusers={"1"}, log_level="WARNING")
plugin = nonebot.load_plugin(_PKG_NAME)
assert plugin is not None, "插件加载失败"

access_file = tmp / "data" / _PKG_NAME / "gallery_access.json"
assert access_file.exists(), f"权限文件未创建：{access_file}"

access_data = importlib.import_module(f"{_PKG_NAME}.access").access_data
AccessConfig = importlib.import_module(f"{_PKG_NAME}.access_core").AccessConfig

assert isinstance(access_data.current, AccessConfig)
assert access_data.current.default_policy == "rw"

# 热更新：外部改写文件后 current 即时反映
access_file.write_text('{"default_policy": "ro"}', encoding="utf-8")
os.utime(access_file, ns=(access_file.stat().st_mtime_ns + 10**9,) * 2)
assert access_data.current.default_policy == "ro", "热重载未生效"

print("SMOKE_OK")
