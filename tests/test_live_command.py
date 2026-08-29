import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import nonebot
from nonebot.adapters.onebot.v11 import MessageSegment
from PIL import Image

from src.core.services.draw_api import DrawApiError
from src.core.services.draw_payloads import LIVE_RENDER_ROUTE
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


class _FakeLiveDM:
    def get_character_name(self, char_id):
        return {1031: "日野下花帆"}.get(char_id)

    def get_character_theme_color(self, char_id):
        return {1031: "#f8b500"}.get(char_id)

    def get_live_location_label(self, location_id):
        return None


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
        fake_draw = _FakeDrawApiService(enabled=False)
        fake_generate = AsyncMock(return_value=b"fake-png")
        with patch.object(live_detail_module, "live_detail_cmd", matcher), patch.object(
            live_detail_module, "get_draw_api_service", lambda: fake_draw
        ), patch.object(
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
        fake_draw = _FakeDrawApiService(enabled=False)
        fake_generate = AsyncMock(return_value=b"fake-png")
        with patch.object(live_detail_module, "live_detail_cmd", matcher), patch.object(
            live_detail_module, "get_draw_api_service", lambda: fake_draw
        ), patch.object(
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

    async def test_live_detail_draw_api_success(self):
        import src.plugins.llll.live_detail as live_detail_module

        matcher = _DummyMatcher()
        fake_draw = _FakeDrawApiService()
        fake_payload = AsyncMock(return_value={"kind": "llll.live"})
        fake_generate = AsyncMock(return_value=b"fake-png")
        with patch.object(live_detail_module, "live_detail_cmd", matcher), patch.object(
            live_detail_module, "get_draw_api_service", lambda: fake_draw
        ), patch.object(
            live_detail_module, "build_with_live_detail_render_payload", fake_payload
        ), patch.object(
            live_detail_module, "generate_with_live_detail_image", fake_generate
        ):
            with self.assertRaises(_FinishCalled) as ctx:
                await live_detail_module._(_DummyMessage("2 --spoiler"))

        self.assertIsInstance(ctx.exception.payload, MessageSegment)
        self.assertEqual(ctx.exception.payload.type, "image")
        self.assertEqual(fake_draw.route, LIVE_RENDER_ROUTE)
        self.assertEqual(fake_draw.payload, {"kind": "llll.live"})
        fake_payload.assert_awaited_once_with(
            index=2,
            auto_refresh_on_miss=True,
            show_spoiler=True,
        )
        fake_generate.assert_not_awaited()

    async def test_live_detail_draw_api_failure_falls_back(self):
        import src.plugins.llll.live_detail as live_detail_module

        matcher = _DummyMatcher()
        fake_draw = _FakeDrawApiService(error=DrawApiError("boom"))
        fake_payload = AsyncMock(return_value={"kind": "llll.live"})
        fake_generate = AsyncMock(return_value=b"fake-png")
        with patch.object(live_detail_module, "live_detail_cmd", matcher), patch.object(
            live_detail_module, "get_draw_api_service", lambda: fake_draw
        ), patch.object(
            live_detail_module, "build_with_live_detail_render_payload", fake_payload
        ), patch.object(
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

    async def test_live_detail_payload_build_failure_falls_back(self):
        import src.plugins.llll.live_detail as live_detail_module

        matcher = _DummyMatcher()
        fake_draw = _FakeDrawApiService()
        fake_payload = AsyncMock(side_effect=RuntimeError("未找到 with_live 数据"))
        fake_generate = AsyncMock(return_value=b"fake-png")
        with patch.object(live_detail_module, "live_detail_cmd", matcher), patch.object(
            live_detail_module, "get_draw_api_service", lambda: fake_draw
        ), patch.object(
            live_detail_module, "build_with_live_detail_render_payload", fake_payload
        ), patch.object(
            live_detail_module, "generate_with_live_detail_image", fake_generate
        ):
            with self.assertRaises(_FinishCalled) as ctx:
                await live_detail_module._(_DummyMessage("1"))

        self.assertIsInstance(ctx.exception.payload, MessageSegment)
        self.assertEqual(ctx.exception.payload.type, "image")
        # payload 构建已失败，不应触发绘图服务请求
        self.assertIsNone(fake_draw.route)
        fake_generate.assert_awaited_once()

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
        fake_draw = _FakeDrawApiService(enabled=False)
        fake_generate = AsyncMock(side_effect=ValueError("序号超出范围，可选范围: 1-2"))
        with patch.object(live_detail_module, "live_detail_cmd", matcher), patch.object(
            live_detail_module, "get_draw_api_service", lambda: fake_draw
        ), patch.object(
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

    async def test_build_live_detail_render_payload(self):
        archive = self._build_archive()
        archive["character_list"] = [{"character_id": 1031}]
        self._write_snapshot(
            {
                "with_live_archive_home": [archive],
                "latest_archive": {"archives_id": "A1"},
                "latest_archive_detail": {"total_gift_pt": 42},
            }
        )
        service = WithLiveImageService(project_root=self.root)
        fake_cover = AsyncMock(return_value="c" * 64)

        with patch.object(
            service, "_get_data_manager", AsyncMock(return_value=_FakeLiveDM())
        ), patch.object(service, "ensure_cover_exported", fake_cover):
            payload = await service.build_live_detail_render_payload(
                index=1, auto_refresh_on_miss=False
            )

        self.assertEqual(payload["kind"], "llll.live")
        live = payload["data"]["live"]
        self.assertEqual(live["id"], "A1")
        self.assertEqual(live["title"], "测试直播")
        self.assertEqual(live["live_type"], 2)
        self.assertEqual(payload["data"]["stats"], {"gift_point": 42})
        self.assertEqual(
            payload["assets"]["cover"], {"type": "live_cover", "id": "c" * 64}
        )
        self.assertEqual(
            [c["id"] for c in payload["data"]["characters"]], [1031]
        )
        fake_cover.assert_awaited_once_with("https://example.com/missing.png")

    async def test_build_live_detail_render_payload_skips_other_archive_gift(self):
        archive = self._build_archive()
        self._write_snapshot(
            {
                "with_live_archive_home": [archive],
                "latest_archive": {"archives_id": "OTHER"},
                "latest_archive_detail": {"total_gift_pt": 42},
            }
        )
        service = WithLiveImageService(project_root=self.root)

        with patch.object(
            service, "_get_data_manager", AsyncMock(return_value=_FakeLiveDM())
        ), patch.object(service, "ensure_cover_exported", AsyncMock(return_value=None)):
            payload = await service.build_live_detail_render_payload(
                index=1, auto_refresh_on_miss=False
            )

        self.assertNotIn("stats", payload["data"])
        self.assertNotIn("assets", payload)

    async def test_build_live_detail_render_payload_out_of_range(self):
        self._write_snapshot({"with_live_archive_home": [self._build_archive()]})
        service = WithLiveImageService(project_root=self.root)

        with self.assertRaises(ValueError) as ctx:
            await service.build_live_detail_render_payload(
                index=2, auto_refresh_on_miss=False
            )
        self.assertIn("序号超出范围", str(ctx.exception))

    async def test_build_live_detail_render_payload_no_data(self):
        self._write_snapshot({"with_live_archive_home": []})
        service = WithLiveImageService(project_root=self.root)

        with self.assertRaises(RuntimeError) as ctx:
            await service.build_live_detail_render_payload(
                index=1, auto_refresh_on_miss=False
            )
        self.assertIn("/update with_live", str(ctx.exception))

    async def test_ensure_cover_exported_from_cache(self):
        service = WithLiveImageService(project_root=self.root)
        url = "https://example.com/cover.jpg"
        cache_path = service._build_cover_cache_path(url)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (4, 4), "#ff0000").save(cache_path, format="JPEG")

        digest = await service.ensure_cover_exported(url)

        expected = hashlib.sha256(url.encode("utf-8")).hexdigest()
        self.assertEqual(digest, expected)
        target = service.cover_export_dir / f"live_cover_{expected}.png"
        self.assertTrue(target.exists())
        with Image.open(target) as exported:
            self.assertEqual(exported.format, "PNG")

        # 已导出后不再依赖缓存文件
        cache_path.unlink()
        self.assertEqual(await service.ensure_cover_exported(url), expected)

    async def test_ensure_cover_exported_fetch_failure_returns_none(self):
        service = WithLiveImageService(project_root=self.root)
        url = "https://example.com/missing.jpg"

        with patch(
            "src.core.services.with_live_image.httpx.AsyncClient",
            lambda *args, **kwargs: _FailImageClient(),
        ):
            digest = await service.ensure_cover_exported(url)

        self.assertIsNone(digest)
        self.assertFalse(service.cover_export_dir.exists())

    async def test_ensure_cover_exported_empty_url(self):
        service = WithLiveImageService(project_root=self.root)
        self.assertIsNone(await service.ensure_cover_exported(""))
        self.assertIsNone(await service.ensure_cover_exported(None))


if __name__ == "__main__":
    unittest.main()
