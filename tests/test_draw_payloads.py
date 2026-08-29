import unittest
from datetime import datetime, timezone
from typing import ClassVar

from src.core.services.draw_payloads import (
    CHARA_RENDER_ROUTE,
    FIND_RENDER_ROUTE,
    LIST_RENDER_ROUTE,
    LIVE_RENDER_ROUTE,
    LIVE_SPOILER_HIDDEN_TEXT,
    MUSIC_RENDER_ROUTE,
    build_chara_render_payload,
    build_find_render_payload,
    build_list_render_payload,
    build_live_render_payload,
    build_music_mastery_items,
    build_music_render_payload,
    format_live_duration,
)


class _FakeDM:
    def __init__(self, characters):
        # characters: {char_id: {"name", "generation", "unit", "color"}}
        self._characters = characters

    def get_character_ids(self):
        return list(self._characters.keys())

    def get_character_name(self, char_id):
        return self._characters[char_id]["name"]

    def get_generation_str(self, char_id):
        return self._characters[char_id].get("generation", "")

    def get_character_unit(self, char_id):
        return self._characters[char_id].get("unit")

    def get_character_theme_color(self, char_id):
        return self._characters[char_id].get("color")


class BuildListRenderPayloadTest(unittest.TestCase):
    def test_route_constant(self):
        self.assertEqual(LIST_RENDER_ROUTE, "/api/llll/list")

    def test_happy_path_full_fields(self):
        dm = _FakeDM(
            {
                1031: {
                    "name": "日野下花帆",
                    "generation": "103期",
                    "unit": "スリーズブーケ",
                    "color": "#f8b500",
                },
                1021: {
                    "name": "乙宗梢",
                    "generation": "102期",
                    "unit": "スリーズブーケ",
                    "color": "#68be8d",
                },
            }
        )
        payload = build_list_render_payload(dm)

        self.assertEqual(payload["schema_version"], "1")
        self.assertEqual(payload["kind"], "llll.list")
        self.assertEqual(payload["locale"], "zh-CN")
        self.assertEqual(payload["theme"], "light")
        self.assertTrue(payload["data"]["title"])

        characters = payload["data"]["characters"]
        # 按角色 id 升序
        self.assertEqual([c["id"] for c in characters], [1021, 1031])
        first = characters[0]
        self.assertEqual(first["name"], "乙宗梢")
        self.assertEqual(first["generation"], "102期")
        self.assertEqual(first["unit"], "スリーズブーケ")
        self.assertEqual(first["color"], "#68be8d")
        self.assertEqual(first["icon"], {"type": "chara_icon", "id": "1021"})

    def test_missing_optional_fields(self):
        dm = _FakeDM({1: {"name": "テスト"}})
        payload = build_list_render_payload(dm)

        item = payload["data"]["characters"][0]
        # 空 generation 归一为 None，unit 缺省为 None
        self.assertIsNone(item["generation"])
        self.assertIsNone(item["unit"])
        # 无主题色时省略字段，交给服务端默认值
        self.assertNotIn("color", item)

    def test_empty_characters_raises(self):
        dm = _FakeDM({})
        with self.assertRaises(ValueError):
            build_list_render_payload(dm)


class _FakeCharaDM:
    def __init__(
        self,
        char=None,
        member_profiles=None,
        generation="102期",
        name="乙宗梢",
        unit="スリーズブーケ",
        unit_id=101,
        color="#68be8d",
        gifts=None,
        costumes=None,
    ):
        self._char = char if char is not None else {}
        self._member_profiles = member_profiles or []
        self._generation = generation
        self._name = name
        self._unit = unit
        self._unit_id = unit_id
        self._color = color
        self._gifts = gifts or []
        self._costumes = costumes or {}

    def get_character(self, char_id):
        return self._char

    def get_member_profiles(self, char_id):
        return self._member_profiles

    def get_generation_str(self, char_id):
        return self._generation

    def get_character_name(self, char_id):
        return self._name

    def get_character_unit(self, char_id):
        return self._unit

    def get_character_unit_id(self, char_id):
        return self._unit_id

    def get_character_theme_color(self, char_id):
        return self._color

    def get_favorite_gifts(self, char_id):
        return self._gifts

    def get_costume_models_by_character(self, char_id):
        return self._costumes


