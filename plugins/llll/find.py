from nonebot import on_command
from nonebot.adapters.console import Message
from nonebot.params import CommandArg

from ._common import execute


find_cmd = on_command("find")


@find_cmd.handle()
async def _(args: Message = CommandArg()):
    output = await execute("find", args.extract_plain_text().strip())
    if output:
        await find_cmd.finish(output)
