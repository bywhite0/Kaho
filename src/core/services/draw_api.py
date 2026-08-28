import os

import httpx

try:
    from nonebot import logger
except ImportError:
    import logging

    logger = logging.getLogger("DrawApiService")


class DrawApiError(Exception):
    """绘图服务调用失败。"""


class DrawApiService:
    """外部绘图服务（Kozue）client，只负责请求、校验与错误归一。"""

    def __init__(self):
        self.base_url = os.getenv("DRAW_API_BASE_URL", "").strip().rstrip("/")
        self.timeout = max(self._env_float("DRAW_API_TIMEOUT", 15.0), 1.0)
        self.max_connections = max(self._env_int("DRAW_API_MAX_CONNECTIONS", 10), 1)
        self._client = None

    @property
    def enabled(self) -> bool:
        return bool(self.base_url)

    def _env_float(self, key: str, default: float) -> float:
        try:
            return float(os.getenv(key, str(default)))
        except (TypeError, ValueError):
            return default

    def _env_int(self, key: str, default: int) -> int:
        try:
            return int(os.getenv(key, str(default)))
        except (TypeError, ValueError):
            return default

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            limits = httpx.Limits(
                max_keepalive_connections=self.max_connections,
                max_connections=self.max_connections,
            )
            self._client = httpx.AsyncClient(timeout=self.timeout, limits=limits)
        return self._client

    async def close(self):
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
        self._client = None

    async def check_health(self) -> bool:
        """访问绘图服务 /health，任何异常均视为不可用。"""
        if not self.enabled:
            return False
        try:
            response = await self._get_client().get(f"{self.base_url}/health")
        except httpx.HTTPError:
            return False
        return response.status_code == 200

    async def render(self, route: str, payload: dict) -> bytes:
        """POST 结构化 payload，返回图片字节；非图片或失败抛 DrawApiError。"""
        if not self.enabled:
            raise DrawApiError("未配置 DRAW_API_BASE_URL")
        try:
            response = await self._get_client().post(
                f"{self.base_url}{route}", json=payload
            )
        except httpx.HTTPError as error:
            raise DrawApiError(f"绘图服务请求失败: {error}") from error
        if response.status_code != 200:
            detail = response.text[:200]
            raise DrawApiError(f"绘图服务返回 {response.status_code}: {detail}")
        content_type = response.headers.get("content-type", "")
        if not content_type.startswith("image/"):
            raise DrawApiError(f"绘图服务返回非图片内容: {content_type or '未知类型'}")
        return response.content


_draw_api_instance = None


def get_draw_api_service() -> DrawApiService:
    global _draw_api_instance
    if _draw_api_instance is None:
        _draw_api_instance = DrawApiService()
    return _draw_api_instance


async def close_draw_api_service():
    global _draw_api_instance
    if _draw_api_instance is None:
        return
    await _draw_api_instance.close()
    _draw_api_instance = None
