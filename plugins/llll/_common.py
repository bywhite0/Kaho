from bot.commands import run_command
from bot.services.dm_provider import get_dm, init_dm


async def execute(cmd, args):
    dm = get_dm()
    if dm is None:
        dm = await init_dm()
    line = cmd if not args else f"{cmd} {args}"
    return await run_command(dm, line)
