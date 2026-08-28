from nonebot import logger, on_command
from nonebot.adapters.onebot.v11 import MessageSegment

from src.core.services.draw_api import get_draw_api_service
from src.core.services.draw_payloads import (
    LIST_RENDER_ROUTE,
    build_list_render_payload,
)
from src.core.services.t2i import get_t2i_service

from ._common import get_dm_instance

list_cmd = on_command("list")


@list_cmd.handle()
async def _():
    dm = await get_dm_instance()

    img_bytes = None
    draw_api = get_draw_api_service()
    if draw_api.enabled:
        try:
            payload = build_list_render_payload(dm)
            img_bytes = await draw_api.render(LIST_RENDER_ROUTE, payload)
        except Exception:
            logger.exception("绘图服务渲染 list 失败，回退 T2I")

    if img_bytes is None:
        characters = []
        for char_id in sorted(dm.get_character_ids()):
            gen = dm.get_generation_str(char_id)
            characters.append(
                {
                    "id": char_id,
                    "name": dm.get_character_name(char_id),
                    "generation": f"（{gen}）" if gen else "",
                }
            )
        try:
            img_bytes = await get_t2i_service().generate_image(
                "list.html", {"characters": characters}
            )
        except Exception as e:
            await list_cmd.finish(f"生成图片失败: {e}")
            return

    await list_cmd.finish(MessageSegment.image(img_bytes))
