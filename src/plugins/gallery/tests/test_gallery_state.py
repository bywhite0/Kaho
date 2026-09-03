"""gallery 状态逻辑集成测试：画廊模式、封面、图片 id 索引、全库查重

localstore 要通过插件上下文解析数据目录，因此必须走 load_plugin 路径；
nonebot.init 与 LOCALSTORE_* 环境变量都是进程级的，故本文件作为独立进程运行。
运行：python test_gallery_state.py（run_tests.py 会以子进程方式调用）
"""

import importlib
import os
import sys
import tempfile
import traceback
from pathlib import Path

_tmp = Path(tempfile.mkdtemp(prefix="gallery_state_"))
os.environ["LOCALSTORE_DATA_DIR"] = str(_tmp / "data")
os.environ["LOCALSTORE_CACHE_DIR"] = str(_tmp / "cache")
os.environ["LOCALSTORE_CONFIG_DIR"] = str(_tmp / "config")

# 插件包名跟随目录名，Kaho 内为 gallery，独立仓库为 nonebot_plugin_gallery
_PKG_NAME = Path(__file__).resolve().parents[1].name
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import nonebot
from PIL import Image, ImageDraw

nonebot.init(driver="~none", superusers={"1"}, log_level="WARNING")
assert nonebot.load_plugin(_PKG_NAME) is not None, "插件加载失败"

gallery = importlib.import_module(f"{_PKG_NAME}.gallery")
handler = importlib.import_module(f"{_PKG_NAME}.handler")
_config = importlib.import_module(f"{_PKG_NAME}.config")
cfg = _config.cfg
gallery_name_data = _config.gallery_name_data


def _register_gallery(name: str) -> Path:
    gallery_dir = cfg.data_dir_path / name
    gallery_dir.mkdir(parents=True, exist_ok=True)
    gallery_name_data.instance.name_to_aliases.setdefault(name, [])
    gallery_name_data.save_to_file()
    return gallery_dir


