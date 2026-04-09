import tempfile
import unittest
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw

from src.core.services.bgp_icon_image import BgpIconImageService


class BgpIconImageServiceTest(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp_dir.cleanup)
        self.root = Path(self.tmp_dir.name)
        (self.root / "assets" / "bgp_icon").mkdir(parents=True, exist_ok=True)

    def _build_png_bytes(self, width: int, height: int, color: tuple) -> bytes:
        buffer = BytesIO()
        Image.new("RGBA", (width, height), color).save(buffer, format="PNG")
        return buffer.getvalue()

    def _write_frame(self, size: int):
        frame = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(frame)
        border = max(2, size // 20)
        draw.rectangle((0, 0, size - 1, size - 1), outline=(255, 255, 255, 255), width=border)
        frame.save(self.root / "assets" / "bgp_icon" / "frame.png")

    def test_large_image_scaled_to_frame_size(self):
        self._write_frame(800)
        service = BgpIconImageService(project_root=self.root)

        output = service.generate(self._build_png_bytes(1200, 1200, (255, 0, 0, 255)))

        with Image.open(BytesIO(output)) as result:
            self.assertEqual(result.size, (800, 800))

    def test_small_image_scales_frame_down(self):
        self._write_frame(800)
        service = BgpIconImageService(project_root=self.root)

        output = service.generate(self._build_png_bytes(400, 400, (255, 0, 0, 255)))

        with Image.open(BytesIO(output)) as result:
            self.assertEqual(result.size, (400, 400))
            self.assertGreater(result.getpixel((0, 0))[3], 0)

    def test_equal_size_keeps_resolution(self):
        self._write_frame(800)
        service = BgpIconImageService(project_root=self.root)

        output = service.generate(self._build_png_bytes(800, 800, (255, 0, 0, 255)))

        with Image.open(BytesIO(output)) as result:
            self.assertEqual(result.size, (800, 800))

    def test_non_square_image_raises(self):
        self._write_frame(800)
        service = BgpIconImageService(project_root=self.root)

        with self.assertRaises(ValueError) as ctx:
            service.generate(self._build_png_bytes(800, 600, (255, 0, 0, 255)))

        self.assertIn("1:1", str(ctx.exception))

    def test_missing_frame_raises(self):
        service = BgpIconImageService(project_root=self.root)

        with self.assertRaises(RuntimeError) as ctx:
            service.generate(self._build_png_bytes(800, 800, (255, 0, 0, 255)))

        self.assertIn("未找到头像框资源", str(ctx.exception))

    def test_output_is_png(self):
        self._write_frame(800)
        service = BgpIconImageService(project_root=self.root)

        output = service.generate(self._build_png_bytes(800, 800, (255, 0, 0, 255)))

        self.assertTrue(output.startswith(b"\x89PNG\r\n\x1a\n"))


if __name__ == "__main__":
    unittest.main()
