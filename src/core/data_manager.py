import csv
import os
import re

from src.core.services.data_store import DataStore
from src.core.data_manager_search import DataManagerSearchMixin
from src.core.data_manager_stage import DataManagerStageMixin


class DataManager(DataManagerSearchMixin, DataManagerStageMixin):
    def __init__(self, data_dir):
        self.data_dir = data_dir
        self.cache_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "cache",
            "plain",
        )
        self.data = {}
        self.store = DataStore(data_dir)
        self.card_datas = []
        self.card_series_index = {}
        self.cards_by_character_index = {}
        self.card_series_heads = []
        self.card_rarities = {}
        self.characters = {}
        self.character_alias_map = {}
        self.skill_series = {}
        self.skills = {}
        self.items = {}
        self.favorite_gifts = {}
        self.char_units = {}
        self.gachas = []
        self.card_series_meta = {}
        self.costumes = {}
        self.costume_models = []
        self.card_duet_voices = {}
        self.style_voice_entries = {}
        self.style_movie_series = set()
        self.comics = []
        self.comic_by_id = {}
        self.comics_by_character = {}
        self.musics = []
        self.music_by_id = {}
        self.musics_by_character = {}
        self.song_type_map = {}
        self.music_scores = {}
        self.learning_stages_by_music = {}
        self.quest_live_stages_by_music = {}
        self.grade_live_stages_by_music = {}
        self.grand_prix_stages_by_music = {}
        self.live_stages = {}
        self.standard_quest_areas = {}
        self.grade_quest_seasons = {}
        self.grade_quest_series = {}
        self.grand_prix_series = {}
        self.grand_prix = {}
        self.section_skills = {}
        self.section_skill_effects = {}
        self.section_skill_effect_details = {}
        self.quest_sections_by_stage = {}
        self.stage_skill_sets = {}
        self.stage_skill_conditions = {}
        self.stage_skill_condition_details = {}
        self.stage_skill_effects = {}
        self.stage_skill_effect_details = {}
        self.music_mastery_levels = {}
        self.music_mastery_skills = {}
        self.music_mastery_bonus_voltage = {}
        self.music_mastery_bonus_mental = {}
        self.music_mastery_bonus_heart = {}
        self.music_mastery_bonus_love = {}

        self.center_skills = {}
        self.center_attributes = {}
        self.rhythm_skills = {}

        self.token_skill_map = {}

        self._loaded = set()

        self.unit_names = {
            100: "蓮ノ空女学院スクールアイドルクラブ",
            101: "スリーズブーケ",
            102: "DOLLCHESTRA",
            103: "みらくらぱーく！",
            105: "Edel Note",
        }

        self.STYLES = {
            1: "Performer",
            2: "Mood Maker",
            3: "Cheerleader",
            4: "Trickster",
        }
        self.MOODS = {1: "Happy", 2: "Neutral", 3: "Mellow"}

        self.LIMITED_TYPES = {
            0: "常驻",
            1: "春季限定",
            2: "夏季限定",
            3: "秋季限定",
            4: "冬季限定",
            5: "毕业限定",
            9: "生日限定",
            11: "派对限定",
            101: "Live Grand Prix 奖励",
            201: "偶像活动！限定",
            202: "音击限定",
            203: "BanG Dream! 限定",
            204: "混组限定",
        }

    def sanitize_yaml(self, content):
        return re.sub(r":\s+-\s*$", r': "-"', content, flags=re.MULTILINE)

    def load_yaml_file(self, filename):
        try:
            return self.store.load_yaml_file(filename, self.sanitize_yaml)
        except Exception as e:
            print(f"Error loading {filename}: {e}")
            return None

    def load_data(self):
        self._ensure_all()

    def sync_version_cache(self, version_path):
        return self.store.sync_version(version_path, self.sanitize_yaml)

    def _ensure_all(self):
        self._ensure(
            "characters",
            "card_rarities",
            "card_datas",
            "card_series_meta",
            "skill_series",
            "skills",
            "items",
            "favorite_gifts",
            "unit_characters",
            "gachas",
            "costumes",
            "costume_models",
            "card_duet_voices",
            "style_voices",
            "style_movies",
            "comics",
            "musics",
            "music_scores",
            "learning_stages",
            "quest_live_stages",
            "grade_live_stages",
            "grand_prix_stages",
            "live_stages",
            "standard_quest_areas",
            "grade_quest_seasons",
            "grade_quest_series",
            "grand_prix_series",
            "grand_prix",
            "section_skills",
            "section_skill_effects",
            "section_skill_effect_details",
            "quest_sections",
            "stage_skills",
            "music_mastery",
            "center_skills",
            "center_attributes",
            "rhythm_skills",
            "token_skill_map",
            "card_evolution_materials",
            "card_skill_levelup_materials",
        )

    def _ensure(self, *groups):
        for group in groups:
            if group in self._loaded:
                continue
            if group == "characters":
                self._load_characters()
            elif group == "card_rarities":
                self._load_card_rarities()
            elif group == "card_datas":
                self._load_card_datas()
            elif group == "card_series_meta":
                self._load_card_series_meta()
            elif group == "skill_series":
                self._load_skill_series()
            elif group == "skills":
                self._load_skills()
            elif group == "items":
                self._load_items()
            elif group == "favorite_gifts":
                self._load_favorite_gifts()
            elif group == "unit_characters":
                self._load_unit_characters()
            elif group == "gachas":
                self._load_gachas()
            elif group == "costumes":
                self._load_costumes()
            elif group == "costume_models":
                self._load_costume_models()
            elif group == "card_duet_voices":
                self._load_card_duet_voices()
            elif group == "style_voices":
                self._load_style_voices()
            elif group == "style_movies":
                self._load_style_movies()
            elif group == "comics":
                self._load_comics()
            elif group == "musics":
                self._load_musics()
            elif group == "music_scores":
                self._load_music_scores()
            elif group == "learning_stages":
                self._load_learning_stages()
            elif group == "quest_live_stages":
                self._load_quest_live_stages()
            elif group == "grade_live_stages":
                self._load_grade_live_stages()
            elif group == "grand_prix_stages":
                self._load_grand_prix_stages()
            elif group == "live_stages":
                self._load_live_stages()
            elif group == "standard_quest_areas":
                self._load_standard_quest_areas()
            elif group == "grade_quest_seasons":
                self._load_grade_quest_seasons()
            elif group == "grade_quest_series":
                self._load_grade_quest_series()
            elif group == "grand_prix_series":
                self._load_grand_prix_series()
            elif group == "grand_prix":
                self._load_grand_prix()
            elif group == "section_skills":
                self._load_section_skills()
            elif group == "section_skill_effects":
                self._load_section_skill_effects()
            elif group == "section_skill_effect_details":
                self._load_section_skill_effect_details()
            elif group == "quest_sections":
                self._load_quest_sections()
            elif group == "stage_skills":
                self._load_stage_skills()
            elif group == "music_mastery":
                self._load_music_mastery()
            elif group == "center_skills":
                self._load_center_skills()
            elif group == "center_attributes":
                self._load_center_attributes()
            elif group == "rhythm_skills":
                self._load_rhythm_skills()
            elif group == "token_skill_map":
                self._load_token_skill_map()
            elif group == "card_evolution_materials":
                self._load_card_evolution_materials()
            elif group == "card_skill_levelup_materials":
                self._load_card_skill_levelup_materials()
            self._loaded.add(group)

    def _load_characters(self):
        self.characters = {}
        self.character_alias_map = {}
        for c in self.load_yaml_file("Characters.yaml") or []:
            char_id = c.get("Id")
            if char_id is None:
                continue
            self.characters[char_id] = c
            aliases = [
                c.get("NameFirst"),
                c.get("NameLast"),
                (c.get("NameLast") or "") + (c.get("NameFirst") or ""),
                c.get("LatinAlphabetNameFirst"),
                c.get("LatinAlphabetNameLast"),
                c.get("DisplayFullName"),
            ]
            for alias in aliases:
                key = self._normalize_name_key(alias)
                if key and key not in self.character_alias_map:
                    self.character_alias_map[key] = char_id
            self.character_alias_map[str(char_id)] = char_id

    def _load_card_rarities(self):
        self.card_rarities = {
            r["Id"]: r["RarityName"]
            for r in (self.load_yaml_file("CardRarities.yaml") or [])
        }

    def _load_card_datas(self):
        self.card_datas = sorted(
            self.load_yaml_file("CardDatas.yaml") or [],
            key=lambda x: x.get("Id") or 0,
        )
        self.card_series_index = {}
        self.cards_by_character_index = {}
        for card in self.card_datas:
            series_id = card.get("CardSeriesId")
            if series_id is not None:
                if series_id not in self.card_series_index:
                    self.card_series_index[series_id] = []
                self.card_series_index[series_id].append(card)
            char_id = card.get("CharactersId")
            if char_id is not None:
                if char_id not in self.cards_by_character_index:
                    self.cards_by_character_index[char_id] = []
                self.cards_by_character_index[char_id].append(card)
        self.card_series_heads = [
            self.card_series_index[series_id][0]
            for series_id in sorted(self.card_series_index)
            if self.card_series_index[series_id]
        ]

    def _load_card_series_meta(self):
        self.card_series_meta = {}
        c_series = self.load_yaml_file("CardSeries.yaml") or []
        for s in c_series:
            self.card_series_meta[s["Id"]] = s

    def _load_skill_series(self):
        self.skill_series = {
            s["Id"]: s for s in (self.load_yaml_file("CardSkillSeries.yaml") or [])
        }

    def _load_skills(self):
        self.skills = {}
        all_skills = self.load_yaml_file("CardSkills.yaml") or []
        for s in all_skills:
            ss_id = s["CardSkillSeriesId"]
            if ss_id not in self.skills:
                self.skills[ss_id] = []
            self.skills[ss_id].append(s)
        for ss_id in self.skills:
            self.skills[ss_id].sort(key=lambda x: x["SkillLevel"])

    def _load_items(self):
        self.items = {
            item["Id"]: item for item in (self.load_yaml_file("Items.yaml") or [])
        }

    def _load_favorite_gifts(self):
        self.favorite_gifts = {}
        gifts_data = self.load_yaml_file("CharacterFavoriteGifts.yaml") or []
        for g in gifts_data:
            cid = g["CharactersId"]
            if cid not in self.favorite_gifts:
                self.favorite_gifts[cid] = []
            self.favorite_gifts[cid].append((g["ItemsId"], g["FavoriteRank"]))

    def _load_unit_characters(self):
        self.char_units = {}
        unit_chars = self.load_yaml_file("UnitCharacters.yaml") or []
        for uc in unit_chars:
            cid, uid = uc["CharactersId"], uc["UnitsId"]
            if uid > 100 and cid not in self.char_units:
                self.char_units[cid] = uid

    def _load_gachas(self):
        self.gachas = self.load_yaml_file("GachaSeries.yaml") or []

    def _load_costumes(self):
        self.costumes = {
            c["Id"]: c for c in (self.load_yaml_file("Costumes.yaml") or [])
        }

    def _load_costume_models(self):
        self.costume_models = self.load_yaml_file("CostumeModels.yaml") or []

    def _load_center_skills(self):
        self.center_skills = {}
        c_skills = self.load_yaml_file("CenterSkills.yaml") or []
        for s in c_skills:
            sid = s["CenterSkillSeriesId"]
            if sid not in self.center_skills:
                self.center_skills[sid] = []
            self.center_skills[sid].append(s)
        for sid in self.center_skills:
            self.center_skills[sid].sort(key=lambda x: x["SkillLevel"])

    def _load_center_attributes(self):
        self.center_attributes = {}
        c_attrs = self.load_yaml_file("CenterAttributes.yaml") or []
        for a in c_attrs:
            sid = a["CenterAttributeSeriesId"]
            if sid not in self.center_attributes:
                self.center_attributes[sid] = []
            self.center_attributes[sid].append(a)

    def _load_rhythm_skills(self):
        self.rhythm_skills = {}
        r_skills = self.load_yaml_file("RhythmGameSkills.yaml") or []
        for s in r_skills:
            sid = s["RhythmGameSkillSeriesId"]
            if sid not in self.rhythm_skills:
                self.rhythm_skills[sid] = []
            self.rhythm_skills[sid].append(s)
        for sid in self.rhythm_skills:
            self.rhythm_skills[sid].sort(key=lambda x: x["SkillLevel"])

    def _load_token_skill_map(self):
        self.token_skill_map = {}
        direct_map = {}
        effect_links = {}
        details = self.load_yaml_file("CardSkillEffectDetails.yaml") or []
        for d in details:
            d_id = str(d.get("Id") or "")
            if len(d_id) < 2:
                continue
            prefix = d_id[:-1]
            effect_type = str(d.get("SkillEffectDetailType") or "")
            if prefix not in direct_map:
                direct_map[prefix] = {
                    "skill_series_id": None,
                    "ability_series_id": None,
                    "resource_id": None,
                }

            if "EFFECT_ID" in effect_type:
                try:
                    ref_effect_id = int(d.get("EffectValue"))
                except (TypeError, ValueError):
                    ref_effect_id = None
                if ref_effect_id:
                    if prefix not in effect_links:
                        effect_links[prefix] = set()
                    effect_links[prefix].add(str(ref_effect_id))

            if effect_type not in (
                "TOKEN_CARD_SKILL_CARD_SKILL_SERIES_ID",
                "TOKEN_CARD_ABILITY_CARD_SKILL_SERIES_ID",
                "TOKEN_CARD_RESOURCE_ID",
            ):
                continue
            if effect_type == "TOKEN_CARD_SKILL_CARD_SKILL_SERIES_ID":
                direct_map[prefix]["skill_series_id"] = d.get("EffectValue")
            elif effect_type == "TOKEN_CARD_ABILITY_CARD_SKILL_SERIES_ID":
                direct_map[prefix]["ability_series_id"] = d.get("EffectValue")
            elif effect_type == "TOKEN_CARD_RESOURCE_ID":
                direct_map[prefix]["resource_id"] = d.get("EffectValue")

        resolved_cache = {}
        resolving = set()

        def _merge_token_info(base, extra):
            if (
                not base.get("skill_series_id")
                and extra
                and extra.get("skill_series_id")
            ):
                base["skill_series_id"] = extra.get("skill_series_id")
            if (
                not base.get("ability_series_id")
                and extra
                and extra.get("ability_series_id")
            ):
                base["ability_series_id"] = extra.get("ability_series_id")
            if not base.get("resource_id") and extra and extra.get("resource_id"):
                base["resource_id"] = extra.get("resource_id")

        def _resolve_token_info(effect_id):
            if effect_id in resolved_cache:
                return resolved_cache[effect_id]
            if effect_id in resolving:
                return None

            resolving.add(effect_id)
            merged = {
                "skill_series_id": None,
                "ability_series_id": None,
                "resource_id": None,
            }
            _merge_token_info(merged, direct_map.get(effect_id))

            for next_effect_id in effect_links.get(effect_id, set()):
                _merge_token_info(merged, _resolve_token_info(next_effect_id))
                if merged.get("skill_series_id") and merged.get("ability_series_id"):
                    break

            resolving.remove(effect_id)

            if (
                merged.get("skill_series_id")
                or merged.get("ability_series_id")
                or merged.get("resource_id")
            ):
                resolved_cache[effect_id] = merged
            else:
                resolved_cache[effect_id] = None
            return resolved_cache[effect_id]

        for effect_id in set(direct_map.keys()) | set(effect_links.keys()):
            resolved = _resolve_token_info(effect_id)
            if resolved:
                self.token_skill_map[effect_id] = resolved

    def _load_card_evolution_materials(self):
        self.card_evolution_materials = {
            m["Id"]: m
            for m in (self.load_yaml_file("CardEvolutionMaterials.yaml") or [])
        }

    def _load_card_skill_levelup_materials(self):
        self.card_skill_levelup_materials = {}
        mats = self.load_yaml_file("CardSkillLevelUpMaterials.yaml") or []
        for m in mats:
            sid = m["CardSeriesId"]
            if sid not in self.card_skill_levelup_materials:
                self.card_skill_levelup_materials[sid] = []
            self.card_skill_levelup_materials[sid].append(m)
        for sid in self.card_skill_levelup_materials:
            self.card_skill_levelup_materials[sid].sort(
                key=lambda x: (x.get("SkillType", 0), x.get("SkillLevel", 0))
            )

    def get_music_chart_data(self, music_id):
        # Check DB first
        cached = self.store.get_music_chart(music_id)
        if cached:
            return cached

        csv_path = os.path.join(self.cache_dir, f"musicscore_{music_id}.csv")
        if not os.path.exists(csv_path):
            return None

        try:
            with open(csv_path, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                header = next(reader, None)
                if not header:
                    return None

                rows = []
                for row in reader:
                    if len(row) < 3:
                        continue
                    rows.append(row)
        except Exception:
            return None

        # Parse data
        beat_hearts = []
        sections = []
        moods = []
        end_time = 0

        # Row format: id, song_time, key_type, key_value, heart_appear_ratio
        for row in rows:
            try:
                time = int(row[1])
                k_type = int(row[2])
                val = int(row[3])
            except ValueError:
                continue

            if k_type == 1:
                beat_hearts.append(time)
            elif k_type == 10:
                moods.append({"time": time, "value": val})
            elif k_type == 20:
                sections.append(time)
            elif k_type == 99:
                end_time = time

        if not end_time and rows:
            try:
                end_time = int(rows[-1][1])
            except (ValueError, IndexError):
                end_time = 120000

        # Calculate section stats
        # Sections should include start times.
        # Section 1 starts at 0.
        # Subsequent sections start at the times in `sections`.
        # Total usually 5 sections.

        section_boundaries = [0] + sorted(sections) + [end_time]
        # Remove duplicates if 0 is already in sections (unlikely but safe)
        section_boundaries = sorted(list(set(section_boundaries)))

        # Ensure we have at least start and end
        if len(section_boundaries) < 2:
            section_boundaries = [0, end_time]

        chart_sections = []
        for i in range(len(section_boundaries) - 1):
            start = section_boundaries[i]
            end = section_boundaries[i + 1]
            duration = end - start

            # Count beats in this section
            count = sum(1 for t in beat_hearts if start <= t < end)

            chart_sections.append(
                {
                    "index": i + 1,
                    "start_time": start,
                    "end_time": end,
                    "duration": duration,
                    "duration_sec": round(duration / 1000, 1),
                    "beat_count": count,
                    "percentage": (duration / end_time * 100) if end_time > 0 else 0,
                }
            )

        # Calculate Mood Line
        # Mood value changes at specific times. We want to sample or list these points.
        # Initial mood is 0 at time 0.
        # The points should be normalized to percentage for CSS plotting.

        mood_points = []
        # Add start point
        mood_points.append({"time": 0, "value": 0})

        sorted_moods = sorted(moods, key=lambda x: x["time"])

        for m in sorted_moods:
            t = m["time"]
            val = m["value"]
            # Step function: mood stays at previous value until 't', then jumps to 'val'
            if mood_points:
                prev = mood_points[-1]
                if prev["time"] < t:
                    mood_points.append(
                        {"time": t, "value": prev["value"]}
                    )  # Point before jump
            mood_points.append({"time": t, "value": val})  # Jump to new value

        # Add end point
        if end_time > mood_points[-1]["time"]:
            mood_points.append({"time": end_time, "value": mood_points[-1]["value"]})

        # Normalize Y
        max_val = max((p["value"] for p in mood_points), default=100)
        min_val = min((p["value"] for p in mood_points), default=-100)
        abs_max = max(abs(max_val), abs(min_val))
        if abs_max == 0:
            abs_max = 100

        final_points = []
        for p in mood_points:
            x_pct = (p["time"] / end_time * 100) if end_time > 0 else 0
            # 50% is center (0). +abs_max -> 10% (top). -abs_max -> 90% (bottom).
            # Range is 80% (from 10% to 90%).
            y_pct = 50 - (p["value"] / abs_max * 40)
            final_points.append(
                {"x": round(x_pct, 2), "y": round(y_pct, 2), "val": p["value"]}
            )

        result = {
            "total_time": end_time,
            "total_time_sec": round(end_time / 1000, 1),
            "total_beats": len(beat_hearts),
            "sections": chart_sections,
            "moods": final_points,
        }

        # Save to DB
        self.store.save_music_chart(music_id, result)

        return result

    def get_character(self, char_id):
        self._ensure("characters")
        return self.characters.get(char_id)

    def get_character_ids(self):
        self._ensure("characters")
        return list(self.characters.keys())

    def get_character_name(self, char_id):
        self._ensure("characters")
        char = self.characters.get(char_id)
        if char:
            last, first = char.get("NameLast", ""), char.get("NameFirst", "")
            if last or first:
                return f"{last}{first}".strip()
            return char.get("DisplayFullName") or str(char_id)
        return str(char_id)

    def get_generation_str(self, char_id):
        self._ensure("characters")
        char = self.characters.get(char_id)
        if not char or char.get("GenerationsId") == 100:
            return ""
        gen_val = char.get("DisplayGeneration") or char.get("GenerationsId")
        return str(gen_val) + "期"

    def get_character_unit(self, char_id):
        self._ensure("unit_characters")
        uid = self.char_units.get(char_id)
        if uid:
            return self.unit_names.get(uid, f"Unit {uid}")
        return None

    def get_favorite_gifts(self, char_id):
        self._ensure("items", "favorite_gifts")
        gifts = self.favorite_gifts.get(char_id, [])
        results = []
        for item_id, rank in gifts:
            item = self.items.get(item_id)
            if item:
                results.append({"name": item.get("Name"), "rank": rank, "id": item_id})
        results.sort(key=lambda x: x["rank"], reverse=True)
        return results

    def get_rarity_name(self, rarity_id):
        self._ensure("card_rarities")
        return self.card_rarities.get(rarity_id, str(rarity_id))

    def get_card_series_meta(self, series_id):
        self._ensure("card_series_meta")
        return self.card_series_meta.get(series_id, {})

    def get_card_skills_map(self):
        self._ensure("skills")
        return self.skills

    def get_rhythm_skills_map(self):
        self._ensure("rhythm_skills")
        return self.rhythm_skills

    def get_center_attributes_map(self):
        self._ensure("center_attributes")
        return self.center_attributes

    def get_gachas_for_series(self, series_id):
        self._ensure("gachas")
        results = []
        for g in self.gachas:
            for i in range(1, 15):
                field = f"PickUpCardSeriesId_{i}"
                if g.get(field) == series_id:
                    results.append(
                        {
                            "name": g["GachaSeriesName"],
                            "start_time": g.get("StartTime"),
                            "end_time": g.get("EndTime"),
                        }
                    )
                    break
        results.sort(key=lambda x: x["start_time"] or 0)
        return results

    def get_costume_models_by_character(self, char_id):
        self._ensure("costume_models", "costumes")
        models = [m for m in self.costume_models if m.get("CharactersId") == char_id]
        grouped = {}
        for m in models:
            costume_id = m.get("CostumesId")
            costume_label = (self.costumes.get(costume_id) or {}).get(
                "Label"
            ) or f"CostumesId {costume_id}"
            if costume_label not in grouped:
                grouped[costume_label] = []
            model_label = m.get("Label")
            if model_label and model_label not in grouped[costume_label]:
                grouped[costume_label].append(model_label)
        for label in grouped:
            grouped[label].sort()
        return dict(sorted(grouped.items(), key=lambda x: x[0]))

    def get_duet_voice_character_ids(self, series_id):
        self._ensure("card_duet_voices")
        return self.card_duet_voices.get(series_id, [])

    def get_style_voice_entries(self, series_id):
        self._ensure("style_voices")
        return self.style_voice_entries.get(series_id, [])

    def has_style_movie(self, series_id):
        self._ensure("style_movies")
        return series_id in self.style_movie_series

    def _normalize_character_ids(self, raw):
        if raw is None:
            return []
        if isinstance(raw, list):
            values = raw
        elif isinstance(raw, (int, float)):
            values = [raw]
        else:
            text = str(raw)
            values = [p for p in re.split(r"[,\s]+", text.strip()) if p]
        result = []
        for v in values:
            try:
                result.append(int(v))
            except ValueError:
                continue
        return result

    def _load_card_duet_voices(self):
        entries = self.load_yaml_file("CardDuetVoice.yaml") or []
        for entry in entries:
            series_id = entry.get("CardSeriesId")
            if series_id is None:
                continue
            raw_ids = entry.get("CharacterIds")
            ids = self._normalize_character_ids(raw_ids)
            if ids:
                self.card_duet_voices[series_id] = ids

    def _load_style_voices(self):
        entries = self.load_yaml_file("StyleVoices.yaml") or []
        for entry in entries:
            series_id = entry.get("CardSeriesId")
            if series_id is None:
                continue
            name = entry.get("Name")
            voice_name = entry.get("VoiceName")
            if not name or not voice_name:
                continue
            if series_id not in self.style_voice_entries:
                self.style_voice_entries[series_id] = []
            entry_key = (name, voice_name)
            if entry_key not in [
                (e["name"], e["voice"]) for e in self.style_voice_entries[series_id]
            ]:
                self.style_voice_entries[series_id].append(
                    {"name": name, "voice": voice_name}
                )
        for series_id in self.style_voice_entries:
            self.style_voice_entries[series_id].sort(
                key=lambda x: (x["name"], x["voice"])
            )

    def _load_style_movies(self):
        entries = self.load_yaml_file("StyleMovies.yaml") or []
        for entry in entries:
            series_id = entry.get("CardSeriesId")
            if series_id is None:
                continue
            self.style_movie_series.add(series_id)

    def _load_comics(self):
        self.comics = []
        self.comic_by_id = {}
        self.comics_by_character = {}
        entries = self.load_yaml_file("Comics.yaml") or []
        for entry in entries:
            appearance_ids = self._normalize_character_ids(
                entry.get("AppearanceCharacterIds")
            )
            entry["AppearanceCharacterIds"] = appearance_ids
            self.comics.append(entry)
            comic_id = entry.get("Id")
            if comic_id is not None:
                self.comic_by_id[comic_id] = entry
            for char_id in appearance_ids:
                if char_id not in self.comics_by_character:
                    self.comics_by_character[char_id] = []
                self.comics_by_character[char_id].append(entry)

    def _load_musics(self):
        self.musics = []
        self.music_by_id = {}
        self.musics_by_character = {}
        self.song_type_map = {}
        entries = self.load_yaml_file("Musics.yaml") or []
        for entry in entries:
            entry["SingerCharacterId"] = self._normalize_character_ids(
                entry.get("SingerCharacterId")
            )
            entry["SupportCharacterId"] = self._normalize_character_ids(
                entry.get("SupportCharacterId")
            )
            self.musics.append(entry)
            music_id = entry.get("Id")
            if music_id is not None:
                self.music_by_id[music_id] = entry
            related_char_ids = set()
            center_id = entry.get("CenterCharacterId")
            if center_id:
                related_char_ids.add(center_id)
            for char_id in entry.get("SingerCharacterId") or []:
                if char_id:
                    related_char_ids.add(char_id)
            for char_id in entry.get("SupportCharacterId") or []:
                if char_id:
                    related_char_ids.add(char_id)
            for char_id in related_char_ids:
                if char_id not in self.musics_by_character:
                    self.musics_by_character[char_id] = []
                self.musics_by_character[char_id].append(entry)
            song_type = entry.get("SongType")
            desc = entry.get("Description")
            if song_type is not None and desc and song_type not in self.song_type_map:
                self.song_type_map[song_type] = desc

    def get_song_type_label(self, song_type):
        self._ensure("musics")
        if song_type == 1:
            return "オリジナル曲"
        return self.song_type_map.get(song_type)

    def get_music_score(self, music_id):
        self._ensure("music_scores")
        return self.music_scores.get(music_id)

    def _load_music_scores(self):
        entries = self.load_yaml_file("MusicScores.yaml") or []
        for entry in entries:
            music_id = entry.get("Id")
            if music_id is None:
                continue
            self.music_scores[music_id] = entry

    def _load_learning_stages(self):
        entries = self.load_yaml_file("MusicLearningQuestStages.yaml") or []
        for entry in entries:
            music_id = entry.get("QuestMusicsDetail")
            if music_id is None:
                continue
            if music_id not in self.learning_stages_by_music:
                self.learning_stages_by_music[music_id] = []
            self.learning_stages_by_music[music_id].append(entry)
        for music_id in self.learning_stages_by_music:
            self.learning_stages_by_music[music_id].sort(
                key=lambda x: x.get("QuestLevel") or 0
            )

    def _load_quest_live_stages(self):
        entries = self.load_yaml_file("StandardQuestStages.yaml") or []
        for entry in entries:
            music_id = entry.get("QuestMusicsDetail")
            if music_id is None:
                continue
            if music_id not in self.quest_live_stages_by_music:
                self.quest_live_stages_by_music[music_id] = []
            self.quest_live_stages_by_music[music_id].append(entry)
        for music_id in self.quest_live_stages_by_music:
            self.quest_live_stages_by_music[music_id].sort(
                key=lambda x: x.get("QuestLevel") or 0
            )

    def _load_grade_live_stages(self):
        entries = self.load_yaml_file("GradeQuestStages.yaml") or []
        for entry in entries:
            music_id = entry.get("QuestMusicsDetail")
            if music_id is None:
                continue
            if music_id not in self.grade_live_stages_by_music:
                self.grade_live_stages_by_music[music_id] = []
            self.grade_live_stages_by_music[music_id].append(entry)
        for music_id in self.grade_live_stages_by_music:
            self.grade_live_stages_by_music[music_id].sort(
                key=lambda x: x.get("LivePoint") or 0
            )

    def _load_grand_prix_stages(self):
        entries = self.load_yaml_file("GrandPrixQuestStages.yaml") or []
        for entry in entries:
            music_id = entry.get("QuestMusicsDetail")
            if music_id is None:
                continue
            if music_id not in self.grand_prix_stages_by_music:
                self.grand_prix_stages_by_music[music_id] = []
            self.grand_prix_stages_by_music[music_id].append(entry)
        for music_id in self.grand_prix_stages_by_music:
            self.grand_prix_stages_by_music[music_id].sort(
                key=lambda x: x.get("QuestLevel") or 0
            )

    def _load_live_stages(self):
        entries = self.load_yaml_file("LiveStages.yaml") or []
        for entry in entries:
            stage_id = entry.get("Id")
            if stage_id is None:
                continue
            entry["StageSkillSetIds"] = self._normalize_character_ids(
                entry.get("StageSkillSetIds")
            )
            self.live_stages[stage_id] = entry

    def _load_standard_quest_areas(self):
        entries = self.load_yaml_file("StandardQuestAreas.yaml") or []
        for entry in entries:
            area_id = entry.get("Id")
            if area_id is None:
                continue
            self.standard_quest_areas[area_id] = entry

    def _load_grade_quest_seasons(self):
        entries = self.load_yaml_file("GradeQuestSeason.yaml") or []
        for entry in entries:
            season_id = entry.get("Id")
            if season_id is None:
                continue
            self.grade_quest_seasons[season_id] = entry

    def _load_grade_quest_series(self):
        entries = self.load_yaml_file("GradeQuestSeries.yaml") or []
        for entry in entries:
            series_id = entry.get("Id")
            if series_id is None:
                continue
            self.grade_quest_series[series_id] = entry

    def _load_grand_prix_series(self):
        entries = self.load_yaml_file("GrandPrixQuestSeries.yaml") or []
        for entry in entries:
            series_id = entry.get("Id")
            if series_id is None:
                continue
            self.grand_prix_series[series_id] = entry

    def _load_grand_prix(self):
        entries = self.load_yaml_file("GrandPrix.yaml") or []
        for entry in entries:
            gp_id = entry.get("Id")
            if gp_id is None:
                continue
            self.grand_prix[gp_id] = entry

    def _load_section_skills(self):
        entries = self.load_yaml_file("SectionSkills.yaml") or []
        for entry in entries:
            section_id = entry.get("Id")
            if section_id is None:
                continue
            effect_ids = self._normalize_id_list(entry.get("SectionSkillsEffectId"))
            entry["effect_ids"] = effect_ids
            self.section_skills[section_id] = entry

    def _load_section_skill_effects(self):
        entries = self.load_yaml_file("SectionSkillEffects.yaml") or []
        for entry in entries:
            effect_id = entry.get("Id")
            if effect_id is None:
                continue
            self.section_skill_effects[effect_id] = entry

    def _load_section_skill_effect_details(self):
        entries = self.load_yaml_file("SectionSkillEffectDetails.yaml") or []
        for entry in entries:
            effect_id = entry.get("Id")
            if effect_id is None:
                continue
            effect_key = (
                int(str(effect_id)[:-1]) if len(str(effect_id)) > 1 else effect_id
            )
            if effect_key not in self.section_skill_effect_details:
                self.section_skill_effect_details[effect_key] = []
            self.section_skill_effect_details[effect_key].append(entry)

    def _load_quest_sections(self):
        entries = self.load_yaml_file("QuestSections.yaml") or []
        for entry in entries:
            stage_id = entry.get("QuestStagesId")
            if stage_id is None:
                continue
            if stage_id not in self.quest_sections_by_stage:
                self.quest_sections_by_stage[stage_id] = []
            self.quest_sections_by_stage[stage_id].append(entry)
        for stage_id in self.quest_sections_by_stage:
            self.quest_sections_by_stage[stage_id].sort(
                key=lambda x: x.get("SectionNo") or 0
            )

    def _normalize_id_list(self, raw):
        if raw is None:
            return []
        if isinstance(raw, list):
            values = raw
        elif isinstance(raw, (int, float)):
            values = [raw]
        else:
            text = str(raw)
            values = [p for p in re.split(r"[,\s]+", text.strip()) if p]
        result = []
        for v in values:
            try:
                result.append(int(v))
            except ValueError:
                continue
        return result

    def _load_stage_skills(self):
        sets_entries = self.load_yaml_file("StageSkillSets.yaml") or []
        for entry in sets_entries:
            set_id = entry.get("Id")
            if set_id is None:
                continue
            self.stage_skill_sets[set_id] = entry

        condition_entries = self.load_yaml_file("StageSkillConditions.yaml") or []
        for entry in condition_entries:
            condition_id = entry.get("Id")
            if condition_id is None:
                continue
            self.stage_skill_conditions[condition_id] = entry

        condition_detail_entries = (
            self.load_yaml_file("StageSkillConditionDetails.yaml") or []
        )
        for entry in condition_detail_entries:
            condition_id = entry.get("StageSkillConditionId")
            if condition_id is None:
                continue
            if condition_id not in self.stage_skill_condition_details:
                self.stage_skill_condition_details[condition_id] = []
            self.stage_skill_condition_details[condition_id].append(entry)

        effect_entries = self.load_yaml_file("StageSkillEffects.yaml") or []
        for entry in effect_entries:
            effect_id = entry.get("Id")
            if effect_id is None:
                continue
            self.stage_skill_effects[effect_id] = entry

        effect_detail_entries = (
            self.load_yaml_file("StageSkillEffectDetails.yaml") or []
        )
        for entry in effect_detail_entries:
            effect_id = entry.get("StageSkillEffectId")
            if effect_id is None:
                continue
            if effect_id not in self.stage_skill_effect_details:
                self.stage_skill_effect_details[effect_id] = []
            self.stage_skill_effect_details[effect_id].append(entry)

        for condition_id in self.stage_skill_condition_details:
            self.stage_skill_condition_details[condition_id].sort(
                key=lambda x: x.get("Id") or 0
            )
        for effect_id in self.stage_skill_effect_details:
            self.stage_skill_effect_details[effect_id].sort(
                key=lambda x: x.get("Id") or 0
            )

    def _load_music_mastery(self):
        skill_entries = self.load_yaml_file("MusicMasterySkill.yaml") or []
        for entry in skill_entries:
            skill_id = entry.get("Id")
            if skill_id is None:
                continue
            self.music_mastery_skills[skill_id] = entry.get("MusicMasterySkillsName")

        level_entries = self.load_yaml_file("MusicMasteryLevels.yaml") or []
        for entry in level_entries:
            music_id = entry.get("MusicsId")
            if music_id is None:
                continue
            if music_id not in self.music_mastery_levels:
                self.music_mastery_levels[music_id] = []
            self.music_mastery_levels[music_id].append(entry)
        for music_id in self.music_mastery_levels:
            self.music_mastery_levels[music_id].sort(key=lambda x: x.get("Level") or 0)

        voltage_entries = self.load_yaml_file("MusicMasteryVoltageBonuses.yaml") or []
        for entry in voltage_entries:
            level = entry.get("Level")
            if level is None:
                continue
            self.music_mastery_bonus_voltage[level] = entry

        mental_entries = self.load_yaml_file("MusicMasteryMentalBonuses.yaml") or []
        for entry in mental_entries:
            level = entry.get("Level")
            if level is None:
                continue
            self.music_mastery_bonus_mental[level] = entry

        heart_entries = self.load_yaml_file("MusicMasteryHeartBonuses.yaml") or []
        for entry in heart_entries:
            level = entry.get("Level")
            if level is None:
                continue
            self.music_mastery_bonus_heart[level] = entry

        love_entries = self.load_yaml_file("MusicMasteryLoveBonuses.yaml") or []
        for entry in love_entries:
            level = entry.get("Level")
            if level is None:
                continue
            self.music_mastery_bonus_love[level] = entry

    def get_merged_skill_desc(self, series_dict, key="skills"):
        self._ensure("token_skill_map")
        if not series_dict or not series_dict.get(key):
            return None
        skills = series_dict[key]
        first_desc = str(skills[0].get("Description") or "")
        has_placeholders = "$" in first_desc
        template = (
            re.sub(r"\$.*?\$", "{}", first_desc) if has_placeholders else first_desc
        )

        level_to_vals = {}
        for s in skills:
            lv = s.get("SkillLevel")
            if lv is None:
                continue
            desc = str(s.get("Description") or "")
            vals = re.findall(r"\$(.*?)\$", desc)
            val_str = "/".join(vals)
            if lv not in level_to_vals:
                level_to_vals[lv] = set()
            level_to_vals[lv].add(val_str)

        ranges = []
        if has_placeholders:
            sorted_lvs = sorted(level_to_vals.keys())
            if not sorted_lvs:
                return {"name": series_dict.get("name"), "template": template, "ranges": []}
            curr_start = sorted_lvs[0]
            curr_val = " & ".join(sorted(list(level_to_vals[curr_start])))
            for i in range(1, len(sorted_lvs)):
                lv = sorted_lvs[i]
                val = " & ".join(sorted(list(level_to_vals[lv])))
                if val != curr_val:
                    ranges.append(
                        {
                            "start_level": curr_start,
                            "end_level": sorted_lvs[i - 1],
                            "value": curr_val,
                        }
                    )
                    curr_start, curr_val = lv, val
            ranges.append(
                {
                    "start_level": curr_start,
                    "end_level": sorted_lvs[-1],
                    "value": curr_val,
                }
            )

        token_cards = []
        token_keys = set()
        for s in skills:
            effect_ids = self._normalize_id_list(s.get("CardSkillEffectId"))
            for effect_id in effect_ids:
                token_ref = self.token_skill_map.get(str(effect_id))
                if not token_ref:
                    continue
                skill_series_id = token_ref.get("skill_series_id")
                ability_series_id = token_ref.get("ability_series_id")
                resource_id = token_ref.get("resource_id")
                token_key = (skill_series_id, ability_series_id, resource_id)
                if token_key in token_keys:
                    continue
                token_skill = (
                    self.get_all_skills_data(skill_series_id) if skill_series_id else None
                )
                token_ability = (
                    self.get_all_skills_data(ability_series_id)
                    if ability_series_id
                    else None
                )
                if not (token_skill or token_ability or resource_id):
                    continue
                token_cards.append(
                    {
                        "skill": token_skill,
                        "ability": token_ability,
                        "resource_id": resource_id,
                    }
                )
                token_keys.add(token_key)

        token_info = None
        if token_cards:
            token_info = {
                "skill": token_cards[0].get("skill"),
                "ability": token_cards[0].get("ability"),
            }
        return {
            "name": series_dict.get("name"),
            "template": template,
            "ranges": ranges,
            "has_placeholders": has_placeholders,
            "token": token_info,
            "token_cards": token_cards,
        }

    def get_all_skills_data(self, skill_series_id):
        self._ensure("skill_series", "skills")
        series = self.skill_series.get(skill_series_id)
        if not series:
            return None
        return {
            "id": skill_series_id,
            "name": series.get("Name"),
            "icon_id": series.get("SkillIcon"),
            "main_effect": series.get("SkillMainEffect"),
            "skills": self.skills.get(skill_series_id, []),
        }

    def get_all_center_skills_data(self, series_id):
        self._ensure("center_skills")
        skills = self.center_skills.get(series_id, [])
        if not skills:
            return None
        return {
            "id": series_id,
            "name": skills[0].get("CenterSkillName"),
            "skills": skills,
        }

    def get_all_rhythm_skills_data(self, series_id):
        self._ensure("rhythm_skills")
        skills = self.rhythm_skills.get(series_id, [])
        if not skills:
            return None
        return {
            "id": series_id,
            "name": skills[0].get("RhythmGameSkillName"),
            "skills": skills,
        }

    def get_cost_transition(
        self, series_id, skill_series_field, skill_source_dict, cost_field="SkillCost"
    ):
        self._ensure("card_datas")
        costs = []
        cards = self.get_card_series_data(series_id)
        for c in cards:
            s_id = c.get(skill_series_field)
            if s_id and s_id in skill_source_dict and skill_source_dict[s_id]:
                val = skill_source_dict[s_id][0].get(cost_field)
                costs.append(str(val) if val is not None else "?")
            else:
                costs.append("?")
        unique_path = []
        if costs:
            unique_path.append(costs[0])
            for i in range(1, len(costs)):
                if costs[i] != costs[i - 1]:
                    unique_path.append(costs[i])
        return " -> ".join(unique_path)

    def get_image_set(self, card_id):
        series_id = card_id // 10
        return {
            "full": f"image_card_full_{card_id}.png",
            "half": f"image_card_half_{card_id}.png",
            "middle_vertical": f"image_card_middle_vertical_{card_id}.png",
            "deck_frame_chara": f"image_deck_frame_chara_{series_id}.png",
            "prof_custom": f"image_prof_custom_{card_id}.png",
        }

    def get_skill_icons(self, s_id, sa_id, attr_id=None):
        icons = {}
        s_data = self.get_all_skills_data(s_id)
        if s_data and s_data["icon_id"]:
            icons["skill_icon"] = f"icon_skill_{s_data['icon_id']}.png"
        sa_data = self.get_all_skills_data(sa_id)
        if sa_data and sa_data["icon_id"]:
            icons["special_appeal_icon"] = f"icon_skill_{sa_data['icon_id']}.png"
        if attr_id:
            attr_data = self.get_all_skills_data(attr_id)
            if attr_data and attr_data["icon_id"]:
                icons["special_attribute_icon"] = (
                    f"icon_skill_{attr_data['icon_id']}.png"
                )
        return icons

    def get_card_evolution_materials(self, card_id):
        self._ensure("card_evolution_materials", "items")
        mat_entry = self.card_evolution_materials.get(card_id)
        if not mat_entry:
            return []
        result = []
        for i in range(1, 4):
            item_id = mat_entry.get(f"CostItemsId{i}")
            num = mat_entry.get(f"CostNum{i}")
            if item_id and num:
                item = self.items.get(item_id)
                name = item.get("Name") if item else str(item_id)
                result.append({"name": name, "count": num})
        return result

    def get_card_skill_levelup_materials(self, series_id):
        self._ensure("card_skill_levelup_materials", "items")
        entries = self.card_skill_levelup_materials.get(series_id, [])
        result = []
        for entry in entries:
            mats = []
            item_ids = self._normalize_id_list(entry.get("Cost_ItemsIds"))
            nums = self._normalize_id_list(entry.get("CostNums"))
            for i, item_id in enumerate(item_ids):
                if i < len(nums):
                    num = nums[i]
                    if item_id and num:
                        item = self.items.get(item_id)
                        name = item.get("Name") if item else str(item_id)
                        mats.append({"name": name, "count": num})
            if not mats:
                for i in range(1, 4):
                    item_id = entry.get(f"Cost_ItemsId{i}")
                    num = entry.get(f"CostNum{i}")
                    if item_id and num:
                        item = self.items.get(item_id)
                        name = item.get("Name") if item else str(item_id)
                        mats.append({"name": name, "count": num})
            if mats:
                result.append(
                    {
                        "type": entry.get("SkillType"),
                        "level": entry.get("SkillLevel"),
                        "materials": mats,
                    }
                )
        return result
