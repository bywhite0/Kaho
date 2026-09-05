"""gallery 授权集成测试：GALLERY_ADMIN 判定 + 画廊可见性/只读门对群管的约束

必须独立进程运行：nonebot.init、适配器注册与 LOCALSTORE_* 环境变量都是进程级的。
运行：python test_permission.py（run_tests.py 会以子进程方式调用）
"""

import asyncio
import os
import sys
import tempfile
import traceback
from pathlib import Path
from typing import ClassVar

_tmp = Path(tempfile.mkdtemp(prefix="gallery_perm_"))
os.environ["LOCALSTORE_DATA_DIR"] = str(_tmp / "data")
os.environ["LOCALSTORE_CACHE_DIR"] = str(_tmp / "cache")
os.environ["LOCALSTORE_CONFIG_DIR"] = str(_tmp / "config")

_PKG_NAME = Path(__file__).resolve().parents[1].name
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import importlib

import nonebot

nonebot.init(driver="~none", superusers={"1"}, log_level="WARNING")
assert nonebot.load_plugin(_PKG_NAME) is not None, "插件加载失败"

from nonebot.adapters.onebot.v11 import Adapter, Bot, GroupMessageEvent, PrivateMessageEvent
from nonebot.exception import FinishedException

nonebot.get_driver().register_adapter(Adapter)
BOT = Bot(nonebot.get_adapter(Adapter), "10000")

access = importlib.import_module(f"{_PKG_NAME}.access")
gallery = importlib.import_module(f"{_PKG_NAME}.gallery")
handler = importlib.import_module(f"{_PKG_NAME}.handler")
matcher = importlib.import_module(f"{_PKG_NAME}.matcher")
cfg = importlib.import_module(f"{_PKG_NAME}.config").cfg
gallery_name_data = importlib.import_module(f"{_PKG_NAME}.config").gallery_name_data

SUPERUSER_ID = "1"
"""与 nonebot.init(superusers=...) 保持一致"""

OWNER_ID, ADMIN_ID, MEMBER_ID = "2", "3", "4"

_TEXT = [{"type": "text", "data": {"text": "hi"}}]


def _group_event(user_id: str, role: str) -> GroupMessageEvent:
    """合成群消息事件；role 取 owner/admin/member，对应协议端上报的 sender.role"""
    return GroupMessageEvent.model_validate(
        {
            "time": 0,
            "self_id": 10000,
            "post_type": "message",
            "sub_type": "normal",
            "message_type": "group",
            "message_id": 1,
            "group_id": 999,
            "user_id": int(user_id),
            "message": _TEXT,
            "original_message": _TEXT,
            "raw_message": "hi",
            "font": 0,
            "anonymous": None,
            "sender": {"user_id": int(user_id), "role": role},
        }
    )


def _private_event(user_id: str) -> PrivateMessageEvent:
    return PrivateMessageEvent.model_validate(
        {
            "time": 0,
            "self_id": 10000,
            "post_type": "message",
            "sub_type": "friend",
            "message_type": "private",
            "message_id": 2,
            "user_id": int(user_id),
            "message": _TEXT,
            "original_message": _TEXT,
            "raw_message": "hi",
            "font": 0,
            "sender": {"user_id": int(user_id)},
        }
    )


class _FakeMatcher:
    """替代 Matcher：记录回复内容并以 FinishedException 中断，与真实 finish 语义一致"""

    replies: ClassVar[list[str]] = []

    @classmethod
    async def finish(cls, message="") -> None:
        cls.replies.append(str(message))
        raise FinishedException


async def _is_blocked(coro) -> bool:
    """门是否拦住了本次调用"""
    _FakeMatcher.replies.clear()
    try:
        await coro
    except FinishedException:
        return True
    return False


