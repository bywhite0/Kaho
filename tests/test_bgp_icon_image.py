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

    def _build_transparent_gif_bytes(
        self,
        width: int,
        height: int,
        frame_count: int = 1,
    ) -> bytes:
        frames = []
        durations = []
        for index in range(frame_count):
            frame = Image.new("P", (width, height), 0)
            palette = [0, 0, 0, 255, 0, 0, 0, 0, 255] + [0] * (768 - 9)
            frame.putpalette(palette)
            draw = ImageDraw.Draw(frame)
            offset = 10 + index * 5
            draw.rectangle(
                (offset, 10, width - 10, height - 10),
                fill=1 if index % 2 == 0 else 2,
            )
            frame.info["transparency"] = 0
            frames.append(frame)
            durations.append(70 + index * 60)

        buffer = BytesIO()
        frames[0].save(
            buffer,
            format="GIF",
            save_all=True,
            append_images=frames[1:],
            duration=durations,
            loop=1,
            transparency=0,
            disposal=2,
        )
        return buffer.getvalue()

    def _build_vertical_stripes_png_bytes(
        self, width: int, height: int, left: tuple, middle: tuple, right: tuple
    ) -> bytes:
        image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        one_third = width // 3
        draw.rectangle((0, 0, one_third - 1, height - 1), fill=left)
        draw.rectangle((one_third, 0, one_third * 2 - 1, height - 1), fill=middle)
        draw.rectangle((one_third * 2, 0, width - 1, height - 1), fill=right)
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()

    def _build_horizontal_stripes_png_bytes(
        self, width: int, height: int, top: tuple, middle: tuple, bottom: tuple
    ) -> bytes:
        image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        one_third = height // 3
        draw.rectangle((0, 0, width - 1, one_third - 1), fill=top)
        draw.rectangle((0, one_third, width - 1, one_third * 2 - 1), fill=middle)
        draw.rectangle((0, one_third * 2, width - 1, height - 1), fill=bottom)
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()

    def _write_frame(self, size: int):
        frame = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(frame)
        border = max(2, size // 20)
        draw.rectangle((0, 0, size - 1, size - 1), outline=(255, 255, 255, 255), width=border)
        frame.save(self.root / "assets" / "bgp_icon" / "bgp.png")

    def _write_solid_frame(self, name: str, size: int, color: tuple):
        frame = Image.new("RGBA", (size, size), color)
        frame.save(self.root / "assets" / "bgp_icon" / f"{name}.png")

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

    def test_non_square_wide_image_center_crops_successfully(self):
        self._write_frame(800)
        service = BgpIconImageService(project_root=self.root)
        source = self._build_vertical_stripes_png_bytes(
            600,
            400,
            (255, 0, 0, 255),
            (0, 255, 0, 255),
            (0, 0, 255, 255),
        )

        output = service.generate(source)

        with Image.open(BytesIO(output)) as result:
            self.assertEqual(result.size, (400, 400))
            self.assertEqual(result.getpixel((60, 200)), (255, 0, 0, 255))
            self.assertEqual(result.getpixel((200, 200)), (0, 255, 0, 255))
            self.assertEqual(result.getpixel((340, 200)), (0, 0, 255, 255))

    def test_non_square_tall_image_center_crops_successfully(self):
        self._write_frame(800)
        service = BgpIconImageService(project_root=self.root)
        source = self._build_horizontal_stripes_png_bytes(
            400,
            600,
            (255, 0, 0, 255),
            (0, 255, 0, 255),
            (0, 0, 255, 255),
        )

        output = service.generate(source)

        with Image.open(BytesIO(output)) as result:
            self.assertEqual(result.size, (400, 400))
            self.assertEqual(result.getpixel((200, 60)), (255, 0, 0, 255))
            self.assertEqual(result.getpixel((200, 200)), (0, 255, 0, 255))
            self.assertEqual(result.getpixel((200, 340)), (0, 0, 255, 255))

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

    def test_default_frame_name_uses_bgp_png(self):
        self._write_solid_frame("bgp", 800, (0, 255, 0, 255))
        self._write_solid_frame("kaho", 800, (0, 0, 255, 255))
        service = BgpIconImageService(project_root=self.root)

        output = service.generate(self._build_png_bytes(800, 800, (255, 0, 0, 255)))

        with Image.open(BytesIO(output)) as result:
            self.assertEqual(result.getpixel((400, 400)), (0, 255, 0, 255))

    def test_specified_frame_name_uses_target_png(self):
        self._write_solid_frame("bgp", 800, (0, 255, 0, 255))
        self._write_solid_frame("kaho", 800, (0, 0, 255, 255))
        service = BgpIconImageService(project_root=self.root)

        output = service.generate(
            self._build_png_bytes(800, 800, (255, 0, 0, 255)),
            frame_name="kaho",
        )

        with Image.open(BytesIO(output)) as result:
            self.assertEqual(result.getpixel((400, 400)), (0, 0, 255, 255))

    def test_missing_frame_name_raises_with_available_list(self):
        self._write_solid_frame("bgp", 800, (0, 255, 0, 255))
        self._write_solid_frame("kaho", 800, (0, 0, 255, 255))
        service = BgpIconImageService(project_root=self.root)

        with self.assertRaises(RuntimeError) as ctx:
            service.generate(
                self._build_png_bytes(800, 800, (255, 0, 0, 255)),
                frame_name="unknown",
            )

        message = str(ctx.exception)
        self.assertIn("可选", message)
        self.assertIn("bgp", message)
        self.assertIn("kaho", message)

    def test_invalid_frame_name_raises(self):
        self._write_solid_frame("bgp", 800, (0, 255, 0, 255))
        service = BgpIconImageService(project_root=self.root)

        with self.assertRaises(ValueError) as ctx:
            service.generate(
                self._build_png_bytes(800, 800, (255, 0, 0, 255)),
                frame_name="../kaho",
            )

        self.assertIn("frame 参数", str(ctx.exception))

    def test_transparent_gif_input_outputs_transparent_gif(self):
        self._write_solid_frame("bgp", 800, (0, 0, 0, 0))
        service = BgpIconImageService(project_root=self.root)
        source = self._build_transparent_gif_bytes(400, 400, frame_count=1)

        output = service.generate(source)

        self.assertTrue(output.startswith(b"GIF87a") or output.startswith(b"GIF89a"))
        with Image.open(BytesIO(output)) as result:
            self.assertEqual(result.format, "GIF")
            self.assertIn("transparency", result.info)
            rgba = result.convert("RGBA")
            self.assertEqual(rgba.getpixel((0, 0))[3], 0)
            self.assertGreater(rgba.getpixel((200, 200))[3], 0)

    def test_animated_gif_input_outputs_animated_gif(self):
        self._write_solid_frame("bgp", 800, (0, 0, 0, 0))
        service = BgpIconImageService(project_root=self.root)
        source = self._build_transparent_gif_bytes(360, 360, frame_count=2)

        output = service.generate(source)

        self.assertTrue(output.startswith(b"GIF87a") or output.startswith(b"GIF89a"))
        with Image.open(BytesIO(output)) as result:
            self.assertEqual(result.format, "GIF")
            self.assertTrue(getattr(result, "is_animated", False))
            self.assertEqual(getattr(result, "n_frames", 1), 2)
            self.assertEqual(int(result.info.get("loop") or 0), 1)


if __name__ == "__main__":
    unittest.main()
