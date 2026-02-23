from nonebot import on_command
from nonebot.adapters.onebot.v11 import Message, MessageSegment
from nonebot.params import CommandArg

from src.core.services.t2i import get_t2i_service
from ._common import get_dm_instance


music_cmd = on_command("music")


def _get_stage_info(dm, stage_entries, fever_section_no=None, level_key=None, group_type=None):
    stages = []
    for stage_entry in stage_entries:
        level_value = stage_entry.get(level_key) if level_key else None
        live_stage_id = stage_entry.get("LiveStagesId")
        live_stage = dm.get_live_stage(live_stage_id) if live_stage_id else None
        stage_name = live_stage.get("Name") if live_stage else stage_entry.get("Name") or f"Stage {live_stage_id}"
        stage_desc = live_stage.get("Description") if live_stage else stage_entry.get("Description") or ""
        
        section_name = None
        if group_type == "quest":
            section_name = dm.get_quest_live_section_name(stage_entry)
        elif group_type == "grade":
            section_name = dm.get_grade_live_section_name(stage_entry)
        elif group_type == "grand_prix":
            section_name = dm.get_grand_prix_section_name(stage_entry)
            
        stage_data = {
            "name": section_name if section_name else stage_name,
            "level": level_value,
            "desc": stage_desc,
            "effects": []
        }
        
        if group_type in ["quest", "grade"]:
            section_effects = dm.get_section_effects(stage_entry.get("Id"))
            if section_effects:
                # Fever section handling
                if fever_section_no is not None and len(section_effects) > 1:
                    try:
                        target = int(fever_section_no)
                    except:
                        target = None
                    if target is not None:
                        target_index = target - 1 if target > 0 else 0
                        if 0 <= target_index < len(section_effects):
                            first_effect = section_effects.pop(0)
                            section_effects.insert(target_index, first_effect)
                
                for effect in section_effects:
                    stage_data["effects"].append({
                        "text": effect.get("description"),
                        "icon_id": effect.get("skill_icon")
                    })
                    
        if live_stage:
            skill_desc = live_stage.get("StageSkillDescription") or ""
            if skill_desc:
                stage_data["effects"].append({"text": f"舞台技能: {skill_desc}"})
            
            stage_skill_sets = dm.get_stage_skill_sets(live_stage.get("StageSkillSetIds") or [])
            if stage_skill_sets:
                for ss in stage_skill_sets:
                    condition_details = ss["condition_details"]
                    effect_details = ss["effect_details"]
                    effect_parts = []
                    for detail in effect_details:
                        effect_parts.append(f"{detail.get('SkillEffectDetailType')}={detail.get('EffectValue')}")
                    effect_text = " / ".join(effect_parts) if effect_parts else "-"
                    stage_data["effects"].append({"text": f"区段 {ss['id']}: {effect_text}"})
        
        stages.append(stage_data)
    return stages


def _format_duration(ms_value):
    try:
        total_seconds = int(ms_value) // 1000
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        return f"{minutes}:{seconds:02d}"
    except:
        return str(ms_value)


@music_cmd.handle()
async def _(args: Message = CommandArg()):
    dm = await get_dm_instance()
    query = args.extract_plain_text().strip()
    results = dm.search_musics(query)
    if not results:
        await music_cmd.finish("未找到。")
        return

    musics_data = []
    for entry in results:
        music_id = entry.get("Id")
        
        # Basic Info
        singers = []
        center_id = entry.get("CenterCharacterId")
        if center_id:
            singers.append(dm.get_character_name(center_id))
        for cid in (entry.get("SingerCharacterId") or []):
            name = dm.get_character_name(cid)
            if name not in singers:
                singers.append(name)
                
        supports = []
        for cid in (entry.get("SupportCharacterId") or []):
            if cid and cid != 0:
                supports.append(dm.get_character_name(cid))

        music_data = {
            "music_id": music_id,
            "title": entry.get("Title") or "",
            "description": entry.get("Description") or "",
            "song_type": entry.get("SongType"),
            "song_type_label": dm.get_song_type_label(entry.get("SongType")),
            "mood_name": dm.MOODS.get(entry.get("MusicType")) if entry.get("MusicType") is not None else entry.get("MusicType"),
            "play_time_ms": entry.get("PlayTime"),
            "duration_text": _format_duration(entry.get("PlayTime")),
            "center_name": dm.get_character_name(center_id) if center_id else "-",
            "singers": singers,
            "supports": supports,
            "fever_section_no": entry.get("FeverSectionNo"),
        }

        # Score
        score = dm.get_music_score(music_id)
        if score:
            music_data["score"] = score

        # Stages
        fever_section_no = entry.get("FeverSectionNo")
        quest_live_stages = dm.get_quest_live_stages(music_id)
        grade_live_stages = dm.get_grade_live_stages(music_id)
        grand_prix_stages = dm.get_grand_prix_stages(music_id)
        
        if quest_live_stages:
            music_data["quest_live_stages"] = _get_stage_info(dm, quest_live_stages, fever_section_no=fever_section_no, level_key="QuestLevel", group_type="quest")
        if grade_live_stages:
            music_data["grade_live_stages"] = _get_stage_info(dm, grade_live_stages, fever_section_no=fever_section_no, level_key="LivePoint", group_type="grade")
        if grand_prix_stages:
            music_data["grand_prix_stages"] = _get_stage_info(dm, grand_prix_stages, fever_section_no=fever_section_no, level_key="QuestLevel", group_type="grand_prix")

        # Mastery
        mastery_levels = dm.get_music_mastery(music_id)
        if mastery_levels:
            music_data["mastery_levels"] = []
            for mastery in mastery_levels:
                level = mastery.get("Level")
                skill_id = mastery.get("MusicMasterySkillsId")
                skill_name = dm.get_music_mastery_skill_name(skill_id) or f"技能 {skill_id}"
                bonus = dm.get_mastery_bonus(skill_name, level) or {}
                if "GainVoltagePt" in bonus:
                    bonus_text = f"需求电压点 {bonus.get('DemandVoltagePt')} / 获得电压点 {bonus.get('GainVoltagePt')}"
                elif "GainMentalPt" in bonus:
                    bonus_text = f"需求伤害点 {bonus.get('DemandDamagePt')} / 获得体力点 {bonus.get('GainMentalPt')}"
                elif "LoveRate" in bonus:
                    bonus_text = f"好感倍率 {bonus.get('LoveRate')}"
                else:
                    bonus_text = "-"
                
                music_data["mastery_levels"].append({
                    "level": level,
                    "skill_name": skill_name,
                    "bonus_text": bonus_text
                })

        # Chart Data
        chart_data = dm.get_music_chart_data(music_id)
        if chart_data:
            music_data["chart"] = chart_data
        
        musics_data.append(music_data)

    try:
        img_bytes = await get_t2i_service().generate_image("music.html", {"musics": musics_data})
    except Exception as e:
        await music_cmd.finish(f"生成图片失败: {e}")
        return

    await music_cmd.finish(MessageSegment.image(img_bytes))
