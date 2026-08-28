"""access_core 单元测试

独立于 NoneBot 运行时：通过合成包上下文加载 access_core。
运行（需在 tests 目录内，避免 pytest 把插件包目录当作 Package 导入）：
    cd tests && python -m pytest test_access_core.py -q
"""

import importlib
import json
import os
import sys
import types
from pathlib import Path

_PKG_DIR = Path(__file__).resolve().parents[1]
_PKG_NAME = "_gallery_under_test"
if _PKG_NAME not in sys.modules:
    _pkg = types.ModuleType(_PKG_NAME)
    _pkg.__path__ = [str(_PKG_DIR)]
    sys.modules[_PKG_NAME] = _pkg

_core = importlib.import_module(f"{_PKG_NAME}.access_core")
AccessConfig = _core.AccessConfig
HotReloadJsonModelFile = _core.HotReloadJsonModelFile
resolve_policy = _core.resolve_policy
parse_policy_token = _core.parse_policy_token
is_remove_token = _core.is_remove_token


# ---------- 策略解析 ----------


def test_default_rw_for_unlisted():
    config = AccessConfig()
    assert resolve_policy(config, "1", None) == "rw"
    assert resolve_policy(config, "1", "100") == "rw"


def test_user_deny_blocks_everywhere():
    config = AccessConfig(users={"1": "deny"})
    assert resolve_policy(config, "1", None) == "deny"
    assert resolve_policy(config, "1", "100") == "deny"


def test_user_readonly():
    config = AccessConfig(users={"1": "ro"})
    assert resolve_policy(config, "1", "100") == "ro"


def test_group_rule_only_applies_in_that_group():
    config = AccessConfig(groups={"100": "ro"})
    assert resolve_policy(config, "1", "100") == "ro"
    assert resolve_policy(config, "1", None) == "rw"  # 私聊不受群规则影响
    assert resolve_policy(config, "1", "200") == "rw"  # 其它群不受影响


def test_user_rule_overrides_group_rule():
    config = AccessConfig(groups={"100": "deny"}, users={"1": "rw"})
    assert resolve_policy(config, "1", "100") == "rw"
    assert resolve_policy(config, "2", "100") == "deny"


def test_superuser_always_rw():
    config = AccessConfig(default_policy="deny", users={"1": "deny"})
    assert resolve_policy(config, "1", "100", is_superuser=True) == "rw"


def test_whitelist_mode():
    config = AccessConfig(default_policy="deny", groups={"100": "rw"}, users={"9": "ro"})
    assert resolve_policy(config, "1", "100") == "rw"  # 白名单群可用
    assert resolve_policy(config, "1", "200") == "deny"  # 未列群拒绝
    assert resolve_policy(config, "1", None) == "deny"  # 私聊拒绝
    assert resolve_policy(config, "9", None) == "ro"  # 白名单用户私聊只读


# ---------- 策略词解析 ----------


def test_parse_policy_token_aliases():
    for token in ("rw", "RW", "readwrite", "读写", "正常"):
        assert parse_policy_token(token) == "rw"
    for token in ("ro", "readonly", "只读"):
        assert parse_policy_token(token) == "ro"
    for token in ("deny", "ban", "禁用", "拉黑", "黑名单"):
        assert parse_policy_token(token) == "deny"
    assert parse_policy_token("whatever") is None


def test_remove_token():
    for token in ("移除", "删除", "清除", "remove", "DEL"):
        assert is_remove_token(token)
    assert not is_remove_token("只读")


# ---------- 热重载容器 ----------


def _bump_mtime(path: Path, offset_s: int) -> None:
    ns = path.stat().st_mtime_ns + offset_s * 1_000_000_000
    os.utime(path, ns=(ns, ns))


def test_missing_file_creates_default(tmp_path):
    path = tmp_path / "access.json"
    store = HotReloadJsonModelFile(AccessConfig, path)
    assert path.exists()
    assert store.current.default_policy == "rw"


def test_existing_file_loaded(tmp_path):
    path = tmp_path / "access.json"
    path.write_text(json.dumps({"default_policy": "ro"}), encoding="utf-8")
    store = HotReloadJsonModelFile(AccessConfig, path)
    assert store.current.default_policy == "ro"


def test_external_edit_hot_reloads(tmp_path):
    path = tmp_path / "access.json"
    store = HotReloadJsonModelFile(AccessConfig, path)
    assert store.current.users == {}
    path.write_text(json.dumps({"users": {"1": "deny"}}), encoding="utf-8")
    _bump_mtime(path, 1)
    assert store.current.users == {"1": "deny"}


def test_broken_json_keeps_last_good(tmp_path):
    path = tmp_path / "access.json"
    path.write_text(json.dumps({"default_policy": "ro"}), encoding="utf-8")
    store = HotReloadJsonModelFile(AccessConfig, path)
    path.write_text("{ broken", encoding="utf-8")
    _bump_mtime(path, 1)
    assert store.current.default_policy == "ro"


def test_invalid_policy_value_keeps_last_good(tmp_path):
    path = tmp_path / "access.json"
    store = HotReloadJsonModelFile(AccessConfig, path)
    path.write_text(json.dumps({"default_policy": "nope"}), encoding="utf-8")
    _bump_mtime(path, 1)
    assert store.current.default_policy == "rw"


def test_broken_then_fixed_reloads(tmp_path):
    path = tmp_path / "access.json"
    store = HotReloadJsonModelFile(AccessConfig, path)
    path.write_text("{ broken", encoding="utf-8")
    _bump_mtime(path, 1)
    assert store.current.default_policy == "rw"
    path.write_text(json.dumps({"default_policy": "deny"}), encoding="utf-8")
    _bump_mtime(path, 2)
    assert store.current.default_policy == "deny"


def test_deleted_file_falls_back_to_default(tmp_path):
    path = tmp_path / "access.json"
    path.write_text(json.dumps({"default_policy": "deny"}), encoding="utf-8")
    store = HotReloadJsonModelFile(AccessConfig, path)
    assert store.current.default_policy == "deny"
    path.unlink()
    assert store.current.default_policy == "rw"


def test_save_persists_and_round_trips(tmp_path):
    path = tmp_path / "access.json"
    store = HotReloadJsonModelFile(AccessConfig, path)
    store.current.groups["100"] = "ro"
    store.save()
    assert store.current.groups == {"100": "ro"}  # save 后不应误回滚
    reread = HotReloadJsonModelFile(AccessConfig, path)
    assert reread.current.groups == {"100": "ro"}
