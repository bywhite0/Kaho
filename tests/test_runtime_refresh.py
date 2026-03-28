import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import nonebot

from src.core.data_manager import DataManager


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


class RuntimeRefreshTest(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        try:
            nonebot.get_driver()
        except ValueError:
            nonebot.init()

    async def test_dbrebuild_handler_refreshes_runtime_cache(self):
        import src.plugins.llll.dbrebuild as dbrebuild_module

        class _FakeStore:
            def rebuild(self, *_args, **_kwargs):
                return 0

        class _FakeDM:
            def __init__(self):
                self.store = _FakeStore()
                self.sanitize_yaml = object()
                self.reset_calls = 0

            def reset_runtime_cache(self):
                self.reset_calls += 1

        fake_dm = _FakeDM()
        matcher = _DummyMatcher()
        fake_to_thread = AsyncMock(return_value=123)

        async def fake_get_dm():
            return fake_dm

        with patch.object(dbrebuild_module, "dbrebuild_cmd", matcher), patch.object(
            dbrebuild_module, "get_dm_instance", fake_get_dm
        ), patch.object(
            dbrebuild_module, "get_version_path", lambda: "fake_version.txt"
        ), patch.object(
            dbrebuild_module.asyncio, "to_thread", fake_to_thread
        ):
            with self.assertRaises(_FinishCalled) as ctx:
                await dbrebuild_module._()

        self.assertEqual(ctx.exception.payload, "数据库已重建，变更行数: 123")
        self.assertEqual(fake_dm.reset_calls, 1)
        fake_to_thread.assert_awaited_once_with(
            fake_dm.store.rebuild,
            "fake_version.txt",
            fake_dm.sanitize_yaml,
        )

    async def test_card_empty_query_returns_hint(self):
        import src.plugins.llll.card as card_module

        async def fake_get_dm():
            return object()

        matcher = _DummyMatcher()
        with patch.object(card_module, "card_cmd", matcher), patch.object(
            card_module, "get_dm_instance", fake_get_dm
        ):
            with self.assertRaises(_FinishCalled) as ctx:
                await card_module._(_DummyMessage("   "))

        self.assertEqual(ctx.exception.payload, "请输入卡牌ID。")


class DataManagerResetTest(unittest.TestCase):
    def test_reset_runtime_cache_clears_runtime_state(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            data_dir = root / "masterdata"
            data_dir.mkdir(parents=True, exist_ok=True)
            dm = DataManager(str(data_dir))
            try:
                dm.card_datas.append({"Id": 1})
                dm._loaded.add("card_datas")
                dm.style_movie_series.add(1001)
                dm.token_skill_map["x"] = {"skill_series_id": 1}
                dm.reset_runtime_cache()

                self.assertEqual(dm.card_datas, [])
                self.assertEqual(dm._loaded, set())
                self.assertEqual(dm.style_movie_series, set())
                self.assertEqual(dm.token_skill_map, {})
            finally:
                dm.close()

    def test_rebuild_then_reset_runtime_cache_uses_new_masterdata(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            data_dir = root / "masterdata"
            cache_dir = root / "cache"
            data_dir.mkdir(parents=True, exist_ok=True)
            cache_dir.mkdir(parents=True, exist_ok=True)
            version_path = cache_dir / "currentVersion.txt"
            version_path.write_text("v1", encoding="utf-8")

            (data_dir / "CardDatas.yaml").write_text(
                """
- Id: 10010
  CardSeriesId: 1001
  CharactersId: 1
  Name: 旧卡名
  State: 0
  Rarity: 1
""".strip(),
                encoding="utf-8",
            )

            dm = DataManager(str(data_dir))
            try:
                dm.sync_version_cache(str(version_path))
                self.assertEqual(len(dm.search_card_series("旧卡名", limit=10)), 1)
                self.assertEqual(len(dm.search_card_series("新卡名", limit=10)), 0)

                (data_dir / "CardDatas.yaml").write_text(
                    """
- Id: 10010
  CardSeriesId: 1001
  CharactersId: 1
  Name: 新卡名
  State: 0
  Rarity: 1
""".strip(),
                    encoding="utf-8",
                )
                version_path.write_text("v2", encoding="utf-8")

                dm.store.rebuild(str(version_path), dm.sanitize_yaml)
                dm.reset_runtime_cache()

                self.assertEqual(len(dm.search_card_series("新卡名", limit=10)), 1)
                self.assertEqual(len(dm.search_card_series("旧卡名", limit=10)), 0)
            finally:
                dm.close()


if __name__ == "__main__":
    unittest.main()