def _register_gallery(name: str) -> Path:
    gallery_dir = cfg.data_dir_path / name
    gallery_dir.mkdir(parents=True, exist_ok=True)
    gallery_name_data.instance.name_to_aliases.setdefault(name, [])
    gallery_name_data.save_to_file()
    return gallery_dir


# ---------- GALLERY_ADMIN 判定 ----------


async def test_superuser_is_admin_in_group_and_private():
    # 超管不受群职位与会话类型影响，即使在群里只是普通成员
    assert await access.GALLERY_ADMIN(BOT, _group_event(SUPERUSER_ID, "member"))
    assert await access.GALLERY_ADMIN(BOT, _private_event(SUPERUSER_ID))


async def test_group_owner_and_admin_are_admins_in_group():
    assert await access.GALLERY_ADMIN(BOT, _group_event(OWNER_ID, "owner"))
    assert await access.GALLERY_ADMIN(BOT, _group_event(ADMIN_ID, "admin"))


async def test_plain_member_is_not_admin():
    assert not await access.GALLERY_ADMIN(BOT, _group_event(MEMBER_ID, "member"))


async def test_group_admin_is_not_admin_in_private():
    """私聊里群职位无从判定，故群管在私聊一律不具备管理权（超管不受影响）。"""
    assert not await access.GALLERY_ADMIN(BOT, _private_event(ADMIN_ID))
    assert not await access.GALLERY_ADMIN(BOT, _private_event(OWNER_ID))


async def test_missing_role_falls_back_to_superuser_only():
    """协议端不上报 role 时判定失败，退回仅超管（fail-closed）。"""
    assert not await access.GALLERY_ADMIN(BOT, _group_event(ADMIN_ID, ""))


# ---------- 群管不越权：隐藏画廊 ----------


async def test_hidden_gallery_is_invisible_to_group_admin():
    """群管拿到管理权后仍不该看见运营方下架的画廊。"""
    name = "隐藏权限库"
    _register_gallery(name)
    gallery.set_gallery_mode(name, "off")
    event = _group_event(ADMIN_ID, "admin")

    assert await _is_blocked(handler._ensure_gallery_visible(_FakeMatcher, BOT, event, name))
    gallery.set_gallery_mode(name, "edit")


async def test_hidden_gallery_stays_visible_to_superuser():
    name = "隐藏超管库"
    _register_gallery(name)
    gallery.set_gallery_mode(name, "off")
    event = _group_event(SUPERUSER_ID, "member")

    assert not await _is_blocked(handler._ensure_gallery_visible(_FakeMatcher, BOT, event, name))
    gallery.set_gallery_mode(name, "edit")


# ---------- 群管不越权：只读画廊 ----------


async def test_readonly_gallery_rejects_group_admin_edit():
    """画廊模式仍是超管专属，群管不得绕过只读锁，否则该功能形同虚设。"""
    name = "只读权限库"
    _register_gallery(name)
    gallery.set_gallery_mode(name, "view")
    event = _group_event(ADMIN_ID, "admin")

    assert await _is_blocked(handler._ensure_gallery_editable(_FakeMatcher, BOT, event, name))
    assert "只读" in _FakeMatcher.replies[-1]
    gallery.set_gallery_mode(name, "edit")


async def test_readonly_gallery_allows_superuser_edit():
    name = "只读超管库"
    _register_gallery(name)
    gallery.set_gallery_mode(name, "view")
    event = _group_event(SUPERUSER_ID, "member")

    assert not await _is_blocked(handler._ensure_gallery_editable(_FakeMatcher, BOT, event, name))
    gallery.set_gallery_mode(name, "edit")


async def test_editable_gallery_allows_group_admin():
    name = "可写权限库"
    _register_gallery(name)
    event = _group_event(ADMIN_ID, "admin")

    assert not await _is_blocked(handler._ensure_gallery_editable(_FakeMatcher, BOT, event, name))


