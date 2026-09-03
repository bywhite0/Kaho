from pathlib import Path
from typing import Literal

from nonebot import get_plugin_config, require
from pydantic import BaseModel

require("nonebot_plugin_localstore")

from nonebot_plugin_localstore import (
    get_plugin_cache_dir,
    get_plugin_data_dir,
    get_plugin_data_file,
)

from .compat import JsonModelFile


class ScopedConfig(BaseModel):
    model_config = {"use_attribute_docstrings": True}

    name_data_file: str = "gallery_name_indices.json"
    """画廊的名称数据文件名"""

    access_data_file: str = "gallery_access.json"
    """读写权限（黑白名单）数据文件名，手动编辑后即时生效"""

    send_pic_limit: int = 10
    """每次发送图片的数量限制"""

    send_pic_as_meme: bool = True
    """是否将发送的图片作为表情包发送"""

    send_pic_mode: Literal["base64", "path"] = "base64"
    """发图方式：base64 内联图片字节，协议端与 bot 异机也可用；path 直发本地文件路径，需协议端与 bot 同机，开销更低"""

    # 以下路径一律返回展开符号链接后的真实路径：索引层用 resolve() 后的路径做 relative_to 比较，
    # send2trash 在 Windows 走 SHFileOperationW，穿过符号链接的路径会被 Shell 拒绝（WinError 161）。
    @property
    def name_data_file_path(self) -> Path:
        return get_plugin_data_file(self.name_data_file).resolve()

    @property
    def access_data_file_path(self) -> Path:
        return get_plugin_data_file(self.access_data_file).resolve()

    @property
    def data_dir_path(self) -> Path:
        """画廊数据存储根目录"""
        return get_plugin_data_dir().resolve()

    @property
    def cache_dir_path(self) -> Path:
        """画廊缓存目录"""
        return get_plugin_cache_dir().resolve()


class Config(BaseModel):
    gallery: ScopedConfig = ScopedConfig()


cfg = get_plugin_config(Config).gallery


class GalleryNameData(BaseModel):
    """画廊数据

    画廊名称唯一，且与目录名一致；画廊别名不能重复
    """

    alias_to_name: dict[str, str] = {}
    """画廊别名到名称的映射"""

    name_to_aliases: dict[str, list[str]] = {}
    """画廊名称到别名的映射"""

    name_to_mode: dict[str, str] = {}
    """画廊名称到开放模式（edit/view/off）的映射，缺省视为 edit

    存成裸 str 而非 Literal：手工改坏这个值只应让单个画廊回退到默认模式，
    不该让整份索引文件校验失败、拖垮整个插件加载。
    """

    name_to_cover: dict[str, int] = {}
    """画廊名称到封面图片 id 的映射，缺省用目录内 id 最小的图片"""

    iota: int = 0
    """用于生成图片名称的自增计数器"""


gallery_name_data = JsonModelFile(GalleryNameData, cfg.name_data_file_path)
