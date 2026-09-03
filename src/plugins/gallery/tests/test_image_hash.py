"""image_hash 单元测试：查重指纹的透明通道处理与判定阈值

独立于 NoneBot 运行时：通过合成包上下文加载 image_hash。
运行：python run_tests.py（见同目录 run_tests.py 的说明）
"""

import importlib
import sys
import types
from pathlib import Path

from PIL import Image, ImageDraw

_PKG_DIR = Path(__file__).resolve().parents[1]
_PKG_NAME = "_gallery_under_test"
if _PKG_NAME not in sys.modules:
    _pkg = types.ModuleType(_PKG_NAME)
    _pkg.__path__ = [str(_PKG_DIR)]
    sys.modules[_PKG_NAME] = _pkg

_image_hash = importlib.import_module(f"{_PKG_NAME}.image_hash")
calculate_image_hashes = _image_hash.calculate_image_hashes
perceptual_distances = _image_hash.perceptual_distances
hamming_distance = _image_hash.hamming_distance


def _transparent_artwork(size: tuple[int, int] = (96, 96)) -> Image.Image:
    """透明背景 + 高对比图形：方差足够大，保证 ahash 不被低方差规则丢弃"""
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((10, 10, 55, 55), fill=(15, 25, 190, 255))
    draw.ellipse((40, 45, 88, 90), fill=(245, 205, 20, 255))
    draw.line((0, 92, 96, 4), fill=(10, 10, 10, 255), width=5)
    return image


def _flatten_on_white(image: Image.Image) -> Image.Image:
    background = Image.new("RGB", image.size, (255, 255, 255))
    background.paste(image, (0, 0), image)
    return background


# ---------- 透明通道 ----------


def test_transparent_png_matches_its_white_background_render(tmp_path):
    """透明 PNG 与"同一张图铺白底"的无损渲染必须得到完全相同的指纹。

    PIL 的 RGBA -> L 会丢弃 alpha、把透明像素当黑色，两者指纹会天差地别，
    表情包的 PNG 版与白底版因此漏判重复。合成到白底后指纹必须收敛。
    """
    artwork = _transparent_artwork()
    transparent_path = tmp_path / "transparent.png"
    flattened_path = tmp_path / "flattened.png"
    artwork.save(transparent_path)
    _flatten_on_white(artwork).save(flattened_path)

    transparent = calculate_image_hashes(transparent_path)
    flattened = calculate_image_hashes(flattened_path)

    assert transparent.dhash == flattened.dhash
    assert transparent.phash == flattened.phash
    assert transparent.ahash == flattened.ahash


def test_transparent_png_is_duplicate_of_white_background_jpeg(tmp_path):
    """跨格式（PNG 透明底 vs JPEG 白底）也要被判为重复，容许 JPEG 压缩噪声"""
    artwork = _transparent_artwork()
    png_path = tmp_path / "sticker.png"
    jpeg_path = tmp_path / "sticker.jpg"
    artwork.save(png_path)
    _flatten_on_white(artwork).save(jpeg_path, quality=95)

    distances = perceptual_distances(
        calculate_image_hashes(png_path),
        calculate_image_hashes(jpeg_path),
    )
    assert distances is not None, "透明 PNG 与其白底 JPEG 应判为重复"


def test_palette_gif_with_transparency_matches_white_background(tmp_path):
    """调色板 GIF 的透明信息在 info['transparency'] 里，同样要走白底合成"""
    artwork = _transparent_artwork()
    gif_path = tmp_path / "sticker.gif"
    flattened_path = tmp_path / "flattened.png"
    artwork.convert("P", palette=Image.Palette.ADAPTIVE).save(gif_path, transparency=0)
    _flatten_on_white(artwork).save(flattened_path)

    distances = perceptual_distances(
        calculate_image_hashes(gif_path),
        calculate_image_hashes(flattened_path),
    )
    assert distances is not None, "透明 GIF 与其白底渲染应判为重复"


def test_opaque_image_hashing_is_deterministic(tmp_path):
    """不含 alpha 的图片不受白底合成影响，同内容两份文件指纹一致"""
    opaque = _flatten_on_white(_transparent_artwork())
    first_path = tmp_path / "a.png"
    second_path = tmp_path / "b.png"
    opaque.save(first_path)
    opaque.save(second_path)

    first = calculate_image_hashes(first_path)
    second = calculate_image_hashes(second_path)
    assert first == second


# ---------- 判定阈值 ----------


def test_distinct_images_are_not_duplicates(tmp_path):
    """内容不同的图片不能被误判为重复"""
    left = Image.new("RGB", (96, 96), (255, 255, 255))
    ImageDraw.Draw(left).rectangle((0, 0, 47, 95), fill=(0, 0, 0))
    right = Image.new("RGB", (96, 96), (255, 255, 255))
    ImageDraw.Draw(right).ellipse((60, 4, 92, 36), fill=(0, 0, 0))

    left_path = tmp_path / "left.png"
    right_path = tmp_path / "right.png"
    left.save(left_path)
    right.save(right_path)

    distances = perceptual_distances(
        calculate_image_hashes(left_path),
        calculate_image_hashes(right_path),
    )
    assert distances is None


def test_flat_color_image_disables_perceptual_match(tmp_path):
    """纯色图方差过低，ahash 置空并放弃感知比较，避免把所有纯色图判成同一张"""
    for index, color in enumerate(((255, 255, 255), (12, 200, 90))):
        path = tmp_path / f"flat{index}.png"
        Image.new("RGB", (96, 96), color).save(path)
        assert calculate_image_hashes(path).ahash is None

    first = calculate_image_hashes(tmp_path / "flat0.png")
    second = calculate_image_hashes(tmp_path / "flat1.png")
    assert perceptual_distances(first, second) is None


# ---------- 精确哈希 ----------


def test_file_hash_tracks_content_not_path(tmp_path):
    artwork = _flatten_on_white(_transparent_artwork())
    same_a = tmp_path / "same_a.png"
    same_b = tmp_path / "same_b.png"
    artwork.save(same_a)
    artwork.save(same_b)
    different = tmp_path / "different.png"
    Image.new("RGB", (96, 96), (3, 4, 5)).save(different)

    assert calculate_image_hashes(same_a).file_hash == calculate_image_hashes(same_b).file_hash
    assert calculate_image_hashes(same_a).file_hash != calculate_image_hashes(different).file_hash


def test_hamming_distance_counts_differing_bits():
    assert hamming_distance(0b1011, 0b1011) == 0
    assert hamming_distance(0b1011, 0b1010) == 1
    assert hamming_distance(0, 0b1111) == 4
