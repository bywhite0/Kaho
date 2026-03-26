from nonebot import on_command
from nonebot.adapters.onebot.v11 import Message
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER

from src.core.services.game_api import refresh_with_live_data


update_cmd = on_command("update", permission=SUPERUSER)

HELP_TEXT = "用法:\n/update with_live - 刷新当前 with_live 信息"


@update_cmd.handle()
async def _(args: Message = CommandArg()):
    raw_args = args.extract_plain_text().strip()
    if not raw_args:
        await update_cmd.finish(HELP_TEXT)
        return

    if raw_args != "with_live":
        await update_cmd.finish(f"不支持的更新参数: {raw_args}\n{HELP_TEXT}")
        return

    try:
        result = await refresh_with_live_data(command_args=raw_args)
    except Exception as exc:
        await update_cmd.finish(f"刷新失败: {exc}")
        return

    source = result.get("source") or {}
    updated_at = str(result.get("updated_at") or "-")
    cache_path = str(result.get("cache_path") or "-")
    latest_archive = result.get("latest_archive") or {}
    latest_meta = result.get("latest_archive_detail_meta") or {}
    home_total = int(source.get("archive_get_home_count") or 0)
    home_live = int(source.get("archive_get_home_live_count") or 0)
    home_trailer = int(source.get("archive_get_home_trailer_count") or 0)
    latest_archive_id = str(
        latest_archive.get("archives_id")
        or latest_archive.get("live_id")
        or "-"
    )
    latest_archive_name = str(latest_archive.get("name") or "-")
    latest_source = str(latest_meta.get("source") or "-")
    latest_status = "已获取" if latest_archive and latest_meta.get("source") != "none" else "未获取"

    output = (
        "with_live 数据刷新完成\n"
        f"home 总场次: {home_total}\n"
        f"home live_archive: {home_live}\n"
        f"home trailer_archive: {home_trailer}\n"
        f"最新 Archive ID: {latest_archive_id}\n"
        f"最新 Archive 标题: {latest_archive_name}\n"
        f"最新详情: {latest_status}\n"
        f"详情来源: {latest_source}\n"
        f"缓存文件: {cache_path}\n"
        f"刷新时间: {updated_at}"
    )
    await update_cmd.finish(output)
