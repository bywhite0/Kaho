import functools
import os
import unittest
from pathlib import Path
from typing import Optional

import yaml


def _safe_is_dir(path: Path) -> bool:
    try:
        return path.is_dir()
    except Exception:
        return False


def get_real_masterdata_dir() -> Optional[Path]:
    env_path = os.getenv("KAHO_REAL_MASTERDATA_DIR", "").strip()
    candidates = []
    if env_path:
        candidates.append(Path(env_path))
    repo_root = Path(__file__).resolve().parents[1]
    candidates.append(repo_root / "masterdata")

    for path in candidates:
        if _safe_is_dir(path):
            return path
    return None


def require_real_masterdata_dir() -> Path:
    enabled = str(os.getenv("KAHO_ENABLE_REALDATA_TESTS", "")).strip().lower()
    if enabled not in {"1", "true", "yes", "on"}:
        raise unittest.SkipTest("未启用真实数据测试，设置 KAHO_ENABLE_REALDATA_TESTS=1 后可运行")
    root = get_real_masterdata_dir()
    if root is None:
        raise unittest.SkipTest("未找到真实 masterdata 目录")
    return root


@functools.lru_cache(maxsize=128)
def load_real_yaml(filename: str):
    root = require_real_masterdata_dir()
    file_path = root / filename
    if not file_path.exists():
        raise unittest.SkipTest(f"缺少真实数据文件: {filename}")
    data = yaml.safe_load(file_path.read_text(encoding="utf-8"))
    if data is None:
        return []
    return data


def normalize_id_list(raw):
    if raw is None:
        return []
    if isinstance(raw, list):
        values = raw
    elif isinstance(raw, (int, float)):
        values = [raw]
    else:
        text = str(raw).strip()
        values = [p for p in text.replace("，", ",").replace(" ", ",").split(",") if p]
    result = []
    for value in values:
        try:
            result.append(int(value))
        except (TypeError, ValueError):
            continue
    return result


