import os

import nonebot
from nonebot.adapters.onebot.v11 import Adapter as ONEBOT_V11Adapter

from src.core.services.dm_provider import init_dm
from src.core.services.draw_api import close_draw_api_service
from src.core.services.t2i import close_t2i_service

nonebot.init()
driver = nonebot.get_driver()
# driver.register_adapter(ConsoleAdapter)
driver.register_adapter(ONEBOT_V11Adapter)
plugin_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "src", "plugins"))
nonebot.load_plugins(plugin_dir)


@driver.on_startup
async def _on_startup():
    await init_dm()


@driver.on_shutdown
async def _on_shutdown():
    await close_t2i_service()
    await close_draw_api_service()


if __name__ == "__main__":
    nonebot.run()
