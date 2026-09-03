"""names 单元测试：画廊名称校验与模式解析

独立于 NoneBot 运行时：通过合成包上下文加载 names。
运行（需在 tests 目录内，避免 pytest 把插件包目录当作 Package 导入）：
    cd tests && python -m pytest test_names.py -q
"""

import importlib
import sys
import types
from pathlib import Path

_PKG_DIR = Path(__file__).resolve().parents[1]
_PKG_NAME = "_gallery_under_test"
if _PKG_NAME not in sys.modules:
    _pkg = types.ModuleType(_PKG_NAME)
    _pkg.__path__ = [str(_PKG_DIR)]
    sys.modules[_PKG_NAME] = _pkg

_names = importlib.import_module(f"{_PKG_NAME}.names")
validate_gallery_name = _names.validate_gallery_name
parse_mode_token = _names.parse_mode_token
INTEGER_PATTERN = _names.INTEGER_PATTERN
MAX_NAME_LENGTH = _names.MAX_NAME_LENGTH
MODE_LABELS = _names.MODE_LABELS
DEFAULT_MODE = _names.DEFAULT_MODE


# ---------- 合法名称 ----------


def test_accepts_ordinary_names():
    for name in ("表情包", "memes", "kaho-2024", "群友语录", "第1季", "a.b", "全角１２３"):
        assert validate_gallery_name(name) is None, name


def test_accepts_emoji_name():
    # 总览渲染专门支持 emoji 绘制，校验层不应把它挡掉
    assert validate_gallery_name("🐟摸鱼") is None


def test_accepts_name_at_length_limit():
    assert validate_gallery_name("啊" * MAX_NAME_LENGTH) is None


# ---------- 长度与空白 ----------


def test_rejects_empty_name():
    assert validate_gallery_name("") is not None


def test_rejects_name_over_length_limit():
    assert validate_gallery_name("啊" * (MAX_NAME_LENGTH + 1)) is not None


def test_rejects_surrounding_whitespace():
    # Windows 会静默去掉目录名首尾的空格，导致索引名与真实目录名不一致
    for name in (" memes", "memes ", "\tmemes"):
        assert validate_gallery_name(name) is not None, name


def test_rejects_inner_whitespace():
    # 命令参数按空白分割（如 "看 <画廊> x2"），名称含空白会让参数解析截断
    for name in ("表情 包", "a　b"):
        assert validate_gallery_name(name) is not None, name


def test_rejects_control_characters():
    for name in ("a\nb", "a\tb", "a\x00b", "a\x7fb"):
        assert validate_gallery_name(name) is not None, name


# ---------- 与图片 id 的互斥 ----------


def test_rejects_pure_digits():
    for name in ("1", "123", "0", "-1", "+5"):
        assert validate_gallery_name(name) is not None, name


def test_integer_forms_are_never_valid_names():
    """凡是能被解析成图片 id 的字符串都必须是非法名称。

    这是"画廊名遮蔽图片 id"不会发生的充要条件：命令层用同一个
    INTEGER_PATTERN 识别 id，两边一致就不存在取不到图的死角。
    """
    for candidate in ("7", "-7", "+7", "0", "999999"):
        assert INTEGER_PATTERN.match(candidate), candidate
        assert validate_gallery_name(candidate) is not None, candidate


def test_fullwidth_digits_are_not_picture_ids():
    # 全角数字不被 id 解析识别，因此允许做画廊名，也不会遮蔽任何 id
    assert INTEGER_PATTERN.match("１２３") is None
    assert validate_gallery_name("１２３") is None


# ---------- 文件系统安全 ----------


def test_rejects_path_traversal():
    for name in ("..", ".", "../x", "..\\x", "a/b", "a\\b", "/etc", "C:"):
        assert validate_gallery_name(name) is not None, name


def test_rejects_windows_reserved_characters():
    for char in '<>:"/\\|?*':
        assert validate_gallery_name(f"a{char}b") is not None, char


def test_rejects_trailing_dot():
    assert validate_gallery_name("memes.") is not None


def test_rejects_windows_reserved_device_names():
    for name in ("CON", "con", "Nul", "AUX", "PRN", "COM1", "LPT9", "NUL.txt", "con.png"):
        assert validate_gallery_name(name) is not None, name


def test_accepts_names_merely_resembling_device_names():
    for name in ("CONS", "COM0", "COM10", "LPT", "NULL"):
        assert validate_gallery_name(name) is None, name


# ---------- 模式解析 ----------


def test_parses_mode_tokens():
    expected = {
        "edit": ("edit", "读写", "正常", "可写", "开放"),
        "view": ("view", "只读", "查看", "锁定"),
        "off": ("off", "关闭", "隐藏", "下架"),
    }
    for mode, tokens in expected.items():
        for token in tokens:
            assert parse_mode_token(token) == mode, token


def test_mode_token_parsing_is_case_and_space_insensitive():
    for token in ("EDIT", " Edit ", "OFF", "\tview\n"):
        assert parse_mode_token(token) is not None, token


def test_rejects_unknown_mode_token():
    for token in ("", "readonly", "开", "删除"):
        assert parse_mode_token(token) is None, token


def test_every_mode_has_a_label_and_default_is_editable():
    assert set(MODE_LABELS) == {"edit", "view", "off"}
    assert DEFAULT_MODE == "edit"