class BuildCharaRenderPayloadTest(unittest.TestCase):
    def _full_dm(self):
        return _FakeCharaDM(
            char={"CharacterVoice": "花宮初奈"},
            member_profiles=[
                {
                    "profile_id": 1021030,
                    "generation": "103期",
                    "introduction": "誕生日　6月15日\n身長　167cm\n趣味　紅茶、読書",
                    "graduate_introduction": "",
                    "stand_image_id": 1021030,
                },
                {
                    "profile_id": 1021050,
                    "generation": "卒業後",
                    "introduction": "誕生日　6月15日\n身長　167cm\n趣味　紅茶、読書",
                    "graduate_introduction": "毕业寄语\n文本",
                    "stand_image_id": 1021050,
                },
            ],
            gifts=[{"name": "メトロノーム", "rank": 2, "id": 2003012}],
            costumes={"制服(冬)": ["制服(冬)_乙宗梢"]},
        )

    def test_route_constant(self):
        self.assertEqual(CHARA_RENDER_ROUTE, "/api/llll/chara")

    def test_happy_path_full_fields(self):
        payload = build_chara_render_payload(self._full_dm(), 1021)

        self.assertEqual(payload["schema_version"], "1")
        self.assertEqual(payload["kind"], "llll.chara")
        self.assertEqual(payload["locale"], "zh-CN")
        self.assertEqual(payload["theme"], "light")

        character = payload["data"]["character"]
        self.assertEqual(character["id"], 1021)
        self.assertEqual(character["name"], "乙宗梢")
        self.assertEqual(character["generation"], "蓮ノ空女学院 102期生")
        self.assertEqual(character["unit"], "スリーズブーケ")
        self.assertEqual(character["cv"], "花宮初奈")
        self.assertEqual(character["color"], "#68be8d")

        # 档案取最新 MemberProfile 的 Introduction
        profile = payload["data"]["profile"]
        self.assertEqual(
            profile,
            [
                {"label": "生日", "value": "6月15日"},
                {"label": "身高", "value": "167cm"},
                {"label": "兴趣", "value": "紅茶、読書"},
            ],
        )

        # 毕业条目只贡献毕业寄语，不进时间线；寄语拼回整段
        timelines = payload["data"]["timelines"]
        self.assertEqual(
            timelines,
            [
                {
                    "generation": "103期",
                    "stand": {"type": "image_chara_stand", "id": "1021030"},
                }
            ],
        )
        self.assertEqual(payload["data"]["graduate_message"], "毕业寄语文本")

        gifts = payload["data"]["gifts"]
        self.assertEqual(
            gifts,
            [
                {
                    "id": 2003012,
                    "name": "メトロノーム",
                    "rank": 2,
                    "icon": {"type": "icon_item", "id": "2003012"},
                }
            ],
        )
        self.assertEqual(
            payload["data"]["costumes"],
            [{"label": "制服(冬)", "values": ["制服(冬)_乙宗梢"]}],
        )

        assets = payload["assets"]
        self.assertEqual(assets["icon"], {"type": "chara_icon", "id": "1021"})
        self.assertEqual(assets["unit_logo"], {"type": "unit_logo", "id": "101"})
        self.assertEqual(
            assets["gift_icons"],
            {"2003012": {"type": "icon_item", "id": "2003012"}},
        )

    def test_profile_falls_back_to_character_introduction(self):
        # MemberProfile 简介解析不出档案时，回退 Characters.Introduction
        dm = _FakeCharaDM(
            char={"Introduction": "誕生日　6月15日"},
            member_profiles=[
                {
                    "profile_id": 1,
                    "generation": "105期",
                    "introduction": "纯散文简介，无档案字段",
                    "graduate_introduction": "",
                    "stand_image_id": 1,
                }
            ],
        )
        payload = build_chara_render_payload(dm, 1)
        self.assertEqual(
            payload["data"]["profile"],
            [{"label": "生日", "value": "6月15日"}],
        )

    def test_profile_history_with_generation_badges(self):
        # 档案随年度变化时输出取值历史，generation 标注取值开始适用的期数
        def entry(pid, gen, intro):
            return {
                "profile_id": pid,
                "generation": gen,
                "introduction": intro,
                "graduate_introduction": "",
                "stand_image_id": pid,
            }

        dm = _FakeCharaDM(
            member_profiles=[
                entry(1, "104期", "誕生日　11月2日\n特技　　特技と言えるようなことは何も…"),
                entry(2, "105期", "誕生日　11月2日\n特技　　ひとの長所を見つけること！"),
            ]
        )
        items = {i["label"]: i for i in build_chara_render_payload(dm, 1042)["data"]["profile"]}

        # 稳定字段只有最新值，不带历史
        self.assertEqual(items["生日"], {"label": "生日", "value": "11月2日"})

        changed = items["特长"]
        self.assertEqual(changed["value"], "ひとの長所を見つけること！")
        self.assertEqual(
            changed["values"],
            [
                {"value": "特技と言えるようなことは何も…", "generation": "104期"},
                {"value": "ひとの長所を見つけること！", "generation": "105期〜"},
            ],
        )

    def test_profile_history_range_labels(self):
        # 追加式顿号列表 → 项目级 segments：基线项不标注，新增项标注区间
        def entry(pid, gen, intro):
            return {
                "profile_id": pid,
                "generation": gen,
                "introduction": intro,
                "graduate_introduction": "",
                "stand_image_id": pid,
            }

        dm = _FakeCharaDM(
            member_profiles=[
                entry(1, "103期", "趣味　釣り\n特技　絵"),
                entry(2, "104期", "趣味　釣り、配信\n特技　絵"),
                entry(3, "卒業後", "趣味　釣り、配信\n特技　絵、作詞"),
            ]
        )
        items = {i["label"]: i for i in build_chara_render_payload(dm, 1)["data"]["profile"]}

        # 新增项延续到最后 → 一律开放区间「起〜」，即使新增于最后一期
        self.assertEqual(items["兴趣"]["value"], "釣り、配信")
        self.assertEqual(
            items["兴趣"]["segments"],
            [
                {"text": "釣り"},
                {"text": "配信", "generation": "104期〜"},
            ],
        )
        self.assertNotIn("values", items["兴趣"])
        self.assertEqual(
            items["特长"]["segments"],
            [
                {"text": "絵"},
                {"text": "作詞", "generation": "卒業後〜"},
            ],
        )

    def test_profile_replacement_range_labels(self):
        # 整体替换式变化 → 整值 values 历史，跨年度段压缩区间
        def entry(pid, gen, intro):
            return {
                "profile_id": pid,
                "generation": gen,
                "introduction": intro,
                "graduate_introduction": "",
                "stand_image_id": pid,
            }

        dm = _FakeCharaDM(
            member_profiles=[
                entry(1, "103期", "特技　クラシックバレエ"),
                entry(2, "104期", "特技　クラシックバレエ"),
                entry(3, "卒業後", "特技　バレエ"),
            ]
        )
        items = {i["label"]: i for i in build_chara_render_payload(dm, 1)["data"]["profile"]}
        changed = items["特长"]
        self.assertNotIn("segments", changed)
        self.assertEqual(
            changed["values"],
            [
                {"value": "クラシックバレエ", "generation": "103〜104期"},
                {"value": "バレエ", "generation": "卒業後〜"},
            ],
        )

    def test_missing_optional_fields(self):
        dm = _FakeCharaDM(
            generation="",
            unit=None,
            unit_id=None,
            color=None,
            member_profiles=[
                {
                    "profile_id": 1,
                    "generation": "105期",
                    "introduction": "",
                    "graduate_introduction": "",
                    "stand_image_id": 1,
                }
            ],
        )
        payload = build_chara_render_payload(dm, 1)

        character = payload["data"]["character"]
        self.assertIsNone(character["generation"])
        self.assertIsNone(character["unit"])
        self.assertIsNone(character["cv"])
        self.assertNotIn("color", character)
        self.assertEqual(payload["data"]["profile"], [])
        self.assertEqual(payload["data"]["gifts"], [])
        self.assertEqual(payload["data"]["costumes"], [])
        self.assertNotIn("graduate_message", payload["data"])
        self.assertNotIn("unit_logo", payload["assets"])
        self.assertNotIn("gift_icons", payload["assets"])

    def test_no_member_profiles_raises(self):
        with self.assertRaises(ValueError):
            build_chara_render_payload(_FakeCharaDM(), 1021)

    def test_only_graduate_profile_raises(self):
        # 毕业条目不产生时间线，仅有毕业条目时无法满足 timelines 至少一个
        dm = _FakeCharaDM(
            member_profiles=[
                {
                    "profile_id": 1,
                    "generation": "卒業後",
                    "introduction": "",
                    "graduate_introduction": "寄语",
                    "stand_image_id": 1,
                }
            ]
        )
        with self.assertRaises(ValueError):
            build_chara_render_payload(dm, 1021)

    def test_invalid_profiles_skipped_and_raises_when_all_invalid(self):
        dm = _FakeCharaDM(
            generation="",
            member_profiles=[
                {"profile_id": 1, "generation": "", "stand_image_id": None},
                {"profile_id": 2, "generation": "103期", "stand_image_id": None},
            ],
        )
        with self.assertRaises(ValueError):
            build_chara_render_payload(dm, 1021)

    def test_generation_falls_back_to_character_generation(self):
        # 条目无 DisplayGeneration 时，时间点标签回退角色自身期数
        dm = _FakeCharaDM(
            generation="101期",
            member_profiles=[
                {"profile_id": 1011030, "generation": "", "stand_image_id": 1011030},
            ],
        )
        payload = build_chara_render_payload(dm, 1011)
        timelines = payload["data"]["timelines"]
        self.assertEqual(len(timelines), 1)
        self.assertEqual(timelines[0]["generation"], "101期")

    def test_invalid_gift_filtered(self):
        dm = self._full_dm()
        dm._gifts = [
            {"name": "", "rank": 2, "id": 1},
            {"name": "有效礼物", "rank": "2", "id": 2},
            {"name": "有效礼物", "rank": 3, "id": None},
            {"name": "保留礼物", "rank": 4, "id": 9},
        ]
        payload = build_chara_render_payload(dm, 1021)
        self.assertEqual([g["id"] for g in payload["data"]["gifts"]], [9])
        self.assertEqual(list(payload["assets"]["gift_icons"]), ["9"])


