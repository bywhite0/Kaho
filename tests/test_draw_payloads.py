import unittest

from src.core.services.draw_payloads import (
    CHARA_RENDER_ROUTE,
    LIST_RENDER_ROUTE,
    build_chara_render_payload,
    build_list_render_payload,
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


if __name__ == "__main__":
    unittest.main()
