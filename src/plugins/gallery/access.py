"""黑白名单读写权限：NoneBot 粘合层（Rule 检查器与热更新存取）"""

from nonebot.adapters.onebot.v11 import Bot as OneBot
from nonebot.adapters.onebot.v11 import GroupMessageEvent
from nonebot.adapters.onebot.v11 import MessageEvent as OneBotMessageEvent
from nonebot.adapters.onebot.v11.permission import GROUP_ADMIN, GROUP_OWNER
from nonebot.permission import SUPERUSER, Permission

from .access_core import (
    POLICY_LABELS,
    AccessConfig,
    HotReloadJsonModelFile,
    Policy,
    resolve_policy,
)
from .config import cfg

access_data = HotReloadJsonModelFile(AccessConfig, cfg.access_data_file_path)


async def resolve_event_policy(bot: OneBot, event: OneBotMessageEvent) -> Policy:
    group_id = str(event.group_id) if isinstance(event, GroupMessageEvent) else None
    return resolve_policy(
        access_data.current,
        event.get_user_id(),
        group_id,
        is_superuser=await SUPERUSER(bot, event),
    )


async def gallery_readable(bot: OneBot, event: OneBotMessageEvent) -> bool:
    """Rule：读命令要求 rw 或 ro，不满足时静默不响应"""
    return await resolve_event_policy(bot, event) != "deny"


async def gallery_writable(bot: OneBot, event: OneBotMessageEvent) -> bool:
    """Rule：写命令要求 rw，不满足时静默不响应"""
    return await resolve_event_policy(bot, event) == "rw"


def format_access_config(config: AccessConfig) -> str:
    lines = [f"画廊权限（默认策略：{POLICY_LABELS[config.default_policy]}）"]
    if config.groups:
        lines.append("群名单：")
        lines += [f"  {gid}：{POLICY_LABELS[p]}" for gid, p in config.groups.items()]
    if config.users:
        lines.append("用户名单：")
        lines += [f"  {uid}：{POLICY_LABELS[p]}" for uid, p in config.users.items()]
    if not config.groups and not config.users:
        lines.append("名单为空")
    lines.append("超级用户始终不受限制")
    return "\n".join(lines)


async def is_superuser(bot: OneBot, event: OneBotMessageEvent) -> bool:
    """运营方越权：可越过画廊自身的 view/off 模式限制，并看见 off 画廊的内容。

    与 GALLERY_ADMIN（能否执行管理命令）刻意分开：群管获得管理能力后，仍不该
    绕过运营方设的只读锁，也不该看见运营方下架的画廊。
    """
    return await SUPERUSER(bot, event)


GALLERY_ADMIN: Permission = SUPERUSER | GROUP_ADMIN | GROUP_OWNER
"""可执行画廊管理命令：超级用户，或群聊中的群主/群管理员。

群职位取自消息事件的 sender.role，不额外请求协议端；私聊事件不匹配 GROUP_ADMIN /
GROUP_OWNER 的入参类型，会被依赖解析跳过，故私聊仅超级用户可用。协议端不提供
role 时判定失败，退回仅超级用户（fail-closed）。

它只管「能否触发命令」，不放宽画廊的 view/off 模式——后者仍由 is_superuser 把关。
"""