class _FakeFindDM:
    LIMITED_TYPES: ClassVar[dict] = {0: "常驻", 2: "夏季限定", 202: "音击限定"}

    def __init__(
        self,
        cards,
        series_meta=None,
        rarities=None,
        name="乙宗梢",
        generation="102期",
        unit="スリーズブーケ",
        unit_id=101,
        color="#68be8d",
    ):
        self._cards = cards
        self._series_meta = series_meta or {}
        self._rarities = rarities or {}
        self._name = name
        self._generation = generation
        self._unit = unit
        self._unit_id = unit_id
        self._color = color

    def get_cards_by_character(self, char_id):
        return list(self._cards)

    def get_card_series_meta(self, series_id):
        return self._series_meta.get(series_id, {})

    def get_rarity_name(self, rarity_id):
        return self._rarities.get(rarity_id, str(rarity_id))

    def get_character_name(self, char_id):
        return self._name

    def get_generation_str(self, char_id):
        return self._generation

    def get_character_unit(self, char_id):
        return self._unit

    def get_character_unit_id(self, char_id):
        return self._unit_id

    def get_character_theme_color(self, char_id):
        return self._color


def _card(card_id, series_id, rarity, name, order_id=1):
    return {
        "Id": card_id,
        "CardSeriesId": series_id,
        "Rarity": rarity,
        "Name": name,
        "OrderId": order_id,
    }


