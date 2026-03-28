import argparse
import ctypes
import gc
import json
import os
import sys
import threading
import time
import tracemalloc
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

if os.name == "nt":
    from ctypes import wintypes
    _DWORD_T = wintypes.DWORD
else:
    _DWORD_T = ctypes.c_uint32


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.core.data_manager import DataManager


class _ProcessMemoryCounters(ctypes.Structure):
    _fields_ = [
        ("cb", _DWORD_T),
        ("PageFaultCount", _DWORD_T),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


@dataclass
class StageResult:
    stage: str
    ok: bool
    seconds: float
    rss_before_mb: float
    rss_after_mb: float
    rss_peak_mb: float
    py_peak_mb: float
    loaded_groups: int
    note: str = ""


def get_rss_mb() -> float:
    if os.name == "nt":
        counters = _ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(_ProcessMemoryCounters)
        get_info = ctypes.windll.psapi.GetProcessMemoryInfo
        get_info.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(_ProcessMemoryCounters),
            wintypes.DWORD,
        ]
        get_info.restype = wintypes.BOOL
        ok = get_info(
            ctypes.windll.kernel32.GetCurrentProcess(),
            ctypes.byref(counters),
            counters.cb,
        )
        if ok:
            return counters.WorkingSetSize / 1024 / 1024
    try:
        import resource  # type: ignore

        usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if sys.platform == "darwin":
            return usage / 1024 / 1024
        return usage / 1024
    except Exception:
        return 0.0


def _format_stage_line(item: StageResult) -> str:
    status = "OK" if item.ok else "FAIL"
    return (
        f"{item.stage:<14} {status:<4} {item.seconds:>7.3f}s  "
        f"RSS {item.rss_before_mb:>8.2f}->{item.rss_after_mb:>8.2f} MB  "
        f"Peak {item.rss_peak_mb:>8.2f} MB  "
        f"PyPeak {item.py_peak_mb:>8.2f} MB  "
        f"Loaded {item.loaded_groups:>3d}  {item.note}"
    )


