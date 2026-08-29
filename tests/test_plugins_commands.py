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


class _FakeDrawApiService:
    def __init__(self, enabled=True, result=b"draw-image", error=None):
        self.enabled = enabled
        self.result = result
        self.error = error
        self.route = None
        self.payload = None

    async def render(self, route, payload):
        self.route = route
        self.payload = payload
        if self.error is not None:
            raise self.error
        return self.result


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
        cls.dm = DataManager(str(cls.data_dir))

    @classmethod
    def tearDownClass(cls):
        cls.dm.close()
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
        fake_draw = _FakeDrawApiService(enabled=False)
        matcher = _DummyMatcher()
        query = self.meta.get("first_char_name") or str(self.meta["first_char_id"])
        with patch.object(find_module, "find_cmd", matcher), patch.object(
            find_module, "get_dm_instance", fake_get_dm
        ), patch.object(find_module, "get_t2i_service", lambda: fake_t2i), patch.object(
            find_module, "get_draw_api_service", lambda: fake_draw
        ):
            with self.assertRaises(_FinishCalled) as ctx:
                await find_module._(_DummyMessage(query))

        self.assertEqual(fake_t2i.template_name, "find.html")
        self.assertIsInstance(ctx.exception.payload, MessageSegment)
        self.assertEqual(ctx.exception.payload.type, "image")

    async def test_find_draw_api_success(self):
        import src.plugins.llll.find as find_module
        from src.core.services.draw_payloads import FIND_RENDER_ROUTE

        async def fake_get_dm():
            return self.dm

        fake_t2i = _FakeT2IService()
        fake_draw = _FakeDrawApiService()
        matcher = _DummyMatcher()
        query = self.meta.get("first_char_name") or str(self.meta["first_char_id"])
        with patch.object(find_module, "find_cmd", matcher), patch.object(
            find_module, "get_dm_instance", fake_get_dm
        ), patch.object(find_module, "get_t2i_service", lambda: fake_t2i), patch.object(
            find_module, "get_draw_api_service", lambda: fake_draw
        ):
            with self.assertRaises(_FinishCalled) as ctx:
                await find_module._(_DummyMessage(query))

        self.assertEqual(fake_draw.route, FIND_RENDER_ROUTE)
        self.assertEqual(fake_draw.payload["kind"], "llll.find")
        self.assertGreaterEqual(len(fake_draw.payload["data"]["cards"]), 1)
        # 绘图服务成功时不再走 T2I
        self.assertIsNone(fake_t2i.template_name)
        self.assertIsInstance(ctx.exception.payload, MessageSegment)
        self.assertEqual(ctx.exception.payload.type, "image")

    async def test_find_draw_api_failure_falls_back_to_t2i(self):
        import src.plugins.llll.find as find_module
        from src.core.services.draw_api import DrawApiError

        async def fake_get_dm():
            return self.dm

        fake_t2i = _FakeT2IService()
        fake_draw = _FakeDrawApiService(error=DrawApiError("boom"))
        matcher = _DummyMatcher()
        query = self.meta.get("first_char_name") or str(self.meta["first_char_id"])
        with patch.object(find_module, "find_cmd", matcher), patch.object(
            find_module, "get_dm_instance", fake_get_dm
        ), patch.object(find_module, "get_t2i_service", lambda: fake_t2i), patch.object(
            find_module, "get_draw_api_service", lambda: fake_draw
        ):
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
        fake_draw = _FakeDrawApiService(enabled=False)
        matcher = _DummyMatcher()
        query = self.meta.get("first_char_name") or str(self.meta["first_char_id"])
        with patch.object(chara_module, "chara_cmd", matcher), patch.object(
            chara_module, "get_dm_instance", fake_get_dm
        ), patch.object(chara_module, "get_t2i_service", lambda: fake_t2i), patch.object(
            chara_module, "get_draw_api_service", lambda: fake_draw
        ):
            with self.assertRaises(_FinishCalled) as ctx:
                await chara_module._(_DummyMessage(query))

        self.assertEqual(fake_t2i.template_name, "chara.html")
        self.assertIn("member_profiles", fake_t2i.payload)
        self.assertIsInstance(fake_t2i.payload["member_profiles"], list)
        self.assertIsInstance(ctx.exception.payload, MessageSegment)
        self.assertEqual(ctx.exception.payload.type, "image")

    async def test_chara_member_profiles_payload(self):
        # 有 MemberProfiles 的角色应带上 generation / introduction
        import src.plugins.llll.chara as chara_module

        profile_char_id = self.meta.get("profile_char_id")
        if not profile_char_id:
            self.skipTest("fixture 中所选角色无 MemberProfiles 数据")

        async def fake_get_dm():
            return self.dm

        fake_t2i = _FakeT2IService()
        fake_draw = _FakeDrawApiService(enabled=False)
        matcher = _DummyMatcher()
        with patch.object(chara_module, "chara_cmd", matcher), patch.object(
            chara_module, "get_dm_instance", fake_get_dm
        ), patch.object(chara_module, "get_t2i_service", lambda: fake_t2i), patch.object(
            chara_module, "get_draw_api_service", lambda: fake_draw
        ):
            with self.assertRaises(_FinishCalled):
                await chara_module._(_DummyMessage(str(profile_char_id)))

        profiles = fake_t2i.payload["member_profiles"]
        self.assertGreaterEqual(len(profiles), 1)
        self.assertIn("generation", profiles[0])
        self.assertIn("introduction", profiles[0])

    async def test_chara_draw_api_success(self):
        import src.plugins.llll.chara as chara_module
        from src.core.services.draw_payloads import CHARA_RENDER_ROUTE

        profile_char_id = self.meta.get("profile_char_id")
        if not profile_char_id:
            self.skipTest("fixture 中所选角色无 MemberProfiles 数据")

        async def fake_get_dm():
            return self.dm

        fake_t2i = _FakeT2IService()
        fake_draw = _FakeDrawApiService()
        matcher = _DummyMatcher()
        with patch.object(chara_module, "chara_cmd", matcher), patch.object(
            chara_module, "get_dm_instance", fake_get_dm
        ), patch.object(chara_module, "get_t2i_service", lambda: fake_t2i), patch.object(
            chara_module, "get_draw_api_service", lambda: fake_draw
        ):
            with self.assertRaises(_FinishCalled) as ctx:
                await chara_module._(_DummyMessage(str(profile_char_id)))

        self.assertEqual(fake_draw.route, CHARA_RENDER_ROUTE)
        self.assertEqual(fake_draw.payload["kind"], "llll.chara")
        self.assertGreaterEqual(len(fake_draw.payload["data"]["timelines"]), 1)
        # 绘图服务成功时不再走 T2I
        self.assertIsNone(fake_t2i.template_name)
        self.assertIsInstance(ctx.exception.payload, MessageSegment)
        self.assertEqual(ctx.exception.payload.type, "image")

    async def test_chara_draw_api_failure_falls_back_to_t2i(self):
        import src.plugins.llll.chara as chara_module
        from src.core.services.draw_api import DrawApiError

        async def fake_get_dm():
            return self.dm

        fake_t2i = _FakeT2IService()
        fake_draw = _FakeDrawApiService(error=DrawApiError("boom"))
        matcher = _DummyMatcher()
        query = self.meta.get("first_char_name") or str(self.meta["first_char_id"])
        with patch.object(chara_module, "chara_cmd", matcher), patch.object(
            chara_module, "get_dm_instance", fake_get_dm
        ), patch.object(chara_module, "get_t2i_service", lambda: fake_t2i), patch.object(
            chara_module, "get_draw_api_service", lambda: fake_draw
        ):
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
        fake_draw = _FakeDrawApiService(enabled=False)
        matcher = _DummyMatcher()
        query = str(self.meta.get("first_music_title") or "")[:4]
        with patch.object(music_module, "music_cmd", matcher), patch.object(
            music_module, "get_dm_instance", fake_get_dm
        ), patch.object(music_module, "get_t2i_service", lambda: fake_t2i), patch.object(
            music_module, "get_draw_api_service", lambda: fake_draw
        ):
            with self.assertRaises(_FinishCalled) as ctx:
                await music_module._(_DummyMessage(query))

        self.assertEqual(fake_t2i.template_name, "music.html")
        first_music = fake_t2i.payload["musics"][0]
        self.assertIn("generations_id", first_music)
        self.assertIn("generation_label", first_music)
        self.assertIn("music_type_icon_key", first_music)
        self.assertIn("center_id", first_music)
        self.assertIn("singer_ids", first_music)
        self.assertIn("support_ids", first_music)
        self.assertIn("title_size_class", first_music)
        self.assertIn("title_len", first_music)
        self.assertIn(first_music["title_size_class"], {"xl", "lg", "md", "sm", "xs"})
        self.assertEqual(first_music["title_len"], len(first_music["title"]))
        self.assertIsInstance(ctx.exception.payload, MessageSegment)
        self.assertEqual(ctx.exception.payload.type, "image")

    async def test_music_draw_api_success_single_result(self):
        import src.plugins.llll.music as music_module
        from src.core.services.draw_payloads import MUSIC_RENDER_ROUTE

        async def fake_get_dm():
            return self.dm

        fake_t2i = _FakeT2IService()
        fake_draw = _FakeDrawApiService()
        matcher = _DummyMatcher()
        # 长数字查询按 Id 精确命中，保证单结果
        query = str(self.meta["first_music_id"])
        with patch.object(music_module, "music_cmd", matcher), patch.object(
            music_module, "get_dm_instance", fake_get_dm
        ), patch.object(music_module, "get_t2i_service", lambda: fake_t2i), patch.object(
            music_module, "get_draw_api_service", lambda: fake_draw
        ):
            with self.assertRaises(_FinishCalled) as ctx:
                await music_module._(_DummyMessage(query))

        self.assertEqual(fake_draw.route, MUSIC_RENDER_ROUTE)
        self.assertEqual(fake_draw.payload["kind"], "llll.music")
        self.assertEqual(
            fake_draw.payload["data"]["music"]["id"], self.meta["first_music_id"]
        )
        # 绘图服务成功时不再走 T2I
        self.assertIsNone(fake_t2i.template_name)
        self.assertIsInstance(ctx.exception.payload, MessageSegment)
        self.assertEqual(ctx.exception.payload.type, "image")

    async def test_music_draw_api_failure_falls_back_to_t2i(self):
        import src.plugins.llll.music as music_module
        from src.core.services.draw_api import DrawApiError

        async def fake_get_dm():
            return self.dm

        fake_t2i = _FakeT2IService()
        fake_draw = _FakeDrawApiService(error=DrawApiError("boom"))
        matcher = _DummyMatcher()
        query = str(self.meta["first_music_id"])
        with patch.object(music_module, "music_cmd", matcher), patch.object(
            music_module, "get_dm_instance", fake_get_dm
        ), patch.object(music_module, "get_t2i_service", lambda: fake_t2i), patch.object(
            music_module, "get_draw_api_service", lambda: fake_draw
        ):
            with self.assertRaises(_FinishCalled) as ctx:
                await music_module._(_DummyMessage(query))

        self.assertEqual(fake_t2i.template_name, "music.html")
        self.assertIsInstance(ctx.exception.payload, MessageSegment)
        self.assertEqual(ctx.exception.payload.type, "image")

    async def test_music_multi_result_skips_draw_api(self):
        import src.plugins.llll.music as music_module

        entry = self.dm.search_musics(str(self.meta["first_music_id"]))[0]

        class _MultiDM:
            def __init__(self, dm, results):
                self._dm = dm
                self._results = results

            def __getattr__(self, name):
                return getattr(self._dm, name)

            def search_musics(self, query, limit=None):
                return list(self._results)

        multi_dm = _MultiDM(self.dm, [entry, entry])

        async def fake_get_dm():
            return multi_dm

        fake_t2i = _FakeT2IService()
        fake_draw = _FakeDrawApiService()
        matcher = _DummyMatcher()
        with patch.object(music_module, "music_cmd", matcher), patch.object(
            music_module, "get_dm_instance", fake_get_dm
        ), patch.object(music_module, "get_t2i_service", lambda: fake_t2i), patch.object(
            music_module, "get_draw_api_service", lambda: fake_draw
        ):
            with self.assertRaises(_FinishCalled):
                await music_module._(_DummyMessage("多结果"))

        # 多结果不请求绘图服务，直接走 T2I 合页
        self.assertIsNone(fake_draw.route)
        self.assertEqual(fake_t2i.template_name, "music.html")
        self.assertEqual(len(fake_t2i.payload["musics"]), 2)

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
        fake_draw = _FakeDrawApiService(enabled=False)
        matcher = _DummyMatcher()
        with patch.object(list_module, "list_cmd", matcher), patch.object(
            list_module, "get_dm_instance", fake_get_dm
        ), patch.object(list_module, "get_t2i_service", lambda: fake_t2i), patch.object(
            list_module, "get_draw_api_service", lambda: fake_draw
        ):
            with self.assertRaises(_FinishCalled) as ctx:
                await list_module._()

        self.assertEqual(fake_t2i.template_name, "list.html")
        # 绘图服务未启用时不应发起渲染请求
        self.assertIsNone(fake_draw.route)
        self.assertIsInstance(ctx.exception.payload, MessageSegment)
        self.assertEqual(ctx.exception.payload.type, "image")

    async def test_list_draw_api_success(self):
        import src.plugins.llll.list as list_module

        async def fake_get_dm():
            return self.dm

        fake_t2i = _FakeT2IService()
        fake_draw = _FakeDrawApiService()
        matcher = _DummyMatcher()
        with patch.object(list_module, "list_cmd", matcher), patch.object(
            list_module, "get_dm_instance", fake_get_dm
        ), patch.object(list_module, "get_t2i_service", lambda: fake_t2i), patch.object(
            list_module, "get_draw_api_service", lambda: fake_draw
        ):
            with self.assertRaises(_FinishCalled) as ctx:
                await list_module._()

        self.assertEqual(fake_draw.route, "/api/llll/list")
        self.assertEqual(fake_draw.payload["schema_version"], "1")
        self.assertEqual(fake_draw.payload["kind"], "llll.list")
        self.assertTrue(fake_draw.payload["data"]["characters"])
        first = fake_draw.payload["data"]["characters"][0]
        self.assertEqual(first["icon"]["type"], "chara_icon")
        # 命中绘图服务时不应再走 T2I
        self.assertIsNone(fake_t2i.template_name)
        self.assertIsInstance(ctx.exception.payload, MessageSegment)
        self.assertEqual(ctx.exception.payload.type, "image")

    async def test_list_draw_api_failure_falls_back_to_t2i(self):
        import src.plugins.llll.list as list_module
        from src.core.services.draw_api import DrawApiError

        async def fake_get_dm():
            return self.dm

        fake_t2i = _FakeT2IService()
        fake_draw = _FakeDrawApiService(error=DrawApiError("boom"))
        matcher = _DummyMatcher()
        with patch.object(list_module, "list_cmd", matcher), patch.object(
            list_module, "get_dm_instance", fake_get_dm
        ), patch.object(list_module, "get_t2i_service", lambda: fake_t2i), patch.object(
            list_module, "get_draw_api_service", lambda: fake_draw
        ):
            with self.assertRaises(_FinishCalled) as ctx:
                await list_module._()

        # 绘图服务失败后回退 T2I 渲染
        self.assertEqual(fake_draw.route, "/api/llll/list")
        self.assertEqual(fake_t2i.template_name, "list.html")
        self.assertIsInstance(ctx.exception.payload, MessageSegment)
        self.assertEqual(ctx.exception.payload.type, "image")


if __name__ == "__main__":
    unittest.main()
