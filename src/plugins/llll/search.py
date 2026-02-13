from nonebot import on_command
from nonebot.adapters.console import Message
from nonebot.params import CommandArg

from ._common import get_dm_instance


search_cmd = on_command("search")


@search_cmd.handle()
async def _(args: Message = CommandArg()):
    dm = await get_dm_instance()
    query = args.extract_plain_text().strip()
    lines = []
    results = []
    seen = set()
    for c in dm.get_all_card_datas():
        if c['CardSeriesId'] in seen:
            continue
        if query.lower() in (c.get('Name') or "").lower():
            results.append(c)
            seen.add(c['CardSeriesId'])
    for c in results:
        lines.append(f"  [{c['CardSeriesId']}] {dm.get_rarity_name(c['Rarity'])} - {c['Name']}（{dm.get_character_name(c['CharactersId'])}）")
    output = "\n".join(lines).rstrip()
    if output:
        await search_cmd.finish(output)