async def test_hidden_gallery_edit_reports_not_found_not_readonly():
    """隐藏画廊对群管要伪装成不存在，不能因为它同时是只读而暴露它的存在。"""
    name = "隐藏只读库"
    _register_gallery(name)
    gallery.set_gallery_mode(name, "off")
    event = _group_event(ADMIN_ID, "admin")

    assert await _is_blocked(handler._ensure_gallery_editable(_FakeMatcher, BOT, event, name))
    assert "未找到画廊" in _FakeMatcher.replies[-1]
    gallery.set_gallery_mode(name, "edit")


# ---------- 授权矩阵：谁能触发哪些命令 ----------

DELEGATED_COMMANDS = (
    "add_gallery",
    "remove_gallery_alias",
    "remove_picture",
    "set_gallery_cover_cmd",
    "gallery_dedupe",
)
"""下放给群管的管理命令（matcher 变量名）"""

SUPERUSER_ONLY_COMMANDS = ("remove_gallery", "gallery_mode_ctrl", "export_gallery", "gallery_access_ctrl")
"""必须保持超管专属：删除画廊、画廊模式、导出画廊、画廊权限"""


async def test_group_admin_can_trigger_delegated_commands():
    event = _group_event(ADMIN_ID, "admin")
    for var in DELEGATED_COMMANDS:
        cmd = getattr(matcher, var)
        assert await cmd.permission(BOT, event), var


async def test_group_admin_cannot_trigger_superuser_only_commands():
    """删除画廊/画廊模式/导出画廊/画廊权限 的爆炸半径太大，必须挡住群管。"""
    event = _group_event(ADMIN_ID, "admin")
    for var in SUPERUSER_ONLY_COMMANDS:
        cmd = getattr(matcher, var)
        assert not await cmd.permission(BOT, event), var


async def test_superuser_can_trigger_every_admin_command():
    event = _group_event(SUPERUSER_ID, "member")
    for var in DELEGATED_COMMANDS + SUPERUSER_ONLY_COMMANDS:
        cmd = getattr(matcher, var)
        assert await cmd.permission(BOT, event), var


async def test_plain_member_cannot_trigger_any_admin_command():
    event = _group_event(MEMBER_ID, "member")
    for var in DELEGATED_COMMANDS + SUPERUSER_ONLY_COMMANDS:
        cmd = getattr(matcher, var)
        assert not await cmd.permission(BOT, event), var


async def test_group_admin_loses_delegated_commands_in_private():
    """私聊无群职位可判，下放的命令对群管一律不触发。"""
    event = _private_event(ADMIN_ID)
    for var in DELEGATED_COMMANDS:
        cmd = getattr(matcher, var)
        assert not await cmd.permission(BOT, event), var


# ---------- 黑白名单优先于群职位 ----------


def _set_group_policy(group_id: str, policy: str | None) -> None:
    config = access.access_data.current
    if policy is None:
        config.groups.pop(group_id, None)
    else:
        config.groups[group_id] = policy
    access.access_data.save()


async def test_blacklist_outranks_group_role():
    """所在群被降级为只读/禁用时，群管一条管理命令都用不了——运营方名单优先。"""
    event = _group_event(ADMIN_ID, "admin")
    try:
        for policy in ("ro", "deny"):
            _set_group_policy("999", policy)
            assert not await access.gallery_writable(BOT, event), policy
        _set_group_policy("999", "rw")
        assert await access.gallery_writable(BOT, event)
    finally:
        _set_group_policy("999", None)


async def test_blacklist_never_blocks_superuser():
    """超管豁免名单，否则运营方可能把自己锁在外面。"""
    event = _group_event(SUPERUSER_ID, "member")
    try:
        _set_group_policy("999", "deny")
        assert await access.gallery_writable(BOT, event)
    finally:
        _set_group_policy("999", None)


def main() -> int:
    failed: list[str] = []
    passed = 0
    for case_name in sorted(name for name in globals() if name.startswith("test_")):
        try:
            asyncio.run(globals()[case_name]())
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
