from nonebot import on_command
from nonebot.adapters.console import Message
from nonebot.params import CommandArg

from ._common import get_dm_instance


find_cmd = on_command("find")


@find_cmd.handle()
async def _(args: Message = CommandArg()):
    dm = await get_dm_instance()
    query = args.extract_plain_text().strip()
    cid = dm.get_character_id_by_name(query)
    if not cid:
        output = "未找到。"
    else:
        lines = []
        cards = dm.get_cards_by_character(cid)
        series_map = {}
        for c in cards:
            sid = c['CardSeriesId']
            if sid not in series_map:
                series_map[sid] = []
            series_map[sid].append(c)
        lines.append(f"\n找到 {dm.get_character_name(cid)} 的 {len(series_map)} 张卡牌：")
        for sid in sorted(series_map.keys()):
            c = series_map[sid][0]
            lines.append(f"  [{sid}] {dm.get_rarity_name(c['Rarity'])} - {c['Name']}")
        output = "\n".join(lines)
    output = (output or "").rstrip()
    if output:
        await find_cmd.finish(output)