class BuildFindRenderPayloadTest(unittest.TestCase):
    def _full_dm(self):
        # 双形态 R 常驻（含 2-4 高阶形态，应被过滤）+ 单形态 BR 生日
        cards = [
            _card(10213010 + i, 1021301, 3, "オーロラスカイ") for i in range(5)
        ] + [
            _card(10219011 + i, 1021901, 9, "18th Birthday") for i in range(4)
        ]
        return _FakeFindDM(
            cards,
            series_meta={1021301: {"LimitedType": 0}, 1021901: {"LimitedType": 9}},
            rarities={3: "R", 9: "BR"},
        )

    def test_route_constant(self):
        self.assertEqual(FIND_RENDER_ROUTE, "/api/llll/find")

    def test_happy_path_forms_and_summary(self):
        payload = build_find_render_payload(self._full_dm(), 1021)

        self.assertEqual(payload["schema_version"], "1")
        self.assertEqual(payload["kind"], "llll.find")

        character = payload["data"]["character"]
        self.assertEqual(character["id"], 1021)
        self.assertEqual(character["generation"], "102期")
        self.assertEqual(character["color"], "#68be8d")

        cards = payload["data"]["cards"]
        self.assertEqual(
            cards,
            [
                {
                    "id": 10213010,
                    "name": "オーロラスカイ",
                    "rarity": "R",
                    "series": "常驻",
                    "form": "特训前",
                    "thumb": {"type": "image_card_middle_vertical", "id": "10213010"},
                },
                {
                    "id": 10213011,
                    "name": "オーロラスカイ",
                    "rarity": "R",
                    "series": "常驻",
                    "form": "特训后",
                    "thumb": {"type": "image_card_middle_vertical", "id": "10213011"},
                },
                {
                    "id": 10219011,
                    "name": "18th Birthday",
                    "rarity": "BR",
                    # LimitedType 9 不在 fake 映射表，回退 Type 标签
                    "series": "Type 9",
                    "thumb": {"type": "image_card_middle_vertical", "id": "10219011"},
                },
            ],
        )
        self.assertEqual(payload["data"]["total_count"], 2)
        self.assertEqual(
            payload["data"]["rarity_summary"],
            [{"label": "R", "count": 1}, {"label": "BR", "count": 1}],
        )
        self.assertEqual(payload["assets"]["icon"], {"type": "chara_icon", "id": "1021"})
        self.assertEqual(payload["assets"]["unit_logo"], {"type": "unit_logo", "id": "101"})

    def test_placeholder_series_excluded(self):
        dm = self._full_dm()
        dm._cards += [_card(10105000, 1010500, 5, "？？？", order_id=99999999)]
        payload = build_find_render_payload(dm, 1021)
        self.assertEqual(payload["data"]["total_count"], 2)
        self.assertNotIn("？？？", [c["name"] for c in payload["data"]["cards"]])

    def test_ongeki_series_shows_only_first_form(self):
        cards = [_card(10215280 + i, 1021528, 5, "STARTLINER") for i in range(2)]
        dm = _FakeFindDM(
            cards,
            series_meta={1021528: {"LimitedType": 202}},
            rarities={5: "UR"},
        )
        payload = build_find_render_payload(dm, 1021)
        cards_out = payload["data"]["cards"]
        self.assertEqual(len(cards_out), 1)
        self.assertEqual(cards_out[0]["id"], 10215280)
        self.assertEqual(cards_out[0]["series"], "音击限定")
        self.assertNotIn("form", cards_out[0])

    def test_no_cards_raises(self):
        with self.assertRaises(ValueError):
            build_find_render_payload(_FakeFindDM([]), 1021)

    def test_missing_optional_fields(self):
        dm = _FakeFindDM(
            [_card(10213010, 1021301, 3, "テスト")],
            series_meta={1021301: {"LimitedType": 0}},
            rarities={3: "R"},
            generation="",
            unit=None,
            unit_id=None,
            color=None,
        )
        payload = build_find_render_payload(dm, 1)
        character = payload["data"]["character"]
        self.assertIsNone(character["generation"])
        self.assertIsNone(character["unit"])
        self.assertNotIn("color", character)
        self.assertNotIn("unit_logo", payload["assets"])
        # 系列内只有 0 形态 → 单形态，不带 form
        self.assertNotIn("form", payload["data"]["cards"][0])


