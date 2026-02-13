import os

import nonebot
from nonebot.adapters.console import Adapter as ConsoleAdapter

from bot.services.dm_provider import init_dm


nonebot.init()
driver = nonebot.get_driver()
driver.register_adapter(ConsoleAdapter)
plugin_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "plugins", "llll"))
nonebot.load_plugins(plugin_dir)


@driver.on_startup
async def _():
    await init_dm()

if __name__ == "__main__":
    nonebot.run()
