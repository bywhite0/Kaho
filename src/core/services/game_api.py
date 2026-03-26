import json
import os
import secrets
import string
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import httpx

try:
    from nonebot import logger
except ImportError:
    import logging

    logger = logging.getLogger("GameApiService")


ENV_GAME_API_BASE_URL = "GAME_API_BASE_URL"
ENV_GAME_API_HOST = "GAME_API_HOST"
ENV_GAME_API_X_API_KEY = "GAME_API_X_API_KEY"
ENV_GAME_API_UA_PREFIX = "GAME_API_UA_PREFIX"
ENV_GAME_API_DEVICE_TYPE = "GAME_API_DEVICE_TYPE"
ENV_GAME_API_USER_API_VERSION = "GAME_API_USER_API_VERSION"
DEFAULT_UA_PREFIX = "inspix-android"
DEFAULT_DEVICE_TYPE = "android"
DEFAULT_USER_API_VERSION = "1.0.0"
REQUIRED_CREDENTIAL_KEYS = (
    "res_version",
    "client_version",
    "device_specific_id",
    "player_id",
)


class GameApiServiceError(RuntimeError):
    pass


class GameApiRequestError(GameApiServiceError):
    def __init__(self, path: str, status_code: int, body: str):
        super().__init__(f"请求失败: {path} ({status_code})")
        self.path = path
        self.status_code = status_code
        self.body = body


