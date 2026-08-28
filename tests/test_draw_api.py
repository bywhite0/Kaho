import os
import unittest
from unittest.mock import patch

import httpx

from src.core.services.draw_api import DrawApiError, DrawApiService


def _build_service(base_url="http://draw.test", handler=None):
    with patch.dict(os.environ, {"DRAW_API_BASE_URL": base_url}):
        service = DrawApiService()
    if handler is not None:
        service._client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler), timeout=service.timeout
        )
    return service


class DrawApiServiceTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._services = []

    async def asyncTearDown(self):
        for service in self._services:
            await service.close()

    def _track(self, service):
        self._services.append(service)
        return service

    async def test_disabled_without_base_url(self):
        service = self._track(_build_service(base_url=""))
        self.assertFalse(service.enabled)
        with self.assertRaises(DrawApiError):
            await service.render("/api/llll/list", {})
        self.assertFalse(await service.check_health())

    async def test_base_url_trailing_slash_stripped(self):
        service = self._track(_build_service(base_url="http://draw.test/"))
        self.assertEqual(service.base_url, "http://draw.test")

    async def test_render_success_returns_image_bytes(self):
        captured = {}

        def handler(request):
            captured["url"] = str(request.url)
            captured["method"] = request.method
            captured["body"] = request.read()
            return httpx.Response(
                200, content=b"png-bytes", headers={"content-type": "image/png"}
            )

        service = self._track(_build_service(handler=handler))
        result = await service.render("/api/llll/list", {"kind": "llll.list"})

        self.assertEqual(result, b"png-bytes")
        self.assertEqual(captured["url"], "http://draw.test/api/llll/list")
        self.assertEqual(captured["method"], "POST")
        self.assertIn(b'"kind"', captured["body"])

    async def test_render_non_image_response_raises(self):
        def handler(request):
            return httpx.Response(
                200, json={"detail": "ok"}, headers={"content-type": "application/json"}
            )

        service = self._track(_build_service(handler=handler))
        with self.assertRaises(DrawApiError) as ctx:
            await service.render("/api/llll/list", {})
        self.assertIn("非图片", str(ctx.exception))

    async def test_render_http_error_raises(self):
        def handler(request):
            return httpx.Response(500, json={"detail": "boom"})

        service = self._track(_build_service(handler=handler))
        with self.assertRaises(DrawApiError) as ctx:
            await service.render("/api/llll/list", {})
        self.assertIn("500", str(ctx.exception))

    async def test_render_validation_error_raises(self):
        def handler(request):
            return httpx.Response(422, json={"detail": "invalid payload"})

        service = self._track(_build_service(handler=handler))
        with self.assertRaises(DrawApiError) as ctx:
            await service.render("/api/llll/list", {})
        self.assertIn("422", str(ctx.exception))

    async def test_render_network_error_raises(self):
        def handler(request):
            raise httpx.ConnectTimeout("boom")

        service = self._track(_build_service(handler=handler))
        with self.assertRaises(DrawApiError):
            await service.render("/api/llll/list", {})

    async def test_check_health_ok(self):
        def handler(request):
            self.assertEqual(str(request.url), "http://draw.test/health")
            return httpx.Response(200, json={"status": "healthy"})

        service = self._track(_build_service(handler=handler))
        self.assertTrue(await service.check_health())

    async def test_check_health_error_status(self):
        def handler(request):
            return httpx.Response(503, json={"status": "not_ready"})

        service = self._track(_build_service(handler=handler))
        self.assertFalse(await service.check_health())

    async def test_check_health_network_error(self):
        def handler(request):
            raise httpx.ConnectError("boom")

        service = self._track(_build_service(handler=handler))
        self.assertFalse(await service.check_health())

    async def test_client_recreated_after_close(self):
        service = self._track(_build_service())
        first = service._get_client()
        await service.close()
        second = service._get_client()
        self.assertIsNot(first, second)
        self.assertFalse(second.is_closed)


if __name__ == "__main__":
    unittest.main()
