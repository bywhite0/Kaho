from nonebot import on_command
from nonebot.adapters.console import Message
from nonebot.params import CommandArg

from ._common import execute


comic_cmd = on_command("comic")


@comic_cmd.handle()
async def _(args: Message = CommandArg()):
    output = await execute("comic", args.extract_plain_text().strip())
    if output:
        await comic_cmd.finish(output)
