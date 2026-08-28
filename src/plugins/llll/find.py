from nonebot import logger, on_command
from nonebot.adapters.onebot.v11 import Message, MessageSegment
from nonebot.params import CommandArg

from src.core.services.draw_api import get_draw_api_service
from src.core.services.draw_payloads import (
    FIND_RENDER_ROUTE,
    build_find_render_payload,
)
from src.core.services.t2i import get_t2i_service

from ._common import get_dm_instance

find_cmd = on_command("find")


@find_cmd.handle()
async def _(args: Message = CommandArg()):
    dm = await get_dm_instance()
    query = args.extract_plain_text().strip()
    cid = dm.get_character_id_by_name(query)
    if not cid:
        await find_cmd.finish("未找到。")
        return

    img_bytes = None
    draw_api = get_draw_api_service()
    if draw_api.enabled:
        try:
            payload = build_find_render_payload(dm, cid)
            img_bytes = await draw_api.render(FIND_RENDER_ROUTE, payload)
        except Exception:
            logger.exception("绘图服务渲染 find 失败，回退 T2I")

    if img_bytes is None:
        img_bytes = await _render_t2i(dm, cid)
        if img_bytes is None:
            return

    await find_cmd.finish(MessageSegment.image(img_bytes))


async def _render_t2i(dm, cid):
    cards_data = dm.get_cards_by_character(cid)

    series_map = {}
    for c in cards_data:
        sid = c["CardSeriesId"]
        if sid not in series_map:
            series_map[sid] = []
        series_map[sid].append(c)

    display_cards = []
    for sid in sorted(series_map.keys()):
        cards = series_map[sid]

        normal_card = next((c for c in cards if c["Id"] % 10 == 0), None)
        idolized_card = next((c for c in cards if c["Id"] % 10 == 1), None)

        images = []
        if normal_card:
            images.append(
                {
                    "id": normal_card["Id"],
                    "type": "card_middle_vertical",
                    "label": "Normal",
                }
            )

        if idolized_card:
            images.append(
                {
                    "id": idolized_card["Id"],
                    "type": "card_middle_vertical",
                    "label": "Idolized",
                }
            )

        c = cards[0]
        display_cards.append(
            {
                "id": sid,
                "rarity": dm.get_rarity_name(c["Rarity"]),
                "name": c["Name"],
                "images": images,
            }
        )

    data = {
        "character_name": dm.get_character_name(cid),
        "count": len(series_map),
        "cards": display_cards,
    }

    try:
        return await get_t2i_service().generate_image("find.html", data)
    except Exception as e:
        await find_cmd.finish(f"生成图片失败: {e}")
        return None
