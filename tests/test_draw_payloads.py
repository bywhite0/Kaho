import unittest

from src.core.services.draw_payloads import (
    LIST_RENDER_ROUTE,
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


if __name__ == "__main__":
    unittest.main()
