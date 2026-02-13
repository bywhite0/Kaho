from src.core.services.dm_provider import get_dm, get_paths, init_dm


async def get_dm_instance():
    dm = get_dm()
    if dm is None:
        dm = await init_dm()
    return dm


def get_version_path():
    return get_paths()[2]
