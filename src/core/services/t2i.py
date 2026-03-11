import asyncio
import os
from io import BytesIO
from pathlib import Path
from typing import Any, Dict

import httpx
import jinja2
from PIL import Image, ImageDraw, ImageFont


class T2IService:
    def __init__(self):
        self.service_url = os.getenv("T2I_SERVICE_URL", "http://localhost:8999")
        self.method = os.getenv("T2I_METHOD", "t2i-service")
        self.timeout = max(self._env_float("T2I_TIMEOUT", 30.0), 1.0)
        self.retry_count = max(self._env_int("T2I_RETRIES", 2), 0)
        self.retry_delay = max(self._env_float("T2I_RETRY_DELAY", 0.2), 0.0)
        self.max_connections = max(self._env_int("T2I_MAX_CONNECTIONS", 20), 1)

        self.project_root = Path(__file__).resolve().parents[3]
        template_dir = Path(__file__).resolve().parents[2] / "templates"
        self.env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(template_dir)),
            autoescape=jinja2.select_autoescape(["html", "xml"]),
        )

        self._client = self._create_client()

        self.icon_base_url = self._resolve_path(
            os.getenv("ICON_BASE_URL", "exports/icons/skill")
        )
        self.assets_icon_url = self._resolve_path(
            os.getenv("ASSETS_ICON_URL", "assets/icons")
        )
        self.env.globals["config"] = {
            "ASSETS_ICON_URL": self.assets_icon_url,
            "ICON_BASE_URL": self.icon_base_url,
            "ICON_SECTION_URL": self._resolve_path(
                os.getenv("ICON_SECTION_URL", "exports/icons/section")
            ),
            "ICON_ITEM_URL": self._resolve_path(
                os.getenv("ICON_ITEM_URL", "exports/icons/item")
            ),
            "IMG_MUSIC_THUMBNAIL_URL": self._resolve_path(
                os.getenv("IMG_MUSIC_THUMBNAIL_URL", "exports/images/music/thumbnail")
            ),
            "IMG_COMIC_THUMBNAIL_URL": self._resolve_path(
                os.getenv("IMG_COMIC_THUMBNAIL_URL", "exports/images/comic_thumbnail")
            ),
            "IMG_CARD_FULL_URL": self._resolve_path(
                os.getenv("IMG_CARD_FULL_URL", "exports/images/card_full")
            ),
            "IMG_CARD_HALF_URL": self._resolve_path(
                os.getenv("IMG_CARD_HALF_URL", "exports/images/card_half")
            ),
            "IMG_CARD_MIDDLE_VERTICAL_URL": self._resolve_path(
                os.getenv(
                    "IMG_CARD_MIDDLE_VERTICAL_URL",
                    "exports/images/card_middle_vertical",
                )
            ),
            "IMG_DECK_FRAME_CHARA_URL": self._resolve_path(
                os.getenv("IMG_DECK_FRAME_CHARA_URL", "exports/images/deck_frame_chara")
            ),
            "IMG_PROF_CUSTOM_URL": self._resolve_path(
                os.getenv("IMG_PROF_CUSTOM_URL", "exports/images/prof_custom")
            ),
        }

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

    def _create_client(self) -> httpx.AsyncClient:
        limits = httpx.Limits(
            max_keepalive_connections=self.max_connections,
            max_connections=self.max_connections,
        )
        return httpx.AsyncClient(timeout=self.timeout, limits=limits)

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = self._create_client()
        return self._client

    def _is_url(self, path: str) -> bool:
        lower = path.lower()
        return lower.startswith(("http://", "https://", "file://", "data:"))

    def _resolve_path(self, path: str) -> str:
        value = str(path or "").strip()
        if not value:
            return value
        if self._is_url(value):
            return value
        candidate = Path(value)
        if candidate.is_absolute():
            return candidate.resolve().as_uri()
        return (self.project_root / value).resolve().as_uri()

    def _should_retry(self, error: Exception) -> bool:
        if isinstance(error, httpx.RequestError):
            return True
        if isinstance(error, httpx.HTTPStatusError):
            return error.response.status_code >= 500
        return False

    async def close(self):
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
        self._client = None

    async def generate_image(self, template_name: str, data: Dict[str, Any]) -> bytes:
        if self.method == "t2i-service":
            try:
                return await self._generate_via_service(template_name, data)
            except Exception as error:
                print(f"T2I Service failed: {error}. Falling back to Pillow.")
                return await self._generate_via_pillow(template_name, data)
        return await self._generate_via_pillow(template_name, data)

    async def _generate_via_service(
        self, template_name: str, data: Dict[str, Any]
    ) -> bytes:
        template = self.env.get_template(template_name)
        rendered_html = template.render(**data)
        payload = {"html": rendered_html}
        client = self._get_client()
        max_attempts = self.retry_count + 1

        for attempt in range(max_attempts):
            try:
                response = await client.post(
                    f"{self.service_url}/text2img/generate",
                    json=payload,
                )
                response.raise_for_status()
                return response.content
            except (httpx.RequestError, httpx.HTTPStatusError) as error:
                can_retry = attempt < max_attempts - 1 and self._should_retry(error)
                if not can_retry:
                    raise
                if self.retry_delay > 0:
                    await asyncio.sleep(self.retry_delay * (2**attempt))

        raise RuntimeError("T2I 请求失败")

    async def _generate_via_pillow(
        self, template_name: str, data: Dict[str, Any]
    ) -> bytes:
        text_content = ""

        def dump_data(obj, indent=0):
            text = ""
            for key, value in obj.items():
                if isinstance(value, dict):
                    text += " " * indent + f"{key}:\n" + dump_data(value, indent + 2)
                elif isinstance(value, list):
                    text += " " * indent + f"{key}:\n"
                    for item in value:
                        if isinstance(item, dict):
                            text += (
                                " " * (indent + 2)
                                + "- \n"
                                + dump_data(item, indent + 4)
                            )
                        else:
                            text += " " * (indent + 2) + f"- {item}\n"
                else:
                    text += " " * indent + f"{key}: {value}\n"
            return text

        if "text_fallback" in data:
            text_content = data["text_fallback"]
        else:
            text_content = dump_data(data)

        img_width = 800
        font_size = 20
        lines = text_content.split("\n")
        img_height = max(100, len(lines) * (font_size + 5) + 40)

        image = Image.new("RGB", (img_width, img_height), color=(255, 255, 255))
        draw = ImageDraw.Draw(image)

        try:
            font = ImageFont.truetype("arial.ttf", font_size)
        except IOError:
            font = ImageFont.load_default()

        draw.text((20, 20), text_content, fill=(0, 0, 0), font=font)

        buf = BytesIO()
        image.save(buf, format="PNG")
        return buf.getvalue()


_t2i_instance = None


def get_t2i_service() -> T2IService:
    global _t2i_instance
    if _t2i_instance is None:
        _t2i_instance = T2IService()
    return _t2i_instance


async def close_t2i_service():
    global _t2i_instance
    if _t2i_instance is None:
        return
    await _t2i_instance.close()
    _t2i_instance = None
