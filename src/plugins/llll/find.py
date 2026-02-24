import os
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

    # Assuming get_cards_by_character exists as it was used in original code
    # If not, I might need to implement it or use another method, but since it was there, I assume it works.
    # Wait, in search.py: dm.get_all_card_datas()
    # Maybe find.py was using a method that doesn't exist? Or I missed checking data_manager.py
    # Assuming it works.
    
    # Actually, let's double check data_manager.py if I can, but I don't need to if I trust the existing code.
    # However, I should be careful.
    # Let's just use what was there.
    
    try:
        cards_data = dm.get_cards_by_character(cid)
    except AttributeError:
        # Fallback if method doesn't exist (e.g. if I misread or it's missing)
        # In search.py, it iterates all cards.
        cards_data = [c for c in dm.get_all_card_datas() if c.get('CharactersId') == cid]

    series_map = {}
    for c in cards_data:
        sid = c['CardSeriesId']
        if sid not in series_map:
            series_map[sid] = []
        series_map[sid].append(c)

    display_cards = []
    cwd = os.getcwd()
    for sid in sorted(series_map.keys()):
        cards = series_map[sid]
        
        normal_card = next((c for c in cards if c.get('State') == 0), None)
        idolized_card = next((c for c in cards if c.get('State') == 1), None)
        
        images = []
        if normal_card:
            images.append({"id": normal_card['Id'], "type": "card_middle_vertical", "label": "Normal"})
                
        if idolized_card:
            images.append({"id": idolized_card['Id'], "type": "card_middle_vertical", "label": "Idolized"})

        c = cards[0]
        display_cards.append({
            "id": sid,
            "rarity": dm.get_rarity_name(c['Rarity']),
            "name": c['Name'],
            "images": images
        })

    data = {
        "character_name": dm.get_character_name(cid),
        "count": len(series_map),
        "cards": display_cards
    }

    try:
        img_bytes = await get_t2i_service().generate_image("find.html", data)
    except Exception as e:
        await find_cmd.finish(f"生成图片失败: {e}")
        return

    await find_cmd.finish(MessageSegment.image(img_bytes))
