from nonebot import on_command
from nonebot.adapters.onebot.v11 import Message, MessageSegment
from nonebot.params import CommandArg

from src.core.services.t2i import get_t2i_service
from ._common import get_dm_instance


comic_cmd = on_command("comic")
MAX_COMIC_RESULTS = 20


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
    if not query:
        await comic_cmd.finish("请输入关键词。")
        return
    search_results = dm.search_comics(query, limit=MAX_COMIC_RESULTS + 1)
    is_limited = len(search_results) > MAX_COMIC_RESULTS
    results = search_results[:MAX_COMIC_RESULTS]
    if not results:
        await comic_cmd.finish("未找到。")
        return

    comics = []
    for entry in results:
        comic_id = entry.get("Id")
        name = entry.get("Name") or ""
        tab_id = entry.get("TabListId")
        tab_name = TAB_LIST_MAP.get(tab_id, f"标签 {tab_id}")
        appearance_ids = entry.get("AppearanceCharacterIds") or []
        appearance_names = [dm.get_character_name(cid) for cid in appearance_ids]
        characters = ", ".join(appearance_names) if appearance_names else "-"

        comics.append(
            {
                "Id": comic_id,
                "Name": name,
                "tab_name": tab_name,
                "characters": characters,
            }
        )

    try:
        img_bytes = await get_t2i_service().generate_image(
            "comic.html",
            {
                "query": query,
                "results": comics,
                "is_limited": is_limited,
                "max_results": MAX_COMIC_RESULTS,
            },
        )
    except Exception as e:
        await comic_cmd.finish(f"生成图片失败: {e}")
        return

    await comic_cmd.finish(MessageSegment.image(img_bytes))
