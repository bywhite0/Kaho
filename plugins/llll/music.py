from nonebot import on_command
from nonebot.adapters.console import Message
from nonebot.params import CommandArg

from ._common import execute


music_cmd = on_command("music")


@music_cmd.handle()
async def _(args: Message = CommandArg()):
    output = await execute("music", args.extract_plain_text().strip())
    if output:
        await music_cmd.finish(output)
