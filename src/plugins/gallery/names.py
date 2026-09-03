"""画廊名称校验与模式解析：不依赖 NoneBot 运行时的纯逻辑层，便于单测。

与 access_core（黑白名单纯逻辑）同定位：handler 只负责取参和回话，规则判定集中在此。
"""

import re
from typing import Literal

GalleryMode = Literal["edit", "view", "off"]
"""画廊自身的开放程度，与按用户/群的黑白名单策略正交"""

DEFAULT_MODE: GalleryMode = "edit"

MODE_LABELS: dict[str, str] = {
    "edit": "可读写",
    "view": "只读",
    "off": "已关闭",
}

_MODE_TOKENS: dict[str, GalleryMode] = {
    "edit": "edit",
    "读写": "edit",
    "可写": "edit",
    "正常": "edit",
    "开放": "edit",
    "view": "view",
    "只读": "view",
    "查看": "view",
    "锁定": "view",
    "off": "off",
    "关闭": "off",
    "隐藏": "off",
    "下架": "off",
}

MAX_NAME_LENGTH = 32
"""名称长度上限。

画廊名直接作为数据目录下的子目录名，需要为 Windows 的 MAX_PATH(260) 留预算：
localstore 数据根目录本身通常已占上百字符，其下还要接 "/{图片id}{扩展名}"。
"""

INTEGER_PATTERN = re.compile(r"^[+-]?[0-9]+$")
"""图片 id 的唯一识别形式（仅 ASCII 数字，允许正负号）。

名称校验与命令层的 id 解析必须共用它：只要两边一致，就不存在
"画廊名恰好是数字导致图片 id 取不到" 的遮蔽问题。
"""

_WINDOWS_RESERVED_CHARS = '<>:"/\\|?*'

_WINDOWS_RESERVED_STEMS = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{index}" for index in range(1, 10)}
    | {f"LPT{index}" for index in range(1, 10)}
)


def parse_mode_token(token: str) -> GalleryMode | None:
    """解析模式词，无法识别时返回 None"""
    return _MODE_TOKENS.get(token.strip().lower())


def validate_gallery_name(name: str) -> str | None:
    """校验画廊名称或别名，合法返回 None，否则返回可直接回复用户的原因。

    名称与别名共用一套规则：别名虽然不落文件系统，但同样要参与命令参数解析
    和图片 id 区分，放宽只会让两类名字的可用字符集不一致，增加困惑。
    """
    if not name:
        return "名称不能为空"
    if name != name.strip():
        return "名称首尾不能有空白字符"
    if len(name) > MAX_NAME_LENGTH:
        return f"名称长度不能超过 {MAX_NAME_LENGTH} 个字符"

    # 命令参数按空白分割（如 "看 <画廊> x2"），名称含空白会让参数解析截断
    if any(char.isspace() for char in name):
        return "名称不能包含空格等空白字符"
    if any(char < " " or char == "\x7f" for char in name):
        return "名称不能包含控制字符"

    if INTEGER_PATTERN.match(name):
        return "名称不能是纯数字，否则会与图片 id 冲突"

    if bad_chars := sorted({char for char in name if char in _WINDOWS_RESERVED_CHARS}):
        return f"名称不能包含字符：{' '.join(bad_chars)}"
    if name in {".", ".."}:
        return "名称不能是 . 或 .."
    if name.endswith("."):
        return "名称不能以 . 结尾"
    if name.split(".", 1)[0].upper() in _WINDOWS_RESERVED_STEMS:
        return f"名称 {name} 与系统保留设备名冲突"

    return None
