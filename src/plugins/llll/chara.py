from nonebot import on_command
from nonebot.adapters.console import Message
from nonebot.params import CommandArg

from src.utils.formatters import parse_intro

from ._common import get_dm_instance


chara_cmd = on_command("chara")


@chara_cmd.handle()
async def _(args: Message = CommandArg()):
    dm = await get_dm_instance()
    query = args.extract_plain_text().strip()
    cid = dm.get_character_id_by_name(query)
    if not cid:
        output = "未找到。"
    else:
        lines = []
        char = dm.get_character(cid) or {}
        lines.append(f"\n=== {dm.get_character_name(cid)} ({cid}) ===")
        gen, unit = dm.get_generation_str(cid), dm.get_character_unit(cid)
        if gen:
            lines.append(f"期数: {gen}")
        if unit:
            lines.append(f"组合: {unit}")
        lines.append(f"声优: {char.get('CharacterVoice')}")
        parsed = parse_intro(char.get('Introduction', ''))
        label_map = {
            'Birthday': '生日',
            'Height': '身高',
            'Hobbies': '兴趣',
            'Special Skills': '特长',
            'Favorite Food': '喜欢的食物',
            'Favorite Word': '喜欢的一句话',
            'Favorite Subject': '喜欢的科目',
            'Favorite Animal': '喜欢的动物',
        }
        for k in ['Birthday', 'Height', 'Hobbies', 'Special Skills', 'Favorite Food', 'Favorite Word', 'Favorite Subject', 'Favorite Animal']:
            if k in parsed:
                lines.append(f"{label_map.get(k, k)}: {parsed[k]}")

        gifts = dm.get_favorite_gifts(cid)
        if gifts:
            lines.append("\n--- 喜好礼物 ---")
            for g in gifts:
                lines.append(f"  [{'★' * g['rank']}] {g['name']}")

        costume_groups = dm.get_costume_models_by_character(cid)
        if costume_groups:
            lines.append("\n--- 服装 ---")
            for costume_label, model_labels in costume_groups.items():
                if model_labels:
                    sample = " / ".join(model_labels[:5])
                    suffix = " ..." if len(model_labels) > 5 else ""
                    lines.append(f"  {costume_label}: {sample}{suffix}")
                else:
                    lines.append(f"  {costume_label}")

        lines.append("==============================\n")
        output = "\n".join(lines)
    output = (output or "").rstrip()
    if output:
        await chara_cmd.finish(output)
