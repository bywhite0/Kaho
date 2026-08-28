# 对齐 Kozue 各 route 的 Pydantic 请求模型（schema_version=1），
# 只传绘图所需字段与稳定资源引用，不传原始 masterdata。

from src.utils.formatters import parse_intro

LIST_RENDER_ROUTE = "/api/llll/list"
CHARA_RENDER_ROUTE = "/api/llll/chara"

# 档案字段顺序即展示顺序，key 为 parse_intro 的解析结果键
_CHARA_PROFILE_LABELS = [
    ("Birthday", "生日"),
    ("Height", "身高"),
    ("Hobbies", "兴趣"),
    ("Special Skills", "特长"),
    ("Favorite Food", "喜欢的食物"),
    ("Favorite Word", "喜欢的一句话"),
    ("Favorite Subject", "喜欢的科目"),
    ("Favorite Animal", "喜欢的动物"),
]


def build_list_render_payload(dm) -> dict:
    """构建 llll.list 渲染 payload。角色为空时抛 ValueError。"""
    characters = []
    for char_id in sorted(dm.get_character_ids()):
        item = {
            "id": char_id,
            "name": dm.get_character_name(char_id),
            "generation": dm.get_generation_str(char_id) or None,
            "unit": dm.get_character_unit(char_id),
            "icon": {"type": "chara_icon", "id": str(char_id)},
        }
        color = dm.get_character_theme_color(char_id)
        # 无主题色时省略字段，交给服务端默认值
        if color:
            item["color"] = color
        characters.append(item)
    if not characters:
        raise ValueError("角色列表为空，无法构建 list 渲染 payload")
    return {
        "schema_version": "1",
        "kind": "llll.list",
        "locale": "zh-CN",
        "theme": "light",
        "data": {
            "title": "蓮ノ空 角色一览",
            "subtitle": "Link! Like! ラブライブ！",
            "characters": characters,
        },
    }


def _parse_profile_items(introduction) -> list:
    parsed = parse_intro(str(introduction or ""))
    items = []
    for key, label in _CHARA_PROFILE_LABELS:
        value = str(parsed.get(key) or "").strip()
        if value:
            items.append({"label": label, "value": value})
    return items


def build_chara_profile_items(dm, char_id) -> list:
    """解析角色档案为 label/value 列表。

    最终版 masterdata 已清空 Characters.Introduction，档案 stats 移入
    MemberProfiles 各条目的 Introduction；取最新条目，失败再回退旧字段。
    """
    profiles = dm.get_member_profiles(char_id)
    if profiles:
        items = _parse_profile_items(profiles[-1].get("introduction"))
        if items:
            return items
    char = dm.get_character(char_id) or {}
    return _parse_profile_items(char.get("Introduction"))


def build_chara_render_payload(dm, char_id) -> dict:
    """构建 llll.chara 渲染 payload。无可用 MemberProfiles 时抛 ValueError。"""
    gen = dm.get_generation_str(char_id)
    # 每条 MemberProfile 对应一个时间点立绘；带毕业简介的条目只贡献毕业寄语，
    # 不进时间线（卒業後立绘资源不存在）；个别条目无 DisplayGeneration（如沙知），
    # 时间点标签回退角色自身期数
    timelines = []
    graduate_message = None
    for p in dm.get_member_profiles(char_id):
        grad_text = str(p.get("graduate_introduction") or "").strip()
        if grad_text:
            # 原文含游戏 UI 的硬换行，拼回整段交给绘图服务按宽度换行
            graduate_message = grad_text.replace("\n", "")
            continue
        stand_id = p.get("stand_image_id")
        generation = str(p.get("generation") or "").strip() or gen
        if not stand_id or not generation:
            continue
        timelines.append(
            {
                "generation": generation,
                "stand": {"type": "image_chara_stand", "id": str(stand_id)},
            }
        )
    if not timelines:
        raise ValueError(f"角色 {char_id} 无 MemberProfiles，无法构建 chara 渲染 payload")

    char = dm.get_character(char_id) or {}
    character = {
        "id": char_id,
        "name": dm.get_character_name(char_id),
        "generation": f"蓮ノ空女学院 {gen}生" if gen else None,
        "unit": dm.get_character_unit(char_id),
        "cv": char.get("CharacterVoice"),
    }
    # 无主题色时省略字段，交给服务端默认值
    color = dm.get_character_theme_color(char_id)
    if color:
        character["color"] = color

    gifts = []
    gift_icons = {}
    for g in dm.get_favorite_gifts(char_id):
        gift_id = g.get("id")
        name = str(g.get("name") or "").strip()
        rank = g.get("rank")
        if gift_id is None or not name or not isinstance(rank, int):
            continue
        icon = {"type": "icon_item", "id": str(gift_id)}
        gifts.append({"id": gift_id, "name": name, "rank": rank, "icon": icon})
        gift_icons[str(gift_id)] = icon

    costumes = [
        {"label": label, "values": values}
        for label, values in dm.get_costume_models_by_character(char_id).items()
    ]

    data = {
        "character": character,
        "profile": build_chara_profile_items(dm, char_id),
        "timelines": timelines,
        "gifts": gifts,
        "costumes": costumes,
    }
    if graduate_message:
        data["graduate_message"] = graduate_message

    assets = {"icon": {"type": "chara_icon", "id": str(char_id)}}
    unit_id = dm.get_character_unit_id(char_id)
    if unit_id:
        assets["unit_logo"] = {"type": "unit_logo", "id": str(unit_id)}
    if gift_icons:
        assets["gift_icons"] = gift_icons

    return {
        "schema_version": "1",
        "kind": "llll.chara",
        "locale": "zh-CN",
        "theme": "light",
        "data": data,
        "assets": assets,
    }
