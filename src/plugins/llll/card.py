from nonebot import on_command
from nonebot.adapters.console import Message
from nonebot.params import CommandArg

from src.utils.formatters import print_merged_skill

from ._common import get_dm_instance


card_cmd = on_command("card")


@card_cmd.handle()
async def _(args: Message = CommandArg()):
    dm = await get_dm_instance()
    query = args.extract_plain_text().strip()
    if not query:
        return
    val = int(query)
    series_id = val if val < 10000000 else val // 10
    all_cards = dm.get_card_series_data(series_id)
    if not all_cards:
        output = "未找到。"
    else:
        lines = []
        base = all_cards[0]
        series_meta = dm.get_card_series_meta(series_id)
        lim_type = dm.LIMITED_TYPES.get(series_meta.get('LimitedType'), f"Type {series_meta.get('LimitedType')}")

        lines.append(f"\n=== 卡牌: {base['Name']} ({series_id}) ===")
        lines.append(f"角色: {dm.get_character_name(base['CharactersId'])}")
        lines.append(f"稀有度: {dm.get_rarity_name(base['Rarity'])} | 限定类型: {lim_type}")
        lines.append(f"风格: {dm.STYLES.get(base['Style'])} | 心情: {dm.MOODS.get(base['Mood'])}")

        gachas = dm.get_gachas_for_series(series_id)
        if gachas:
            lines.append(f"登场卡池: {', '.join(gachas)}")

        lines.append("\n--- 最大数值 ---")
        lines.append(f"{'ID':<10} | {'State':<5} | {'Smile':<5} | {'Pure':<5} | {'Cool':<5} | {'Mental':<6}")
        lines.append("-" * 55)
        for c in all_cards:
            lines.append(f"{c['Id']:<10} | {c['Id'] % 10:<5} | {c['MaxSmile']:<5} | {c['MaxPure']:<5} | {c['MaxCool']:<5} | {c['MaxMental']:<6}")

        lines.append("\n[SIS Mode (School Idol Stage)]")
        cost_s = dm.get_cost_transition(series_id, 'SkillSeriesId', dm.get_card_skills_map(), 'SkillCost')
        cost_sa = dm.get_cost_transition(series_id, 'SpecialAppealSeriesId', dm.get_card_skills_map(), 'SkillCost')
        lines.append(print_merged_skill(dm, dm.get_all_skills_data(base.get('SkillSeriesId')), "技能: ", cost_str=f"（AP 消耗: {cost_s}）") or "")
        lines.append(print_merged_skill(dm, dm.get_all_skills_data(base.get('SpecialAppealSeriesId')), "\n特殊演出: ", cost_str=f"（AP 消耗: {cost_sa}）") or "")
        lines.append(print_merged_skill(dm, dm.get_all_skills_data(base.get('AttributeId')), "\n特性: ") or "")

        lines.append("\n[Rhythm Mode (School Idol Show)]")
        cost_r = dm.get_cost_transition(series_id, 'RhythmGameSkillSeriesId', dm.get_rhythm_skills_map(), 'ConsumeAP')

        lines.append(print_merged_skill(dm, dm.get_all_rhythm_skills_data(base.get('RhythmGameSkillSeriesId')), "技能: ", cost_str=f"（AP 消耗: {cost_r}）", show_type=False) or "")
        lines.append(print_merged_skill(dm, dm.get_all_center_skills_data(base.get('CenterSkillSeriesId')), "\nCenter 技能: ", show_type=False) or "")

        c_attr_id = base.get('CenterAttributeSeriesId')
        if c_attr_id:
            attrs = dm.get_center_attributes_map().get(c_attr_id, [])
            if attrs:
                lines.append("\nCenter 属性:")
                unique_attrs = {}
                for a in attrs:
                    key = (a['CenterAttributeName'], a['Description'])
                    if key not in unique_attrs:
                        unique_attrs[key] = a
                for a in unique_attrs.values():
                    lines.append(f"  {a['CenterAttributeName']}: {a['Description']}")

        duet_ids = dm.get_duet_voice_character_ids(series_id)
        if duet_ids:
            duet_names = [dm.get_character_name(cid) for cid in duet_ids]
            lines.append("\n[互动语音]")
            lines.append(f"角色: {', '.join(duet_names)}")

        style_voice_entries = dm.get_style_voice_entries(series_id)
        has_style_movie = dm.has_style_movie(series_id)
        if style_voice_entries or (base.get('Rarity') in [5, 7, 9] and has_style_movie):
            lines.append("\n[风格素材]")
            if base.get('Rarity') in [5, 7, 9] and has_style_movie:
                lines.append(f"视频: picture_ur_get_{series_id}_in.usm / picture_ur_get_{series_id}_loop.usm")
            if style_voice_entries:
                lines.append("语音:")
                for entry in style_voice_entries:
                    lines.append(f"  {entry['name']}: {entry['voice']}")

        lines.append("\n--- 图片资源 ---")
        lines.append("[通用]")
        lines.append(f"  deck_frame_chara: image_deck_frame_chara_{series_id}.png")
        state_0_card = next((c for c in all_cards if c['Id'] % 10 == 0), None)
        state_1_card = next((c for c in all_cards if c['Id'] % 10 == 1), None)

        if state_0_card:
            lines.append("[形态 0（特训前）]")
            images = dm.get_image_set(state_0_card['Id'])
            images.pop("deck_frame_chara", None)
            for k, v in images.items():
                lines.append(f"  {k}: {v}")

        if state_1_card:
            label = "形态 1（特训后）" if state_0_card else "形态 1（仅此形态）"
            lines.append(f"\n[{label}]")
            images = dm.get_image_set(state_1_card['Id'])
            images.pop("deck_frame_chara", None)
            for k, v in images.items():
                lines.append(f"  {k}: {v}")

        icons = dm.get_skill_icons(base.get('SkillSeriesId'), base.get('SpecialAppealSeriesId'), base.get('AttributeId'))
        if icons:
            lines.append("\n[图标]")
            for k, v in icons.items():
                lines.append(f"  {k}: {v}")

        lines.append("==============================\n")
        lines = [line for line in lines if line]
        output = "\n".join(lines)
    output = (output or "").rstrip()
    if output:
        await card_cmd.finish(output)