class _FakeMusicDM:
    MOODS: ClassVar[dict] = {1: "Happy", 2: "Neutral", 3: "Mellow"}

    def __init__(self, chart=None, mastery=None, bonus=None, color="#f8b500"):
        self.unit_names = {100: "蓮ノ空女学院スクールアイドルクラブ"}
        self._chart = chart
        self._mastery = mastery or []
        self._bonus = bonus or {}
        self._color = color

    def get_song_type_label(self, song_type):
        return "オリジナル曲" if song_type == 1 else None

    def get_character_name(self, char_id):
        return {1031: "日野下花帆", 1021: "乙宗梢", 1023: "藤島慈"}.get(
            char_id, f"角色{char_id}"
        )

    def get_character_theme_color(self, char_id):
        return self._color

    def get_music_chart_data(self, music_id):
        return self._chart

    def get_music_mastery(self, music_id):
        return self._mastery

    def get_music_mastery_skill_name(self, skill_id):
        return "LOVEボーナス"

    def get_mastery_bonus(self, skill_name, level):
        return self._bonus


_MUSIC_ENTRY = {
    "Id": 103101,
    "Title": "Dream Believers（4人Ver.）",
    "TitleFurigana": "どりーむびりーばーず",
    "Description": "全体曲",
    "GenerationsId": 103,
    "UnitId": 100,
    "SongType": 1,
    "MusicType": 1,
    "PlayTime": 139259,
    "MaxAp": 10,
    "FeverSectionNo": 4,
    "ReleaseConditionText": "初めから習得",
    "CenterCharacterId": 1031,
    "SingerCharacterId": [1031, 1021],
    "SupportCharacterId": [1023, 0],
    "JacketId": 103101,
}


