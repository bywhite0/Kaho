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


def _resp(url, status_code, payload):
    request = httpx.Request("POST", url)
    return httpx.Response(status_code, request=request, json=payload)


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

    async def test_refresh_archive_only_and_pick_latest_detail(self):
        config_path = self.root / "cache" / "game_api" / "config.json"
        self._write_config(config_path, token="token-ok")
        service = GameApiService(project_root=self.root)

        now = datetime.now(timezone.utc)
        live_open = (now - timedelta(minutes=10)).isoformat().replace("+00:00", "Z")
        live_close = (now + timedelta(minutes=10)).isoformat().replace("+00:00", "Z")
        latest_live_start = (now + timedelta(hours=2)).isoformat().replace("+00:00", "Z")
        latest_live_open = (now + timedelta(hours=1)).isoformat().replace("+00:00", "Z")
        trailer_start = (now + timedelta(hours=4)).isoformat().replace("+00:00", "Z")
        trailer_open = (now + timedelta(hours=3)).isoformat().replace("+00:00", "Z")

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
                                    "archives_id": "A1",
                                    "live_id": "L1",
                                    "live_type": 2,
                                    "name": "live-one",
                                    "open_time": live_open,
                                    "close_time": live_close,
                                    "live_start_time": live_open,
                                },
                                {
                                    "archives_id": "IGNORE",
                                    "live_id": "X1",
                                    "live_type": 1,
                                    "name": "not-with-live",
                                },
                                {
                                    "archives_id": "A3",
                                    "live_id": "L3",
                                    "live_type": 2,
                                    "name": "latest-live-archive",
                                    "open_time": latest_live_open,
                                    "live_start_time": latest_live_start,
                                },
                            ],
                            "trailer_archive_list": [
                                {
                                    "archives_id": "A2",
                                    "live_id": "L2",
                                    "live_type": 2,
                                    "name": "upcoming-two",
                                    "open_time": trailer_open,
                                    "live_start_time": trailer_start,
                                }
                            ],
                        },
                    ),
                ],
                "/archive/get_with_archive_data": [
                    lambda url, request_json, _headers: _resp(
                        url,
                        200,
                        {
                            "archives_id": request_json["archives_id"],
                            "title": "latest-detail",
                        },
                    )
                ],
                "/archive/get_archive_list": [
                    lambda url, _json, _headers: _resp(
                        url,
                        200,
                        {
                            "archive_list": [
                                {
                                    "archives_id": "A3",
                                    "live_id": "L3",
                                    "live_type": 2,
                                    "name": "latest-live-archive",
                                    "open_time": latest_live_open,
                                    "live_start_time": latest_live_start,
                                }
                            ]
                        },
                    )
                ],
            }
        )

        with patch("src.core.services.game_api.httpx.AsyncClient", lambda *args, **kwargs: fake_client):
            result = await service.refresh_with_live(command_args="with_live")

        source = result["source"]
        self.assertEqual(source["archive_get_home_count"], 3)
        self.assertEqual(source["archive_get_home_live_count"], 2)
        self.assertEqual(source["archive_get_home_trailer_count"], 1)
        self.assertEqual(result["latest_archive"]["archives_id"], "A3")
        self.assertEqual(result["latest_archive_detail"]["archives_id"], "A3")
        self.assertEqual(
            result["latest_archive_detail_meta"]["source"],
            "archive_get_with_archive_data",
        )
        self.assertNotIn("summary", result)

        detail_call = next(
            call for call in fake_client.calls if call["path"] == "/archive/get_with_archive_data"
        )
        self.assertEqual(detail_call["json"]["archives_id"], "A3")
        self.assertTrue(
            all(not call["path"].startswith("/withlive/") for call in fake_client.calls)
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
                    lambda url, _json, _headers: _resp(url, 200, {"session_token": "token-new"})
                ],
                "/archive/get_archive_list": [
                    lambda url, _json, _headers: _resp(url, 200, {"archive_list": []})
                ],
            }
        )

        with patch("src.core.services.game_api.httpx.AsyncClient", lambda *args, **kwargs: fake_client):
            result = await service.refresh_with_live(command_args="with_live")

        self.assertEqual(result["source"]["archive_get_home_count"], 0)
        self.assertEqual(result["latest_archive_detail_meta"]["source"], "none")
        saved = json.loads(config_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["credential"]["session_token"], "token-new")

        home_calls = [call for call in fake_client.calls if call["path"] == "/archive/get_home"]
        self.assertGreaterEqual(len(home_calls), 2)
        self.assertEqual(home_calls[-1]["headers"].get("authorization"), "Bearer token-new")

    async def test_detail_fail_ignore_old_cache_and_fallback_to_home(self):
        config_path = self.root / "cache" / "game_api" / "config.json"
        self._write_config(config_path, token="token-ok")
        self._write_old_snapshot(
            {
                "updated_at": "2026-03-20T10:00:00+08:00",
                "with_live_archive_home": [
                    {
                        "archives_id": "A1",
                        "live_id": "L1",
                        "live_type": 2,
                        "name": "old-live",
                    }
                ],
                "latest_archive": {
                    "archives_id": "A1",
                    "live_id": "L1",
                    "live_type": 2,
                    "name": "old-live",
                },
                "latest_archive_detail": {"archives_id": "A1", "from": "old-cache"},
            }
        )
        service = GameApiService(project_root=self.root)

        fake_client = _RouteClient(
            {
                "/archive/get_home": [
                    lambda url, _json, _headers: _resp(url, 200, {"ok": True}),
                    lambda url, _json, _headers: _resp(url, 500, {"message": "server error"}),
                ],
                "/archive/get_with_archive_data": [
                    lambda url, _json, _headers: _resp(url, 500, {"message": "error"})
                ],
                "/archive/get_archive_list": [
                    lambda url, _json, _headers: _resp(
                        url,
                        200,
                        {"archive_list": [{"archives_id": "A1", "live_id": "L1", "live_type": 2}]},
                    )
                ],
            }
        )

        with patch("src.core.services.game_api.httpx.AsyncClient", lambda *args, **kwargs: fake_client):
            result = await service.refresh_with_live(command_args="with_live")

        self.assertEqual(result["source"]["archive_get_home_count"], 0)
        self.assertEqual(result["latest_archive"]["archives_id"], "A1")
        self.assertEqual(result["latest_archive_detail"]["archives_id"], "A1")
        self.assertEqual(result["latest_archive_detail_meta"]["source"], "home")
        self.assertNotIn("from", result["latest_archive_detail"])

        backup_path = self.root / "cache" / "game_api" / "with_live.prev.json"
        self.assertTrue(backup_path.exists())
        backup = json.loads(backup_path.read_text(encoding="utf-8"))
        self.assertEqual(backup["updated_at"], "2026-03-20T10:00:00+08:00")

    async def test_detail_fail_fallback_to_home_when_latest_changed(self):
        config_path = self.root / "cache" / "game_api" / "config.json"
        self._write_config(config_path, token="token-ok")
        self._write_old_snapshot(
            {
                "updated_at": "2026-03-22T10:00:00+08:00",
                "latest_archive": {"archives_id": "A1", "live_id": "L1", "live_type": 2},
                "latest_archive_detail": {"archives_id": "A1", "from": "old-cache"},
            }
        )
        service = GameApiService(project_root=self.root)

        now = datetime.now(timezone.utc)
        start_time = (now + timedelta(hours=1)).isoformat().replace("+00:00", "Z")
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
                                    "archives_id": "A2",
                                    "live_id": "L2",
                                    "live_type": 2,
                                    "name": "new-live",
                                    "live_start_time": start_time,
                                }
                            ],
                            "trailer_archive_list": [
                                {
                                    "archives_id": "A9",
                                    "live_id": "L9",
                                    "live_type": 2,
                                    "name": "new-trailer",
                                    "live_start_time": (now + timedelta(hours=3))
                                    .isoformat()
                                    .replace("+00:00", "Z"),
                                }
                            ],
                        },
                    ),
                ],
                "/archive/get_with_archive_data": [
                    lambda url, _json, _headers: _resp(url, 500, {"message": "error"})
                ],
                "/archive/get_archive_list": [
                    lambda url, _json, _headers: _resp(url, 200, {"archive_list": []})
                ],
            }
        )

        with patch("src.core.services.game_api.httpx.AsyncClient", lambda *args, **kwargs: fake_client):
            result = await service.refresh_with_live(command_args="with_live")

        self.assertEqual(result["latest_archive_detail_meta"]["source"], "home")
        self.assertEqual(result["latest_archive"]["archives_id"], "A2")
        self.assertEqual(result["latest_archive_detail"]["archives_id"], "A2")
        self.assertIn(
            "archive_get_with_archive_data",
            " ".join(result["latest_archive_detail_meta"]["errors"]),
        )


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
                    "archive_get_home_count": 3,
                    "archive_get_home_live_count": 1,
                    "archive_get_home_trailer_count": 2,
                },
                "latest_archive": {
                    "archives_id": "A100",
                    "name": "最新场次",
                },
                "latest_archive_detail_meta": {
                    "source": "archive_get_with_archive_data",
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
        self.assertIn("home live_archive: 1", payload)
        self.assertIn("home trailer_archive: 2", payload)
        self.assertIn("最新 Archive ID: A100", payload)
        self.assertIn("详情来源: archive_get_with_archive_data", payload)
        self.assertNotIn("保留历史详情", payload)
        fake_refresh.assert_awaited_once_with(command_args="with_live")


if __name__ == "__main__":
    unittest.main()
