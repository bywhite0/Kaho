"""黑白名单读写权限：NoneBot 粘合层（Rule 检查器与热更新存取）"""

from nonebot.adapters.onebot.v11 import Bot as OneBot
from nonebot.adapters.onebot.v11 import GroupMessageEvent
from nonebot.adapters.onebot.v11 import MessageEvent as OneBotMessageEvent
from nonebot.permission import SUPERUSER

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
    """超级用户可越过画廊自身的 view/off 模式限制"""
    return await SUPERUSER(bot, event)