class BuildMusicRenderPayloadTest(unittest.TestCase):
    def _chart(self):
        return {
            "total_time": 139259,
            "total_time_sec": 139.3,
            "total_beats": 85,
            "sections": [
                {
                    "index": 1,
                    "start_time": 0,
                    "end_time": 28148,
                    "duration": 28148,
                    "duration_sec": 28.1,
                    "beat_count": 17,
                    "percentage": 20.2,
                },
                {
                    "index": 2,
                    "start_time": 28148,
                    "end_time": 28148,
                    "duration": 0,
                    "duration_sec": 0.0,
                    "beat_count": 0,
                    "percentage": 0,
                },
            ],
            "moods": [{"x": 0.0, "y": 50.0, "val": 0}, {"x": 100.0, "y": 10.0, "val": 100}],
        }

    def test_route_constant(self):
        self.assertEqual(MUSIC_RENDER_ROUTE, "/api/llll/music")

    def test_happy_path_full_fields(self):
        payload = build_music_render_payload(_FakeMusicDM(chart=self._chart()), _MUSIC_ENTRY)

        self.assertEqual(payload["schema_version"], "1")
        self.assertEqual(payload["kind"], "llll.music")

        music = payload["data"]["music"]
        self.assertEqual(music["id"], 103101)
        self.assertEqual(music["title"], "Dream Believers（4人Ver.）")
        self.assertEqual(music["title_furigana"], "どりーむびりーばーず")
        self.assertEqual(music["generation_label"], "103期")
        self.assertEqual(music["unit"], "蓮ノ空女学院スクールアイドルクラブ")
        self.assertEqual(music["song_type_label"], "オリジナル曲")
        self.assertEqual(music["mood_name"], "Happy")
        self.assertEqual(music["duration_text"], "2:19")
        self.assertEqual(music["color"], "#f8b500")
        self.assertNotIn("bpm", music)

        self.assertEqual(
            payload["data"]["info"],
            [
                {"label": "歌曲类型", "value": "オリジナル曲"},
                {"label": "属性", "value": "Happy"},
                {"label": "时长", "value": "2:19 (139259ms)"},
                {"label": "AP 上限", "value": "10"},
                {"label": "Fever 区段", "value": "第 4 区段"},
                {"label": "解锁条件", "value": "初めから習得"},
                {"label": "中心角色", "value": "日野下花帆"},
            ],
        )

        # 中心角色排最前且不在 singer 中重复；SupportCharacterId 的 0 被过滤
        performers = payload["data"]["performers"]
        self.assertEqual(
            [(p["id"], p["role"]) for p in performers],
            [(1031, "center"), (1021, "singer"), (1023, "support")],
        )
        self.assertEqual(performers[0]["icon"], {"type": "chara_icon", "id": "1031"})

        # 零占比区段被过滤，moods 只保留 x/y
        chart = payload["data"]["chart"]
        self.assertEqual(chart["total_time_sec"], 139.3)
        self.assertEqual(
            chart["sections"],
            [{"index": 1, "percentage": 20.2, "beat_count": 17, "duration_sec": 28.1}],
        )
        self.assertEqual(chart["moods"], [{"x": 0.0, "y": 50.0}, {"x": 100.0, "y": 10.0}])
        self.assertEqual(payload["data"]["fever_section"], 4)

        self.assertEqual(
            payload["assets"]["jacket"], {"type": "music_jacket", "id": "103101"}
        )

    def test_no_chart_omits_chart_and_fever(self):
        payload = build_music_render_payload(_FakeMusicDM(), _MUSIC_ENTRY)
        self.assertNotIn("chart", payload["data"])
        self.assertNotIn("fever_section", payload["data"])

    def test_all_zero_sections_omit_chart(self):
        chart = self._chart()
        for s in chart["sections"]:
            s["percentage"] = 0
        payload = build_music_render_payload(_FakeMusicDM(chart=chart), _MUSIC_ENTRY)
        self.assertNotIn("chart", payload["data"])

    def test_missing_title_raises(self):
        with self.assertRaises(ValueError):
            build_music_render_payload(_FakeMusicDM(), {"Id": 1, "Title": " "})

    def test_minimal_entry(self):
        dm = _FakeMusicDM(color=None)
        payload = build_music_render_payload(dm, {"Id": 999901, "Title": "テスト"})
        music = payload["data"]["music"]
        self.assertIsNone(music["title_furigana"])
        self.assertIsNone(music["generation_label"])
        self.assertIsNone(music["unit"])
        self.assertNotIn("color", music)
        self.assertNotIn("duration_text", music)
        self.assertEqual(payload["data"]["info"], [])
        self.assertEqual(payload["data"]["performers"], [])
        # 无 JacketId 时封面回退歌曲 Id
        self.assertEqual(
            payload["assets"]["jacket"], {"type": "music_jacket", "id": "999901"}
        )

    def test_mastery_love_rate_bonus(self):
        dm = _FakeMusicDM(
            mastery=[
                {"Level": 10, "MusicMasterySkillsId": 1},
                {"Level": None, "MusicMasterySkillsId": 1},
            ],
            bonus={"LoveRate": 17500},
        )
        items = build_music_mastery_items(dm, 103101)
        self.assertEqual(
            items,
            [
                {
                    "level": 10,
                    "skill_name": "LOVEボーナス",
                    "bonus_text": "爱心回收时 LOVE 获得量 +1.75%",
                }
            ],
        )


