from nonebot import on_command

from ._common import execute


list_cmd = on_command("list")


@list_cmd.handle()
async def _():
    output = await execute("list", "")
    if output:
        await list_cmd.finish(output)
