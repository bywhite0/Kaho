import json
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from src.core.services.with_live_image import WithLiveImageService


class _FakeResponse:
    def __init__(self, content: bytes, status_code: int = 200):
        self.content = content
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"status={self.status_code}")


class WithLiveImageCacheTest(unittest.IsolatedAsyncioTestCase):
    def _build_png_bytes(self, color: str) -> bytes:
        buf = BytesIO()
        Image.new("RGB", (64, 36), color).save(buf, format="PNG")
        return buf.getvalue()

    async def test_fetch_image_uses_local_cache_after_first_download(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = WithLiveImageService(project_root=Path(tmp_dir))
            image_bytes = self._build_png_bytes("#56c1ff")
            requested_urls = []

            class _Client:
                async def get(self, url, timeout=None):
                    requested_urls.append(url)
                    return _FakeResponse(image_bytes)

            url = "https://example.com/covers/live_a.png"
            first = await service._fetch_image(_Client(), url)
            second = await service._fetch_image(_Client(), url)

            self.assertEqual(first.size, (64, 36))
            self.assertEqual(second.size, (64, 36))
            self.assertEqual(requested_urls, [url])
            self.assertTrue(service._build_cover_cache_path(url).exists())

    async def test_build_current_live_image_downloads_same_cover_only_once(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            snapshot_path = root / "cache" / "game_api" / "with_live.json"
            snapshot_path.parent.mkdir(parents=True, exist_ok=True)

            cover_url = "https://example.com/covers/live_shared.jpg"
            snapshot = {
                "with_live_archive_home": [
                    {
                        "name": "A",
                        "thumbnail_image_url": cover_url,
                        "live_start_time": "2026-03-25T12:00:00+09:00",
                    },
                    {
                        "name": "B",
                        "thumbnail_image_url": cover_url,
                        "live_start_time": "2026-03-26T12:00:00+09:00",
                    },
                ]
            }
            snapshot_path.write_text(
                json.dumps(snapshot, ensure_ascii=False),
                encoding="utf-8",
            )

            image_bytes = self._build_png_bytes("#4dd39a")
            requested_urls = []

            class _FakeAsyncClient:
                def __init__(self, *args, **kwargs):
                    pass

                async def __aenter__(self):
                    return self

                async def __aexit__(self, exc_type, exc, tb):
                    return False

                async def get(self, url, timeout=None):
                    requested_urls.append(url)
                    return _FakeResponse(image_bytes)

            service = WithLiveImageService(project_root=root)
            with patch("src.core.services.with_live_image.httpx.AsyncClient", _FakeAsyncClient):
                rendered = await service.build_current_live_image(auto_refresh_on_miss=False)

            self.assertTrue(rendered.startswith(b"\x89PNG\r\n\x1a\n"))
            self.assertEqual(requested_urls, [cover_url])


if __name__ == "__main__":
    unittest.main()
