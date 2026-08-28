from nonebot import logger, on_command
from nonebot.adapters.onebot.v11 import Message, MessageSegment
from nonebot.params import CommandArg

from src.core.services.draw_api import get_draw_api_service
from src.core.services.draw_payloads import (
    CHARA_RENDER_ROUTE,
    build_chara_profile_items,
    build_chara_render_payload,
)
from src.core.services.t2i import get_t2i_service

from ._common import get_dm_instance

chara_cmd = on_command("chara")


@chara_cmd.handle()
async def _(args: Message = CommandArg()):
    dm = await get_dm_instance()
    query = args.extract_plain_text().strip()
    cid = dm.get_character_id_by_name(query)
    if not cid:
        await chara_cmd.finish("未找到。")
        return

    img_bytes = None
    draw_api = get_draw_api_service()
    if draw_api.enabled:
        try:
            payload = build_chara_render_payload(dm, cid)
            img_bytes = await draw_api.render(CHARA_RENDER_ROUTE, payload)
        except Exception:
            logger.exception("绘图服务渲染 chara 失败，回退 T2I")

    if img_bytes is None:
        img_bytes = await _render_t2i(dm, cid)
        if img_bytes is None:
            return

    await chara_cmd.finish(MessageSegment.image(img_bytes))


async def _render_t2i(dm, cid):
    char = dm.get_character(cid) or {}
    data = {
        "cid": cid,
        "name": dm.get_character_name(cid),
        "generation": dm.get_generation_str(cid),
        "unit": dm.get_character_unit(cid),
        "cv": char.get("CharacterVoice"),
        "profile": {},
        # 各学年/毕业时间点简介（MemberProfiles）
        "member_profiles": dm.get_member_profiles(cid),
        "gifts": [],
        "costumes": {},
    }

    # Profile（最终版数据的档案在 MemberProfiles，见 build_chara_profile_items）
    for item in build_chara_profile_items(dm, cid):
        data["profile"][item["label"]] = item["value"]

    # Gifts
    gifts = dm.get_favorite_gifts(cid)
    if gifts:
        data["gifts"] = gifts

    # Costumes
    costume_groups = dm.get_costume_models_by_character(cid)
    if costume_groups:
        for costume_label, model_labels in costume_groups.items():
            if model_labels:
                sample = " / ".join(model_labels[:5])
                suffix = " ..." if len(model_labels) > 5 else ""
                data["costumes"][costume_label] = f"{sample}{suffix}"
            else:
                data["costumes"][costume_label] = ""

    try:
        return await get_t2i_service().generate_image("chara.html", data)
    except Exception as e:
        await chara_cmd.finish(f"生成图片失败: {e}")
        return None
