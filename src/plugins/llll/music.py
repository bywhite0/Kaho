from nonebot import on_command
from nonebot.adapters.console import Message
from nonebot.params import CommandArg

from ._common import get_dm_instance


music_cmd = on_command("music")


def _append_stage_info(lines, dm, stage_entries, fever_section_no=None, show_level=False, level_key=None, level_label="Lv", group_type=None):
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
        prefix = f"    {level_label}{level_value}: " if show_level and level_value is not None else "    "
        if section_name:
            lines.append(f"{prefix}{section_name}")
        else:
            lines.append(f"{prefix}{stage_name}")
        if stage_desc:
            lines.append(f"      {stage_desc}")
        if group_type in ["quest", "grade"]:
            section_effects = dm.get_section_effects(stage_entry.get("Id"))
            if section_effects:
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
                lines.append("      区段效果:")
                for effect in section_effects:
                    desc = effect.get("description")
                    lines.append(f"        - {desc}")
        if live_stage:
            skill_desc = live_stage.get("StageSkillDescription") or ""
            if skill_desc:
                lines.append(f"      舞台技能: {skill_desc}")
            stage_skill_sets = dm.get_stage_skill_sets(live_stage.get("StageSkillSetIds") or [])
            if stage_skill_sets:
                lines.append("      舞台区段效果:")
                for ss in stage_skill_sets:
                    condition_details = ss["condition_details"]
                    effect_details = ss["effect_details"]
                    effect_parts = []
                    for detail in effect_details:
                        effect_parts.append(f"{detail.get('SkillEffectDetailType')}={detail.get('EffectValue')}")
                    effect_text = " / ".join(effect_parts) if effect_parts else "-"
                    lines.append(f"        区段 {ss['id']}: {effect_text}")


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
        output = "未找到。"
    else:
        lines = []
        for entry in results:
            music_id = entry.get("Id")
            title = entry.get("Title") or ""
            desc = entry.get("Description") or ""
            song_type = entry.get("SongType")
            song_type_label = dm.get_song_type_label(song_type)
            music_type = entry.get("MusicType")
            mood_name = dm.MOODS.get(music_type) if music_type is not None else None
            play_time_ms = entry.get("PlayTime")
            center_id = entry.get("CenterCharacterId")
            center_name = dm.get_character_name(center_id) if center_id else "-"
            singers = []
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
            lines.append(f"[{music_id}] {title}")
            lines.append(f"  简介: {desc}")
            if song_type_label:
                lines.append(f"  歌曲类型: {song_type}（{song_type_label}）")
            else:
                lines.append(f"  歌曲类型: {song_type}")
            if mood_name:
                lines.append(f"  心情: {mood_name}")
            elif music_type is not None:
                lines.append(f"  心情: {music_type}")
            if play_time_ms is not None:
                duration_text = _format_duration(play_time_ms)
                lines.append(f"  时长: {play_time_ms} 毫秒（{duration_text}）")
            lines.append(f"  Center: {center_name}")
            if singers:
                lines.append(f"  演唱: {', '.join(singers)}")
            if supports:
                lines.append(f"  支援角色: {', '.join(supports)}")

            score = dm.get_music_score(music_id)
            fever_section_no = entry.get("FeverSectionNo")
            if score:
                lines.append("\n[节奏模式]")
                lines.append(f"  难度: N{score.get('NormalLevel')} / H{score.get('HardLevel')} / E{score.get('ExpertLevel')} / M{score.get('MasterLevel')}")
                lines.append(f"  最大连击数: N{score.get('NormalMaxCombo')} / H{score.get('HardMaxCombo')} / E{score.get('ExpertMaxCombo')} / M{score.get('MasterMaxCombo')}")

            quest_live_stages = dm.get_quest_live_stages(music_id)
            grade_live_stages = dm.get_grade_live_stages(music_id)
            grand_prix_stages = dm.get_grand_prix_stages(music_id)
            if quest_live_stages or grade_live_stages or grand_prix_stages:
                lines.append("\n[舞台模式]")
                if quest_live_stages:
                    lines.append("  Quest Live:")
                    _append_stage_info(lines, dm, quest_live_stages, fever_section_no=fever_section_no, show_level=True, level_key="QuestLevel", group_type="quest")
                if grade_live_stages:
                    lines.append("  Grade Live:")
                    _append_stage_info(lines, dm, grade_live_stages, fever_section_no=fever_section_no, show_level=True, level_key="LivePoint", level_label="LivePoint", group_type="grade")
                if grand_prix_stages:
                    lines.append("  Live Grand Prix:")
                    _append_stage_info(lines, dm, grand_prix_stages, fever_section_no=fever_section_no, show_level=True, level_key="QuestLevel", group_type="grand_prix")

            mastery_levels = dm.get_music_mastery(music_id)
            if mastery_levels:
                lines.append("\n[熟练度]")
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
                    lines.append(f"  等级{level}: {skill_name} | {bonus_text}")
        output = "\n".join(lines)
    output = (output or "").rstrip()
    if output:
        await music_cmd.finish(output)
