# 对齐 Kozue 各 route 的 Pydantic 请求模型（schema_version=1），
# 只传绘图所需字段与稳定资源引用，不传原始 masterdata。

LIST_RENDER_ROUTE = "/api/llll/list"


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
