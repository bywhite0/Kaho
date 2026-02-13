from nonebot import on_command
from nonebot.adapters.console import Message
from nonebot.params import CommandArg

from ._common import execute


card_cmd = on_command("card")


@card_cmd.handle()
async def _(args: Message = CommandArg()):
    output = await execute("card", args.extract_plain_text().strip())
    if output:
        await card_cmd.finish(output)
