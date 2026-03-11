import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx

import src.core.services.t2i as t2i_module
from src.core.services.t2i import T2IService


class _FakeTemplate:
    def render(self, **_data):
        return "<html>ok</html>"


class _FakeEnv:
    def get_template(self, _name):
        return _FakeTemplate()


class _RetryClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0
        self.closed = False

    @property
    def is_closed(self):
        return self.closed

    async def post(self, url, json):
        self.calls += 1
        request = httpx.Request("POST", url, json=json)
        result = self.responses[self.calls - 1]
        if isinstance(result, Exception):
            raise result
        return httpx.Response(result, request=request, content=b"image")

    async def aclose(self):
        self.closed = True


class T2IServiceTest(unittest.IsolatedAsyncioTestCase):
    async def test_resolve_path(self):
        service = T2IService()
        self.addAsyncCleanup(service.close)
        relative = service._resolve_path("exports/icons/skill")
        self.assertTrue(relative.startswith("file:///"))
        self.assertIn("exports", relative)
        self.assertEqual(
            service._resolve_path("https://example.com/a.png"),
            "https://example.com/a.png",
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            abs_path = str(Path(tmp_dir).resolve())
            self.assertEqual(service._resolve_path(abs_path), Path(abs_path).as_uri())

    async def test_retry_on_5xx(self):
        service = T2IService()
        self.addAsyncCleanup(service.close)
        service.env = _FakeEnv()
        service.retry_count = 2
        service.retry_delay = 0.2
        service._client = _RetryClient([503, 200])

        with patch("src.core.services.t2i.asyncio.sleep", new=AsyncMock()) as mocked:
            content = await service._generate_via_service("dummy.html", {})

        self.assertEqual(content, b"image")
        self.assertEqual(service._client.calls, 2)
        mocked.assert_awaited_once()

    async def test_no_retry_on_4xx(self):
        service = T2IService()
        self.addAsyncCleanup(service.close)
        service.env = _FakeEnv()
        service.retry_count = 3
        service.retry_delay = 0.2
        service._client = _RetryClient([400, 200, 200, 200])

        with self.assertRaises(httpx.HTTPStatusError):
            await service._generate_via_service("dummy.html", {})
        self.assertEqual(service._client.calls, 1)

    async def test_close_singleton(self):
        old_instance = t2i_module._t2i_instance
        service = T2IService()
        try:
            t2i_module._t2i_instance = service
            with patch.object(service, "close", new=AsyncMock()) as close_mock:
                await t2i_module.close_t2i_service()
            self.assertIsNone(t2i_module._t2i_instance)
            close_mock.assert_awaited_once()
        finally:
            await service.close()
            t2i_module._t2i_instance = old_instance


if __name__ == "__main__":
    unittest.main()
