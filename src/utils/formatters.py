import re


def parse_intro(intro_text):
    data = {}
    labels = [
        "誕生日",
        "身長",
        "趣味",
        "特技",
        "好きな食べ物",
        "好きな言葉",
        "好きな教科",
        "好きな動物",
    ]
    label_map = {
        "誕生日": "Birthday",
        "身長": "Height",
        "趣味": "Hobbies",
        "特技": "Special Skills",
        "好きな食べ物": "Favorite Food",
        "好きな言葉": "Favorite Word",
        "好きな教科": "Favorite Subject",
        "好きな動物": "Favorite Animal",
    }
    lines = intro_text.split("\n")
    for line in lines:
        segments = [s for s in re.split(r"[\s　]+", line.strip()) if s]
        for i, seg in enumerate(segments):
            if (
                seg in labels
                and i + 1 < len(segments)
                and segments[i + 1] not in labels
            ):
                data[label_map[seg]] = segments[i + 1]
    return data


def _build_skill_view_impl(
    dm, skill_data, title_prefix="", cost_str="", show_type=True, visited=None
):
    if not skill_data:
        return None
    current_id = skill_data.get("id")
    visited_set = set(visited or set())
    if current_id is not None and current_id in visited_set:
        return None
    if current_id is not None:
        visited_set.add(current_id)
    res = dm.get_merged_skill_desc(skill_data)
    if not res:
        return None
    ranges = []
    for entry in res.get("ranges") or []:
        start_level = entry.get("start_level")
        end_level = entry.get("end_level")
        value = entry.get("value") or "-"
        if start_level is None or end_level is None:
            continue
        if start_level == end_level:
            label = f"Lv.{start_level}"
        else:
            label = f"Lv.{start_level}-{end_level}"
        ranges.append({"label": label, "value": value})

    token_data = res.get("token") or {}
    token_skill = _build_skill_view_impl(
        dm,
        token_data.get("skill"),
        title_prefix="技能:",
        show_type=False,
        visited=visited_set,
    )
    token_ability = _build_skill_view_impl(
        dm,
        token_data.get("ability"),
        title_prefix="特性:",
        show_type=False,
        visited=visited_set,
    )
    token_view = None
    if token_skill or token_ability:
        token_view = {"skill": token_skill, "ability": token_ability}

    return {
        "title_prefix": title_prefix,
        "name": res.get("name") or "",
        "template": res.get("template") or "",
        "cost": cost_str,
        "type": skill_data.get("main_effect") if show_type else "",
        "ranges": ranges,
        "token": token_view,
    }


def build_skill_view(dm, skill_data, title_prefix="", cost_str="", show_type=True):
    return _build_skill_view_impl(
        dm,
        skill_data,
        title_prefix=title_prefix,
        cost_str=cost_str,
        show_type=show_type,
    )


def _render_skill_view_text(view, lines=None, indent=0):
    if not view:
        return ""
    if lines is None:
        lines = []
    prefix = " " * indent
    title = f"{view.get('title_prefix', '')}{view.get('name', '')}".strip()
    cost = view.get("cost") or ""
    typ = view.get("type") or ""
    if typ:
        lines.append(f"{prefix}{title}{cost} [Type: {typ}]")
    else:
        lines.append(f"{prefix}{title}{cost}")
    template = view.get("template") or ""
    if template:
        lines.append(f"{prefix}Effect: {template}")
    for row in view.get("ranges") or []:
        lines.append(f"{prefix}{row.get('label')}: {row.get('value')}")
    token = view.get("token") or {}
    if token:
        lines.append(f"{prefix}[Added Card Info]")
    if token.get("skill"):
        _render_skill_view_text(token.get("skill"), lines, indent + 2)
    if token.get("ability"):
        _render_skill_view_text(token.get("ability"), lines, indent + 2)
    return "\n".join(lines).rstrip()


def print_merged_skill(dm, skill_data, title_prefix="", cost_str="", show_type=True):
    view = build_skill_view(
        dm,
        skill_data,
        title_prefix=title_prefix,
        cost_str=cost_str,
        show_type=show_type,
    )
    return _render_skill_view_text(view)
