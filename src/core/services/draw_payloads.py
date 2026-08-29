# 对齐 Kozue 各 route 的 Pydantic 请求模型（schema_version=1），
# 只传绘图所需字段与稳定资源引用，不传原始 masterdata。

import re

from src.utils.formatters import parse_intro

LIST_RENDER_ROUTE = "/api/llll/list"
CHARA_RENDER_ROUTE = "/api/llll/chara"
FIND_RENDER_ROUTE = "/api/llll/find"
MUSIC_RENDER_ROUTE = "/api/llll/music"

# 未实装占位卡（？？？）的 OrderId 哨兵值，不进入画廊
_PLACEHOLDER_ORDER_ID = 99999999

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


def _collect_profile_eras(dm, char_id) -> list:
    """按时间顺序返回 (期数标签, 档案解析结果)，解析不出档案的条目跳过。"""
    gen = dm.get_generation_str(char_id)
    eras = []
    for p in dm.get_member_profiles(char_id):
        parsed = parse_intro(str(p.get("introduction") or ""))
        if not parsed:
            continue
        label = str(p.get("generation") or "").strip() or gen
        eras.append((label, parsed))
    return eras


def _era_range_label(start: str, end: str, final_era: str) -> str:
    """取值适用区间的 badge 文本。

    延续到最后一期的是开放区间，一律「起〜」（即使起点就是最后一期），
    避免被误读成仅该期适用；中途结束的封闭段用单期或区间。
    """
    if end == final_era:
        return f"{start}〜"
    if start == end:
        return start
    m_start = re.match(r"^(\d+)期$", start)
    m_end = re.match(r"^\d+期$", end)
    if m_start and m_end:
        return f"{m_start.group(1)}〜{end}"
    return f"{start}〜{end}"


def _split_profile_items(value: str):
    """顿号列表拆项；出现括号被拆断等歧义时返回 None，交回整值路径。"""
    items = [s.strip() for s in value.split("、") if s.strip()]
    for item in items:
        if item.count("（") != item.count("）") or item.count("(") != item.count(")"):
            return None
    return items


def _try_profile_segments(present: list, final_era: str):
    """项目级细分：各年度均为前一年度列表的尾部追加时，按项标注新增区间。"""
    prev = []
    first_seen = {}
    for era_label, value in present:
        items = _split_profile_items(value)
        if items is None or items[: len(prev)] != prev:
            return None
        for item in items[len(prev) :]:
            first_seen[item] = era_label
        prev = items
    base_era = present[0][0]
    field_final = present[-1][0]
    segments = []
    for item in prev:
        seg = {"text": item}
        if first_seen[item] != base_era:
            seg["generation"] = _era_range_label(first_seen[item], field_final, final_era)
        segments.append(seg)
    return segments


def _profile_value_runs(present: list, final_era: str) -> list:
    """整值历史：按取值变化切分连续段，badge 标注各段适用区间。"""
    runs = []
    for era_label, value in present:
        if runs and runs[-1]["value"] == value:
            runs[-1]["end"] = era_label
        else:
            runs.append({"value": value, "start": era_label, "end": era_label})
    return [
        {
            "value": r["value"],
            "generation": _era_range_label(r["start"], r["end"], final_era),
        }
        for r in runs
    ]


def build_chara_profile_items(dm, char_id) -> list:
    """解析角色档案为 label/value 列表。

    最终版 masterdata 已清空 Characters.Introduction，档案 stats 移入
    MemberProfiles 各条目的 Introduction。取值随年度变化时：追加式的顿号
    列表输出项目级 segments，仅新增项带期数 badge；整体替换输出 values
    整值历史。全部解析失败再回退旧字段。
    """
    eras = _collect_profile_eras(dm, char_id)
    if not eras:
        char = dm.get_character(char_id) or {}
        return _parse_profile_items(char.get("Introduction"))
    final_era = eras[-1][0]
    items = []
    for key, label in _CHARA_PROFILE_LABELS:
        present = []
        for era_label, parsed in eras:
            value = str(parsed.get(key) or "").strip()
            if value:
                present.append((era_label, value))
        if not present:
            continue
        item = {"label": label, "value": present[-1][1]}
        if len({value for _, value in present}) > 1:
            segments = _try_profile_segments(present, final_era)
            if segments is not None:
                item["segments"] = segments
            else:
                item["values"] = _profile_value_runs(present, final_era)
        items.append(item)
    return items


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


