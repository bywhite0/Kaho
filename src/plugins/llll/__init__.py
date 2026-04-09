import nonebot
from pathlib import Path

sub_plugins = nonebot.load_plugins(
    str(Path(__file__).parent.resolve())
)