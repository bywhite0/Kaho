from nonebot import on_command
from nonebot.adapters.onebot.v11 import Message, MessageSegment
from nonebot.params import CommandArg

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

        normal_card = next((c for c in cards if c.get("State") == 0), None)
        idolized_card = next((c for c in cards if c.get("State") == 1), None)

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
        img_bytes = await get_t2i_service().generate_image("find.html", data)
    except Exception as e:
        await find_cmd.finish(f"生成图片失败: {e}")
        return

    await find_cmd.finish(MessageSegment.image(img_bytes))
