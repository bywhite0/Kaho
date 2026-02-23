from nonebot import on_command
from nonebot.adapters.onebot.v11 import Message, MessageSegment
from nonebot.params import CommandArg

from src.utils.formatters import print_merged_skill
from src.core.services.t2i import get_t2i_service
from ._common import get_dm_instance


card_cmd = on_command("card")


@card_cmd.handle()
async def _(args: Message = CommandArg()):
    dm = await get_dm_instance()
    query = args.extract_plain_text().strip()
    if not query:
        return
    try:
        val = int(query)
    except ValueError:
        await card_cmd.finish("请输入有效的卡牌ID。")
        return

    series_id = val if val < 10000000 else val // 10
    all_cards = dm.get_card_series_data(series_id)
    if not all_cards:
        await card_cmd.finish("未找到。")
        return

    base = all_cards[0]
    series_meta = dm.get_card_series_meta(series_id)
    lim_type = dm.LIMITED_TYPES.get(series_meta.get('LimitedType'), f"Type {series_meta.get('LimitedType')}")

    gachas_info = dm.get_gachas_for_series(series_id)
    gacha_names = [g['name'] for g in gachas_info]
    release_date = gachas_info[0]['start_time'] if gachas_info else None
    
    evo1_id = series_meta.get('Evolution1Id')
    evo_mats = dm.get_card_evolution_materials(evo1_id) if evo1_id else []
    
    skill_mats = dm.get_card_skill_levelup_materials(series_id)

    data = {
        "series_id": series_id,
        "base": base,
        "character_name": dm.get_character_name(base['CharactersId']),
        "rarity_name": dm.get_rarity_name(base['Rarity']),
        "limited_type": lim_type,
        "style_name": dm.STYLES.get(base['Style']),
        "mood_name": dm.MOODS.get(base['Mood']),
        "gachas": gacha_names,
        "release_date": release_date,
        "evolution_materials": evo_mats,
        "skill_materials": skill_mats,
        "all_cards": all_cards,
    }

    # SIS Mode Skills
    cost_s = dm.get_cost_transition(series_id, 'SkillSeriesId', dm.get_card_skills_map(), 'SkillCost')
    cost_sa = dm.get_cost_transition(series_id, 'SpecialAppealSeriesId', dm.get_card_skills_map(), 'SkillCost')
    
    data["sis_skill_text"] = print_merged_skill(dm, dm.get_all_skills_data(base.get('SkillSeriesId')), "技能: ", cost_str=f"（AP 消耗: {cost_s}）")
    data["sis_special_text"] = print_merged_skill(dm, dm.get_all_skills_data(base.get('SpecialAppealSeriesId')), "特殊演出: ", cost_str=f"（AP 消耗: {cost_sa}）")
    data["sis_attribute_text"] = print_merged_skill(dm, dm.get_all_skills_data(base.get('AttributeId')), "特性: ")

    # Rhythm Mode Skills
    cost_r = dm.get_cost_transition(series_id, 'RhythmGameSkillSeriesId', dm.get_rhythm_skills_map(), 'ConsumeAP')
    data["rhythm_skill_text"] = print_merged_skill(dm, dm.get_all_rhythm_skills_data(base.get('RhythmGameSkillSeriesId')), "技能: ", cost_str=f"（AP 消耗: {cost_r}）", show_type=False)
    data["center_skill_text"] = print_merged_skill(dm, dm.get_all_center_skills_data(base.get('CenterSkillSeriesId')), "Center 技能: ", show_type=False)

    # Center Attributes
    c_attr_id = base.get('CenterAttributeSeriesId')
    if c_attr_id:
        attrs = dm.get_center_attributes_map().get(c_attr_id, [])
        if attrs:
            unique_attrs = {}
            for a in attrs:
                key = (a['CenterAttributeName'], a['Description'])
                if key not in unique_attrs:
                    unique_attrs[key] = a
            data["center_attributes"] = list(unique_attrs.values())

    # Duet Voice
    duet_ids = dm.get_duet_voice_character_ids(series_id)
    if duet_ids:
        data["duet_voice"] = [dm.get_character_name(cid) for cid in duet_ids]

    # Style Voice & Movie
    data["style_voice_entries"] = dm.get_style_voice_entries(series_id)
    data["has_style_movie"] = dm.has_style_movie(series_id)

    # Images
    state_0_card = next((c for c in all_cards if c['Id'] % 10 == 0), None)
    state_1_card = next((c for c in all_cards if c['Id'] % 10 == 1), None)

    if state_0_card:
        imgs = dm.get_image_set(state_0_card['Id'])
        imgs.pop("deck_frame_chara", None)
        data["state_0_images"] = imgs
    
    if state_1_card:
        data["state_1_label"] = "形态 1（特训后）" if state_0_card else "形态 1（仅此形态）"
        imgs = dm.get_image_set(state_1_card['Id'])
        imgs.pop("deck_frame_chara", None)
        data["state_1_images"] = imgs

    # Icons
    data["icons"] = dm.get_skill_icons(base.get('SkillSeriesId'), base.get('SpecialAppealSeriesId'), base.get('AttributeId'))

    try:
        img_bytes = await get_t2i_service().generate_image("card.html", data)
    except Exception as e:
        await card_cmd.finish(f"生成图片失败: {e}")
        return

    await card_cmd.finish(MessageSegment.image(img_bytes))
