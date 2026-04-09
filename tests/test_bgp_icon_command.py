import unittest
from unittest.mock import AsyncMock, patch

import nonebot
from nonebot.adapters.onebot.v11 import Message, MessageSegment


class _FinishCalled(Exception):
    def __init__(self, payload):
        super().__init__("finish")
        self.payload = payload


class _DummyMatcher:
    async def finish(self, payload=None):
        raise _FinishCalled(payload)


class _DummyBot:
    def __init__(self):
        self.call_api = AsyncMock()


class BgpIconCommandTest(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        try:
            nonebot.get_driver()
        except ValueError:
            nonebot.init()

    async def test_bgp_icon_success_with_image_url(self):
        import src.plugins.bgp_icon.command as bgp_icon_module

        matcher = _DummyMatcher()
        bot = _DummyBot()
        args = Message(
            [
                MessageSegment("text", {"text": " "}),
                MessageSegment("image", {"url": "https://example.com/image.png", "file": "a"}),
            ]
        )

        fake_download = AsyncMock(return_value=b"source-bytes")
        with patch.object(bgp_icon_module, "bgp_icon_cmd", matcher), patch.object(
            bgp_icon_module, "_download_image_bytes", fake_download
        ), patch.object(
            bgp_icon_module, "generate_bgp_icon_image", lambda _: b"result-bytes"
        ):
            with self.assertRaises(_FinishCalled) as ctx:
                await bgp_icon_module._(bot, args)

        self.assertIsInstance(ctx.exception.payload, MessageSegment)
        self.assertEqual(ctx.exception.payload.type, "image")
        fake_download.assert_awaited_once_with("https://example.com/image.png")
        bot.call_api.assert_not_awaited()

    async def test_bgp_icon_without_image(self):
        import src.plugins.bgp_icon.command as bgp_icon_module

        matcher = _DummyMatcher()
        bot = _DummyBot()
        args = Message("   ")

        with patch.object(bgp_icon_module, "bgp_icon_cmd", matcher):
            with self.assertRaises(_FinishCalled) as ctx:
                await bgp_icon_module._(bot, args)

        self.assertIn("同一条消息附带", str(ctx.exception.payload))

    async def test_bgp_icon_process_failed(self):
        import src.plugins.bgp_icon.command as bgp_icon_module

        matcher = _DummyMatcher()
        bot = _DummyBot()
        args = Message([MessageSegment("image", {"url": "https://example.com/image.png"})])
        fake_download = AsyncMock(return_value=b"source-bytes")

        with patch.object(bgp_icon_module, "bgp_icon_cmd", matcher), patch.object(
            bgp_icon_module, "_download_image_bytes", fake_download
        ), patch.object(
            bgp_icon_module,
            "generate_bgp_icon_image",
            side_effect=ValueError("仅支持 1:1 比例图片"),
        ):
            with self.assertRaises(_FinishCalled) as ctx:
                await bgp_icon_module._(bot, args)

        payload = str(ctx.exception.payload)
        self.assertIn("生成头像框图片失败", payload)
        self.assertIn("1:1", payload)

    async def test_bgp_icon_uses_first_image_segment(self):
        import src.plugins.bgp_icon.command as bgp_icon_module

        matcher = _DummyMatcher()
        bot = _DummyBot()
        args = Message(
            [
                MessageSegment("image", {"url": "https://example.com/first.png"}),
                MessageSegment("image", {"url": "https://example.com/second.png"}),
            ]
        )
        fake_download = AsyncMock(return_value=b"source-bytes")

        with patch.object(bgp_icon_module, "bgp_icon_cmd", matcher), patch.object(
            bgp_icon_module, "_download_image_bytes", fake_download
        ), patch.object(
            bgp_icon_module, "generate_bgp_icon_image", lambda _: b"result-bytes"
        ):
            with self.assertRaises(_FinishCalled):
                await bgp_icon_module._(bot, args)

        fake_download.assert_awaited_once_with("https://example.com/first.png")

    async def test_bgp_icon_fallback_get_image_api(self):
        import src.plugins.bgp_icon.command as bgp_icon_module

        matcher = _DummyMatcher()
        bot = _DummyBot()
        bot.call_api.return_value = {"url": "https://example.com/from_api.png"}
        args = Message([MessageSegment("image", {"file": "abc"})])
        fake_download = AsyncMock(return_value=b"source-bytes")

        with patch.object(bgp_icon_module, "bgp_icon_cmd", matcher), patch.object(
            bgp_icon_module, "_download_image_bytes", fake_download
        ), patch.object(
            bgp_icon_module, "generate_bgp_icon_image", lambda _: b"result-bytes"
        ):
            with self.assertRaises(_FinishCalled) as ctx:
                await bgp_icon_module._(bot, args)

        self.assertIsInstance(ctx.exception.payload, MessageSegment)
        self.assertEqual(ctx.exception.payload.type, "image")
        bot.call_api.assert_awaited_once_with("get_image", file="abc")
        fake_download.assert_awaited_once_with("https://example.com/from_api.png")


if __name__ == "__main__":
    unittest.main()
