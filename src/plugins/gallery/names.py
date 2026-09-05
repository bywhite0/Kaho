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

画廊名校验与命令层的 id 解析共用它：画廊名不许是纯数字，所以裸数字 token
永远能指向图片。别名不受此限（见 validate_gallery_alias）——纯数字别名会遮蔽
同号图片的 "看 <id>" 通路，届时用 "看 #<id>" 精确取图。
"""

_HASH_ID_GAP_PATTERN = re.compile(r"#\s+(?=[+-]?[0-9])")
"""让 "看 # 5" 与 "看 #5" 等价。

只在 # 后确实跟着数字时才合并，以免影响以 # 开头的画廊名（如 "看 # x2"）。
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


def parse_hash_picture_ids(arg_str: str) -> list[int]:
    """解析 "#<图片id>" 形式的显式取图参数，不是该形式时返回空列表。

    成立条件：去掉 # 后每个 token 都是整数，且至少一个 token 带 #。收紧到
    "必须全是整数" 是为了不抢走以 # 开头的画廊名——名称校验允许这种名字。
    """
    tokens = _HASH_ID_GAP_PATTERN.sub("#", arg_str).split()
    if not any(token.startswith("#") for token in tokens):
        return []
    stripped = [token.removeprefix("#") for token in tokens]
    if not all(INTEGER_PATTERN.match(token) for token in stripped):
        return []
    return [int(token) for token in stripped]


def _validate_common(name: str) -> str | None:
    """画廊名与别名共用的规则：长度、可解析性、文件系统安全。

    别名不落文件系统，但仍共用同一套字符集：放宽只会让两类名字的可用字符不一致，
    增加困惑。二者唯一的差异是能否为纯数字，见下面两个入口。
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

    if bad_chars := sorted({char for char in name if char in _WINDOWS_RESERVED_CHARS}):
        return f"名称不能包含字符：{' '.join(bad_chars)}"
    if name in {".", ".."}:
        return "名称不能是 . 或 .."
    if name.endswith("."):
        return "名称不能以 . 结尾"
    if name.split(".", 1)[0].upper() in _WINDOWS_RESERVED_STEMS:
        return f"名称 {name} 与系统保留设备名冲突"

    return None


def validate_gallery_name(name: str) -> str | None:
    """校验画廊名称，合法返回 None，否则返回可直接回复用户的原因。

    画廊名比别名多一条限制：不能是纯数字。它既要当数据目录下的子目录名，
    又是画廊的主标识，遮蔽图片 id 的代价比别名大，且没有"删掉别名"这种撤销手段。
    """
    if reason := _validate_common(name):
        return reason
    if INTEGER_PATTERN.match(name):
        return "画廊名不能是纯数字，需要数字入口请改用别名"
    return None


def validate_gallery_alias(alias: str) -> str | None:
    """校验画廊别名，合法返回 None，否则返回可直接回复用户的原因。

    允许纯数字：代价仅是 "看 <该数字>" 命中画廊而非同号图片，"看 #<图片id>"
    仍能精确取图；别名可随时删除，这种遮蔽是可撤销的。
    """
    return _validate_common(alias)
