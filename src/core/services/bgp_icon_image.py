from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import re
from typing import List, Optional, Tuple

from PIL import Image, ImageChops, ImageDraw, ImageSequence


@dataclass
class _SourceImagePayload:
    frames: List[Image.Image]
    durations: List[int]
    loop: int
    output_format: str


class BgpIconImageService:
    if hasattr(Image, "Resampling"):
        RESAMPLE = Image.Resampling.LANCZOS
    else:
        RESAMPLE = Image.LANCZOS

    def __init__(self, project_root: Optional[Path] = None):
        default_root = Path(__file__).resolve().parents[3]
        self.project_root = Path(project_root) if project_root is not None else default_root
        self.frame_dir = self.project_root / "assets" / "bgp_icon"

    def generate(self, source_bytes: bytes, frame_name: str = "bgp") -> bytes:
        source_payload = self._load_source_image(source_bytes)
        frame_image = self._load_frame_image(frame_name=frame_name)
        output_frames: List[Image.Image] = []

        for source_image in source_payload.frames:
            aligned_source, aligned_frame = self._align_resolution(source_image, frame_image)
            circle_image = self._build_circle_image(aligned_source)
            merged = Image.alpha_composite(circle_image, aligned_frame)
            output_frames.append(merged)

        if source_payload.output_format == "GIF":
            return self._save_transparent_gif(
                frames=output_frames,
                durations=source_payload.durations,
                loop=source_payload.loop,
            )
        return self._save_png(output_frames[0])

    def _load_source_image(self, source_bytes: bytes) -> _SourceImagePayload:
        if not source_bytes:
            raise ValueError("图片内容为空")

        try:
            with Image.open(BytesIO(source_bytes)) as loaded:
                image_format = str(loaded.format or "").upper()
                loop = int(loaded.info.get("loop") or 0)
                default_duration = int(loaded.info.get("duration") or 100)
                is_gif = image_format == "GIF"
                is_animated = bool(getattr(loaded, "is_animated", False))

                if is_gif and is_animated:
                    frames: List[Image.Image] = []
                    durations: List[int] = []
                    for frame in ImageSequence.Iterator(loaded):
                        rgba = frame.convert("RGBA")
                        frames.append(self._normalize_source_frame(rgba))
                        durations.append(int(frame.info.get("duration") or default_duration))

                    if not frames:
                        raise ValueError("GIF 图片帧为空")
                    return _SourceImagePayload(
                        frames=frames,
                        durations=durations,
                        loop=loop,
                        output_format="GIF",
                    )

                image = loaded.convert("RGBA")
        except Exception as exc:
            raise ValueError(f"无法解析图片: {exc}") from exc

        return _SourceImagePayload(
            frames=[self._normalize_source_frame(image)],
            durations=[100],
            loop=0,
            output_format="GIF" if image_format == "GIF" else "PNG",
        )

    def _normalize_source_frame(self, image: Image.Image) -> Image.Image:
        width, height = image.size
        if width <= 0 or height <= 0:
            raise ValueError("图片尺寸无效")
        if width == height:
            return image
        return self._center_crop_to_square(image)

    def _center_crop_to_square(self, image: Image.Image) -> Image.Image:
        width, height = image.size
        target = min(width, height)
        left = (width - target) // 2
        top = (height - target) // 2
        return image.crop((left, top, left + target, top + target))

    def _normalize_frame_name(self, frame_name: str) -> str:
        name = str(frame_name or "").strip().lower()
        if not name:
            name = "bgp"
        if not re.fullmatch(r"[a-z0-9_-]+", name):
            raise ValueError("frame 参数仅支持字母、数字、下划线和短横线")
        return name

    def _list_available_frames(self) -> List[str]:
        if not self.frame_dir.exists() or not self.frame_dir.is_dir():
            return []
        names: List[str] = []
        for file_path in self.frame_dir.glob("*.png"):
            if not file_path.is_file():
                continue
            names.append(file_path.stem.lower())
        return sorted(set(names))

    def _resolve_frame_path(self, frame_name: str) -> Path:
        normalized = self._normalize_frame_name(frame_name)
        target = self.frame_dir / f"{normalized}.png"
        if target.exists() and target.is_file():
            return target

        available = self._list_available_frames()
        if available:
            raise RuntimeError(
                f"未找到头像框资源: {normalized}.png，可选: {', '.join(available)}"
            )
        raise RuntimeError("未找到头像框资源目录或可用头像框文件")

    def _load_frame_image(self, frame_name: str) -> Image.Image:
        frame_path = self._resolve_frame_path(frame_name=frame_name)

        try:
            with Image.open(frame_path) as loaded:
                frame = loaded.convert("RGBA")
        except Exception as exc:
            raise RuntimeError(f"读取头像框资源失败: {exc}") from exc

        width, height = frame.size
        if width <= 0 or height <= 0 or width != height:
            raise RuntimeError("头像框资源尺寸异常")
        return frame

    def _align_resolution(
        self, source_image: Image.Image, frame_image: Image.Image
    ) -> Tuple[Image.Image, Image.Image]:
        source_size = source_image.size[0]
        frame_size = frame_image.size[0]

        if source_size > frame_size:
            source_image = source_image.resize((frame_size, frame_size), self.RESAMPLE)
        elif source_size < frame_size:
            frame_image = frame_image.resize((source_size, source_size), self.RESAMPLE)

        return source_image, frame_image

    def _build_circle_image(self, source_image: Image.Image) -> Image.Image:
        width, height = source_image.size
        mask = Image.new("L", (width, height), 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((0, 0, width - 1, height - 1), fill=255)

        result = source_image.copy()
        source_alpha = result.getchannel("A")
        result.putalpha(ImageChops.multiply(source_alpha, mask))
        return result

    def _save_png(self, image: Image.Image) -> bytes:
        output = BytesIO()
        image.save(output, format="PNG")
        return output.getvalue()

    def _save_transparent_gif(
        self,
        frames: List[Image.Image],
        durations: List[int],
        loop: int,
    ) -> bytes:
        if not frames:
            raise RuntimeError("GIF 输出帧为空")

        paletted_frames = [self._rgba_to_transparent_gif_frame(frame) for frame in frames]
        output = BytesIO()
        first, *rest = paletted_frames
        first.save(
            output,
            format="GIF",
            save_all=True,
            append_images=rest,
            duration=durations if len(durations) == len(paletted_frames) else durations[0],
            loop=loop,
            transparency=255,
            disposal=2,
        )
        return output.getvalue()

    def _rgba_to_transparent_gif_frame(self, image: Image.Image) -> Image.Image:
        rgba = image.convert("RGBA")
        alpha = rgba.getchannel("A")
        rgb = Image.new("RGB", rgba.size, (0, 0, 0))
        rgb.paste(rgba.convert("RGB"), mask=alpha)
        paletted = rgb.quantize(colors=255)
        transparent_index = 255
        transparent_mask = Image.eval(alpha, lambda a: 255 if a <= 127 else 0)
        paletted.paste(transparent_index, mask=transparent_mask)
        palette = paletted.getpalette()
        if palette:
            if len(palette) < 768:
                palette.extend([0] * (768 - len(palette)))
            palette[transparent_index * 3 : transparent_index * 3 + 3] = [0, 0, 0]
            paletted.putpalette(palette)
        paletted.info["transparency"] = transparent_index
        paletted.info["disposal"] = 2
        return paletted


_service: Optional[BgpIconImageService] = None


def get_bgp_icon_image_service() -> BgpIconImageService:
    global _service
    if _service is None:
        _service = BgpIconImageService()
    return _service


def generate_bgp_icon_image(source_bytes: bytes, frame_name: str = "bgp") -> bytes:
    return get_bgp_icon_image_service().generate(
        source_bytes=source_bytes,
        frame_name=frame_name,
    )
