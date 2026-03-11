from src.core.services.dm_provider import get_dm, get_paths, init_dm
from src.utils.formatters import build_skill_view


async def get_dm_instance():
    dm = get_dm()
    if dm is None:
        dm = await init_dm()
    return dm


def get_version_path():
    return get_paths()[2]


def build_skill_block(dm, skill_data, title_prefix, cost_str="", show_type=True):
    view = build_skill_view(
        dm,
        skill_data,
        title_prefix,
        cost_str=cost_str,
        show_type=show_type,
    )
    icon_id = skill_data.get("icon_id") if skill_data else None
    return view, icon_id


def build_state_images(dm, card_id, series_id):
    raw_images = dm.get_image_set(card_id)
    images = {}
    for key in raw_images:
        if key == "deck_frame_chara":
            images[key] = series_id
        else:
            images[key] = card_id
    full_image = images.pop("full", None)
    deck_frame = images.pop("deck_frame_chara", None)
    return full_image, deck_frame, images
