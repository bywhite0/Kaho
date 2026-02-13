import os

import nonebot
from nonebot.adapters.console import Adapter as ConsoleAdapter

from src.core.services.dm_provider import init_dm


nonebot.init()
driver = nonebot.get_driver()
driver.register_adapter(ConsoleAdapter)
nonebot.load_plugin("nonebot_plugin_localstore")
plugin_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "src", "plugins", "llll"))
nonebot.load_plugins(plugin_dir)


@driver.on_startup
async def _():
    await init_dm()

if __name__ == "__main__":
    nonebot.run()
