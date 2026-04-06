import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import nonebot

from src.core.services.game_api import GameApiService


TEST_API_ENV = {
    "GAME_API_BASE_URL": "https://example.com/v1",
    "GAME_API_HOST": "example.com",
    "GAME_API_X_API_KEY": "test-api-key",
}


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


class _RouteClient:
    def __init__(self, routes):
        self.routes = {k: list(v) for k, v in routes.items()}
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, json, headers):
        path = url.split("/v1", 1)[-1]
        self.calls.append({"path": path, "json": json, "headers": headers})
        if path not in self.routes or not self.routes[path]:
            raise AssertionError(f"未配置路由响应: {path}")
        item = self.routes[path].pop(0)
        if callable(item):
            return item(url, json, headers)
        return item


def _resp(url, status_code, payload, headers=None):
    request = httpx.Request("POST", url)
    response_headers = headers or {}
    return httpx.Response(
        status_code,
        request=request,
        json=payload,
        headers=response_headers,
    )


def _build_config(token="token-old"):
    return {
        "credential": {
            "res_version": "TEST_RES_VERSION",
            "client_version": "TEST_CLIENT_VERSION",
            "device_specific_id": "TEST_DEVICE_ID",
            "player_id": "TEST_PLAYER_ID",
            "session_token": token,
        }
    }


class GameApiServiceTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp_dir.cleanup)
        self.root = Path(self.tmp_dir.name)
        (self.root / "cache" / "game_api").mkdir(parents=True, exist_ok=True)
        self.env_patcher = patch.dict(os.environ, TEST_API_ENV, clear=False)
        self.env_patcher.start()
        self.addCleanup(self.env_patcher.stop)

    def _write_json(self, path: Path, payload):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _write_config(self, path: Path, token="token-old"):
        self._write_json(path, _build_config(token=token))

    def _write_old_snapshot(self, payload):
        self._write_json(self.root / "cache" / "game_api" / "with_live.json", payload)

    def test_config_path_priority(self):
        env_cfg = self.root / "custom" / "env_config.json"
        cache_cfg = self.root / "cache" / "game_api" / "config.json"
        local_cfg = self.root / "linkura-cli_config.json"
        home_root = self.root / "home"
        home_cfg = home_root / ".config" / "linkura-cli" / "config.json"

        self._write_config(env_cfg)
        self._write_config(cache_cfg)
        self._write_config(local_cfg)
        self._write_config(home_cfg)

        service = GameApiService(project_root=self.root)
        with patch.dict(
            os.environ,
            {
                "LINKURA_CONFIG_PATH": str(env_cfg),
                "USERPROFILE": str(home_root),
            },
            clear=False,
        ):
            self.assertEqual(service.resolve_config_path(), env_cfg.resolve())

        with patch.dict(
            os.environ,
            {
                "LINKURA_CONFIG_PATH": "",
                "USERPROFILE": str(home_root),
            },
            clear=False,
        ):
            self.assertEqual(service.resolve_config_path(), cache_cfg.resolve())

    def test_load_api_settings_from_nonebot_config(self):
        class _DummyConfig:
            game_api_base_url = "https://config.example.com/v1"
            game_api_x_api_key = "config-key"
            game_api_ua_prefix = "config-ua"

        class _DummyDriver:
            config = _DummyConfig()

        with patch.dict(os.environ, {}, clear=True), patch(
            "nonebot.get_driver", return_value=_DummyDriver()
        ):
            service = GameApiService(project_root=self.root)

        self.assertEqual(service.api_base, "https://config.example.com/v1")
        self.assertEqual(service.api_host, "config.example.com")
        self.assertEqual(service.api_key, "config-key")
        self.assertEqual(service.ua_prefix, "config-ua")

    def test_config_path_from_nonebot_config(self):
        env_cfg = self.root / "custom" / "env_config.json"
        self._write_config(env_cfg)

        class _DummyConfig:
            linkura_config_path = str(env_cfg)
            game_api_base_url = "https://config.example.com/v1"
            game_api_x_api_key = "config-key"

        class _DummyDriver:
            config = _DummyConfig()

        with patch.dict(os.environ, {}, clear=True), patch(
            "nonebot.get_driver", return_value=_DummyDriver()
        ):
            service = GameApiService(project_root=self.root)
            self.assertEqual(service.resolve_config_path(), env_cfg.resolve())

    async def test_refresh_collects_enterable_details_and_latest_any(self):
        config_path = self.root / "cache" / "game_api" / "config.json"
        self._write_config(config_path, token="token-ok")
        service = GameApiService(project_root=self.root)

        now = datetime.now(timezone.utc)
        open_past = (now - timedelta(minutes=15)).isoformat().replace("+00:00", "Z")
        open_future = (now + timedelta(hours=2)).isoformat().replace("+00:00", "Z")
        start_soon = (now + timedelta(minutes=20)).isoformat().replace("+00:00", "Z")
        start_past = (now - timedelta(minutes=5)).isoformat().replace("+00:00", "Z")
        start_late = (now + timedelta(hours=3)).isoformat().replace("+00:00", "Z")

        fake_client = _RouteClient(
            {
                "/archive/get_home": [
                    lambda url, _json, _headers: _resp(url, 200, {"ok": True}),
                    lambda url, _json, _headers: _resp(
                        url,
                        200,
                        {
                            "live_archive_list": [
                                {
                                    "archives_id": "W1",
                                    "live_id": "WLIVE1",
                                    "live_type": 2,
                                    "name": "with-enterable",
                                    "open_time": open_past,
                                    "live_start_time": start_soon,
                                    "thumbnail_image_url": "https://example.com/w1.jpg",
                                },
                                {
                                    "archives_id": "F1",
                                    "live_id": "FLIVE1",
                                    "live_type": 1,
                                    "name": "fes-enterable",
                                    "open_time": open_past,
                                    "live_start_time": start_past,
                                    "thumbnail_image_url": "https://example.com/f1.jpg",
                                },
                                {
                                    "archives_id": "W2",
                                    "live_id": "WLIVE2",
                                    "live_type": 2,
                                    "name": "with-future",
                                    "open_time": open_future,
                                    "live_start_time": start_late,
                                    "thumbnail_image_url": "https://example.com/w2.jpg",
                                },
                            ],
                            "trailer_archive_list": [],
                        },
                    ),
                ],
                "/withlive/enter": [
                    lambda url, request_json, _headers: _resp(
                        url,
                        200,
                        {"live_id": request_json["live_id"], "with_info": "ok"},
                    )
                ],
                "/feslive/lobby": [
                    lambda url, _json, _headers: _resp(url, 200, {"ok": True})
                ],
                "/feslive/enter": [
                    lambda url, request_json, _headers: _resp(
                        url,
                        200,
                        {"live_id": request_json["live_id"], "fes_info": "ok"},
                    )
                ],
                "/archive/get_archive_list": [
                    lambda url, _json, _headers: _resp(
                        url,
                        200,
                        {"archive_list": [{"archives_id": "W2", "live_type": 2}]},
                    ),
                    lambda url, _json, _headers: _resp(
                        url,
                        200,
                        {
                            "archive_list": [
                                {
                                    "archives_id": "ANY1",
                                    "live_id": "ANYLIVE1",
                                    "live_type": 1,
                                    "name": "any-latest",
                                },
                                {
                                    "archives_id": "ANY2",
                                    "live_id": "ANYLIVE2",
                                    "live_type": 2,
                                },
                            ]
                        },
                    ),
                ],
                "/archive/get_with_archive_data": [
                    lambda url, request_json, _headers: _resp(
                        url,
                        200,
                        {"archives_id": request_json["archives_id"], "detail": "ok"},
                    )
                ],
            }
        )

        with patch(
            "src.core.services.game_api.httpx.AsyncClient",
            lambda *args, **kwargs: fake_client,
        ):
            result = await service.refresh_with_live(command_args="with_live")

        source = result["source"]
        self.assertEqual(source["archive_get_home_total_count"], 3)
        self.assertEqual(source["archive_get_home_with_count"], 2)
        self.assertEqual(source["archive_get_home_station_count"], 0)
        self.assertEqual(source["archive_get_home_fes_count"], 1)
        self.assertEqual(source["enterable_total_count"], 2)
        self.assertEqual(source["enterable_with_count"], 1)
        self.assertEqual(source["enterable_fes_count"], 1)
        self.assertEqual(source["enter_detail_success_count"], 2)
        self.assertEqual(source["enter_detail_failed_count"], 0)
        self.assertEqual(len(result["home_trailer_list"]), 3)
        self.assertEqual(len(result["home_trailer_enterable_list"]), 2)
        self.assertEqual(len(result["home_trailer_enter_details"]), 2)
        self.assertIn("with_live_archive_home", result)

        detail_sources = {
            item["detail_source"]
            for item in result["home_trailer_enter_details"]
            if item.get("status") == "ok"
        }
        self.assertEqual(detail_sources, {"withlive_enter", "feslive_enter"})
        self.assertEqual(result["latest_archive_any"]["archives_id"], "ANY1")
        self.assertEqual(
            result["latest_archive_any_meta"]["source"],
            "archive_get_archive_list",
        )

        self.assertEqual(result["latest_archive"]["archives_id"], "W2")
        self.assertEqual(result["latest_archive_detail"]["archives_id"], "W2")
        self.assertEqual(
            result["latest_archive_detail_meta"]["source"],
            "archive_get_with_archive_data",
        )
        self.assertTrue(
            any(call["path"] == "/withlive/enter" for call in fake_client.calls)
        )
        self.assertTrue(
            any(call["path"] == "/feslive/lobby" for call in fake_client.calls)
        )
        self.assertTrue(
            any(call["path"] == "/feslive/enter" for call in fake_client.calls)
        )

    async def test_refresh_supports_with_station_list_and_station_detail(self):
        config_path = self.root / "cache" / "game_api" / "config.json"
        self._write_config(config_path, token="token-ok")
        service = GameApiService(project_root=self.root)

        now = datetime.now(timezone.utc)
        open_future = (now + timedelta(hours=2)).isoformat().replace("+00:00", "Z")
        start_type2 = (now + timedelta(hours=3)).isoformat().replace("+00:00", "Z")
        start_station = (now + timedelta(hours=5)).isoformat().replace("+00:00", "Z")

        fake_client = _RouteClient(
            {
                "/archive/get_home": [
                    lambda url, _json, _headers: _resp(url, 200, {"ok": True}),
                    lambda url, _json, _headers: _resp(
                        url,
                        200,
                        {
                            "live_archive_list": [
                                {
                                    "archives_id": "W1",
                                    "live_id": "WLIVE1",
                                    "live_type": 2,
                                    "name": "with-item",
                                    "open_time": open_future,
                                    "live_start_time": start_type2,
                                }
                            ],
                            "trailer_archive_list": [],
                        },
                    ),
                ],
                "/archive/get_archive_list": [
                    lambda url, _json, _headers: _resp(
                        url,
                        200,
                        {
                            "archive_list": [
                                {
                                    "archives_id": "W1",
                                    "live_id": "WLIVE1",
                                    "live_type": 2,
                                    "name": "with-item",
                                    "live_start_time": start_type2,
                                }
                            ]
                        },
                    ),
                    lambda url, _json, _headers: _resp(url, 200, {"archive_list": []}),
                ],
                "/archive/get_with_station_list": [
                    lambda url, _json, _headers: _resp(
                        url,
                        200,
                        {
                            "archive_list": [
                                {
                                    "archives_id": "S1",
                                    "live_id": "SLIVE1",
                                    "live_type": 3,
                                    "name": "station-item",
                                    "live_start_time": start_station,
                                }
                            ]
                        },
                    )
                ],
                "/archive/get_with_station_data": [
                    lambda url, request_json, _headers: _resp(
                        url,
                        200,
                        {
                            "archives_id": request_json["archives_id"],
                            "detail": "station-ok",
                        },
                    )
                ],
            }
        )

        with patch(
            "src.core.services.game_api.httpx.AsyncClient",
            lambda *args, **kwargs: fake_client,
        ):
            result = await service.refresh_with_live(command_args="with_live")

        self.assertEqual(result["latest_archive"]["archives_id"], "S1")
        self.assertEqual(
            result["latest_archive_detail_meta"]["source"],
            "archive_get_with_station_data",
        )
        self.assertEqual(len(result["with_station_archive_list"]), 1)
        self.assertEqual(result["with_station_archive_list"][0]["archives_id"], "S1")
        self.assertTrue(
            any(call["path"] == "/archive/get_with_station_list" for call in fake_client.calls)
        )
        self.assertTrue(
            any(call["path"] == "/archive/get_with_station_data" for call in fake_client.calls)
        )

    async def test_refresh_station_not_in_enterable_pipeline(self):
        config_path = self.root / "cache" / "game_api" / "config.json"
        self._write_config(config_path, token="token-ok")
        service = GameApiService(project_root=self.root)

        now = datetime.now(timezone.utc)
        open_past = (now - timedelta(minutes=10)).isoformat().replace("+00:00", "Z")
        start_future = (now + timedelta(minutes=30)).isoformat().replace("+00:00", "Z")

        fake_client = _RouteClient(
            {
                "/archive/get_home": [
                    lambda url, _json, _headers: _resp(url, 200, {"ok": True}),
                    lambda url, _json, _headers: _resp(
                        url,
                        200,
                        {
                            "live_archive_list": [
                                {
                                    "archives_id": "S1",
                                    "live_id": "SLIVE1",
                                    "live_type": 3,
                                    "name": "station-enterable",
                                    "open_time": open_past,
                                    "live_start_time": start_future,
                                }
                            ],
                            "trailer_archive_list": [],
                        },
                    ),
                ],
                "/archive/get_archive_list": [
                    lambda url, _json, _headers: _resp(url, 200, {"archive_list": []}),
                    lambda url, _json, _headers: _resp(url, 200, {"archive_list": []}),
                ],
                "/archive/get_with_station_list": [
                    lambda url, _json, _headers: _resp(url, 200, {"archive_list": []})
                ],
            }
        )

        with patch(
            "src.core.services.game_api.httpx.AsyncClient",
            lambda *args, **kwargs: fake_client,
        ):
            result = await service.refresh_with_live(command_args="with_live")

        source = result["source"]
        self.assertEqual(source["enterable_total_count"], 0)
        self.assertEqual(source["enter_detail_success_count"], 0)
        self.assertEqual(source["enter_detail_failed_count"], 0)
        self.assertEqual(len(result["home_trailer_enter_details"]), 0)

    async def test_refresh_skip_fes_enter_when_live_not_started(self):
        config_path = self.root / "cache" / "game_api" / "config.json"
        self._write_config(config_path, token="token-ok")
        service = GameApiService(project_root=self.root)

        now = datetime.now(timezone.utc)
        open_past = (now - timedelta(minutes=10)).isoformat().replace("+00:00", "Z")
        start_future = (now + timedelta(minutes=30)).isoformat().replace("+00:00", "Z")

        fake_client = _RouteClient(
            {
                "/archive/get_home": [
                    lambda url, _json, _headers: _resp(url, 200, {"ok": True}),
                    lambda url, _json, _headers: _resp(
                        url,
                        200,
                        {
                            "live_archive_list": [
                                {
                                    "archives_id": "F1",
                                    "live_id": "FLIVE1",
                                    "live_type": 1,
                                    "name": "fes-lobby-only",
                                    "open_time": open_past,
                                    "live_start_time": start_future,
                                }
                            ],
                            "trailer_archive_list": [],
                        },
                    ),
                ],
                "/feslive/lobby": [
                    lambda url, request_json, _headers: _resp(
                        url,
                        200,
                        {"live_id": request_json["live_id"], "lobby": "ok"},
                    )
                ],
                "/archive/get_archive_list": [
                    lambda url, _json, _headers: _resp(url, 200, {"archive_list": []}),
                    lambda url, _json, _headers: _resp(url, 200, {"archive_list": []}),
                ],
            }
        )

        with patch(
            "src.core.services.game_api.httpx.AsyncClient",
            lambda *args, **kwargs: fake_client,
        ):
            result = await service.refresh_with_live(command_args="with_live")

        source = result["source"]
        self.assertEqual(source["enterable_total_count"], 1)
        self.assertEqual(source["enter_detail_success_count"], 0)
        self.assertEqual(source["enter_detail_failed_count"], 0)
        self.assertFalse(
            any("403" in str(error) for error in source.get("fetch_errors", []))
        )
        self.assertFalse(any(call["path"] == "/feslive/enter" for call in fake_client.calls))
        self.assertTrue(any(call["path"] == "/feslive/lobby" for call in fake_client.calls))
        self.assertEqual(len(result["home_trailer_enter_details"]), 1)
        self.assertEqual(result["home_trailer_enter_details"][0]["status"], "skipped")
        self.assertEqual(
            result["home_trailer_enter_details"][0]["detail_source"],
            "feslive_lobby",
        )

    async def test_refresh_token_when_session_invalid(self):
        config_path = self.root / "cache" / "game_api" / "config.json"
        self._write_config(config_path, token="token-old")
        service = GameApiService(project_root=self.root)

        fake_client = _RouteClient(
            {
                "/archive/get_home": [
                    lambda url, _json, _headers: _resp(url, 401, {"message": "invalid"}),
                    lambda url, _json, _headers: _resp(
                        url,
                        200,
                        {"live_archive_list": [], "trailer_archive_list": []},
                    ),
                ],
                "/user/login": [
                    lambda url, request_json, _headers: _resp(
                        url,
                        400,
                        {"message": "version probe"},
                        headers={
                            "x-res-version": "R2603260@probe",
                        },
                    )
                    if request_json.get("player_id") == ""
                    else _resp(url, 500, {"message": "unexpected probe payload"}),
                    lambda url, _json, _headers: _resp(url, 200, {"session_token": "token-new"}),
                ],
                "/archive/get_archive_list": [
                    lambda url, _json, _headers: _resp(url, 200, {"archive_list": []}),
                    lambda url, _json, _headers: _resp(url, 200, {"archive_list": []}),
                ],
            }
        )

        with patch(
            "src.core.services.game_api.httpx.AsyncClient",
            lambda *args, **kwargs: fake_client,
        ), patch.object(
            service,
            "_detect_latest_client_version",
            AsyncMock(return_value="4.11.5"),
        ):
            result = await service.refresh_with_live(command_args="with_live")

        self.assertEqual(result["source"]["archive_get_home_total_count"], 0)
        self.assertEqual(result["latest_archive_detail_meta"]["source"], "none")
        self.assertEqual(result["latest_archive_any_meta"]["source"], "none")
        saved = json.loads(config_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["credential"]["session_token"], "token-new")
        self.assertEqual(saved["credential"]["client_version"], "4.11.5")
        self.assertEqual(saved["credential"]["res_version"], "R2603260")

        home_calls = [call for call in fake_client.calls if call["path"] == "/archive/get_home"]
        self.assertGreaterEqual(len(home_calls), 2)
        self.assertEqual(home_calls[-1]["headers"].get("authorization"), "Bearer token-new")
        self.assertEqual(home_calls[-1]["headers"].get("x-client-version"), "4.11.5")
        self.assertEqual(home_calls[-1]["headers"].get("x-res-version"), "R2603260")

        login_calls = [call for call in fake_client.calls if call["path"] == "/user/login"]
        self.assertEqual(len(login_calls), 2)
        self.assertEqual(login_calls[0]["json"].get("player_id"), "")
        self.assertEqual(login_calls[0]["headers"].get("x-client-version"), "4.11.5")

    async def test_refresh_token_when_session_check_returns_400(self):
        config_path = self.root / "cache" / "game_api" / "config.json"
        self._write_config(config_path, token="token-old")
        service = GameApiService(project_root=self.root)

        fake_client = _RouteClient(
            {
                "/archive/get_home": [
                    lambda url, _json, _headers: _resp(url, 400, {"message": "bad version"}),
                    lambda url, _json, _headers: _resp(
                        url,
                        200,
                        {"live_archive_list": [], "trailer_archive_list": []},
                    ),
                ],
                "/user/login": [
                    lambda url, request_json, _headers: _resp(
                        url,
                        400,
                        {"message": "version probe"},
                        headers={
                            "x-res-version": "R2603260@probe",
                        },
                    )
                    if request_json.get("player_id") == ""
                    else _resp(url, 500, {"message": "unexpected probe payload"}),
                    lambda url, _json, _headers: _resp(url, 200, {"session_token": "token-new"}),
                ],
                "/archive/get_archive_list": [
                    lambda url, _json, _headers: _resp(url, 200, {"archive_list": []}),
                    lambda url, _json, _headers: _resp(url, 200, {"archive_list": []}),
                ],
            }
        )

        with patch(
            "src.core.services.game_api.httpx.AsyncClient",
            lambda *args, **kwargs: fake_client,
        ), patch.object(
            service,
            "_detect_latest_client_version",
            AsyncMock(return_value="4.11.5"),
        ):
            result = await service.refresh_with_live(command_args="with_live")

        self.assertEqual(result["source"]["archive_get_home_total_count"], 0)
        saved = json.loads(config_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["credential"]["session_token"], "token-new")
        self.assertEqual(saved["credential"]["client_version"], "4.11.5")
        self.assertEqual(saved["credential"]["res_version"], "R2603260")

        home_calls = [call for call in fake_client.calls if call["path"] == "/archive/get_home"]
        self.assertGreaterEqual(len(home_calls), 2)
        self.assertEqual(home_calls[-1]["headers"].get("authorization"), "Bearer token-new")

    async def test_enter_detail_failed_not_block_overall_refresh(self):
        config_path = self.root / "cache" / "game_api" / "config.json"
        self._write_config(config_path, token="token-ok")
        self._write_old_snapshot({"updated_at": "2026-03-20T10:00:00+08:00"})
        service = GameApiService(project_root=self.root)

        now = datetime.now(timezone.utc)
        open_past = (now - timedelta(minutes=10)).isoformat().replace("+00:00", "Z")
        start_soon = (now + timedelta(minutes=10)).isoformat().replace("+00:00", "Z")
        start_past = (now - timedelta(minutes=3)).isoformat().replace("+00:00", "Z")

        fake_client = _RouteClient(
            {
                "/archive/get_home": [
                    lambda url, _json, _headers: _resp(url, 200, {"ok": True}),
                    lambda url, _json, _headers: _resp(
                        url,
                        200,
                        {
                            "live_archive_list": [
                                {
                                    "archives_id": "W1",
                                    "live_id": "WLIVE1",
                                    "live_type": 2,
                                    "name": "with-enterable",
                                    "open_time": open_past,
                                    "live_start_time": start_soon,
                                },
                                {
                                    "archives_id": "F1",
                                    "live_id": "FLIVE1",
                                    "live_type": 1,
                                    "name": "fes-enterable",
                                    "open_time": open_past,
                                    "live_start_time": start_past,
                                },
                            ],
                            "trailer_archive_list": [],
                        },
                    ),
                ],
                "/withlive/enter": [
                    lambda url, _json, _headers: _resp(url, 500, {"message": "boom"})
                ],
                "/feslive/lobby": [
                    lambda url, _json, _headers: _resp(url, 500, {"message": "lobby-boom"})
                ],
                "/feslive/enter": [
                    lambda url, request_json, _headers: _resp(
                        url,
                        200,
                        {"live_id": request_json["live_id"], "fes_info": "ok"},
                    )
                ],
                "/archive/get_archive_list": [
                    lambda url, _json, _headers: _resp(
                        url,
                        200,
                        {"archive_list": [{"archives_id": "W1", "live_type": 2}]},
                    ),
                    lambda url, _json, _headers: _resp(url, 200, {"archive_list": []}),
                ],
                "/archive/get_with_archive_data": [
                    lambda url, _json, _headers: _resp(url, 500, {"message": "detail-boom"})
                ],
            }
        )

        with patch(
            "src.core.services.game_api.httpx.AsyncClient",
            lambda *args, **kwargs: fake_client,
        ):
            result = await service.refresh_with_live(command_args="with_live")

        source = result["source"]
        self.assertEqual(source["enterable_total_count"], 2)
        self.assertEqual(source["enter_detail_success_count"], 1)
        self.assertEqual(source["enter_detail_failed_count"], 1)
        self.assertEqual(
            result["latest_archive_detail_meta"]["source"],
            "home",
        )
        self.assertEqual(
            result["latest_archive_any_meta"]["source"],
            "latest_archive",
        )
        self.assertTrue(
            any("enter_detail:" in str(error) for error in source.get("fetch_errors", []))
        )
        statuses = {item["status"] for item in result["home_trailer_enter_details"]}
        self.assertEqual(statuses, {"ok", "error"})

        backup_path = self.root / "cache" / "game_api" / "with_live.prev.json"
        self.assertTrue(backup_path.exists())