class _FakeLiveDM:
    def __init__(self):
        self.names = {1031: "日野下花帆", 1032: "村野さやか"}
        self.colors = {1031: "#f8b500", 1032: "#5383c3"}
        self.locations = {5: "八重咲ステージ2603"}

    def get_character_name(self, char_id):
        return self.names.get(char_id)

    def get_character_theme_color(self, char_id):
        return self.colors.get(char_id)

    def get_live_location_label(self, location_id):
        return self.locations.get(location_id)


def _build_live_archive(**overrides):
    archive = {
        "archives_id": "arch-1",
        "live_id": "live-1",
        "name": "テスト配信",
        "live_type": 3,
        "live_start_time": "2026-04-16T12:00:00Z",
        "end_time": "2026-04-16T13:00:00Z",
        "total_playing_time_second": 3780,
        "has_extra": True,
        "is_extra_started": False,
        "has_extra_admission": True,
        "gift_stars_threshold_for_extra_admission": 500,
        "earned_star_count": 120,
        "character_list": [{"character_id": 1031}, {"character_id": 1032}],
    }
    archive.update(overrides)
    return archive


def _local_time_text(iso_text):
    parsed = datetime.fromisoformat(iso_text.replace("Z", "+00:00"))
    return parsed.astimezone().strftime("%Y/%m/%d %H:%M")


_LIVE_NOW = datetime(2026, 5, 1, tzinfo=timezone.utc)