class GameApiService:
    def __init__(self, project_root: Optional[Path] = None, timeout: float = 15.0):
        if project_root is None:
            self.project_root = Path(__file__).resolve().parents[3]
        else:
            self.project_root = Path(project_root)
        self.timeout = timeout
        (
            self.api_base,
            self.api_host,
            self.api_key,
            self.ua_prefix,
            self.device_type,
            self.user_api_version,
        ) = self._load_api_settings()

    def _read_env(self, key: str) -> str:
        config_key = key.lower()
        try:
            import nonebot

            config = nonebot.get_driver().config
            value = getattr(config, config_key, None)
            if value is not None:
                text = str(value).strip()
                if text:
                    return text
        except Exception:
            pass
        return os.getenv(key, "").strip()

    def _load_api_settings(self) -> Tuple[str, str, str, str, str, str]:
        api_base = self._read_env(ENV_GAME_API_BASE_URL).rstrip("/")
        if not api_base:
            raise GameApiServiceError(f"缺少环境变量: {ENV_GAME_API_BASE_URL}")

        api_host = self._read_env(ENV_GAME_API_HOST)
        if not api_host:
            api_host = urlparse(api_base).netloc
        if not api_host:
            raise GameApiServiceError(
                f"缺少环境变量: {ENV_GAME_API_HOST}，且无法从 {ENV_GAME_API_BASE_URL} 解析 host"
            )

        api_key = self._read_env(ENV_GAME_API_X_API_KEY)
        if not api_key:
            raise GameApiServiceError(f"缺少环境变量: {ENV_GAME_API_X_API_KEY}")

        ua_prefix = self._read_env(ENV_GAME_API_UA_PREFIX) or DEFAULT_UA_PREFIX
        device_type = self._read_env(ENV_GAME_API_DEVICE_TYPE) or DEFAULT_DEVICE_TYPE
        user_api_version = (
            self._read_env(ENV_GAME_API_USER_API_VERSION) or DEFAULT_USER_API_VERSION
        )
        return api_base, api_host, api_key, ua_prefix, device_type, user_api_version

    def resolve_config_path(self) -> Path:
        env_path = self._read_env("LINKURA_CONFIG_PATH")
        candidates: List[Path] = []

        if env_path:
            candidates.append(Path(os.path.expanduser(env_path)))

        candidates.append(self.project_root / "cache" / "game_api" / "config.json")
        candidates.append(self.project_root / "linkura-cli_config.json")

        home_dir = os.getenv("USERPROFILE", "").strip()
        if home_dir:
            candidates.append(Path(home_dir) / ".config" / "linkura-cli" / "config.json")

        for path in candidates:
            if path.exists() and path.is_file():
                return path.resolve()

        readable = "\n".join(f"- {p}" for p in candidates)
        raise GameApiServiceError(
            "未找到 linkura 配置文件，请检查以下路径:\n" + readable
        )

    def load_credential(self, config_path: Path) -> Dict[str, Any]:
        try:
            payload = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise GameApiServiceError(f"读取配置失败: {config_path} ({exc})") from exc

        credential = payload.get("credential") if isinstance(payload, dict) else None
        if not isinstance(credential, dict):
            raise GameApiServiceError(f"配置格式错误: {config_path} 缺少 credential 对象")

        missing = [
            key
            for key in REQUIRED_CREDENTIAL_KEYS
            if not str(credential.get(key) or "").strip()
        ]
        if missing:
            raise GameApiServiceError(f"配置字段缺失: {', '.join(missing)}")

        return credential

    def save_credential(self, config_path: Path, credential: Dict[str, Any]) -> None:
        if not config_path.parent.exists():
            config_path.parent.mkdir(parents=True, exist_ok=True)

        payload = {"credential": credential}
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        config_path.write_text(text + "\n", encoding="utf-8")

    def _gen_idempotency_key(self, length: int = 32) -> str:
        alphabet = string.ascii_letters + string.digits
        return "".join(secrets.choice(alphabet) for _ in range(length))

    def _build_headers(
        self,
        credential: Dict[str, Any],
        session_token: Optional[str] = None,
    ) -> Dict[str, str]:
        client_version = str(credential["client_version"])
        headers = {
            "x-res-version": str(credential["res_version"]),
            "x-client-version": client_version,
            "x-device-type": self.device_type,
            "inspix-user-api-version": self.user_api_version,
            "accept": "application/json",
            "x-api-key": self.api_key,
            "user-agent": f"{self.ua_prefix}/{client_version}",
            "host": self.api_host,
            "accept-encoding": "gzip, deflate",
            "x-device-specific-id": str(credential["device_specific_id"]),
            "x-idempotency-key": self._gen_idempotency_key(),
        }
        if session_token:
            headers["authorization"] = f"Bearer {session_token}"
        return headers

    async def _post_json(
        self,
        client: httpx.AsyncClient,
        path: str,
        payload: Dict[str, Any],
        credential: Dict[str, Any],
        session_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        response = await client.post(
            f"{self.api_base}{path}",
            json=payload,
            headers=self._build_headers(credential, session_token=session_token),
        )

        body = response.text
        if response.status_code >= 400:
            raise GameApiRequestError(path, response.status_code, body)

        try:
            data = response.json()
        except Exception as exc:
            raise GameApiServiceError(f"响应解析失败: {path}") from exc

        if not isinstance(data, dict):
            raise GameApiServiceError(f"响应格式错误: {path}")
        return data

    async def _is_session_valid(
        self,
        client: httpx.AsyncClient,
        credential: Dict[str, Any],
        session_token: str,
    ) -> bool:
        try:
            await self._post_json(
                client,
                "/archive/get_home",
                {},
                credential,
                session_token=session_token,
            )
            return True
        except GameApiRequestError as exc:
            if exc.status_code in (401, 403):
                return False
            raise

    async def _login_refresh_token(
        self,
        client: httpx.AsyncClient,
        credential: Dict[str, Any],
    ) -> str:
        payload = {
            "player_id": str(credential["player_id"]),
            "device_specific_id": str(credential["device_specific_id"]),
            "version": 1,
        }
        data = await self._post_json(client, "/user/login", payload, credential)
        session_token = str(data.get("session_token") or "").strip()
        if not session_token:
            raise GameApiServiceError("刷新会话失败: 响应缺少 session_token")
        return session_token

    def _parse_time(self, value: Any) -> Optional[datetime]:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        normalized = text.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

    def _pick_first_time(self, item: Dict[str, Any], keys: Tuple[str, ...]) -> Optional[datetime]:
        for key in keys:
            dt = self._parse_time(item.get(key))
            if dt is not None:
                return dt
        return None

    def _extract_dict_items(self, values: Any) -> List[Dict[str, Any]]:
        if not isinstance(values, list):
            return []
        result: List[Dict[str, Any]] = []
        for item in values:
            if isinstance(item, dict):
                result.append(dict(item))
        return result

    def _resolve_live_type(self, item: Dict[str, Any]) -> int:
        live_type = item.get("live_type")
        if isinstance(live_type, int):
            return live_type
        try:
            return int(str(live_type).strip())
        except (TypeError, ValueError):
            return 0

    def _is_enterable_by_open_time(self, item: Dict[str, Any], now: datetime) -> bool:
        open_time = self._pick_first_time(item, ("open_time",))
        if open_time is None:
            return False
        return now >= open_time

    def _extract_with_live_items(self, values: Any) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []
        if not isinstance(values, list):
            return result
        for item in values:
            if not isinstance(item, dict):
                continue
            live_type = self._resolve_live_type(item)
            if live_type != 2:
                continue
            result.append(dict(item))
        return result

    def _extract_home_trailer_groups(
        self,
        home_data: Dict[str, Any],
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
        live_archive_items = self._extract_dict_items(home_data.get("live_archive_list"))
        trailer_archive_items = self._extract_dict_items(home_data.get("trailer_archive_list"))
        return (
            live_archive_items,
            trailer_archive_items,
            [*live_archive_items, *trailer_archive_items],
        )

    def _extract_with_live_home_groups(
        self,
        home_data: Dict[str, Any],
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
        live_archive_items = self._extract_with_live_items(home_data.get("live_archive_list"))
        trailer_archive_items = self._extract_with_live_items(home_data.get("trailer_archive_list"))
        return (
            live_archive_items,
            trailer_archive_items,
            [*live_archive_items, *trailer_archive_items],
        )

    def _pick_latest_sort_time(self, item: Dict[str, Any]) -> Optional[datetime]:
        return self._parse_time(item.get("live_start_time"))

    def _build_enter_detail_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "live_id": str(item.get("live_id") or "").strip(),
            "live_type": self._resolve_live_type(item),
            "name": str(item.get("name") or "").strip(),
            "status": "skipped",
            "detail": None,
            "detail_source": "none",
            "errors": [],
        }

    async def _fetch_enter_detail(
        self,
        client: httpx.AsyncClient,
        credential: Dict[str, Any],
        session_token: str,
        item: Dict[str, Any],
    ) -> Dict[str, Any]:
        result = self._build_enter_detail_item(item)
        live_id = str(result["live_id"])
        live_type = int(result["live_type"])
        errors: List[str] = result["errors"]

        if not live_id:
            errors.append("missing_live_id")
            return result

        if live_type == 2:
            try:
                detail = await self._post_json(
                    client,
                    "/withlive/enter",
                    {"live_id": live_id},
                    credential,
                    session_token=session_token,
                )
                result["detail"] = detail
                result["detail_source"] = "withlive_enter"
                result["status"] = "ok"
            except Exception as exc:
                errors.append(f"withlive_enter:{exc}")
                result["status"] = "error"
            return result

        if live_type == 1:
            try:
                await self._post_json(
                    client,
                    "/feslive/lobby",
                    {"live_id": live_id},
                    credential,
                    session_token=session_token,
                )
            except Exception as exc:
                errors.append(f"feslive_lobby:{exc}")

            try:
                detail = await self._post_json(
                    client,
                    "/feslive/enter",
                    {"live_id": live_id},
                    credential,
                    session_token=session_token,
                )
                result["detail"] = detail
                result["detail_source"] = "feslive_enter"
                result["status"] = "ok"
            except Exception as exc:
                errors.append(f"feslive_enter:{exc}")
                result["status"] = "error"
            return result

        errors.append(f"unsupported_live_type:{live_type}")
        return result

    def _archive_identity(self, item: Dict[str, Any]) -> str:
        archives_id = str(item.get("archives_id") or "").strip()
        if archives_id:
            return archives_id
        return str(item.get("live_id") or "").strip()

    def _pick_latest_archive_item(
        self,
        items: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        if not items:
            return None

        latest_item: Optional[Dict[str, Any]] = None
        latest_dt: Optional[datetime] = None

        for item in items:
            current_dt = self._pick_latest_sort_time(item)
            if latest_item is None:
                latest_item = item
                latest_dt = current_dt
                continue
            if current_dt is not None:
                if latest_dt is None or current_dt > latest_dt:
                    latest_item = item
                    latest_dt = current_dt
                continue
            if latest_dt is None:
                # 全部无时间时，回退到列表中的最后一条。
                latest_item = item

        return dict(latest_item) if latest_item is not None else None

    async def _fetch_archive_detail(
        self,
        client: httpx.AsyncClient,
        credential: Dict[str, Any],
        session_token: str,
        item: Dict[str, Any],
    ) -> Tuple[Optional[Dict[str, Any]], str, List[str]]:
        errors: List[str] = []
        archives_id = self._archive_identity(item)
        if not archives_id:
            errors.append("archive_get_with_archive_data:missing_archives_id")
            return None, "", errors

        try:
            detail = await self._post_json(
                client,
                "/archive/get_with_archive_data",
                {"archives_id": archives_id},
                credential,
                session_token=session_token,
            )
        except Exception as exc:
            errors.append(f"archive_get_with_archive_data:{exc}")
            return None, "", errors

        if not detail:
            errors.append("archive_get_with_archive_data:empty")
            return None, "", errors
        return detail, "archive_get_with_archive_data", errors

    async def _fetch_latest_archive_from_archive_list(
        self,
        client: httpx.AsyncClient,
        credential: Dict[str, Any],
        session_token: str,
        limit: int = 1,
        live_type: Optional[int] = 2,
        error_key: str = "archive_get_archive_list",
    ) -> Tuple[Optional[Dict[str, Any]], List[str]]:
        errors: List[str] = []
        payload = {
            "order": "desc",
            "sort": "live_start_time",
            "limit": limit,
            "offset": 0,
            "characters": [],
        }
        if live_type is not None:
            payload["live_type"] = live_type
        try:
            data = await self._post_json(
                client,
                "/archive/get_archive_list",
                payload,
                credential,
                session_token=session_token,
            )
        except Exception as exc:
            errors.append(f"{error_key}:{exc}")
            return None, errors

        archive_list = data.get("archive_list")
        if not isinstance(archive_list, list) or not archive_list:
            errors.append(f"{error_key}:empty")
            return None, errors

        first_item = archive_list[0]
        if not isinstance(first_item, dict):
            errors.append(f"{error_key}:invalid_item")
            return None, errors
        return dict(first_item), errors

    def _cache_file_path(self) -> Path:
        return self.project_root / "cache" / "game_api" / "with_live.json"

    def _cache_backup_path(self) -> Path:
        return self.project_root / "cache" / "game_api" / "with_live.prev.json"

    def _read_snapshot(self, path: Path) -> Dict[str, Any]:
        if not path.exists() or not path.is_file():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning(f"读取旧缓存失败，已忽略: {path} error={exc}")
            return {}
        if isinstance(payload, dict):
            return payload
        return {}

    def _write_json_atomic(self, path: Path, payload: Dict[str, Any]) -> None:
        if not path.parent.exists():
            path.parent.mkdir(parents=True, exist_ok=True)

        content = json.dumps(payload, ensure_ascii=False, indent=2)
        fd, temp_path = tempfile.mkstemp(
            dir=str(path.parent),
            prefix="with_live_",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
                f.write("\n")
            os.replace(temp_path, path)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    async def refresh_with_live(self, command_args: str = "with_live") -> Dict[str, Any]:
        cache_path = self._cache_file_path()
        old_snapshot = self._read_snapshot(cache_path)

        config_path = self.resolve_config_path()
        credential = self.load_credential(config_path)

        fetch_errors: List[str] = []
        home_trailer_live_list: List[Dict[str, Any]] = []
        home_trailer_trailer_list: List[Dict[str, Any]] = []
        home_trailer_list: List[Dict[str, Any]] = []
        home_trailer_enterable_list: List[Dict[str, Any]] = []
        home_trailer_enter_details: List[Dict[str, Any]] = []
        with_live_home_live_list: List[Dict[str, Any]] = []
        with_live_home_trailer_list: List[Dict[str, Any]] = []
        with_live_home_list: List[Dict[str, Any]] = []
        home_fetched = False
        latest_from_archive_list: Optional[Dict[str, Any]] = None
        latest_archive_any: Optional[Dict[str, Any]] = None
        latest_archive_any_meta: Dict[str, Any] = {
            "source": "none",
            "errors": [],
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            session_token = str(credential.get("session_token") or "").strip()
            if session_token:
                is_valid = await self._is_session_valid(client, credential, session_token)
            else:
                is_valid = False

            if not is_valid:
                session_token = await self._login_refresh_token(client, credential)
                credential["session_token"] = session_token
                self.save_credential(config_path, credential)

            try:
                home_data = await self._post_json(
                    client,
                    "/archive/get_home",
                    {},
                    credential,
                    session_token=session_token,
                )
                (
                    home_trailer_live_list,
                    home_trailer_trailer_list,
                    home_trailer_list,
                ) = self._extract_home_trailer_groups(home_data)
                (
                    with_live_home_live_list,
                    with_live_home_trailer_list,
                    with_live_home_list,
                ) = self._extract_with_live_home_groups(home_data)
                now = datetime.now(timezone.utc)
                home_trailer_enterable_list = [
                    item
                    for item in home_trailer_list
                    if self._is_enterable_by_open_time(item, now)
                ]
                for trailer in home_trailer_enterable_list:
                    detail_item = await self._fetch_enter_detail(
                        client,
                        credential,
                        session_token,
                        trailer,
                    )
                    home_trailer_enter_details.append(detail_item)
                    for error in detail_item.get("errors") or []:
                        fetch_errors.append(
                            f"enter_detail:{detail_item.get('live_id') or '-'}:{error}"
                        )
                home_fetched = True
            except Exception as exc:
                fetch_errors.append(f"archive_get_home:{exc}")

            latest_candidates = with_live_home_live_list

            latest_from_archive_list, archive_list_errors = (
                await self._fetch_latest_archive_from_archive_list(
                    client,
                    credential,
                    session_token,
                )
            )
            fetch_errors.extend(archive_list_errors)

            latest_archive_any_from_list, latest_archive_any_errors = (
                await self._fetch_latest_archive_from_archive_list(
                    client,
                    credential,
                    session_token,
                    limit=4,
                    live_type=None,
                    error_key="archive_get_archive_list_any",
                )
            )
            fetch_errors.extend(latest_archive_any_errors)
            if isinstance(latest_archive_any_from_list, dict):
                latest_archive_any = dict(latest_archive_any_from_list)
                latest_archive_any_meta = {
                    "source": "archive_get_archive_list",
                    "errors": latest_archive_any_errors,
                }

            latest_item = (
                dict(latest_from_archive_list)
                if isinstance(latest_from_archive_list, dict)
                else self._pick_latest_archive_item(latest_candidates)
            )
            if latest_archive_any is None and isinstance(latest_item, dict):
                latest_archive_any = dict(latest_item)
                latest_archive_any_meta = {
                    "source": "latest_archive",
                    "errors": latest_archive_any_errors,
                }
            latest_detail: Optional[Dict[str, Any]] = None
            latest_detail_meta = {
                "source": "none",
                "stale": True,
                "errors": [],
            }

            if latest_item is not None:
                detail, source, errors = await self._fetch_archive_detail(
                    client,
                    credential,
                    session_token,
                    latest_item,
                )
                if detail is None:
                    detail = dict(latest_item)
                    source = "home"
                latest_detail = detail
                latest_detail_meta = {
                    "source": source,
                    "stale": source != "archive_get_with_archive_data",
                    "errors": errors,
                }

        home_with_count = sum(
            1 for item in home_trailer_list if self._resolve_live_type(item) == 2
        )
        home_fes_count = sum(
            1 for item in home_trailer_list if self._resolve_live_type(item) == 1
        )
        enterable_with_count = sum(
            1
            for item in home_trailer_enterable_list
            if self._resolve_live_type(item) == 2
        )
        enterable_fes_count = sum(
            1
            for item in home_trailer_enterable_list
            if self._resolve_live_type(item) == 1
        )
        enter_detail_success_count = sum(
            1 for item in home_trailer_enter_details if item.get("status") == "ok"
        )
        enter_detail_failed_count = sum(
            1 for item in home_trailer_enter_details if item.get("status") == "error"
        )

        updated_at = datetime.now().astimezone().isoformat(timespec="seconds")
        snapshot = {
            "updated_at": updated_at,
            "previous_updated_at": old_snapshot.get("updated_at"),
            "source": {
                "config_path": str(config_path),
                "command_args": command_args,
                "fetch_errors": fetch_errors,
                "archive_get_home_count": len(with_live_home_list),
                "archive_get_home_live_count": len(with_live_home_live_list),
                "archive_get_home_trailer_count": len(with_live_home_trailer_list),
                "archive_get_home_total_count": len(home_trailer_list),
                "archive_get_home_with_count": home_with_count,
                "archive_get_home_fes_count": home_fes_count,
                "enterable_total_count": len(home_trailer_enterable_list),
                "enterable_with_count": enterable_with_count,
                "enterable_fes_count": enterable_fes_count,
                "enter_detail_success_count": enter_detail_success_count,
                "enter_detail_failed_count": enter_detail_failed_count,
                "home_fetched": home_fetched,
            },
            "home_trailer_live_list": home_trailer_live_list,
            "home_trailer_trailer_list": home_trailer_trailer_list,
            "home_trailer_list": home_trailer_list,
            "home_trailer_enterable_list": home_trailer_enterable_list,
            "home_trailer_enter_details": home_trailer_enter_details,
            "with_live_archive_live_home": with_live_home_live_list,
            "with_live_archive_trailer_home": with_live_home_trailer_list,
            "with_live_archive_home": with_live_home_list,
            "latest_archive": latest_item,
            "latest_archive_detail": latest_detail,
            "latest_archive_detail_meta": latest_detail_meta,
            "latest_archive_any": latest_archive_any,
            "latest_archive_any_meta": latest_archive_any_meta,
        }

        if old_snapshot:
            self._write_json_atomic(self._cache_backup_path(), old_snapshot)

        self._write_json_atomic(cache_path, snapshot)
        snapshot["cache_path"] = str(cache_path)
        snapshot["backup_cache_path"] = str(self._cache_backup_path())
        return snapshot


_service: Optional[GameApiService] = None


def get_game_api_service() -> GameApiService:
    global _service
    if _service is None:
        _service = GameApiService()
    return _service


async def refresh_with_live_data(command_args: str = "with_live") -> Dict[str, Any]:
    return await get_game_api_service().refresh_with_live(command_args=command_args)
