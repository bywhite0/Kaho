import asyncio

from nonebot import on_command
from nonebot.permission import SUPERUSER
from src.plugins.llll._common import get_dm_instance, get_version_path


dbrebuild_cmd = on_command("dbrebuild", permission=SUPERUSER)


@dbrebuild_cmd.handle()
async def _():
    dm = await get_dm_instance()
    changed = await asyncio.to_thread(
        dm.store.rebuild,
        get_version_path(),
        dm.sanitize_yaml,
    )
    dm.reset_runtime_cache()
    output = f"数据库已重建，变更行数: {changed}"
    if output:
        await dbrebuild_cmd.finish(output)
