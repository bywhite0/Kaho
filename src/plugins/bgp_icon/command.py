from typing import Any, Dict, Optional

import httpx
from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, Message, MessageSegment
from nonebot.params import CommandArg

from src.core.services.bgp_icon_image import generate_bgp_icon_image


bgp_icon_cmd = on_command("bgp_icon")
HELP_TEXT = "请在同一条消息附带图片，例如：/bgp_icon [图片]"


@bgp_icon_cmd.handle()
async def _(bot: Bot, args: Message = CommandArg()):
    image_url = await _extract_first_image_url(bot, args)
    if not image_url:
        await bgp_icon_cmd.finish(HELP_TEXT)
        return

    try:
        source_bytes = await _download_image_bytes(image_url)
    except Exception as exc:
        await bgp_icon_cmd.finish(f"获取图片失败: {exc}")
        return

    try:
        result_bytes = generate_bgp_icon_image(source_bytes)
    except Exception as exc:
        await bgp_icon_cmd.finish(f"生成头像框图片失败: {exc}")
        return

    await bgp_icon_cmd.finish(MessageSegment.image(result_bytes))


async def _extract_first_image_url(bot: Bot, args: Message) -> str:
    for segment in args:
        if segment.type != "image":
            continue

        segment_url = str(segment.data.get("url") or "").strip()
        if segment_url:
            return segment_url

        file_id = str(segment.data.get("file") or "").strip()
        if not file_id:
            continue

        image_info = await _get_image_info(bot, file_id)
        if image_info is None:
            continue

        info_url = str(image_info.get("url") or "").strip()
        if info_url:
            return info_url

    return ""


async def _get_image_info(bot: Bot, file_id: str) -> Optional[Dict[str, Any]]:
    try:
        result = await bot.call_api("get_image", file=file_id)
    except Exception:
        return None

    if not isinstance(result, dict):
        return None
    return result


async def _download_image_bytes(url: str) -> bytes:
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.content
