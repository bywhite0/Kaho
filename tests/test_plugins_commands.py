import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import nonebot
from nonebot.adapters.onebot.v11 import MessageSegment

from src.core.data_manager import DataManager
from tests.realdata_utils import build_index_fixture


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


class PluginCommandTest(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        try:
            nonebot.get_driver()
        except ValueError:
            nonebot.init()

        cls._tmp_dir = tempfile.TemporaryDirectory()
        root = Path(cls._tmp_dir.name)
        cls.data_dir = root / "masterdata"
        cls.data_dir.mkdir(parents=True, exist_ok=True)
        cls.meta = build_index_fixture(cls.data_dir)

        cls.db_path = root / "data.db"
        cls._prev_db_path = os.getenv("KAHO_DB_PATH")
        os.environ["KAHO_DB_PATH"] = str(cls.db_path)
        cls.dm = DataManager(str(cls.data_dir))

    @classmethod
    def tearDownClass(cls):
        cls.dm.store._engine.dispose()
        if cls._prev_db_path is None:
            os.environ.pop("KAHO_DB_PATH", None)
        else:
            os.environ["KAHO_DB_PATH"] = cls._prev_db_path
        cls._tmp_dir.cleanup()

    async def test_search_empty_query(self):
        import src.plugins.llll.search as search_module

        async def fake_get_dm():
            return self.dm

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
            return self.dm

        fake_t2i = _FakeT2IService()
        matcher = _DummyMatcher()
        query = str(self.meta.get("first_card_name") or "")[:2]
        with patch.object(search_module, "search_cmd", matcher), patch.object(
            search_module, "get_dm_instance", fake_get_dm
        ), patch.object(search_module, "get_t2i_service", lambda: fake_t2i):
            with self.assertRaises(_FinishCalled) as ctx:
                await search_module._(_DummyMessage(query))

        self.assertEqual(fake_t2i.template_name, "search.html")
        self.assertEqual(fake_t2i.payload["query"], query)
        self.assertIsInstance(ctx.exception.payload, MessageSegment)
        self.assertEqual(ctx.exception.payload.type, "image")

    async def test_find_success_generate_image(self):
        import src.plugins.llll.find as find_module

        async def fake_get_dm():
            return self.dm

        fake_t2i = _FakeT2IService()
        matcher = _DummyMatcher()
        query = self.meta.get("first_char_name") or str(self.meta["first_char_id"])
        with patch.object(find_module, "find_cmd", matcher), patch.object(
            find_module, "get_dm_instance", fake_get_dm
        ), patch.object(find_module, "get_t2i_service", lambda: fake_t2i):
            with self.assertRaises(_FinishCalled) as ctx:
                await find_module._(_DummyMessage(query))

        self.assertEqual(fake_t2i.template_name, "find.html")
        self.assertIsInstance(ctx.exception.payload, MessageSegment)
        self.assertEqual(ctx.exception.payload.type, "image")

    async def test_card_empty_query(self):
        import src.plugins.llll.card as card_module

        async def fake_get_dm():
            return self.dm

        matcher = _DummyMatcher()
        with patch.object(card_module, "card_cmd", matcher), patch.object(
            card_module, "get_dm_instance", fake_get_dm
        ):
            with self.assertRaises(_FinishCalled) as ctx:
                await card_module._(_DummyMessage("   "))
        self.assertEqual(ctx.exception.payload, "请输入卡牌ID。")

    async def test_card_invalid_id(self):
        import src.plugins.llll.card as card_module

        async def fake_get_dm():
            return self.dm

        matcher = _DummyMatcher()
        with patch.object(card_module, "card_cmd", matcher), patch.object(
            card_module, "get_dm_instance", fake_get_dm
        ):
            with self.assertRaises(_FinishCalled) as ctx:
                await card_module._(_DummyMessage("abc"))
        self.assertEqual(ctx.exception.payload, "请输入有效的卡牌ID。")

    async def test_chara_success_generate_image(self):
        import src.plugins.llll.chara as chara_module

        async def fake_get_dm():
            return self.dm

        fake_t2i = _FakeT2IService()
        matcher = _DummyMatcher()
        query = self.meta.get("first_char_name") or str(self.meta["first_char_id"])
        with patch.object(chara_module, "chara_cmd", matcher), patch.object(
            chara_module, "get_dm_instance", fake_get_dm
        ), patch.object(chara_module, "get_t2i_service", lambda: fake_t2i):
            with self.assertRaises(_FinishCalled) as ctx:
                await chara_module._(_DummyMessage(query))

        self.assertEqual(fake_t2i.template_name, "chara.html")
        self.assertIsInstance(ctx.exception.payload, MessageSegment)
        self.assertEqual(ctx.exception.payload.type, "image")

    async def test_music_success_generate_image(self):
        import src.plugins.llll.music as music_module

        async def fake_get_dm():
            return self.dm

        fake_t2i = _FakeT2IService()
        matcher = _DummyMatcher()
        query = str(self.meta.get("first_music_title") or "")[:4]
        with patch.object(music_module, "music_cmd", matcher), patch.object(
            music_module, "get_dm_instance", fake_get_dm
        ), patch.object(music_module, "get_t2i_service", lambda: fake_t2i):
            with self.assertRaises(_FinishCalled) as ctx:
                await music_module._(_DummyMessage(query))

        self.assertEqual(fake_t2i.template_name, "music.html")
        self.assertIsInstance(ctx.exception.payload, MessageSegment)
        self.assertEqual(ctx.exception.payload.type, "image")

    async def test_comic_success_generate_image(self):
        import src.plugins.llll.comic as comic_module

        async def fake_get_dm():
            return self.dm

        fake_t2i = _FakeT2IService()
        matcher = _DummyMatcher()
        query = str(self.meta.get("first_comic_name") or "")[:4]
        with patch.object(comic_module, "comic_cmd", matcher), patch.object(
            comic_module, "get_dm_instance", fake_get_dm
        ), patch.object(comic_module, "get_t2i_service", lambda: fake_t2i):
            with self.assertRaises(_FinishCalled) as ctx:
                await comic_module._(_DummyMessage(query))

        self.assertEqual(fake_t2i.template_name, "comic.html")
        self.assertIsInstance(ctx.exception.payload, MessageSegment)
        self.assertEqual(ctx.exception.payload.type, "image")

    async def test_list_success_generate_image(self):
        import src.plugins.llll.list as list_module

        async def fake_get_dm():
            return self.dm

        fake_t2i = _FakeT2IService()
        matcher = _DummyMatcher()
        with patch.object(list_module, "list_cmd", matcher), patch.object(
            list_module, "get_dm_instance", fake_get_dm
        ), patch.object(list_module, "get_t2i_service", lambda: fake_t2i):
            with self.assertRaises(_FinishCalled) as ctx:
                await list_module._()

        self.assertEqual(fake_t2i.template_name, "list.html")
        self.assertIsInstance(ctx.exception.payload, MessageSegment)
        self.assertEqual(ctx.exception.payload.type, "image")


if __name__ == "__main__":
    unittest.main()

