from nonebot import on_command
from nonebot.adapters.console import Message
from nonebot.params import CommandArg

from ._common import get_dm_instance


comic_cmd = on_command("comic")


TAB_LIST_MAP = {
    1030: "103期 入学準備編",
    1031: "103期",
    1041: "104期",
    1051: "105期",
}


@comic_cmd.handle()
async def _(args: Message = CommandArg()):
    dm = await get_dm_instance()
    query = args.extract_plain_text().strip()
    results = dm.search_comics(query)
    if not results:
        output = "未找到。"
    else:
        lines = []
        for entry in results:
            comic_id = entry.get("Id")
            name = entry.get("Name") or ""
            tab_id = entry.get("TabListId")
            tab_name = TAB_LIST_MAP.get(tab_id, f"标签 {tab_id}")
            appearance_ids = entry.get("AppearanceCharacterIds") or []
            appearance_names = [dm.get_character_name(cid) for cid in appearance_ids]
            characters = ", ".join(appearance_names) if appearance_names else "-"
            lines.append(f"[{comic_id}] {name}（{tab_name}）")
            lines.append(f"  登场角色: {characters}")
        output = "\n".join(lines)
    output = (output or "").rstrip()
    if output:
        await comic_cmd.finish(output)
