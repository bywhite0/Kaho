from pathlib import Path
from datetime import datetime, timedelta, timezone

from nonebot import on_command
from nonebot.adapters.onebot.v11 import Message, MessageSegment
from nonebot.params import CommandArg

from src.core.services.t2i import get_t2i_service
from ._common import build_skill_block, build_state_images, get_dm_instance


card_cmd = on_command("card")


def _format_release_time_utc8(raw_time):
    if raw_time is None:
        return None
    text = str(raw_time).strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return text
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    utc8 = timezone(timedelta(hours=8))
    return dt.astimezone(utc8).strftime("%Y-%m-%d %H:%M:%S (UTC+8)")


def _build_skill_material_categories(skill_mats):
    categories = {}
    for entry in skill_mats or []:
        for mat in entry.get("materials") or []:
            name = str(mat.get("name") or "").strip()
            if "技能書" in name or "技能书" in name:
                continue
            if "R3" not in name.upper():
                continue
            item_id = mat.get("id")
            key = item_id if item_id is not None else name
            if key not in categories:
                categories[key] = {"id": item_id, "name": name}
    return list(categories.values())


def _resolve_sticker_ids(all_cards, project_root):
    sticker_dir = project_root / "exports" / "images" / "sticker"
    sticker_ids = []
    for card in all_cards:
        card_id = card.get("Id")
        if card_id is None:
            continue
        sticker_file = sticker_dir / f"image_sticker_{card_id}.png"
        if sticker_file.exists():
            sticker_ids.append(card_id)
    return sorted(sticker_ids)


