from io import BytesIO
from pathlib import Path
from typing import Optional, Tuple

from PIL import Image, ImageChops, ImageDraw


class BgpIconImageService:
    if hasattr(Image, "Resampling"):
        RESAMPLE = Image.Resampling.LANCZOS
    else:
        RESAMPLE = Image.LANCZOS

    def __init__(self, project_root: Optional[Path] = None):
        default_root = Path(__file__).resolve().parents[3]
        self.project_root = Path(project_root) if project_root is not None else default_root
        self.frame_path = self.project_root / "assets" / "bgp_icon" / "frame.png"

    def generate(self, source_bytes: bytes) -> bytes:
        source_image = self._load_source_image(source_bytes)
        frame_image = self._load_frame_image()
        source_image, frame_image = self._align_resolution(source_image, frame_image)
        circle_image = self._build_circle_image(source_image)

        merged = Image.alpha_composite(circle_image, frame_image)
        output = BytesIO()
        merged.save(output, format="PNG")
        return output.getvalue()

    def _load_source_image(self, source_bytes: bytes) -> Image.Image:
        if not source_bytes:
            raise ValueError("图片内容为空")

        try:
            with Image.open(BytesIO(source_bytes)) as loaded:
                image = loaded.convert("RGBA")
        except Exception as exc:
            raise ValueError(f"无法解析图片: {exc}") from exc

        width, height = image.size
        if width <= 0 or height <= 0:
            raise ValueError("图片尺寸无效")
        if width != height:
            raise ValueError("仅支持 1:1 比例图片")
        return image

    def _load_frame_image(self) -> Image.Image:
        if not self.frame_path.exists() or not self.frame_path.is_file():
            raise RuntimeError(f"未找到头像框资源: {self.frame_path}")

        try:
            with Image.open(self.frame_path) as loaded:
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


_service: Optional[BgpIconImageService] = None


def get_bgp_icon_image_service() -> BgpIconImageService:
    global _service
    if _service is None:
        _service = BgpIconImageService()
    return _service


def generate_bgp_icon_image(source_bytes: bytes) -> bytes:
    return get_bgp_icon_image_service().generate(source_bytes)