def _write_yaml(path: Path, payload):
    path.write_text(
        yaml.safe_dump(
            payload,
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def build_index_fixture(data_dir: Path):
    characters = [c for c in load_real_yaml("Characters.yaml") if c.get("Id")]
    cards = [
        c
        for c in load_real_yaml("CardDatas.yaml")
        if c.get("Id") and c.get("CardSeriesId") and c.get("CharactersId")
    ]
    musics = [m for m in load_real_yaml("Musics.yaml") if m.get("Id") and m.get("Title")]
    comics = [c for c in load_real_yaml("Comics.yaml") if c.get("Id") and c.get("Name")]
    rarities = [r for r in load_real_yaml("CardRarities.yaml") if r.get("Id")]

    selected_chars = []
    for char in characters:
        if not char.get("NameFirst") and not char.get("DisplayFullName"):
            continue
        selected_chars.append(char)
        if len(selected_chars) >= 3:
            break
    if len(selected_chars) < 2:
        raise unittest.SkipTest("真实 Characters 数据不足")

    char_ids = {c["Id"] for c in selected_chars}
    series_selected = {}
    for card in cards:
        if card.get("CharactersId") not in char_ids:
            continue
        sid = card.get("CardSeriesId")
        if sid is None:
            continue
        if sid not in series_selected:
            series_selected[sid] = []
        if len(series_selected[sid]) < 2:
            series_selected[sid].append(card)
        if len(series_selected) >= 3 and all(
            len(entries) >= 1 for entries in series_selected.values()
        ):
            break
    if len(series_selected) < 2:
        for card in cards:
            sid = card.get("CardSeriesId")
            if sid is None:
                continue
            if sid not in series_selected:
                series_selected[sid] = []
            if len(series_selected[sid]) < 2:
                series_selected[sid].append(card)
            if len(series_selected) >= 2:
                break

    selected_cards = []
    for entries in series_selected.values():
        selected_cards.extend(entries)
    if not selected_cards:
        raise unittest.SkipTest("真实 CardDatas 数据不足")

    music_candidates = []
    for music in musics:
        related_ids = set()
        center_id = music.get("CenterCharacterId")
        if center_id:
            related_ids.add(center_id)
        related_ids.update(normalize_id_list(music.get("SingerCharacterId")))
        related_ids.update(normalize_id_list(music.get("SupportCharacterId")))
        if related_ids & char_ids:
            music_candidates.append(music)
        if len(music_candidates) >= 2:
            break
    if not music_candidates and musics:
        music_candidates = musics[:2]
    if not music_candidates:
        raise unittest.SkipTest("真实 Musics 数据不足")

    comic_candidates = []
    for comic in comics:
        if set(normalize_id_list(comic.get("AppearanceCharacterIds"))) & char_ids:
            comic_candidates.append(comic)
        if len(comic_candidates) >= 2:
            break
    if not comic_candidates and comics:
        comic_candidates = comics[:2]
    if not comic_candidates:
        raise unittest.SkipTest("真实 Comics 数据不足")

    selected_series_ids = {card["CardSeriesId"] for card in selected_cards}
    card_series = [
        s for s in load_real_yaml("CardSeries.yaml") if s.get("Id") in selected_series_ids
    ]

    _write_yaml(data_dir / "Characters.yaml", selected_chars)
    _write_yaml(data_dir / "CardDatas.yaml", selected_cards)
    _write_yaml(data_dir / "CardRarities.yaml", rarities)
    _write_yaml(data_dir / "Musics.yaml", music_candidates)
    _write_yaml(data_dir / "Comics.yaml", comic_candidates)
    _write_yaml(data_dir / "CardSeries.yaml", card_series)

    first_char = selected_chars[0]
    first_music = music_candidates[0]
    first_comic = comic_candidates[0]
    first_card = selected_cards[0]
    char_name_map = {
        c.get("Id"): (c.get("NameLast") or "") + (c.get("NameFirst") or "")
        for c in selected_chars
    }
    music_related_ids = set()
    center_id = first_music.get("CenterCharacterId")
    if center_id:
        music_related_ids.add(center_id)
    music_related_ids.update(normalize_id_list(first_music.get("SingerCharacterId")))
    music_related_ids.update(normalize_id_list(first_music.get("SupportCharacterId")))
    music_char_id = next((cid for cid in music_related_ids if cid in char_name_map), None)

    comic_related_ids = normalize_id_list(first_comic.get("AppearanceCharacterIds"))
    comic_char_id = next((cid for cid in comic_related_ids if cid in char_name_map), None)
    return {
        "first_char_id": first_char.get("Id"),
        "first_char_name": (first_char.get("NameLast") or "")
        + (first_char.get("NameFirst") or ""),
        "first_char_latin_last": first_char.get("LatinAlphabetNameLast"),
        "first_series_id": first_card.get("CardSeriesId"),
        "first_music_id": first_music.get("Id"),
        "first_music_title": first_music.get("Title"),
        "first_comic_id": first_comic.get("Id"),
        "first_comic_name": first_comic.get("Name"),
        "first_card_id": first_card.get("Id"),
        "first_card_name": first_card.get("Name"),
        "music_query_char": char_name_map.get(music_char_id) or str(music_char_id or ""),
        "comic_query_char": char_name_map.get(comic_char_id) or str(comic_char_id or ""),
    }


def build_skill_fixture(data_dir: Path):
    details = load_real_yaml("CardSkillEffectDetails.yaml")
    token_refs = {}
    for detail in details:
        detail_id = str(detail.get("Id") or "")
        if len(detail_id) < 2:
            continue
        prefix = detail_id[:-1]
        ref = token_refs.setdefault(
            prefix,
            {
                "skill_series_id": None,
                "ability_series_id": None,
                "resource_id": None,
            },
        )
        detail_type = str(detail.get("SkillEffectDetailType") or "")
        if detail_type == "TOKEN_CARD_SKILL_CARD_SKILL_SERIES_ID":
            ref["skill_series_id"] = detail.get("EffectValue")
        elif detail_type == "TOKEN_CARD_ABILITY_CARD_SKILL_SERIES_ID":
            ref["ability_series_id"] = detail.get("EffectValue")
        elif detail_type == "TOKEN_CARD_RESOURCE_ID":
            ref["resource_id"] = detail.get("EffectValue")

    chosen_prefix = None
    chosen_ref = None
    for prefix, ref in token_refs.items():
        if ref.get("skill_series_id") and ref.get("ability_series_id"):
            chosen_prefix = prefix
            chosen_ref = ref
            break
    if not chosen_prefix:
        raise unittest.SkipTest("未在真实数据中找到可用的 token 技能映射")

    all_skills = load_real_yaml("CardSkills.yaml")
    root_series_id = None
    for skill in all_skills:
        effect_ids = normalize_id_list(skill.get("CardSkillEffectId"))
        if int(chosen_prefix) in effect_ids:
            root_series_id = skill.get("CardSkillSeriesId")
            if root_series_id:
                break
    if not root_series_id:
        raise unittest.SkipTest("未在真实数据中找到引用 token 的主技能")

    related_series_ids = {
        root_series_id,
        int(chosen_ref["skill_series_id"]),
        int(chosen_ref["ability_series_id"]),
    }
    skill_series = [
        s for s in load_real_yaml("CardSkillSeries.yaml") if s.get("Id") in related_series_ids
    ]
    selected_skills = [
        s for s in all_skills if s.get("CardSkillSeriesId") in related_series_ids
    ]
    selected_details = [
        d
        for d in details
        if str(d.get("Id") or "").startswith(chosen_prefix)
    ]

    _write_yaml(data_dir / "CardSkillSeries.yaml", skill_series)
    _write_yaml(data_dir / "CardSkills.yaml", selected_skills)
    _write_yaml(data_dir / "CardSkillEffectDetails.yaml", selected_details)

    return {
        "token_prefix": chosen_prefix,
        "root_series_id": root_series_id,
        "skill_series_id": int(chosen_ref["skill_series_id"]),
        "ability_series_id": int(chosen_ref["ability_series_id"]),
    }
