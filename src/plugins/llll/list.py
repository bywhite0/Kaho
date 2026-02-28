from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageSegment

from src.core.services.t2i import get_t2i_service
from ._common import get_dm_instance


list_cmd = on_command("list")


@list_cmd.handle()
async def _():
    dm = await get_dm_instance()
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
