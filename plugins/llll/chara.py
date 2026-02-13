from nonebot import on_command
from nonebot.adapters.console import Message
from nonebot.params import CommandArg

from ._common import execute


chara_cmd = on_command("chara")


@chara_cmd.handle()
async def _(args: Message = CommandArg()):
    output = await execute("chara", args.extract_plain_text().strip())
    if output:
        await chara_cmd.finish(output)
