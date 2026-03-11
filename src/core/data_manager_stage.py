class DataManagerStageMixin:
    def get_learning_stages(self, music_id):
        self._ensure("learning_stages")
        return self.learning_stages_by_music.get(music_id, [])

    def get_quest_live_stages(self, music_id):
        self._ensure("quest_live_stages")
        return self.quest_live_stages_by_music.get(music_id, [])

    def get_grade_live_stages(self, music_id):
        self._ensure("grade_live_stages")
        return self.grade_live_stages_by_music.get(music_id, [])

    def get_grand_prix_stages(self, music_id):
        self._ensure("grand_prix_stages")
        return self.grand_prix_stages_by_music.get(music_id, [])

    def get_standard_quest_area_name(self, area_id):
        self._ensure("standard_quest_areas")
        area = self.standard_quest_areas.get(area_id)
        if not area:
            return None
        return area.get("Name") or area.get("Description")

    def get_grade_quest_season_name(self, season_id):
        self._ensure("grade_quest_seasons")
        season = self.grade_quest_seasons.get(season_id)
        if not season:
            return None
        return season.get("Name")

    def get_quest_live_section_name(self, stage_entry):
        self._ensure("standard_quest_areas")
        area_name = self.get_standard_quest_area_name(
            stage_entry.get("StandardQuestAreasId")
        )
        stage_name = stage_entry.get("Name")
        if area_name:
            base = area_name
            if stage_name:
                return f"{base} {stage_name}"
            return base
        return stage_name

    def get_grade_live_section_name(self, stage_entry):
        self._ensure("grade_quest_series", "grade_quest_seasons")
        stage_id = stage_entry.get("Id")
        series_id = None
        if stage_id:
            stage_str = str(stage_id)
            if len(stage_str) >= 7:
                try:
                    series_id = int(stage_str[2:7])
                except ValueError:
                    series_id = None
        if series_id is None:
            series_id = stage_entry.get("GradeQuestSeriesId")
        series = self.grade_quest_series.get(series_id) if series_id else None
        series_name = series.get("Name") if series else None
        season_name = (
            self.get_grade_quest_season_name(series.get("GradeQuestSeasonId"))
            if series
            else None
        )
        if season_name and series_name:
            return f"{season_name} {series_name}"
        if series_name:
            return series_name
        return stage_entry.get("Name")

    def get_grand_prix_section_name(self, stage_entry):
        self._ensure("grand_prix_series", "grand_prix")
        series_id = stage_entry.get("GrandPrixSeriesId")
        series = self.grand_prix_series.get(series_id) if series_id else None
        gp_name = None
        if series:
            gp = self.grand_prix.get(series.get("GrandPrixesId"))
            if gp:
                gp_name = gp.get("Name")
        stage_name = stage_entry.get("Name")
        if gp_name and stage_name:
            return f"{gp_name} {stage_name}"
        return gp_name or stage_name

    def get_section_effects(self, stage_id):
        self._ensure("quest_sections", "section_skills", "section_skill_effects")
        sections = self.quest_sections_by_stage.get(stage_id, [])
        results = []
        for section in sections:
            section_skill_id = section.get("SectionSkillsId")
            section_skill = self.section_skills.get(section_skill_id)
            if not section_skill:
                continue
            effect_ids = section_skill.get("effect_ids", [])
            effect_ids.sort(
                key=lambda x: (
                    self.section_skill_effects.get(x, {}).get("OrderId", 0),
                    x,
                )
            )
            results.append(
                {
                    "section_no": section.get("SectionNo"),
                    "description": section_skill.get("Description")
                    or f"SectionSkill {section_skill_id}",
                    "effect_ids": effect_ids,
                    "skill_icon": section_skill.get("SkillIcon"),
                }
            )
        results.sort(key=lambda x: x["section_no"])
        return results

    def get_live_stage(self, stage_id):
        self._ensure("live_stages")
        return self.live_stages.get(stage_id)

    def get_stage_skill_sets(self, stage_skill_set_ids):
        self._ensure("stage_skills")
        results = []
        for set_id in stage_skill_set_ids:
            set_entry = self.stage_skill_sets.get(set_id)
            if not set_entry:
                continue
            condition_id = set_entry.get("StageSkillConditionId")
            effect_id = set_entry.get("StageSkillEffectId")
            condition = self.stage_skill_conditions.get(condition_id, {})
            effect = self.stage_skill_effects.get(effect_id, {})
            condition_details = self.stage_skill_condition_details.get(condition_id, [])
            effect_details = self.stage_skill_effect_details.get(effect_id, [])
            results.append(
                {
                    "id": set_id,
                    "condition_id": condition_id,
                    "effect_id": effect_id,
                    "condition": condition,
                    "condition_details": condition_details,
                    "effect": effect,
                    "effect_details": effect_details,
                }
            )
        return results

    def get_music_mastery(self, music_id):
        self._ensure("music_mastery")
        return self.music_mastery_levels.get(music_id, [])

    def get_music_mastery_skill_name(self, skill_id):
        self._ensure("music_mastery")
        return self.music_mastery_skills.get(skill_id)

    def get_mastery_bonus(self, skill_name, level):
        self._ensure("music_mastery")
        if not skill_name or level is None:
            return None
        if "ボルテージ" in skill_name:
            return self.music_mastery_bonus_voltage.get(level)
        if "メンタル" in skill_name:
            return self.music_mastery_bonus_mental.get(level)
        if "ビートハート" in skill_name:
            return self.music_mastery_bonus_heart.get(level)
        if "LOVE" in skill_name:
            return self.music_mastery_bonus_love.get(level)
        return None