def _add_picture(name: str, pic_id: int, *, width: int = 50) -> Path:
    """写入一张以 id 命名的图片；width 控制内容差异，方差足够让 ahash 生效"""
    path = cfg.data_dir_path / name / f"{pic_id}.png"
    image = Image.new("RGB", (96, 96), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    draw.rectangle((5, 5, width, 55), fill=(15, 25, 190))
    draw.ellipse((40, 45, 88, 90), fill=(245, 205, 20))
    draw.line((0, 92, 96, 4), fill=(10, 10, 10), width=5)
    image.save(path)
    return path


# ---------- 模式 ----------


def test_new_gallery_defaults_to_editable():
    _register_gallery("默认模式")
    assert gallery.get_gallery_mode("默认模式") == "edit"
    assert gallery.is_gallery_writable("默认模式")
    assert not gallery.is_gallery_hidden("默认模式")


def test_mode_transitions_cover_every_state():
    name = "状态流转"
    _register_gallery(name)
    expectations = {
        "edit": (True, False),
        "view": (False, False),
        "off": (False, True),
    }
    for mode, (writable, hidden) in expectations.items():
        gallery.set_gallery_mode(name, mode)
        assert gallery.get_gallery_mode(name) == mode, mode
        assert gallery.is_gallery_writable(name) is writable, mode
        assert gallery.is_gallery_hidden(name) is hidden, mode
    # 回到默认模式后不该在索引里留下条目
    gallery.set_gallery_mode(name, "edit")
    assert name not in gallery_name_data.instance.name_to_mode


def test_mode_is_persisted_in_index():
    name = "持久化"
    _register_gallery(name)
    gallery.set_gallery_mode(name, "view")
    reloaded = type(gallery_name_data.instance).model_validate_json(
        cfg.name_data_file_path.read_text(encoding="utf-8")
    )
    assert reloaded.name_to_mode.get(name) == "view"


def test_corrupted_mode_value_falls_back_to_default():
    """手工改坏单个画廊的模式，只应让它回退默认，不该影响其它画廊"""
    name = "坏值"
    _register_gallery(name)
    gallery_name_data.instance.name_to_mode[name] = "bogus"
    assert gallery.get_gallery_mode(name) == "edit"
    assert gallery.is_gallery_writable(name)
    gallery_name_data.instance.name_to_mode.pop(name)


# ---------- 总览可见性 ----------


def test_overview_hides_off_galleries_from_normal_users():
    name = "隐藏画廊"
    _register_gallery(name)
    _add_picture(name, 9001)
    gallery.set_gallery_mode(name, "off")

    visible = [item.name for item in gallery.get_gallery_overview_items()]
    everything = [
        item.name for item in gallery.get_gallery_overview_items(include_hidden=True)
    ]
    assert name not in visible
    assert name in everything
    gallery.set_gallery_mode(name, "edit")


def test_overview_caches_each_visibility_scope_separately():
    """两种可见范围必须落在不同缓存文件，否则普通用户会拿到含隐藏画廊的图"""
    name = "缓存隔离"
    _register_gallery(name)
    _add_picture(name, 9101)
    gallery.set_gallery_mode(name, "off")
    gallery.invalidate_gallery_render_cache()

    public_image = gallery.render_gallery_overview()
    private_image = gallery.render_gallery_overview(include_hidden=True)
    assert public_image and private_image
    assert public_image != private_image

    public_cache = gallery._render_cache_path(include_hidden=False)
    private_cache = gallery._render_cache_path(include_hidden=True)
    assert public_cache != private_cache
    assert public_cache.is_file() and private_cache.is_file()

    # 失效操作必须同时清掉两份，否则改动后仍会发出旧图
    gallery.invalidate_gallery_render_cache()
    assert not public_cache.exists() and not private_cache.exists()
    gallery.set_gallery_mode(name, "edit")


# ---------- 封面 ----------


def test_cover_defaults_to_smallest_id_and_follows_selection():
    name = "封面"
    _register_gallery(name)
    for pic_id in (9203, 9201, 9202):
        _add_picture(name, pic_id)

    def cover_of() -> str | None:
        for item in gallery.get_gallery_overview_items(include_hidden=True):
            if item.name == name:
                return item.cover_path.name if item.cover_path else None
        return None

    assert cover_of() == "9201.png"

    gallery.set_gallery_cover(name, 9203)
    assert cover_of() == "9203.png"

    # 指定的封面图被删除后回退到 id 最小的一张，而不是留空
    (cfg.data_dir_path / name / "9203.png").unlink()
    assert cover_of() == "9201.png"

    gallery.clear_gallery_cover(name)
    assert name not in gallery_name_data.instance.name_to_cover
    assert cover_of() == "9201.png"


# ---------- 图片 id 索引 ----------


def test_picture_ids_are_sorted_and_respect_visibility():
    open_name, hidden_name = "公开库", "隐藏库"
    _register_gallery(open_name)
    _register_gallery(hidden_name)
    _add_picture(open_name, 9302)
    _add_picture(open_name, 9301)
    _add_picture(hidden_name, 9303)
    gallery.set_gallery_mode(hidden_name, "off")

    visible_ids = gallery.list_picture_ids()
    all_ids = gallery.list_picture_ids(include_hidden=True)
    assert visible_ids == sorted(visible_ids)
    assert 9303 not in visible_ids
    assert 9303 in all_ids
    assert {9301, 9302} <= set(visible_ids)
    gallery.set_gallery_mode(hidden_name, "edit")


def test_negative_index_resolves_to_latest_pictures():
    name = "倒数索引"
    _register_gallery(name)
    for pic_id in (9401, 9402, 9403):
        _add_picture(name, pic_id)
    all_ids = gallery.list_picture_ids(include_hidden=True)

    assert gallery.resolve_picture_index(-1, include_hidden=True) == all_ids[-1]
    assert gallery.resolve_picture_index(-2, include_hidden=True) == all_ids[-2]
    assert gallery.resolve_picture_index(-len(all_ids), include_hidden=True) == all_ids[0]
    # 超出范围返回 None，而不是抛错或环绕到别的图
    assert gallery.resolve_picture_index(-len(all_ids) - 1, include_hidden=True) is None
    # 非负数原样返回，交给 id 查找处理
    assert gallery.resolve_picture_index(9402) == 9402


def test_non_numeric_files_are_ignored():
    name = "杂项文件"
    gallery_dir = _register_gallery(name)
    _add_picture(name, 9501)
    (gallery_dir / "notes.txt").write_text("not a picture", encoding="utf-8")
    (gallery_dir / "sub").mkdir(exist_ok=True)

    assert gallery.list_picture_ids(include_hidden=True).count(9501) == 1
    picture_files = handler._gallery_picture_files(name)
    assert [path.name for path in picture_files] == ["9501.png"]
    # 缩略图墙遇到杂项文件不能崩，应跳过后照常出图
    assert gallery.render_gallery_thumbnails(name, list(gallery_dir.iterdir()))


# ---------- 可见性判定 ----------


def test_picture_visibility_follows_owning_gallery():
    name = "可见性"
    _register_gallery(name)
    pic_path = _add_picture(name, 9601)
    assert handler._is_visible_picture(pic_path, False)

    gallery.set_gallery_mode(name, "off")
    assert not handler._is_visible_picture(pic_path, False)
    assert handler._is_visible_picture(pic_path, True)
    gallery.set_gallery_mode(name, "edit")

    # 数据目录之外的路径无法归属到画廊，按不可见处理
    assert not handler._is_visible_picture(Path(__file__), False)


# ---------- 抽图不重复 ----------


def test_picture_message_never_repeats_a_file():
    name = "抽图"
    gallery_dir = _register_gallery(name)
    # 两张图内容必须不同，否则消息段字节一致，无法分辨是否重复抽到同一个文件
    _add_picture(name, 9701, width=50)
    _add_picture(name, 9702, width=88)
    pic_files = handler._gallery_picture_files(name)

    # 请求数超过实际图片数时给出全部且不重复，而不是重复凑数
    message = handler._build_pic_message(pic_files, 5)
    assert len(message) == 2
    assert len({str(segment) for segment in message}) == 2

    assert len(handler._build_pic_message(pic_files, 1)) == 1
    assert len(handler._build_pic_message(list(gallery_dir.glob("9701.png")), 3)) == 1


# ---------- 全库查重 ----------


def test_duplicate_groups_detects_existing_copies():
    name = "查重"
    gallery_dir = _register_gallery(name)
    _add_picture(name, 9801)
    _add_picture(name, 9803, width=50)  # 与 9801 内容一致
    _add_picture(name, 9802, width=88)  # 明显不同

    groups = gallery.find_duplicate_groups(name)
    assert groups == [[9801, 9803]], groups
    # rehash 会丢弃缓存重算，结论必须一致
    assert gallery.find_duplicate_groups(name, rehash=True) == [[9801, 9803]]

    (gallery_dir / "9803.png").unlink()
    gallery.remove_picture_from_index(gallery_dir / "9803.png")
    assert gallery.find_duplicate_groups(name) == []


def test_duplicate_groups_on_empty_gallery():
    _register_gallery("空画廊")
    assert gallery.find_duplicate_groups("空画廊") == []


def main() -> int:
    failed: list[str] = []
    passed = 0
    for case_name in sorted(name for name in globals() if name.startswith("test_")):
        try:
            globals()[case_name]()
        except Exception:
            failed.append(case_name)
            print(f"FAIL {case_name}")
            traceback.print_exc()
        else:
            passed += 1
    print(f"{passed} passed, {len(failed)} failed")
    for case_name in failed:
        print(f"  failed: {case_name}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