def build_find_render_payload(dm, char_id) -> dict:
    """构建 llll.find 渲染 payload。角色无可展示卡牌时抛 ValueError。

    每个卡系列展示特训前/特训后两种形态（Id 末位 0/1）；无 0 形态的系列
    （生日、偶活、LR/DR/BR 等）只展示唯一形态且不带 form 角标。
    """
    by_series = {}
    for c in dm.get_cards_by_character(char_id):
        by_series.setdefault(c["CardSeriesId"], []).append(c)

    display_cards = []
    series_rarities = []
    for sid, entries in sorted(by_series.items()):
        head = entries[0]
        if head.get("OrderId") == _PLACEHOLDER_ORDER_ID:
            continue
        limited_type = dm.get_card_series_meta(sid).get("LimitedType")
        series_label = dm.LIMITED_TYPES.get(
            limited_type,
            f"Type {limited_type}" if limited_type is not None else None,
        )
        form0 = next((c for c in entries if c["Id"] % 10 == 0), None)
        form1 = next((c for c in entries if c["Id"] % 10 == 1), None)
        # 音击联动卡特训前后卡面相同，只展示特训前（对齐 /card 行为）
        if limited_type == 202 and form0 is not None:
            form1 = None
        shown = [c for c in (form0, form1) if c is not None]
        if not shown:
            continue
        rarity_name = dm.get_rarity_name(head["Rarity"])
        for c in shown:
            item = {
                "id": c["Id"],
                "name": c["Name"],
                "rarity": rarity_name,
                "series": series_label,
                "thumb": {"type": "image_card_middle_vertical", "id": str(c["Id"])},
            }
            if len(shown) == 2:
                item["form"] = "特训前" if c["Id"] % 10 == 0 else "特训后"
            display_cards.append(item)
        series_rarities.append((head["Rarity"], rarity_name))
    if not display_cards:
        raise ValueError(f"角色 {char_id} 无可展示卡牌，无法构建 find 渲染 payload")

    rarity_counter = {}
    for rid, name in series_rarities:
        rarity_counter[(rid, name)] = rarity_counter.get((rid, name), 0) + 1
    rarity_summary = [
        {"label": name, "count": count}
        for (_, name), count in sorted(rarity_counter.items(), key=lambda kv: kv[0][0])
    ]

    character = {
        "id": char_id,
        "name": dm.get_character_name(char_id),
        "generation": dm.get_generation_str(char_id) or None,
        "unit": dm.get_character_unit(char_id),
    }
    # 无主题色时省略字段，交给服务端默认值
    color = dm.get_character_theme_color(char_id)
    if color:
        character["color"] = color

    assets = {"icon": {"type": "chara_icon", "id": str(char_id)}}
    unit_id = dm.get_character_unit_id(char_id)
    if unit_id:
        assets["unit_logo"] = {"type": "unit_logo", "id": str(unit_id)}

    return {
        "schema_version": "1",
        "kind": "llll.find",
        "locale": "zh-CN",
        "theme": "light",
        "data": {
            "character": character,
            "cards": display_cards,
            "total_count": len(series_rarities),
            "rarity_summary": rarity_summary,
        },
        "assets": assets,
    }


def format_music_duration(ms_value) -> str:
    """毫秒时长格式化为 m:ss，无法解析时原样返回字符串。"""
    try:
        total_seconds = int(ms_value) // 1000
    except (ValueError, TypeError):
        return str(ms_value)
    return f"{total_seconds // 60}:{total_seconds % 60:02d}"


def build_music_mastery_items(dm, music_id) -> list:
    """构建歌曲熟练度加成列表，payload 与 T2I 共用。"""
    items = []
    for mastery in dm.get_music_mastery(music_id) or []:
        level = mastery.get("Level")
        if not isinstance(level, int) or level < 1:
            continue
        skill_id = mastery.get("MusicMasterySkillsId")
        skill_name = dm.get_music_mastery_skill_name(skill_id) or f"技能 {skill_id}"
        bonus = dm.get_mastery_bonus(skill_name, level) or {}
        if "GainVoltagePt" in bonus:
            bonus_text = (
                f"获得电压点 {bonus.get('DemandVoltagePt')}pt 时，"
                f"追加获得 {bonus.get('GainVoltagePt')}pt"
            )
        elif "GainMentalPt" in bonus:
            bonus_text = (
                f"Mental 减少 {bonus.get('DemandDamagePt')} 时，"
                f"回复 {bonus.get('GainMentalPt')}"
            )
        elif "LoveRate" in bonus:
            bonus_text = (
                f"跳心出现量 +{bonus.get('LoveRate') / 10000}%"
                if skill_id == 3
                else f"爱心回收时 LOVE 获得量 +{bonus.get('LoveRate') / 10000}%"
            )
        else:
            bonus_text = "-"
        items.append({"level": level, "skill_name": skill_name, "bonus_text": bonus_text})
    return items