class UpdateCommandTest(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        try:
            nonebot.get_driver()
        except ValueError:
            nonebot.init()

    async def test_update_no_args_help(self):
        import src.plugins.llll.update as update_module

        matcher = _DummyMatcher()
        with patch.object(update_module, "update_cmd", matcher):
            with self.assertRaises(_FinishCalled) as ctx:
                await update_module._(_DummyMessage("   "))

        self.assertIn("/update with_live", ctx.exception.payload)

    async def test_update_unknown_arg(self):
        import src.plugins.llll.update as update_module

        matcher = _DummyMatcher()
        with patch.object(update_module, "update_cmd", matcher):
            with self.assertRaises(_FinishCalled) as ctx:
                await update_module._(_DummyMessage("unknown"))

        self.assertIn("不支持的更新参数", ctx.exception.payload)

    async def test_update_with_live_success(self):
        import src.plugins.llll.update as update_module

        matcher = _DummyMatcher()
        fake_refresh = AsyncMock(
            return_value={
                "updated_at": "2026-03-23T10:00:00+08:00",
                "cache_path": "/redacted/cache/game_api/with_live.json",
                "source": {
                    "archive_get_home_total_count": 3,
                    "archive_get_home_with_count": 2,
                    "archive_get_home_station_count": 1,
                    "archive_get_home_fes_count": 1,
                    "enterable_total_count": 2,
                    "enterable_with_count": 1,
                    "enterable_fes_count": 1,
                    "enter_detail_success_count": 2,
                    "enter_detail_failed_count": 0,
                    "fetch_errors": ["x"],
                },
                "latest_archive_any": {
                    "archives_id": "A100",
                    "name": "最新场次",
                },
                "latest_archive_any_meta": {
                    "source": "archive_get_archive_list",
                },
            }
        )
        with patch.object(update_module, "update_cmd", matcher), patch.object(
            update_module, "refresh_with_live_data", fake_refresh
        ):
            with self.assertRaises(_FinishCalled) as ctx:
                await update_module._(_DummyMessage("with_live"))

        payload = ctx.exception.payload
        self.assertIn("with_live 数据刷新完成", payload)
        self.assertIn("home 总场次: 3", payload)
        self.assertIn("home With×MEETS: 2", payload)
        self.assertIn("home With×STATION: 1", payload)
        self.assertIn("home Fes×LIVE: 1", payload)
        self.assertIn("可进场总数: 2", payload)
        self.assertIn("详情成功: 2", payload)
        self.assertIn("最新 Archive ID: A100", payload)
        self.assertIn("最新 Archive 来源: archive_get_archive_list", payload)
        self.assertIn("抓取告警: 1", payload)
        fake_refresh.assert_awaited_once_with(command_args="with_live")


if __name__ == "__main__":
    unittest.main()
