from nonebot import on_command
from nonebot.adapters.onebot.v11 import Message, MessageSegment
from nonebot.params import CommandArg

from src.core.services.t2i import get_t2i_service
from src.utils.formatters import parse_intro

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

    # Profile
    parsed = parse_intro(char.get("Introduction", ""))
    label_map = {
        "Birthday": "生日",
        "Height": "身高",
        "Hobbies": "兴趣",
        "Special Skills": "特长",
        "Favorite Food": "喜欢的食物",
        "Favorite Word": "喜欢的一句话",
        "Favorite Subject": "喜欢的科目",
        "Favorite Animal": "喜欢的动物",
    }
    for k in [
        "Birthday",
        "Height",
        "Hobbies",
        "Special Skills",
        "Favorite Food",
        "Favorite Word",
        "Favorite Subject",
        "Favorite Animal",
    ]:
        if k in parsed:
            data["profile"][label_map.get(k, k)] = parsed[k]

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
        img_bytes = await get_t2i_service().generate_image("chara.html", data)
    except Exception as e:
        await chara_cmd.finish(f"生成图片失败: {e}")
        return

    await chara_cmd.finish(MessageSegment.image(img_bytes))