class BuildLiveRenderPayloadTest(unittest.TestCase):
    def setUp(self):
        self.dm = _FakeLiveDM()

    def test_route_constant(self):
        self.assertEqual(LIVE_RENDER_ROUTE, "/api/llll/live")

    def test_basic_fields(self):
        payload = build_live_render_payload(
            self.dm, _build_live_archive(), now=_LIVE_NOW
        )

        self.assertEqual(payload["schema_version"], "1")
        self.assertEqual(payload["kind"], "llll.live")
        self.assertNotIn("assets", payload)

        live = payload["data"]["live"]
        self.assertEqual(live["id"], "arch-1")
        self.assertEqual(live["title"], "テスト配信")
        self.assertEqual(live["live_type"], 3)
        self.assertNotIn("live_type_label", live)
        self.assertEqual(live["status"], "closed")
        self.assertEqual(live["start_time"], _local_time_text("2026-04-16T12:00:00Z"))
        self.assertEqual(live["end_time"], _local_time_text("2026-04-16T13:00:00Z"))
        self.assertEqual(live["duration_text"], "63分00秒")
        self.assertEqual(live["color"], "#f8b500")
        self.assertNotIn("orientation", live)
        self.assertNotIn("location", live)
        self.assertNotIn("description", live)

        self.assertEqual(
            payload["data"]["after"],
            {
                "has_extra": True,
                "is_started": False,
                "has_admission": True,
                "star_threshold": 500,
                "earned_star": 120,
            },
        )
        self.assertNotIn("stats", payload["data"])

        characters = payload["data"]["characters"]
        self.assertEqual(
            characters,
            [
                {
                    "id": 1031,
                    "name": "日野下花帆",
                    "icon": {"type": "chara_icon", "id": "1031"},
                    "color": "#f8b500",
                },
                {
                    "id": 1032,
                    "name": "村野さやか",
                    "icon": {"type": "chara_icon", "id": "1032"},
                    "color": "#5383c3",
                },
            ],
        )

    def test_status_live_and_upcoming(self):
        airing = _build_live_archive(
            end_time="2999-01-01T00:00:00Z", total_playing_time_second=0
        )
        payload = build_live_render_payload(self.dm, airing, now=_LIVE_NOW)
        self.assertEqual(payload["data"]["live"]["status"], "live")
        # 2999 哨兵不算结束时间
        self.assertNotIn("end_time", payload["data"]["live"])

        # 无结束时间的归档条目，已有总时长即视为完结
        archived = _build_live_archive(end_time="2999-01-01T00:00:00Z")
        payload = build_live_render_payload(self.dm, archived, now=_LIVE_NOW)
        self.assertEqual(payload["data"]["live"]["status"], "closed")

        future = _build_live_archive(
            live_start_time="2026-06-01T12:00:00Z",
            end_time="2999-01-01T00:00:00Z",
        )
        payload = build_live_render_payload(self.dm, future, now=_LIVE_NOW)
        self.assertEqual(payload["data"]["live"]["status"], "upcoming")

    def test_id_fallback_and_optional_fields(self):
        archive = _build_live_archive(
            archives_id="",
            total_playing_time_second=0,
            character_list=[],
        )
        payload = build_live_render_payload(self.dm, archive, now=_LIVE_NOW)
        live = payload["data"]["live"]
        self.assertEqual(live["id"], "live-1")
        self.assertNotIn("duration_text", live)
        self.assertNotIn("color", live)
        self.assertEqual(payload["data"]["characters"], [])

    def test_spoiler_gating_and_orientation(self):
        enter_detail = {"is_horizontal": True, "live_location_id": 5}
        payload = build_live_render_payload(
            self.dm,
            _build_live_archive(),
            enter_detail=enter_detail,
            show_spoiler=False,
            now=_LIVE_NOW,
        )
        live = payload["data"]["live"]
        self.assertEqual(live["orientation"], "横画面")
        self.assertEqual(live["location"], LIVE_SPOILER_HIDDEN_TEXT)

        payload = build_live_render_payload(
            self.dm,
            _build_live_archive(),
            enter_detail=enter_detail,
            show_spoiler=True,
            now=_LIVE_NOW,
        )
        self.assertEqual(payload["data"]["live"]["location"], "八重咲ステージ2603")

        payload = build_live_render_payload(
            self.dm,
            _build_live_archive(),
            enter_detail={"is_horizontal": False, "live_location_id": 99},
            show_spoiler=True,
            now=_LIVE_NOW,
        )
        live = payload["data"]["live"]
        self.assertEqual(live["orientation"], "縦画面")
        self.assertEqual(live["location"], "地点ID: 99")

        payload = build_live_render_payload(
            self.dm,
            _build_live_archive(),
            enter_detail={},
            show_spoiler=True,
            now=_LIVE_NOW,
        )
        live = payload["data"]["live"]
        self.assertNotIn("orientation", live)
        self.assertEqual(live["location"], "不明")

    def test_enter_detail_characters_take_priority(self):
        enter_detail = {
            "characters": [
                {"character_id": 1032},
                {"character_id": 1032},
                {"character_id": "bad"},
                {"character_id": 9999},
            ]
        }
        payload = build_live_render_payload(
            self.dm,
            _build_live_archive(),
            enter_detail=enter_detail,
            now=_LIVE_NOW,
        )
        characters = payload["data"]["characters"]
        self.assertEqual([c["id"] for c in characters], [1032, 9999])
        # 未知角色名回退 ID 文本，主题色缺失时省略
        self.assertEqual(characters[1]["name"], "9999")
        self.assertNotIn("color", characters[1])
        self.assertEqual(payload["data"]["live"]["color"], "#5383c3")

    def test_gift_point_cover_and_description(self):
        payload = build_live_render_payload(
            self.dm,
            _build_live_archive(),
            description="出演者のみなさん",
            cover_id="a" * 64,
            gift_point=1359325800,
            now=_LIVE_NOW,
        )
        self.assertEqual(payload["data"]["stats"], {"gift_point": 1359325800})
        self.assertEqual(
            payload["assets"]["cover"],
            {"type": "live_cover", "id": "a" * 64},
        )
        self.assertEqual(payload["data"]["live"]["description"], "出演者のみなさん")

        # 本地占位「不明」不进 payload
        payload = build_live_render_payload(
            self.dm, _build_live_archive(), description="不明", now=_LIVE_NOW
        )
        self.assertNotIn("description", payload["data"]["live"])

    def test_invalid_entries_raise(self):
        with self.assertRaises(ValueError):
            build_live_render_payload(
                self.dm, _build_live_archive(name=""), now=_LIVE_NOW
            )
        with self.assertRaises(ValueError):
            build_live_render_payload(
                self.dm,
                _build_live_archive(archives_id="", live_id=""),
                now=_LIVE_NOW,
            )
        with self.assertRaises(ValueError):
            build_live_render_payload(
                self.dm, _build_live_archive(live_type=4), now=_LIVE_NOW
            )

    def test_format_live_duration(self):
        self.assertEqual(format_live_duration(2366), "39分26秒")
        self.assertEqual(format_live_duration("3780"), "63分00秒")
        self.assertIsNone(format_live_duration(0))
        self.assertIsNone(format_live_duration(None))
        self.assertIsNone(format_live_duration("abc"))


if __name__ == "__main__":
    unittest.main()
