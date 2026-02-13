from nonebot import on_command

from src.core.data_manager import DataManager
from src.plugins.llll._common import get_dm_instance, get_version_path


dbrebuild_cmd = on_command("dbrebuild")


@dbrebuild_cmd.handle()
async def _():
    dm = await get_dm_instance()
    inserted = dm.store.rebuild(get_version_path(), dm.sanitize_yaml)
    output = f"数据库已重建，新增行数: {inserted}"
    if output:
        await dbrebuild_cmd.finish(output)
