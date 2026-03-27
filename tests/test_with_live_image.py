import json
import re
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw

from src.core.services.with_live_image import WithLiveImageService, _WithLiveImageRenderer


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
                "home_trailer_list": [
                    {
                        "name": "A",
                        "live_type": 2,
                        "thumbnail_image_url": cover_url,
                        "live_start_time": "2026-03-25T12:00:00+09:00",
                    },
                    {
                        "name": "B",
                        "live_type": 1,
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

    async def test_build_current_live_image_supports_with_and_fes_items(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            snapshot_path = root / "cache" / "game_api" / "with_live.json"
            snapshot_path.parent.mkdir(parents=True, exist_ok=True)

            snapshot = {
                "home_trailer_list": [
                    {
                        "name": "With 场次",
                        "live_type": 2,
                        "thumbnail_image_url": "https://example.com/covers/with.jpg",
                        "open_time": "2026-03-25T12:00:00+09:00",
                        "live_start_time": "2026-03-25T13:00:00+09:00",
                    },
                    {
                        "name": "Fes 场次",
                        "live_type": 1,
                        "thumbnail_image_url": "https://example.com/covers/fes.jpg",
                        "open_time": "2026-03-25T12:00:00+09:00",
                        "live_start_time": "2026-03-25T13:30:00+09:00",
                    },
                ]
            }
            snapshot_path.write_text(
                json.dumps(snapshot, ensure_ascii=False),
                encoding="utf-8",
            )

            colors = {
                "https://example.com/covers/with.jpg": self._build_png_bytes("#4dd39a"),
                "https://example.com/covers/fes.jpg": self._build_png_bytes("#56c1ff"),
            }

            class _FakeAsyncClient:
                def __init__(self, *args, **kwargs):
                    pass

                async def __aenter__(self):
                    return self

                async def __aexit__(self, exc_type, exc, tb):
                    return False

                async def get(self, url, timeout=None):
                    return _FakeResponse(colors[url])

            service = WithLiveImageService(project_root=root)
            with patch("src.core.services.with_live_image.httpx.AsyncClient", _FakeAsyncClient):
                rendered = await service.build_current_live_image(auto_refresh_on_miss=False)

            self.assertTrue(rendered.startswith(b"\x89PNG\r\n\x1a\n"))

    def test_format_time_live_started_uses_live_text(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = WithLiveImageService(project_root=Path(tmp_dir))
            text = service._format_time(
                {
                    "live_start_time": "2000-01-01T00:00:00Z",
                    "live_end_time": "2100-01-01T00:00:00Z",
                }
            )
            self.assertTrue(re.match(r"^\d{2}:\d{2} 起直播中$", text))

    async def test_build_live_detail_image_success(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            snapshot_path = root / "cache" / "game_api" / "with_live.json"
            snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            snapshot = {
                "home_trailer_list": [
                    {
                        "name": "详情场次",
                        "live_type": 2,
                        "live_id": "L1",
                        "thumbnail_image_url": "https://example.com/covers/detail.jpg",
                        "live_start_time": "2026-03-25T13:00:00+09:00",
                        "description": "第一行\n第二行",
                    }
                ]
            }
            snapshot_path.write_text(
                json.dumps(snapshot, ensure_ascii=False),
                encoding="utf-8",
            )

            image_bytes = self._build_png_bytes("#d896ff")

            class _FakeAsyncClient:
                def __init__(self, *args, **kwargs):
                    pass

                async def __aenter__(self):
                    return self

                async def __aexit__(self, exc_type, exc, tb):
                    return False

                async def get(self, url, timeout=None):
                    return _FakeResponse(image_bytes)

            service = WithLiveImageService(project_root=root)
            with patch("src.core.services.with_live_image.httpx.AsyncClient", _FakeAsyncClient):
                rendered = await service.build_live_detail_image(
                    index=1,
                    auto_refresh_on_miss=False,
                )

            self.assertTrue(rendered.startswith(b"\x89PNG\r\n\x1a\n"))

    def test_build_detail_item_fallbacks_to_enter_detail_description(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = WithLiveImageService(project_root=Path(tmp_dir))
            snapshot = {
                "home_trailer_enter_details": [
                    {
                        "live_id": "L1",
                        "status": "ok",
                        "detail": {"description": "主描述\n第二行"},
                    }
                ]
            }
            archive = {
                "name": "详情场次",
                "live_id": "L1",
                "live_start_time": "2026-03-25T13:00:00+09:00",
                "thumbnail_image_url": "https://example.com/covers/detail.jpg",
            }

            detail_item = service._build_detail_item(snapshot, archive)

            self.assertEqual(detail_item["description"], "主描述\n第二行")

    def test_renderer_wrap_lines_preserves_manual_newline(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            renderer = _WithLiveImageRenderer(icon_path=Path(tmp_dir) / "missing.png")
            draw = ImageDraw.Draw(Image.new("RGB", (1080, 500), "#ffffff"))
            lines = renderer._split_wrapped_lines(
                draw=draw,
                text="第一行\n第二行",
                font=renderer.font_desc,
                max_width=1000,
            )

            self.assertGreaterEqual(len(lines), 2)
            self.assertEqual(lines[0], "第一行")
            self.assertEqual(lines[1], "第二行")

    async def test_build_live_detail_image_index_out_of_range(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            snapshot_path = root / "cache" / "game_api" / "with_live.json"
            snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            snapshot = {
                "home_trailer_list": [
                    {
                        "name": "A",
                        "live_start_time": "2026-03-25T13:00:00+09:00",
                    },
                    {
                        "name": "B",
                        "live_start_time": "2026-03-25T14:00:00+09:00",
                    },
                ]
            }
            snapshot_path.write_text(
                json.dumps(snapshot, ensure_ascii=False),
                encoding="utf-8",
            )

            service = WithLiveImageService(project_root=root)
            with self.assertRaises(ValueError) as ctx:
                await service.build_live_detail_image(index=3, auto_refresh_on_miss=False)

            self.assertIn("1-2", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
