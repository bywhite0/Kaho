from nonebot import on_command
from nonebot.adapters.onebot.v11 import Message, MessageSegment
from nonebot.params import CommandArg

from src.core.services.t2i import get_t2i_service
from ._common import get_dm_instance


search_cmd = on_command("search")


@search_cmd.handle()
async def _(args: Message = CommandArg()):
    dm = await get_dm_instance()
    query = args.extract_plain_text().strip()
    results = []
    seen = set()
    for c in dm.get_all_card_datas():
        if c["CardSeriesId"] in seen:
            continue
        if query.lower() in (c.get("Name") or "").lower():
            results.append(c)
            seen.add(c["CardSeriesId"])

    if not results:
        await search_cmd.finish("未找到。")
        return

    cards = []
    for c in results:
        series_id = c["CardSeriesId"]
        series_cards = dm.get_card_series_data(series_id)

        normal_card = next((x for x in series_cards if x.get("State") == 0), None)
        idolized_card = next((x for x in series_cards if x.get("State") == 1), None)

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

        cards.append(
            {
                "CardSeriesId": series_id,
                "rarity_name": dm.get_rarity_name(c["Rarity"]),
                "Name": c["Name"],
                "character_name": dm.get_character_name(c["CharactersId"]),
                "images": images,
            }
        )

    try:
        img_bytes = await get_t2i_service().generate_image(
            "search.html", {"query": query, "results": cards}
        )
    except Exception as e:
        await search_cmd.finish(f"生成图片失败: {e}")
        return

    await search_cmd.finish(MessageSegment.image(img_bytes))