def _music_performers(dm, entry) -> list:
    performers = []
    seen = set()

    def add(raw_id, role):
        try:
            cid = int(raw_id)
        except (TypeError, ValueError):
            return
        if cid <= 0 or cid in seen:
            return
        seen.add(cid)
        performers.append(
            {
                "id": cid,
                "name": dm.get_character_name(cid),
                "role": role,
                "icon": {"type": "chara_icon", "id": str(cid)},
            }
        )

    if entry.get("CenterCharacterId"):
        add(entry["CenterCharacterId"], "center")
    for cid in entry.get("SingerCharacterId") or []:
        add(cid, "singer")
    for cid in entry.get("SupportCharacterId") or []:
        add(cid, "support")
    return performers


def _music_chart_payload(chart):
    """裁剪 get_music_chart_data 结果为分析仪契约的最小字段集。"""
    if not chart:
        return None
    sections = [
        {
            "index": s["index"],
            "percentage": s["percentage"],
            "beat_count": s["beat_count"],
            "duration_sec": s["duration_sec"],
        }
        for s in chart.get("sections") or []
        if (s.get("percentage") or 0) > 0
    ]
    if not sections:
        return None
    moods = [{"x": m["x"], "y": m["y"]} for m in chart.get("moods") or []]
    return {
        "total_time_sec": chart.get("total_time_sec") or 0,
        "sections": sections,
        "moods": moods,
    }


def build_music_render_payload(dm, entry) -> dict:
    """构建 llll.music 单曲渲染 payload。条目缺 Id/Title 时抛 ValueError。

    masterdata 无 BPM 字段，bpm 留空待 Wiki 补充；封面资源 id 取 JacketId。
    """
    music_id = entry.get("Id")
    title = str(entry.get("Title") or "").strip()
    if not music_id or not title:
        raise ValueError("歌曲条目缺少 Id 或 Title，无法构建 music 渲染 payload")

    music_type = entry.get("MusicType")
    mood_name = dm.MOODS.get(music_type) if music_type is not None else None
    song_type_label = dm.get_song_type_label(entry.get("SongType"))
    generations_id = entry.get("GenerationsId")
    play_time = entry.get("PlayTime")

    music = {
        "id": music_id,
        "title": title,
        "title_furigana": entry.get("TitleFurigana") or None,
        "description": entry.get("Description") or None,
        "generation_label": f"{generations_id}期" if generations_id else None,
        "unit": dm.unit_names.get(entry.get("UnitId")),
        "song_type_label": song_type_label,
        "mood_name": mood_name,
    }
    if play_time:
        music["duration_text"] = format_music_duration(play_time)
    center_id = entry.get("CenterCharacterId")
    # 主题色取中心角色 ThemeColor，无中心或无主题色时交给服务端默认值
    color = dm.get_character_theme_color(center_id) if center_id else None
    if color:
        music["color"] = color

    info = []

    def add_info(label, value):
        text = str(value).strip() if value is not None else ""
        if text:
            info.append({"label": label, "value": text})

    add_info("歌曲类型", song_type_label)
    add_info("属性", mood_name)
    if play_time:
        add_info("时长", f"{music['duration_text']} ({play_time}ms)")
    add_info("AP 上限", entry.get("MaxAp"))
    fever = entry.get("FeverSectionNo")
    if fever:
        add_info("Fever 区段", f"第 {fever} 区段")
    add_info("解锁条件", entry.get("ReleaseConditionText"))
    if center_id:
        add_info("中心角色", dm.get_character_name(center_id))

    data = {
        "music": music,
        "info": info,
        "performers": _music_performers(dm, entry),
        "mastery": build_music_mastery_items(dm, music_id),
    }
    chart = _music_chart_payload(dm.get_music_chart_data(music_id))
    if chart:
        data["chart"] = chart
        if isinstance(fever, int) and fever >= 1:
            data["fever_section"] = fever

    return {
        "schema_version": "1",
        "kind": "llll.music",
        "locale": "zh-CN",
        "theme": "light",
        "data": data,
        "assets": {
            "jacket": {
                "type": "music_jacket",
                "id": str(entry.get("JacketId") or music_id),
            }
        },
    }
