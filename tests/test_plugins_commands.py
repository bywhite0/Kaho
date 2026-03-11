import unittest
from unittest.mock import patch

import nonebot
from nonebot.adapters.onebot.v11 import MessageSegment


class _FinishCalled(Exception):
    def __init__(self, payload):
        super().__init__("finish")
        self.payload = payload


class _DummyMatcher:
    async def finish(self, payload=None):
        raise _FinishCalled(payload)


class _DummyMessage:
    def __init__(self, text):
        self._text = text

    def extract_plain_text(self):
        return self._text


class _FakeT2IService:
    def __init__(self):
        self.template_name = None
        self.payload = None

    async def generate_image(self, template_name, payload):
        self.template_name = template_name
        self.payload = payload
        return b"fake-image"


class _FakeSearchDM:
    def search_card_series(self, query, limit=30):
        if query == "花":
            return [
                {
                    "CardSeriesId": 2001,
                    "Rarity": 5,
                    "Name": "花咲く朝",
                    "CharactersId": 101,
                }
            ]
        return []

    def get_card_series_data(self, series_id):
        if series_id != 2001:
            return []
        return [{"Id": 20010, "State": 0}, {"Id": 20011, "State": 1}]

    def get_rarity_name(self, rarity_id):
        if rarity_id == 5:
            return "UR"
        return str(rarity_id)

    def get_character_name(self, char_id):
        if char_id == 101:
            return "日野下小鈴"
        return str(char_id)


class _FakeFindDM:
    def get_character_id_by_name(self, _query):
        return None


class _FakeMusicDM:
    def search_musics(self, query, limit=None):
        return []


class _FakeComicDM:
    def search_comics(self, query, limit=None):
        return []


class PluginCommandTest(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        try:
            nonebot.get_driver()
        except ValueError:
            nonebot.init()

    async def test_search_empty_query(self):
        import src.plugins.llll.search as search_module

        async def fake_get_dm():
            return _FakeSearchDM()

        matcher = _DummyMatcher()
        with patch.object(search_module, "search_cmd", matcher), patch.object(
            search_module, "get_dm_instance", fake_get_dm
        ):
            with self.assertRaises(_FinishCalled) as ctx:
                await search_module._(_DummyMessage("   "))
        self.assertEqual(ctx.exception.payload, "请输入关键词。")

    async def test_search_success_generate_image(self):
        import src.plugins.llll.search as search_module

        async def fake_get_dm():
            return _FakeSearchDM()

        fake_t2i = _FakeT2IService()
        matcher = _DummyMatcher()
        with patch.object(search_module, "search_cmd", matcher), patch.object(
            search_module, "get_dm_instance", fake_get_dm
        ), patch.object(search_module, "get_t2i_service", lambda: fake_t2i):
            with self.assertRaises(_FinishCalled) as ctx:
                await search_module._(_DummyMessage("花"))

        self.assertEqual(fake_t2i.template_name, "search.html")
        self.assertEqual(fake_t2i.payload["query"], "花")
        self.assertEqual(len(fake_t2i.payload["results"]), 1)
        self.assertFalse(fake_t2i.payload["is_limited"])
        self.assertEqual(fake_t2i.payload["max_results"], 30)
        self.assertIsInstance(ctx.exception.payload, MessageSegment)
        self.assertEqual(ctx.exception.payload.type, "image")

    async def test_find_not_found(self):
        import src.plugins.llll.find as find_module

        async def fake_get_dm():
            return _FakeFindDM()

        matcher = _DummyMatcher()
        with patch.object(find_module, "find_cmd", matcher), patch.object(
            find_module, "get_dm_instance", fake_get_dm
        ):
            with self.assertRaises(_FinishCalled) as ctx:
                await find_module._(_DummyMessage("不存在"))
        self.assertEqual(ctx.exception.payload, "未找到。")

    async def test_card_invalid_id(self):
        import src.plugins.llll.card as card_module

        async def fake_get_dm():
            return object()

        matcher = _DummyMatcher()
        with patch.object(card_module, "card_cmd", matcher), patch.object(
            card_module, "get_dm_instance", fake_get_dm
        ):
            with self.assertRaises(_FinishCalled) as ctx:
                await card_module._(_DummyMessage("abc"))
        self.assertEqual(ctx.exception.payload, "请输入有效的卡牌ID。")

    async def test_music_empty_query(self):
        import src.plugins.llll.music as music_module

        async def fake_get_dm():
            return _FakeMusicDM()

        matcher = _DummyMatcher()
        with patch.object(music_module, "music_cmd", matcher), patch.object(
            music_module, "get_dm_instance", fake_get_dm
        ):
            with self.assertRaises(_FinishCalled) as ctx:
                await music_module._(_DummyMessage(" "))
        self.assertEqual(ctx.exception.payload, "请输入关键词。")

    async def test_comic_empty_query(self):
        import src.plugins.llll.comic as comic_module

        async def fake_get_dm():
            return _FakeComicDM()

        matcher = _DummyMatcher()
        with patch.object(comic_module, "comic_cmd", matcher), patch.object(
            comic_module, "get_dm_instance", fake_get_dm
        ):
            with self.assertRaises(_FinishCalled) as ctx:
                await comic_module._(_DummyMessage(" "))
        self.assertEqual(ctx.exception.payload, "请输入关键词。")


if __name__ == "__main__":
    unittest.main()