def _safe_name(entry: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = entry.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _pick_first_series_id(dm: DataManager) -> int | None:
    cards = dm.get_all_card_datas() or []
    if not cards:
        return None
    first = cards[0]
    series_id = first.get("CardSeriesId")
    if series_id is not None:
        try:
            return int(series_id)
        except Exception:
            return None
    card_id = first.get("Id")
    if card_id is None:
        return None
    try:
        return int(card_id) // 10
    except Exception:
        return None


def profile(
    data_dir: str,
    version_path: str | None,
    stages: list[str],
    interval: float,
) -> tuple[list[StageResult], dict[str, Any]]:
    dm = DataManager(data_dir)
    results: list[StageResult] = []
    baseline = {
        "pid": os.getpid(),
        "data_dir": data_dir,
        "version_path": version_path,
        "rss_start_mb": round(get_rss_mb(), 3),
        "stages": stages,
    }

    def run_stage(name: str, fn: Callable[[], str]) -> None:
        gc.collect()
        rss_before = get_rss_mb()
        py_before, py_peak_before = tracemalloc.get_traced_memory()
        _ = py_before
        _ = py_peak_before
        rss_peak = rss_before
        stop_event = threading.Event()

        def sampler():
            nonlocal rss_peak
            while not stop_event.wait(interval):
                current = get_rss_mb()
                if current > rss_peak:
                    rss_peak = current

        th = threading.Thread(target=sampler, daemon=True)
        th.start()
        t0 = time.perf_counter()
        ok = True
        note = ""
        try:
            note = fn() or ""
        except Exception as exc:
            ok = False
            note = f"{type(exc).__name__}: {exc}"
        elapsed = time.perf_counter() - t0
        stop_event.set()
        th.join(timeout=1)
        rss_after = get_rss_mb()
        _, py_peak = tracemalloc.get_traced_memory()
        loaded_groups = len(getattr(dm, "_loaded", set()))
        results.append(
            StageResult(
                stage=name,
                ok=ok,
                seconds=elapsed,
                rss_before_mb=rss_before,
                rss_after_mb=rss_after,
                rss_peak_mb=max(rss_peak, rss_after),
                py_peak_mb=py_peak / 1024 / 1024,
                loaded_groups=loaded_groups,
                note=note,
            )
        )

    def stage_init() -> str:
        return "DataManager ready"

    def stage_sync() -> str:
        if not version_path:
            return "skip(no version file)"
        changed = dm.sync_version_cache(version_path)
        return f"changed={changed}"

    def stage_card_search() -> str:
        cards = dm.get_all_card_datas() or []
        if not cards:
            return "skip(no cards)"
        series_id = _pick_first_series_id(dm)
        if series_id is None:
            return "skip(no series id)"
        by_id = dm.search_card_series(str(series_id), limit=1)
        by_name = dm.search_card_series(_safe_name(cards[0], ("Name",)), limit=1)
        return f"id_hits={len(by_id)} name_hits={len(by_name)}"

    def stage_music_search() -> str:
        dm._ensure("musics")
        entries = dm.musics or []
        if not entries:
            return "skip(no musics)"
        title = _safe_name(entries[0], ("Title", "Name"))
        result = dm.search_musics(title, limit=5)
        return f"hits={len(result)}"

    def stage_comic_search() -> str:
        dm._ensure("comics")
        entries = dm.comics or []
        if not entries:
            return "skip(no comics)"
        title = _safe_name(entries[0], ("Name", "Title"))
        result = dm.search_comics(title, limit=5)
        return f"hits={len(result)}"

    def stage_card_detail() -> str:
        series_id = _pick_first_series_id(dm)
        if series_id is None:
            return "skip(no series id)"
        cards = dm.get_card_series_data(series_id)
        if not cards:
            return "skip(series empty)"
        base = cards[0]
        dm.get_card_series_meta(series_id)
        dm.get_character(base.get("CharactersId"))
        dm.get_rarity_name(base.get("Rarity"))
        dm.get_gachas_for_series(series_id)
        dm.get_card_skill_levelup_materials(series_id)
        dm.get_card_evolution_materials(base.get("Id"))
        dm.get_all_skills_data(base.get("SkillSeriesId"))
        dm.get_all_skills_data(base.get("SpecialAppealSeriesId"))
        dm.get_all_center_skills_data(base.get("CenterSkillSeriesId"))
        dm.get_all_rhythm_skills_data(base.get("RhythmGameSkillSeriesId"))
        return f"series={series_id} cards={len(cards)}"

    def stage_skill_token() -> str:
        card_skills_map = dm.get_card_skills_map()
        if not card_skills_map:
            return "skip(no skill map)"
        first_series_id = next(iter(card_skills_map.keys()))
        skill_data = dm.get_all_skills_data(first_series_id)
        merged = dm.get_merged_skill_desc(skill_data) if skill_data else None
        token_cards = len((merged or {}).get("token_cards") or [])
        return f"series={first_series_id} token_cards={token_cards}"

    def stage_ensure_all() -> str:
        dm.load_data()
        return "all groups loaded"

    stage_map: dict[str, Callable[[], str]] = {
        "init": stage_init,
        "sync": stage_sync,
        "card_search": stage_card_search,
        "music_search": stage_music_search,
        "comic_search": stage_comic_search,
        "card_detail": stage_card_detail,
        "skill_token": stage_skill_token,
        "ensure_all": stage_ensure_all,
    }

    try:
        for stage in stages:
            fn = stage_map.get(stage)
            if fn is None:
                results.append(
                    StageResult(
                        stage=stage,
                        ok=False,
                        seconds=0.0,
                        rss_before_mb=get_rss_mb(),
                        rss_after_mb=get_rss_mb(),
                        rss_peak_mb=get_rss_mb(),
                        py_peak_mb=tracemalloc.get_traced_memory()[1] / 1024 / 1024,
                        loaded_groups=len(getattr(dm, "_loaded", set())),
                        note="unknown stage",
                    )
                )
                continue
            run_stage(stage, fn)
    finally:
        dm.close()

    summary = {
        "rss_end_mb": round(get_rss_mb(), 3),
        "max_stage_rss_peak_mb": round(
            max((item.rss_peak_mb for item in results), default=0.0), 3
        ),
        "max_stage_seconds": round(
            max((item.seconds for item in results), default=0.0), 3
        ),
        "failed_stages": [item.stage for item in results if not item.ok],
    }
    return results, {**baseline, **summary}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="剖析 DataManager 运行时内存与耗时",
    )
    parser.add_argument(
        "data_dir",
        nargs="?",
        default=os.environ.get("KAHO_REAL_MASTERDATA_DIR", "masterdata"),
        help="masterdata 目录路径",
    )
    parser.add_argument(
        "--version-path",
        default=None,
        help="版本文件路径，默认自动推断为 data_dir 上级目录的 cache/currentVersion.txt",
    )
    parser.add_argument(
        "--stages",
        default="init,sync,card_search,music_search,comic_search,card_detail,skill_token",
        help="逗号分隔的阶段列表",
    )
    parser.add_argument(
        "--sample-interval",
        type=float,
        default=0.02,
        help="内存采样间隔（秒）",
    )
    parser.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="输出 JSON",
    )
    return parser.parse_args()


def resolve_version_path(data_dir: str, raw_version_path: str | None) -> str | None:
    if raw_version_path:
        return raw_version_path
    default = Path(data_dir).resolve().parents[0] / "cache" / "currentVersion.txt"
    if default.exists():
        return str(default)
    return None


def main() -> int:
    args = parse_args()
    data_dir = str(Path(args.data_dir).resolve())
    version_path = resolve_version_path(data_dir, args.version_path)
    stages = [item.strip() for item in args.stages.split(",") if item.strip()]

    if not Path(data_dir).exists():
        print(f"data_dir 不存在: {data_dir}")
        return 2

    tracemalloc.start()
    results, summary = profile(data_dir, version_path, stages, args.sample_interval)

    payload = {
        "summary": summary,
        "stages": [asdict(item) for item in results],
    }
    if args.as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("=== Runtime Memory Profile ===")
        print(f"pid: {summary['pid']}")
        print(f"data_dir: {summary['data_dir']}")
        print(f"version_path: {summary['version_path'] or '-'}")
        print(
            f"rss_start: {summary['rss_start_mb']:.2f} MB -> "
            f"rss_end: {summary['rss_end_mb']:.2f} MB"
        )
        print(
            f"max_stage_peak: {summary['max_stage_rss_peak_mb']:.2f} MB, "
            f"max_stage_seconds: {summary['max_stage_seconds']:.3f}s"
        )
        if summary["failed_stages"]:
            print(f"failed_stages: {','.join(summary['failed_stages'])}")
        print("")
        for item in results:
            print(_format_stage_line(item))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
