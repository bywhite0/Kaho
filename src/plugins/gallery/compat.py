"""替代 kanade-bot 宿主工具层的最小兼容实现"""

from io import BytesIO
from pathlib import Path
from typing import Any, Generic, SupportsIndex, TypeVar

import httpx
from nonebot import logger
from nonebot.adapters.onebot.v11 import ActionFailed
from nonebot.adapters.onebot.v11 import Bot as OneBot
from nonebot.adapters.onebot.v11 import MessageEvent as OneBotMessageEvent
from nonebot.adapters.onebot.v11 import MessageSegment as OneBotMessageSegment
from pydantic import BaseModel

from ._atomic import atomic_write_text

HTTPX_CLIENT = httpx.AsyncClient(timeout=20)
"""全局HTTPX客户端单例"""


TModel = TypeVar("TModel", bound=BaseModel)


class JsonModelFile(Generic[TModel]):
    """JSON 文件持久化的 Pydantic 模型容器（等价于宿主的 load_register_model_from_file）"""

    def __init__(self, cls: type[TModel], path: Path):
        if path.exists():
            self.instance = cls.model_validate_json(path.read_text(encoding="utf-8"))
        else:
            logger.warning(f"数据文件 {path} 不存在，使用默认值并创建")
            self.instance = cls()
            atomic_write_text(
                path,
                self.instance.model_dump_json(indent=2, ensure_ascii=False),
            )
        self.path = path

    def save_to_file(self) -> None:
        atomic_write_text(
            self.path,
            self.instance.model_dump_json(indent=2, ensure_ascii=False),
        )


def meme_image_segment(file: str | bytes | BytesIO | Path) -> OneBotMessageSegment:
    """以表情包形式发送的图片消息段"""
    message = OneBotMessageSegment.image(file)
    message.data["summary"] = "[动画表情]"
    message.data["sub_type"] = 1
    return message


def parse_arg_message(
    arg_str: str,
    mappings: dict[str, type] | None = None,
    *,
    sep: str | None = None,
    maxsplit: SupportsIndex = -1,
) -> dict[str, Any]:
    """按空白字符分割参数并做类型转换，失败或缺位的值为 None"""
    if not mappings:
        return {}

    args = arg_str.strip().split(sep=sep, maxsplit=maxsplit)
    arg_dict: dict[str, Any] = {}

    for index, (name, value_type) in enumerate(mappings.items()):
        if index >= len(args):
            arg_dict[name] = None
            continue

        raw_value = args[index]
        try:
            arg_dict[name] = value_type(raw_value)
        except (TypeError, ValueError):
            arg_dict[name] = None

    return arg_dict


async def get_forward_message_events(
    bot: OneBot, fwd_segment: OneBotMessageSegment
) -> tuple[str, list[OneBotMessageEvent]]:
    """获取合并转发消息中的消息事件列表"""
    assert fwd_segment.type == "forward", "fwd_segment 必须是转发消息段"

    fwd_id: str = fwd_segment.data["id"]
    raw_fwd_msg_events: list[dict[str, Any]] = []
    if "content" in fwd_segment.data:
        raw_fwd_msg_events = fwd_segment.data["content"]
    else:
        try:
            forward_response = await bot.get_forward_msg(id=fwd_id)
            raw_fwd_msg_events = forward_response["messages"]
        except ActionFailed as e:
            logger.warning(f"获取转发消息失败: {e}")

    fwd_msg_events: list[OneBotMessageEvent] = []
    for e in raw_fwd_msg_events:
        e["post_type"] = "message"
        fwd_msg_events.append(OneBotMessageEvent.model_validate(e))
    return fwd_id, fwd_msg_events
