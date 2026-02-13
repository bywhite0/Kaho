from nonebot import on_command

from ._common import get_dm_instance


list_cmd = on_command("list")


@list_cmd.handle()
async def _():
    dm = await get_dm_instance()
    lines = []
    for char_id in sorted(dm.get_character_ids()):
        gen = dm.get_generation_str(char_id)
        lines.append(f"  {char_id}: {dm.get_character_name(char_id)}{'（' + gen + '）' if gen else ''}")
    output = "\n".join(lines).rstrip()
    if output:
        await list_cmd.finish(output)
