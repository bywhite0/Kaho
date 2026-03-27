import asyncio
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import httpx
from PIL import Image, ImageColor, ImageDraw, ImageFont

from src.core.services.game_api import refresh_with_live_data

try:
    from nonebot import logger
except ImportError:
    import logging

    logger = logging.getLogger("WithLiveImageService")


class WithLiveImageService:
    def __init__(self, project_root: Optional[Path] = None, timeout: float = 15.0):
        if project_root is None:
            self.project_root = Path(__file__).resolve().parents[3]
        else:
            self.project_root = Path(project_root)
        self.timeout = timeout
        self.cache_path = self.project_root / "cache" / "game_api" / "with_live.json"
        self.cover_cache_dir = (
            self.project_root / "cache" / "game_api" / "with_live_cover"
        )
        self.icon_path = self.project_root / "assets" / "icons" / "icon_livenow.png"

    async def build_current_live_image(self, auto_refresh_on_miss: bool = True) -> bytes:
        _, archives = await self._load_snapshot_and_archives(
            auto_refresh_on_miss=auto_refresh_on_miss
        )

        if not archives:
            raise RuntimeError("未找到 with_live 数据，请先执行 /update with_live")

        items = self._normalize_archives(archives)
        if not items:
            raise RuntimeError("with_live 数据为空，请先执行 /update with_live")

        unique_urls = list(dict.fromkeys(item["thumb_url"] for item in items))
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            unique_thumbnails = await asyncio.gather(
                *[self._fetch_image(client, thumb_url) for thumb_url in unique_urls]
            )

        thumbnail_map = {
            thumb_url: thumb_image
            for thumb_url, thumb_image in zip(unique_urls, unique_thumbnails)
        }
        thumbnails = [
            thumbnail_map[item["thumb_url"]]
            if item["thumb_url"] in thumbnail_map
            else self._create_placeholder_image()
            for item in items
        ]

        renderer = _WithLiveImageRenderer(icon_path=self.icon_path)
        return renderer.render(items, thumbnails)

    async def build_live_detail_image(
        self, index: int, auto_refresh_on_miss: bool = True
    ) -> bytes:
        if index <= 0:
            raise ValueError("序号必须为正整数")

        snapshot, archives = await self._load_snapshot_and_archives(
            auto_refresh_on_miss=auto_refresh_on_miss
        )
        if not archives:
            raise RuntimeError("未找到 with_live 数据，请先执行 /update with_live")

        total = len(archives)
        if index > total:
            raise ValueError(f"序号超出范围，可选范围: 1-{total}")

        archive = archives[index - 1]
        detail_item = self._build_detail_item(snapshot, archive)
        if not detail_item.get("title"):
            raise RuntimeError("直播数据缺少标题，无法生成详情图")

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            thumbnail = await self._fetch_image(client, detail_item["thumb_url"])

        renderer = _WithLiveImageRenderer(icon_path=self.icon_path)
        return renderer.render_detail(detail_item, thumbnail)

    async def _load_snapshot_and_archives(
        self, auto_refresh_on_miss: bool = True
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        snapshot = self._read_snapshot()
        archives = self._extract_archives(snapshot)

        if not archives and auto_refresh_on_miss:
            await refresh_with_live_data(command_args="with_live")
            snapshot = self._read_snapshot()
            archives = self._extract_archives(snapshot)

        return snapshot, archives

    def _build_detail_item(
        self,
        snapshot: Dict[str, Any],
        archive: Dict[str, Any],
    ) -> Dict[str, str]:
        return {
            "title": str(archive.get("name") or "").strip(),
            "time": self._format_time(archive),
            "thumb_url": str(archive.get("thumbnail_image_url") or "").strip(),
            "description": self._extract_detail_description(snapshot, archive),
        }

    def _extract_detail_description(
        self,
        snapshot: Dict[str, Any],
        archive: Dict[str, Any],
    ) -> str:
        archive_desc = str(archive.get("description") or "").strip()
        if archive_desc:
            return archive_desc

        target_live_id = str(archive.get("live_id") or "").strip()
        enter_details = self._to_dict_list(snapshot.get("home_trailer_enter_details"))
        for enter_item in enter_details:
            if target_live_id and str(enter_item.get("live_id") or "").strip() != target_live_id:
                continue
            detail = enter_item.get("detail")
            if not isinstance(detail, dict):
                continue
            detail_desc = str(detail.get("description") or "").strip()
            if detail_desc:
                return detail_desc

        for enter_item in enter_details:
            detail = enter_item.get("detail")
            if not isinstance(detail, dict):
                continue
            detail_desc = str(detail.get("description") or "").strip()
            if detail_desc:
                return detail_desc

        return "暂无直播描述"

    def _read_snapshot(self) -> Dict[str, Any]:
        if not self.cache_path.exists() or not self.cache_path.is_file():
            return {}

        try:
            payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning(f"读取 with_live 缓存失败: {self.cache_path} error={exc}")
            return {}

        if isinstance(payload, dict):
            return payload
        return {}

    def _extract_archives(self, snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
        trailer_items = self._to_dict_list(snapshot.get("home_trailer_list"))
        if trailer_items:
            return trailer_items

        home_items = self._to_dict_list(snapshot.get("with_live_archive_home"))
        if home_items:
            return home_items

        live_items = self._to_dict_list(snapshot.get("with_live_archive_live_home"))
        with_live_trailer_items = self._to_dict_list(
            snapshot.get("with_live_archive_trailer_home")
        )
        return [*live_items, *with_live_trailer_items]

    def _to_dict_list(self, values: Any) -> List[Dict[str, Any]]:
        if not isinstance(values, list):
            return []
        result: List[Dict[str, Any]] = []
        for item in values:
            if isinstance(item, dict):
                result.append(dict(item))
        return result

    def _normalize_archives(self, archives: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        result: List[Dict[str, str]] = []
        for item in archives:
            title = str(item.get("name") or "").strip()
            if not title:
                continue
            live_status = self._detect_status(item)
            result.append(
                {
                    "status": live_status,
                    "time": self._format_time(item),
                    "thumb_url": str(item.get("thumbnail_image_url") or "").strip(),
                    "title": title,
                }
            )
        return result

    def _format_time(self, item: Dict[str, Any]) -> str:
        dt_live_start = self._parse_time(item.get("live_start_time"))
        if dt_live_start is None:
            return "时间未定"
        now = datetime.now(timezone.utc)
        close_time = self._parse_time(
            item.get("close_time")
            or item.get("live_end_time")
            or item.get("end_time")
        )
        if now >= dt_live_start and (close_time is None or now < close_time):
            return dt_live_start.astimezone().strftime("%H:%M 起直播中")
        return dt_live_start.astimezone().strftime("预计 %Y/%m/%d %H:%M 开始")

    def _detect_status(self, item: Dict[str, Any]) -> str:
        now = datetime.now(timezone.utc)
        open_time = self._parse_time(item.get("open_time"))
        close_time = self._parse_time(
            item.get("close_time")
            or item.get("live_end_time")
            or item.get("end_time")
        )
        start_time = self._parse_time(item.get("live_start_time"))

        if close_time is not None and now >= close_time:
            return "Closed"
        if open_time is not None and now >= open_time:
            return "Upcoming"
        if start_time is not None and now >= start_time:
            return "Live Now!!"
        return "Upcoming"

    def _parse_time(self, value: Any) -> Optional[datetime]:
        if value is None:
            return None
        text = str(value).strip()
        if not text or text.startswith("2999"):
            return None
        normalized = text.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

    async def _fetch_image(self, client: httpx.AsyncClient, url: str) -> Image.Image:
        if not url:
            return self._create_placeholder_image()

        cache_path = self._build_cover_cache_path(url)
        cached_image = self._load_cached_image(cache_path)
        if cached_image is not None:
            return cached_image

        try:
            resp = await client.get(url, timeout=self.timeout)
            resp.raise_for_status()
            with Image.open(BytesIO(resp.content)) as loaded_image:
                image = loaded_image.convert("RGBA")
            try:
                self._save_cached_image(cache_path, resp.content)
            except Exception as cache_exc:
                logger.warning(f"写入直播封面缓存失败: {cache_path} error={cache_exc}")
            return image
        except Exception as exc:
            logger.warning(f"下载缩略图失败，使用占位图: {url} error={exc}")
            return self._create_placeholder_image()

    def _build_cover_cache_path(self, url: str) -> Path:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return self.cover_cache_dir / f"{digest}{self._guess_cache_suffix(url)}"

    def _guess_cache_suffix(self, url: str) -> str:
        suffix = Path(urlparse(url).path).suffix.lower()
        if suffix in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}:
            return suffix
        return ".img"

    def _load_cached_image(self, cache_path: Path) -> Optional[Image.Image]:
        if not cache_path.exists() or not cache_path.is_file():
            return None

        try:
            with Image.open(cache_path) as cached_image:
                return cached_image.convert("RGBA")
        except Exception as exc:
            logger.warning(f"读取直播封面缓存失败，回源重试: {cache_path} error={exc}")
            try:
                cache_path.unlink()
            except OSError:
                pass
            return None

    def _save_cached_image(self, cache_path: Path, content: bytes) -> None:
        if not cache_path.parent.exists():
            cache_path.parent.mkdir(parents=True, exist_ok=True)

        fd, temp_path = tempfile.mkstemp(
            dir=str(cache_path.parent),
            prefix="with_live_cover_",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(content)
            os.replace(temp_path, cache_path)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def _create_placeholder_image(self) -> Image.Image:
        image = Image.new("RGBA", (960, 540), "#E0E0E0")
        draw = ImageDraw.Draw(image)
        draw.text((350, 250), "Image Missing", fill="#999999")
        return image


class _WithLiveImageRenderer:
    WIDTH = 1080
    HEADER_H = 100
    RECT_W = 1480
    RECT_OFFSET_X = -200

    C_START = "#65defc"
    C_END = "#938aff"
    C_TEXT_MAIN = "#4b4b4b"
    C_TEXT_META = "#6b7280"

    if hasattr(Image, "Resampling"):
        RESAMPLE = Image.Resampling.LANCZOS
    else:
        RESAMPLE = Image.LANCZOS

    def __init__(self, icon_path: Path):
        self.font_title = self._load_font_safe(42)
        self.font_status = self._load_font_safe(44, weight="Bold")
        self.font_header = self._load_cn_font_safe(44, weight="Bold")
        self.font_meta = self._load_cn_font_safe(30, weight="Bold")
        self.font_desc = self._load_font_safe(32)
        self.icon_status_img = self._load_icon(icon_path)

    def render(self, items: List[Dict[str, str]], thumbnails: List[Image.Image]) -> bytes:
        max_height = max(2000, len(items) * 1200)
        canvas = Image.new("RGB", (self.WIDTH, max_height), "#FFFFFF")
        self._render_header(canvas)

        current_y = self.HEADER_H + 20
        for item, thumb in zip(items, thumbnails):
            current_y = self._render_item(canvas, current_y, item, thumb)

        final_image = canvas.crop((0, 0, self.WIDTH, current_y))
        buf = BytesIO()
        final_image.save(buf, format="PNG")
        return buf.getvalue()

    def render_detail(self, item: Dict[str, str], thumbnail: Image.Image) -> bytes:
        max_height = 2600
        canvas = Image.new("RGB", (self.WIDTH, max_height), "#FFFFFF")
        self._render_header(canvas)
        draw = ImageDraw.Draw(canvas)

        current_y = self.HEADER_H + 24
        thumb_resized = self._resize_thumbnail(thumbnail)
        canvas.paste(thumb_resized, (0, current_y), thumb_resized)

        current_y += thumb_resized.height + 36
        draw.text(
            (40, current_y),
            item["title"],
            fill=self.C_TEXT_MAIN,
            font=self.font_title,
        )

        title_height = self._measure_text_height(draw, item["title"], self.font_title)
        current_y += title_height + 20
        draw.text(
            (40, current_y),
            item["time"],
            fill=self.C_TEXT_META,
            font=self.font_meta,
        )

        time_height = self._measure_text_height(draw, item["time"], self.font_meta)
        current_y += time_height + 24
        current_y = self._draw_wrapped_text(
            draw=draw,
            x=40,
            y=current_y,
            text=item["description"],
            font=self.font_desc,
            color=self.C_TEXT_MAIN,
            max_width=self.WIDTH - 80,
            line_spacing=12,
        )

        final_height = min(max_height, max(current_y + 40, self.HEADER_H + 300))
        final_image = canvas.crop((0, 0, self.WIDTH, final_height))
        buf = BytesIO()
        final_image.save(buf, format="PNG")
        return buf.getvalue()

    def _load_icon(self, icon_path: Path) -> Optional[Image.Image]:
        if not icon_path.exists() or not icon_path.is_file():
            logger.warning(f"未找到直播状态图标: {icon_path}")
            return None
        try:
            return Image.open(icon_path).convert("RGBA")
        except Exception as exc:
            logger.warning(f"读取直播状态图标失败: {icon_path} error={exc}")
            return None

    def _render_header(self, canvas: Image.Image) -> None:
        full_rect = self._create_gradient_texture(
            self.RECT_W, self.HEADER_H, self.C_START, self.C_END
        )
        overlay = Image.new("RGBA", full_rect.size, (0, 0, 0, 0))
        pattern_draw = ImageDraw.Draw(overlay)
        pattern_draw.text(
            (224, 16),
            "学园偶像连结",
            fill="#FFFFFF",
            font=self.font_header,
        )
        self._draw_svg_polygons(pattern_draw, 1080, 0, self.HEADER_H)
        full_rect = Image.alpha_composite(full_rect, overlay)
        canvas.paste(full_rect, (self.RECT_OFFSET_X, 0), full_rect)

    def _render_item(
        self,
        canvas: Image.Image,
        y_pos: int,
        item: Dict[str, str],
        thumb_img: Image.Image,
    ) -> int:
        draw = ImageDraw.Draw(canvas)
        status_x = 24
        status_y = y_pos

        if self.icon_status_img is not None:
            icon_y = status_y + 4
            canvas.paste(self.icon_status_img, (status_x, icon_y), self.icon_status_img)
            status_x += self.icon_status_img.width + 12
        else:
            fallback_text = "•))  "
            draw.text(
                (status_x, status_y),
                fallback_text,
                fill=self.C_TEXT_META,
                font=self.font_status,
            )
            status_x += int(draw.textlength(fallback_text, font=self.font_status))

        draw.text(
            (status_x, status_y),
            item["status"],
            fill=self.C_TEXT_META,
            font=self.font_status,
        )

        time_text = item["time"]
        time_w = self._measure_text_width(draw, time_text, self.font_meta)
        draw.text(
            (self.WIDTH - time_w - 40, y_pos + 13),
            time_text,
            fill=self.C_TEXT_META,
            font=self.font_meta,
        )

        y_pos += 90

        thumb_resized = self._resize_thumbnail(thumb_img)
        canvas.paste(thumb_resized, (0, y_pos), thumb_resized)

        y_pos += thumb_resized.height + 35
        draw.text((40, y_pos), item["title"], fill=self.C_TEXT_MAIN, font=self.font_title)
        return y_pos + 120

    def _resize_thumbnail(self, thumb_img: Image.Image) -> Image.Image:
        if thumb_img.mode != "RGBA":
            thumb_img = thumb_img.convert("RGBA")
        width, height = thumb_img.size
        if width <= 0 or height <= 0:
            return Image.new("RGBA", (self.WIDTH, 540), "#E0E0E0")
        target_h = max(int(self.WIDTH * (height / width)), 1)
        return thumb_img.resize((self.WIDTH, target_h), self.RESAMPLE)

    def _measure_text_width(
        self, draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont
    ) -> int:
        try:
            box = draw.textbbox((0, 0), text, font=font)
            return int(box[2] - box[0])
        except AttributeError:
            return int(draw.textlength(text, font=font))

    def _measure_text_height(
        self, draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont
    ) -> int:
        sample = text if text else "A"
        try:
            box = draw.textbbox((0, 0), sample, font=font)
            return max(1, int(box[3] - box[1]))
        except AttributeError:
            return int(getattr(font, "size", 16))

    def _split_wrapped_lines(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        font: ImageFont.ImageFont,
        max_width: int,
    ) -> List[str]:
        normalized_text = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
        if not normalized_text:
            return ["暂无直播描述"]

        lines: List[str] = []
        for raw_line in normalized_text.split("\n"):
            if raw_line == "":
                lines.append("")
                continue

            current = ""
            for char in raw_line:
                candidate = current + char
                if current and self._measure_text_width(draw, candidate, font) > max_width:
                    lines.append(current)
                    current = char
                else:
                    current = candidate
            lines.append(current)
        return lines or ["暂无直播描述"]

    def _draw_wrapped_text(
        self,
        draw: ImageDraw.ImageDraw,
        x: int,
        y: int,
        text: str,
        font: ImageFont.ImageFont,
        color: str,
        max_width: int,
        line_spacing: int,
    ) -> int:
        lines = self._split_wrapped_lines(draw, text, font, max_width)
        line_height = self._measure_text_height(draw, "示", font)
        current_y = y
        for line in lines:
            if line:
                draw.text((x, current_y), line, fill=color, font=font)
            current_y += line_height + line_spacing
        return current_y

    @staticmethod
    def _load_cn_font_safe(size: int, weight: str = "Regular") -> ImageFont.ImageFont:
        if weight == "Bold":
            font_names = [
                "NotoSansSC-Bold.otf",
                "NotoSansSC-Bold.ttf",
                "Noto Sans SC Bold",
                "NotoSansCJKsc-Bold.otf",
                "NotoSansCJK-Bold.ttc",
                "SourceHanSansSC-Bold.otf",
                "SourceHanSansCN-Bold.otf",
                "PingFang SC Bold",
                "Microsoft YaHei Bold",
                "msyhbd.ttc",
                "simhei.ttf",
                "simsun.ttc",
            ]
        else:
            font_names = [
                "NotoSansSC-Regular.otf",
                "NotoSansSC-Regular.ttf",
                "Noto Sans SC Regular",
                "Noto Sans SC",
                "NotoSansCJKsc-Regular.otf",
                "NotoSansCJK-Regular.ttc",
                "SourceHanSansSC-Regular.otf",
                "SourceHanSansCN-Regular.otf",
                "PingFang SC",
                "Microsoft YaHei",
                "msyh.ttc",
                "simsun.ttc",
                "simhei.ttf",
            ]

        for font_name in font_names:
            try:
                return ImageFont.truetype(font_name, size)
            except IOError:
                continue
        return ImageFont.load_default()

    @staticmethod
    def _load_font_safe(size: int, weight: str = "Regular") -> ImageFont.ImageFont:
        if weight == "Bold":
            font_names = [
                "NotoSansJP-Bold.otf",
                "NotoSansJP-Bold.ttf",
                "NotoSansCJKjp-Bold.otf",
                "NotoSansCJK-Bold.ttc",
                "meiryob.ttc",
                "YuGothB.ttc",
                "Hiragino Sans W6.ttc",
                "msyhbd.ttc",
                "simhei.ttf",
            ]
        else:
            font_names = [
                "NotoSansJP-Regular.otf",
                "NotoSansJP-Regular.ttf",
                "NotoSansCJKjp-Regular.otf",
                "NotoSansCJK-Regular.ttc",
                "meiryo.ttc",
                "YuGothR.ttc",
                "Hiragino Sans W3.ttc",
                "msyh.ttc",
                "simhei.ttf",
            ]

        for font_name in font_names:
            try:
                return ImageFont.truetype(font_name, size)
            except IOError:
                continue
        return ImageFont.load_default()

    @staticmethod
    def _create_gradient_texture(
        width: int, height: int, c1: str, c2: str
    ) -> Image.Image:
        base = Image.new("RGBA", (width, height))
        draw = ImageDraw.Draw(base)
        start_rgb = ImageColor.getrgb(c1)
        end_rgb = ImageColor.getrgb(c2)

        for x in range(width):
            r = int(start_rgb[0] + (end_rgb[0] - start_rgb[0]) * x / width)
            g = int(start_rgb[1] + (end_rgb[1] - start_rgb[1]) * x / width)
            b = int(start_rgb[2] + (end_rgb[2] - start_rgb[2]) * x / width)
            draw.line([(x, 0), (x, height)], fill=(r, g, b, 255))
        return base

    @staticmethod
    def _draw_svg_polygons(
        draw: ImageDraw.ImageDraw, offset_x: int, offset_y: int, height: int
    ) -> None:
        scale = height / 400

        def scale_points(points: List[List[int]]) -> List[tuple]:
            return [
                (p[0] * scale + offset_x, p[1] * scale + offset_y) for p in points
            ]

        draw.polygon(
            scale_points([[0, 0], [800, 0], [600, 200], [400, 0], [200, 200]]),
            fill=(255, 255, 255, 26),
        )
        draw.polygon(
            scale_points([[0, 400], [800, 400], [600, 200], [400, 400], [200, 200]]),
            fill=(255, 255, 255, 26),
        )
        draw.polygon(
            scale_points([[200, 200], [400, 0], [600, 200], [400, 400]]),
            fill=(255, 255, 255, 36),
        )
        draw.polygon(
            scale_points([[800, 0], [600, 200], [800, 400]]),
            fill=(255, 255, 255, 46),
        )


_service: Optional[WithLiveImageService] = None


def get_with_live_image_service() -> WithLiveImageService:
    global _service
    if _service is None:
        _service = WithLiveImageService()
    return _service


async def generate_with_live_image(auto_refresh_on_miss: bool = True) -> bytes:
    return await get_with_live_image_service().build_current_live_image(
        auto_refresh_on_miss=auto_refresh_on_miss
    )


async def generate_with_live_detail_image(
    index: int,
    auto_refresh_on_miss: bool = True,
) -> bytes:
    return await get_with_live_image_service().build_live_detail_image(
        index=index,
        auto_refresh_on_miss=auto_refresh_on_miss,
    )
