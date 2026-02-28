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


def print_merged_skill(
    dm, skill_data, title_prefix="", is_token=False, cost_str="", show_type=True
):
    if not skill_data:
        return ""
    res = dm.get_merged_skill_desc(skill_data)
    if not res:
        return ""
    lines = []
    indent = "    " if is_token else "  "
    prefix = "  - " if is_token else title_prefix
    type_str = ""
    if show_type and not is_token and "main_effect" in skill_data:
        type_str = f" [Type: {skill_data['main_effect']}]"
    lines.append(f"{prefix}{res['name']}{cost_str}{type_str}")
    lines.append(f"{indent}Effect: {res['template']}")
    if res["ranges"]:
        lines.append(f"{indent}Values: ")
        parts = []
        for start, end, val in res["ranges"]:
            label = f"Lv.{start}" if start == end else f"Lv.{start}-{end}"
            parts.append(f"{label}: {val}")
        line = []
        for p in parts:
            line.append(p)
            if len(line) == 3:
                lines.append(" | ".join(line))
                lines.append(f"{indent}        ")
                line = []
        if line:
            lines.append(" | ".join(line))
    if res.get("token"):
        lines.append(f"{indent}[Added Card Info]")
        nested = print_merged_skill(dm, res["token"], is_token=True, show_type=False)
        if nested:
            lines.append(nested)
    return "\n".join(lines).rstrip()
