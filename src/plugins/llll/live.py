from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageSegment

from src.core.services.with_live_image import generate_with_live_image


live_cmd = on_command("live")


@live_cmd.handle()
async def _():
    try:
        img_bytes = await generate_with_live_image(auto_refresh_on_miss=True)
    except Exception as exc:
        await live_cmd.finish(f"生成直播信息图片失败: {exc}")
        return
    await live_cmd.finish(MessageSegment.image(img_bytes))
