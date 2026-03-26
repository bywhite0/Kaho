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
    latest_archive = result.get("latest_archive_any") or result.get("latest_archive") or {}
    latest_meta = result.get("latest_archive_any_meta") or {}
    home_total = int(
        source.get("archive_get_home_total_count")
        or source.get("archive_get_home_count")
        or 0
    )
    home_with = int(
        source.get("archive_get_home_with_count")
        or source.get("archive_get_home_live_count")
        or 0
    )
    home_fes = int(source.get("archive_get_home_fes_count") or 0)
    enterable_total = int(source.get("enterable_total_count") or 0)
    enterable_with = int(source.get("enterable_with_count") or 0)
    enterable_fes = int(source.get("enterable_fes_count") or 0)
    detail_success = int(source.get("enter_detail_success_count") or 0)
    detail_failed = int(source.get("enter_detail_failed_count") or 0)
    latest_archive_id = str(
        latest_archive.get("archives_id")
        or latest_archive.get("live_id")
        or "-"
    )
    latest_archive_name = str(latest_archive.get("name") or "-")
    latest_source = str(latest_meta.get("source") or "-")
    fetch_errors = source.get("fetch_errors")
    if not isinstance(fetch_errors, list):
        fetch_errors = []

    output = (
        "with_live 数据刷新完成\n"
        f"home 总场次: {home_total}\n"
        f"home With×MEETS: {home_with}\n"
        f"home Fes×LIVE: {home_fes}\n"
        f"可进场总数: {enterable_total}\n"
        f"可进场 With×MEETS: {enterable_with}\n"
        f"可进场 Fes×LIVE: {enterable_fes}\n"
        f"详情成功: {detail_success}\n"
        f"详情失败: {detail_failed}\n"
        f"最新 Archive ID: {latest_archive_id}\n"
        f"最新 Archive 标题: {latest_archive_name}\n"
        f"最新 Archive 来源: {latest_source}\n"
        f"抓取告警: {len(fetch_errors)}\n"
        f"缓存文件: {cache_path}\n"
        f"刷新时间: {updated_at}"
    )
    await update_cmd.finish(output)
