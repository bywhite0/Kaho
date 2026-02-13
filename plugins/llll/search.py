from nonebot import on_command
from nonebot.adapters.console import Message
from nonebot.params import CommandArg

from ._common import execute


search_cmd = on_command("search")


@search_cmd.handle()
async def _(args: Message = CommandArg()):
    output = await execute("search", args.extract_plain_text().strip())
    if output:
        await search_cmd.finish(output)
