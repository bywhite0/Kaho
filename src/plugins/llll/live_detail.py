from nonebot import on_command
from nonebot.adapters.onebot.v11 import Message, MessageSegment
from nonebot.params import CommandArg

from src.core.services.with_live_image import generate_with_live_detail_image

live_detail_cmd = on_command("live_detail")

HELP_TEXT = "用法: /live_detail [序号] [--spoiler]，序号需为正整数"


@live_detail_cmd.handle()
async def _(args: Message = CommandArg()):
    raw_args = args.extract_plain_text().strip()
    if not raw_args:
        await live_detail_cmd.finish(HELP_TEXT)
        return

    arg_parts = raw_args.split()
    if len(arg_parts) not in (1, 2):
        await live_detail_cmd.finish(f"参数错误，请检查参数格式。\n{HELP_TEXT}")
        return

    try:
        index = int(arg_parts[0])
    except ValueError:
        await live_detail_cmd.finish(f"参数错误，请输入正整数序号。\n{HELP_TEXT}")
        return

    show_spoiler = False
    if len(arg_parts) == 2:
        if arg_parts[1] != "--spoiler":
            await live_detail_cmd.finish(f"参数错误，不支持的参数: {arg_parts[1]}\n{HELP_TEXT}")
            return
        show_spoiler = True

    if index <= 0:
        await live_detail_cmd.finish(f"参数错误，请输入正整数序号。\n{HELP_TEXT}")
        return

    try:
        img_bytes = await generate_with_live_detail_image(
            index=index,
            auto_refresh_on_miss=True,
            show_spoiler=show_spoiler,
        )
    except Exception as exc:
        await live_detail_cmd.finish(f"生成直播详情图失败: {exc}")
        return

    await live_detail_cmd.finish(MessageSegment.image(img_bytes))
