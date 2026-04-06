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

    def test_extract_archives_merges_station_list_without_duplication(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = WithLiveImageService(project_root=Path(tmp_dir))
            snapshot = {
                "home_trailer_list": [
                    {
                        "archives_id": "W1",
                        "live_id": "WLIVE1",
                        "name": "With 场次",
                        "live_type": 2,
                    }
                ],
                "with_station_archive_list": [
                    {
                        "archives_id": "S1",
                        "live_id": "SLIVE1",
                        "name": "Station 场次",
                        "live_type": 3,
                    },
                    {
                        "archives_id": "W1",
                        "live_id": "WLIVE1",
                        "name": "With 场次重复",
                        "live_type": 2,
                    },
                ],
            }

            archives = service._extract_archives(snapshot)

            self.assertEqual(len(archives), 2)
            ids = {str(item.get("archives_id")) for item in archives}
            self.assertEqual(ids, {"W1", "S1"})

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
            renderer = _WithLiveImageRenderer(
                icon_path=Path(tmp_dir) / "missing.png",
                project_root=Path(tmp_dir),
            )
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

    def test_renderer_face_avatar_preserves_original_alpha(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            face_dir = root / "exports" / "icons" / "face"
            face_dir.mkdir(parents=True, exist_ok=True)

            source = Image.new("RGBA", (76, 76), (0, 0, 0, 0))
            source_draw = ImageDraw.Draw(source)
            source_draw.rectangle((28, 28, 48, 48), fill=(255, 0, 0, 255))
            source.save(face_dir / "icon_face_sd_1031_01.png")

            renderer = _WithLiveImageRenderer(
                icon_path=root / "missing.png",
                project_root=root,
            )
            avatar = renderer._load_face_avatar(1031, 76)

            # 圆内但角色透明区应保持透明，防止出现黑底
            self.assertEqual(avatar.getpixel((10, 38))[3], 0)
            r, g, b, a = avatar.getpixel((38, 38))
            self.assertGreater(r, 200)
            self.assertLess(g, 40)
            self.assertLess(b, 40)
            self.assertEqual(a, 255)

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

    async def test_build_live_detail_image_non_enterable_uses_legacy_renderer(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            snapshot_path = root / "cache" / "game_api" / "with_live.json"
            snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            snapshot = {
                "home_trailer_list": [
                    {
                        "archives_id": "A1",
                        "name": "详情场次",
                        "live_id": "L1",
                        "thumbnail_image_url": "https://example.com/covers/detail.jpg",
                        "live_start_time": "2026-03-25T13:00:00+09:00",
                        "description": "第一行\n第二行",
                    }
                ],
                "home_trailer_enterable_list": [],
                "home_trailer_enter_details": [
                    {
                        "live_id": "L1",
                        "status": "ok",
                        "detail": {
                            "is_horizontal": False,
                            "live_location_id": 41,
                            "characters": [{"character_id": 1031}],
                            "costume_ids": [1001],
                        },
                    }
                ],
            }
            snapshot_path.write_text(
                json.dumps(snapshot, ensure_ascii=False),
                encoding="utf-8",
            )

            image_bytes = self._build_png_bytes("#9ed8ff")

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
            with patch(
                "src.core.services.with_live_image.httpx.AsyncClient",
                _FakeAsyncClient,
            ), patch.object(
                _WithLiveImageRenderer,
                "render_detail",
                autospec=True,
                return_value=b"legacy",
            ) as legacy_mock, patch.object(
                _WithLiveImageRenderer,
                "render_detail_enhanced",
                autospec=True,
                return_value=b"enhanced",
            ) as enhanced_mock:
                rendered = await service.build_live_detail_image(
                    index=1,
                    auto_refresh_on_miss=False,
                    show_spoiler=True,
                )

            self.assertEqual(rendered, b"legacy")
            legacy_mock.assert_called_once()
            enhanced_mock.assert_not_called()

    async def test_build_live_detail_image_enterable_hides_spoiler_without_flag(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            snapshot_path = root / "cache" / "game_api" / "with_live.json"
            snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            snapshot = {
                "home_trailer_list": [
                    {
                        "archives_id": "A1",
                        "name": "详情场次",
                        "live_id": "L1",
                        "thumbnail_image_url": "https://example.com/covers/detail.jpg",
                        "live_start_time": "2026-03-25T13:00:00+09:00",
                        "description": "第一行\n第二行",
                    }
                ],
                "home_trailer_enterable_list": [
                    {
                        "archives_id": "A1",
                        "live_id": "L1",
                    }
                ],
                "home_trailer_enter_details": [
                    {
                        "live_id": "L1",
                        "status": "ok",
                        "detail": {
                            "is_horizontal": False,
                            "live_location_id": 41,
                            "characters": [{"character_id": 1031}],
                            "costume_ids": [1001],
                        },
                    }
                ],
            }
            snapshot_path.write_text(
                json.dumps(snapshot, ensure_ascii=False),
                encoding="utf-8",
            )

            image_bytes = self._build_png_bytes("#9ed8ff")

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
            with patch(
                "src.core.services.with_live_image.httpx.AsyncClient",
                _FakeAsyncClient,
            ), patch.object(
                _WithLiveImageRenderer,
                "render_detail",
                autospec=True,
                return_value=b"legacy",
            ) as legacy_mock, patch.object(
                _WithLiveImageRenderer,
                "render_detail_enhanced",
                autospec=True,
                return_value=b"enhanced",
            ) as enhanced_mock:
                rendered = await service.build_live_detail_image(
                    index=1,
                    auto_refresh_on_miss=False,
                    show_spoiler=False,
                )

            self.assertEqual(rendered, b"enhanced")
            legacy_mock.assert_not_called()
            enhanced_mock.assert_called_once()
            detail_item = enhanced_mock.call_args.args[1]
            self.assertEqual(detail_item["orientation_text"], "縦画面")
            self.assertEqual(detail_item["character_ids"], [1031])
            self.assertEqual(
                detail_item["location_text"],
                WithLiveImageService.SPOILER_HIDDEN_TEXT,
            )
            self.assertEqual(
                detail_item["costume_text"],
                WithLiveImageService.SPOILER_HIDDEN_TEXT,
            )

    async def test_build_live_detail_image_enterable_spoiler_shows_masterdata(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            snapshot_path = root / "cache" / "game_api" / "with_live.json"
            snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            snapshot = {
                "home_trailer_list": [
                    {
                        "archives_id": "A1",
                        "name": "详情场次",
                        "live_id": "L1",
                        "thumbnail_image_url": "https://example.com/covers/detail.jpg",
                        "live_start_time": "2026-03-25T13:00:00+09:00",
                        "description": "第一行\n第二行",
                    }
                ],
                "home_trailer_enterable_list": [
                    {
                        "archives_id": "A1",
                        "live_id": "L1",
                    }
                ],
                "home_trailer_enter_details": [
                    {
                        "live_id": "L1",
                        "status": "ok",
                        "detail": {
                            "is_horizontal": True,
                            "live_location_id": 41,
                            "characters": [{"character_id": 1031}],
                            "costume_ids": [1001],
                        },
                    }
                ],
            }
            snapshot_path.write_text(
                json.dumps(snapshot, ensure_ascii=False),
                encoding="utf-8",
            )

            masterdata_dir = root / "masterdata"
            masterdata_dir.mkdir(parents=True, exist_ok=True)
            (masterdata_dir / "LiveLocations.yaml").write_text(
                "- Id: 41\n  Label: 花帆自室(家具無し)\n",
                encoding="utf-8",
            )
            (masterdata_dir / "Costumes.yaml").write_text(
                "- Id: 1001\n  Label: 制服(冬)_上靴\n",
                encoding="utf-8",
            )

            image_bytes = self._build_png_bytes("#9ed8ff")

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
            with patch(
                "src.core.services.with_live_image.httpx.AsyncClient",
                _FakeAsyncClient,
            ), patch.object(
                _WithLiveImageRenderer,
                "render_detail",
                autospec=True,
                return_value=b"legacy",
            ) as legacy_mock, patch.object(
                _WithLiveImageRenderer,
                "render_detail_enhanced",
                autospec=True,
                return_value=b"enhanced",
            ) as enhanced_mock:
                rendered = await service.build_live_detail_image(
                    index=1,
                    auto_refresh_on_miss=False,
                    show_spoiler=True,
                )

            self.assertEqual(rendered, b"enhanced")
            legacy_mock.assert_not_called()
            enhanced_mock.assert_called_once()
            detail_item = enhanced_mock.call_args.args[1]
            self.assertEqual(detail_item["orientation_text"], "横画面")
            self.assertEqual(detail_item["location_text"], "花帆自室(家具無し)")
            self.assertEqual(detail_item["costume_text"], "制服(冬)_上靴")

    async def test_build_live_detail_image_enterable_without_ok_detail_uses_legacy(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            snapshot_path = root / "cache" / "game_api" / "with_live.json"
            snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            snapshot = {
                "home_trailer_list": [
                    {
                        "archives_id": "A1",
                        "name": "详情场次",
                        "live_id": "L1",
                        "thumbnail_image_url": "https://example.com/covers/detail.jpg",
                        "live_start_time": "2026-03-25T13:00:00+09:00",
                        "description": "第一行\n第二行",
                    }
                ],
                "home_trailer_enterable_list": [
                    {
                        "archives_id": "A1",
                        "live_id": "L1",
                    }
                ],
                "home_trailer_enter_details": [
                    {
                        "live_id": "L1",
                        "status": "error",
                        "detail": None,
                    }
                ],
            }
            snapshot_path.write_text(
                json.dumps(snapshot, ensure_ascii=False),
                encoding="utf-8",
            )

            image_bytes = self._build_png_bytes("#9ed8ff")

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
            with patch(
                "src.core.services.with_live_image.httpx.AsyncClient",
                _FakeAsyncClient,
            ), patch.object(
                _WithLiveImageRenderer,
                "render_detail",
                autospec=True,
                return_value=b"legacy",
            ) as legacy_mock, patch.object(
                _WithLiveImageRenderer,
                "render_detail_enhanced",
                autospec=True,
                return_value=b"enhanced",
            ) as enhanced_mock:
                rendered = await service.build_live_detail_image(
                    index=1,
                    auto_refresh_on_miss=False,
                    show_spoiler=True,
                )

            self.assertEqual(rendered, b"legacy")
            legacy_mock.assert_called_once()
            enhanced_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