@card_cmd.handle()
async def _(args: Message = CommandArg()):
    dm = await get_dm_instance()
    query = args.extract_plain_text().strip()
    if not query:
        await card_cmd.finish("请输入卡牌ID。")
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
    project_root = Path(__file__).resolve().parents[3]
    series_meta = dm.get_card_series_meta(series_id)
    lim_type = dm.LIMITED_TYPES.get(
        series_meta.get("LimitedType"), f"Type {series_meta.get('LimitedType')}"
    )

    gachas_info = dm.get_gachas_for_series(series_id)
    gacha_names = [g["name"] for g in gachas_info]
    release_date = (
        _format_release_time_utc8(gachas_info[0]["start_time"]) if gachas_info else None
    )

    skill_mats = dm.get_card_skill_levelup_materials(series_id)
    skill_material_categories = _build_skill_material_categories(skill_mats)

    data = {
        "series_id": series_id,
        "base": base,
        "character_name": dm.get_character_name(base["CharactersId"]),
        "rarity_name": dm.get_rarity_name(base["Rarity"]),
        "limited_type": lim_type,
        "style_name": dm.STYLES.get(base["Style"]),
        "mood_name": dm.MOODS.get(base["Mood"]),
        "gachas": gacha_names,
        "release_date": release_date,
        "skill_materials": skill_material_categories,
        "all_cards": all_cards,
    }
    data["sticker_ids"] = _resolve_sticker_ids(all_cards, project_root)
    character_entry = dm.get_character(base.get("CharactersId")) or {}
    last_name = str(character_entry.get("NameLast") or "").strip()
    first_name = str(character_entry.get("NameFirst") or "").strip()
    if last_name and first_name:
        data["character_name_jp_spaced"] = f"{last_name}　{first_name}"
    else:
        data["character_name_jp_spaced"] = data["character_name"]

    rarity_id = base.get("Rarity")
    is_dr_rarity = rarity_id == 8
    theme_color = dm.get_character_theme_color(base.get("CharactersId")) or "#f8b500"
    card_nameplate_id = None
    if not is_dr_rarity:
        try:
            rarity_token = f"{int(rarity_id):02d}"
        except (TypeError, ValueError):
            rarity_token = str(rarity_id)
        char_id = base.get("CharactersId")
        if char_id is not None:
            card_nameplate_id = f"{char_id}_{rarity_token}"
            nameplate_file = (
                project_root
                / "exports"
                / "images"
                / "gacha_cardinfo"
                / f"image_gacha_cardinfo_{card_nameplate_id}.png"
            )
            if not nameplate_file.exists():
                card_nameplate_id = None

    data["character_theme_color"] = theme_color
    data["card_nameplate_id"] = card_nameplate_id
    data["is_dr_rarity"] = is_dr_rarity

    cost_s = dm.get_cost_transition(
        series_id, "SkillSeriesId", dm.get_card_skills_map(), "SkillCost"
    )
    cost_sa = dm.get_cost_transition(
        series_id, "SpecialAppealSeriesId", dm.get_card_skills_map(), "SkillCost"
    )
    sis_skill_data = dm.get_all_skills_data(base.get("SkillSeriesId"))
    sis_special_data = dm.get_all_skills_data(base.get("SpecialAppealSeriesId"))
    sis_attribute_data = dm.get_all_skills_data(base.get("AttributeId"))

    data["sis_skill_view"], sis_skill_icon_id = build_skill_block(
        dm,
        sis_skill_data,
        "技能: ",
        cost_str=f"（AP 消耗: {cost_s}）",
    )
    if sis_skill_icon_id:
        data["sis_skill_icon_id"] = sis_skill_icon_id

    data["sis_special_view"], sis_special_icon_id = build_skill_block(
        dm,
        sis_special_data,
        "特殊演出: ",
        cost_str=f"（AP 消耗: {cost_sa}）",
    )
    if sis_special_icon_id:
        data["sis_special_icon_id"] = sis_special_icon_id

    data["sis_attribute_view"], sis_attribute_icon_id = build_skill_block(
        dm, sis_attribute_data, "特性: "
    )
    if sis_attribute_icon_id:
        data["sis_attribute_icon_id"] = sis_attribute_icon_id

    cost_r = dm.get_cost_transition(
        series_id, "RhythmGameSkillSeriesId", dm.get_rhythm_skills_map(), "ConsumeAP"
    )
    data["rhythm_skill_view"], _ = build_skill_block(
        dm,
        dm.get_all_rhythm_skills_data(base.get("RhythmGameSkillSeriesId")),
        "技能: ",
        cost_str=f"（AP 消耗: {cost_r}）",
        show_type=False,
    )
    data["center_skill_view"], _ = build_skill_block(
        dm,
        dm.get_all_center_skills_data(base.get("CenterSkillSeriesId")),
        "Center 技能: ",
        show_type=False,
    )

    c_attr_id = base.get("CenterAttributeSeriesId")
    if c_attr_id:
        attrs = dm.get_center_attributes_map().get(c_attr_id, [])
        if attrs:
            unique_attrs = {}
            for a in attrs:
                key = (a["CenterAttributeName"], a["Description"])
                if key not in unique_attrs:
                    unique_attrs[key] = a
            data["center_attributes"] = list(unique_attrs.values())

    duet_ids = dm.get_duet_voice_character_ids(series_id)
    if duet_ids:
        data["duet_voice"] = [dm.get_character_name(cid) for cid in duet_ids]

    data["style_voice_entries"] = dm.get_style_voice_entries(series_id)
    data["has_style_movie"] = dm.has_style_movie(series_id)

    state_0_card = next((c for c in all_cards if c["Id"] % 10 == 0), None)
    state_1_card = next((c for c in all_cards if c["Id"] % 10 == 1), None)

    if state_0_card:
        state_0_full, deck_frame_chara, imgs = build_state_images(
            dm, state_0_card["Id"], series_id
        )
        if deck_frame_chara:
            data["deck_frame_chara"] = deck_frame_chara
        if state_0_full:
            data["state_0_full"] = state_0_full
        data["state_0_images"] = imgs

    if state_1_card:
        data["state_1_label"] = (
            "形态 1（特训后）" if state_0_card else "形态 1（仅此形态）"
        )
        state_1_full, deck_frame_chara, imgs = build_state_images(
            dm, state_1_card["Id"], series_id
        )
        if deck_frame_chara and "deck_frame_chara" not in data:
            data["deck_frame_chara"] = deck_frame_chara
        if state_1_full:
            data["state_1_full"] = state_1_full

        data["state_1_images"] = imgs

    try:
        img_bytes = await get_t2i_service().generate_image("card.html", data)
    except Exception as e:
        await card_cmd.finish(f"生成图片失败: {e}")
        return

    await card_cmd.finish(MessageSegment.image(img_bytes))
