import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import nonebot
from nonebot.adapters.onebot.v11 import MessageSegment

from src.core.services.with_live_image import WithLiveImageService


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


class _FailImageClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url, timeout=None):
        request = httpx.Request("GET", url)
        raise httpx.RequestError("mock image fetch failed", request=request)


class LiveCommandTest(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        try:
            nonebot.get_driver()
        except ValueError:
            nonebot.init()

    async def test_live_success(self):
        import src.plugins.llll.live as live_module

        matcher = _DummyMatcher()
        fake_generate = AsyncMock(return_value=b"fake-png")
        with patch.object(live_module, "live_cmd", matcher), patch.object(
            live_module, "generate_with_live_image", fake_generate
        ):
            with self.assertRaises(_FinishCalled) as ctx:
                await live_module._()

        self.assertIsInstance(ctx.exception.payload, MessageSegment)
        self.assertEqual(ctx.exception.payload.type, "image")
        fake_generate.assert_awaited_once_with(auto_refresh_on_miss=True)

    async def test_live_failed(self):
        import src.plugins.llll.live as live_module

        matcher = _DummyMatcher()
        fake_generate = AsyncMock(side_effect=RuntimeError("cache empty"))
        with patch.object(live_module, "live_cmd", matcher), patch.object(
            live_module, "generate_with_live_image", fake_generate
        ):
            with self.assertRaises(_FinishCalled) as ctx:
                await live_module._()

        payload = str(ctx.exception.payload)
        self.assertIn("生成直播信息图片失败", payload)
        self.assertIn("cache empty", payload)

    async def test_live_detail_success(self):
        import src.plugins.llll.live_detail as live_detail_module

        matcher = _DummyMatcher()
        fake_generate = AsyncMock(return_value=b"fake-png")
        with patch.object(live_detail_module, "live_detail_cmd", matcher), patch.object(
            live_detail_module, "generate_with_live_detail_image", fake_generate
        ):
            with self.assertRaises(_FinishCalled) as ctx:
                await live_detail_module._(_DummyMessage("1"))

        self.assertIsInstance(ctx.exception.payload, MessageSegment)
        self.assertEqual(ctx.exception.payload.type, "image")
        fake_generate.assert_awaited_once_with(
            index=1,
            auto_refresh_on_miss=True,
            show_spoiler=False,
        )

    async def test_live_detail_success_with_spoiler(self):
        import src.plugins.llll.live_detail as live_detail_module

        matcher = _DummyMatcher()
        fake_generate = AsyncMock(return_value=b"fake-png")
        with patch.object(live_detail_module, "live_detail_cmd", matcher), patch.object(
            live_detail_module, "generate_with_live_detail_image", fake_generate
        ):
            with self.assertRaises(_FinishCalled) as ctx:
                await live_detail_module._(_DummyMessage("1 --spoiler"))

        self.assertIsInstance(ctx.exception.payload, MessageSegment)
        self.assertEqual(ctx.exception.payload.type, "image")
        fake_generate.assert_awaited_once_with(
            index=1,
            auto_refresh_on_miss=True,
            show_spoiler=True,
        )

    async def test_live_detail_missing_arg(self):
        import src.plugins.llll.live_detail as live_detail_module

        matcher = _DummyMatcher()
        with patch.object(live_detail_module, "live_detail_cmd", matcher):
            with self.assertRaises(_FinishCalled) as ctx:
                await live_detail_module._(_DummyMessage("   "))

        payload = str(ctx.exception.payload)
        self.assertIn("用法", payload)
        self.assertIn("/live_detail", payload)

    async def test_live_detail_non_int_arg(self):
        import src.plugins.llll.live_detail as live_detail_module

        matcher = _DummyMatcher()
        with patch.object(live_detail_module, "live_detail_cmd", matcher):
            with self.assertRaises(_FinishCalled) as ctx:
                await live_detail_module._(_DummyMessage("abc"))

        self.assertIn("请输入正整数序号", str(ctx.exception.payload))

    async def test_live_detail_non_positive_arg(self):
        import src.plugins.llll.live_detail as live_detail_module

        matcher = _DummyMatcher()
        with patch.object(live_detail_module, "live_detail_cmd", matcher):
            with self.assertRaises(_FinishCalled) as ctx:
                await live_detail_module._(_DummyMessage("0"))

        self.assertIn("请输入正整数序号", str(ctx.exception.payload))

    async def test_live_detail_invalid_optional_arg(self):
        import src.plugins.llll.live_detail as live_detail_module

        matcher = _DummyMatcher()
        with patch.object(live_detail_module, "live_detail_cmd", matcher):
            with self.assertRaises(_FinishCalled) as ctx:
                await live_detail_module._(_DummyMessage("1 --test"))

        self.assertIn("不支持的参数", str(ctx.exception.payload))

    async def test_live_detail_out_of_range(self):
        import src.plugins.llll.live_detail as live_detail_module

        matcher = _DummyMatcher()
        fake_generate = AsyncMock(side_effect=ValueError("序号超出范围，可选范围: 1-2"))
        with patch.object(live_detail_module, "live_detail_cmd", matcher), patch.object(
            live_detail_module, "generate_with_live_detail_image", fake_generate
        ):
            with self.assertRaises(_FinishCalled) as ctx:
                await live_detail_module._(_DummyMessage("3"))

        payload = str(ctx.exception.payload)
        self.assertIn("生成直播详情图失败", payload)
        self.assertIn("序号超出范围", payload)


class WithLiveImageServiceTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp_dir.cleanup)
        self.root = Path(self.tmp_dir.name)
        (self.root / "cache" / "game_api").mkdir(parents=True, exist_ok=True)

    def _write_snapshot(self, payload):
        path = self.root / "cache" / "game_api" / "with_live.json"
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def _build_archive(self, name="测试直播"):
        return {
            "archives_id": "A1",
            "live_type": 2,
            "live_id": "L1",
            "name": name,
            "live_start_time": "2026-03-26T11:30:00Z",
            "start_time": "2999-01-01T00:00:00Z",
            "end_time": "2999-01-01T00:00:00Z",
            "thumbnail_image_url": "https://example.com/missing.png",
        }

    async def test_use_cache_without_refresh(self):
        self._write_snapshot({"with_live_archive_home": [self._build_archive()]})
        service = WithLiveImageService(project_root=self.root)
        fake_refresh = AsyncMock()

        with patch(
            "src.core.services.with_live_image.refresh_with_live_data",
            fake_refresh,
        ), patch(
            "src.core.services.with_live_image.httpx.AsyncClient",
            lambda *args, **kwargs: _FailImageClient(),
        ):
            image_bytes = await service.build_current_live_image(auto_refresh_on_miss=True)

        self.assertTrue(image_bytes.startswith(b"\x89PNG"))
        fake_refresh.assert_not_awaited()

    async def test_auto_refresh_when_cache_missing(self):
        service = WithLiveImageService(project_root=self.root)

        async def _write_cache_after_refresh(command_args="with_live"):
            self._write_snapshot(
                {
                    "with_live_archive_home": [],
                    "with_live_archive_live_home": [self._build_archive(name="直播中")],
                    "with_live_archive_trailer_home": [self._build_archive(name="预告")],
                }
            )
            return {"ok": True}

        fake_refresh = AsyncMock(side_effect=_write_cache_after_refresh)

        with patch(
            "src.core.services.with_live_image.refresh_with_live_data",
            fake_refresh,
        ), patch(
            "src.core.services.with_live_image.httpx.AsyncClient",
            lambda *args, **kwargs: _FailImageClient(),
        ):
            image_bytes = await service.build_current_live_image(auto_refresh_on_miss=True)

        self.assertTrue(image_bytes.startswith(b"\x89PNG"))
        fake_refresh.assert_awaited_once_with(command_args="with_live")

    async def test_raise_when_no_data_after_refresh(self):
        service = WithLiveImageService(project_root=self.root)
        fake_refresh = AsyncMock(return_value={"ok": False})

        with patch(
            "src.core.services.with_live_image.refresh_with_live_data",
            fake_refresh,
        ):
            with self.assertRaises(RuntimeError) as ctx:
                await service.build_current_live_image(auto_refresh_on_miss=True)

        self.assertIn("/update with_live", str(ctx.exception))
        fake_refresh.assert_awaited_once_with(command_args="with_live")

    async def test_thumbnail_failed_still_generate(self):
        self._write_snapshot({"with_live_archive_home": [self._build_archive()]})
        service = WithLiveImageService(project_root=self.root)

        with patch(
            "src.core.services.with_live_image.httpx.AsyncClient",
            lambda *args, **kwargs: _FailImageClient(),
        ):
            image_bytes = await service.build_current_live_image(auto_refresh_on_miss=False)

        self.assertTrue(image_bytes.startswith(b"\x89PNG"))


if __name__ == "__main__":
    unittest.main()
