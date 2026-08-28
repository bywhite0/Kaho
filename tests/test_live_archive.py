import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.core.services.live_archive import LiveArchiveService


def _archive(archives_id, live_type, start, title, thumb_uuid):
    return {
        "archives_id": archives_id,
        "live_id": archives_id,
        "live_type": live_type,
        "live_start_time": start,
        "name": title,
        "thumbnail_image_url": (
            f"https://assets.example.test/x/thumbnail_image/{thumb_uuid}.jpg"
        ),
    }


UUID_A = "aaaaaaaa-1111-2222-3333-444444444444"
UUID_B = "bbbbbbbb-1111-2222-3333-444444444444"
UUID_C = "cccccccc-1111-2222-3333-444444444444"


class LiveArchiveServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        root = Path(cls._tmp.name)
        cls.data_dir = root / "data"
        cls.covers_dir = root / "covers"
        cls.data_dir.mkdir()
        cls.covers_dir.mkdir()

        archives = [
            _archive("arc-1", 2, "2023-04-20T11:25:00Z", "最早场", UUID_A),
            _archive("arc-2", 1, "2025-12-28T10:50:00.619Z", "Fes场", UUID_B),
            _archive("arc-3", 2, "2026-03-28T11:20:00.88Z", "最终场", UUID_C),
        ]
        details = {
            "arc-1": {"characters": [{"character_id": 1021}], "total_gift_pt": 10},
            "arc-2": {
                "characters": [{"character_id": 1031}, {"character_id": 1021}],
                "total_gift_pt": 20,
            },
            "arc-3": {"characters": [{"character_id": 1051}], "total_gift_pt": 30},
        }
        (cls.data_dir / "archive.json").write_text(
            json.dumps(archives, ensure_ascii=False), encoding="utf-8"
        )
        (cls.data_dir / "archive-details.json").write_text(
            json.dumps(details, ensure_ascii=False), encoding="utf-8"
        )
        (cls.covers_dir / f"{UUID_A}.jpg").write_bytes(b"fake-jpg")

        cls.counts_path = root / "comment_counts.json"
        cls.counts_path.write_text(
            json.dumps({"arc-1": 123, "arc-2": 0}), encoding="utf-8"
        )

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _service(self):
        return LiveArchiveService(
            data_dir=str(self.data_dir),
            covers_dir=str(self.covers_dir),
            comment_counts_path=str(self.counts_path),
        )

    def test_available_and_sorted_desc(self):
        svc = self._service()
        self.assertTrue(svc.available())
        ids = [a["archives_id"] for a in svc.list_archives()]
        self.assertEqual(ids, ["arc-3", "arc-2", "arc-1"])

    def test_unconfigured_is_unavailable(self):
        with (
            patch(
                "src.core.services.live_archive._default_data_dir", return_value=""
            ),
            patch.dict("os.environ", {"LIVE_ARCHIVE_DATA_DIR": ""}),
        ):
            svc = LiveArchiveService(
                covers_dir=str(self.covers_dir),
                comment_counts_path=str(self.counts_path),
            )
            self.assertFalse(svc.available())
            self.assertEqual(svc.list_archives(), [])

    def test_missing_files_degrade(self):
        svc = LiveArchiveService(
            data_dir=str(self.covers_dir),
            covers_dir=str(self.covers_dir),
            comment_counts_path=str(self.counts_path),
        )
        self.assertFalse(svc.available())

    def test_filter_by_live_type(self):
        svc = self._service()
        ids = [a["archives_id"] for a in svc.list_archives(live_type=1)]
        self.assertEqual(ids, ["arc-2"])

    def test_filter_by_character(self):
        svc = self._service()
        ids = [a["archives_id"] for a in svc.list_archives(character_id=1021)]
        self.assertEqual(ids, ["arc-2", "arc-1"])
        self.assertEqual(svc.list_archives(character_id=9999), [])

    def test_filter_by_time_window(self):
        svc = self._service()
        ids = [
            a["archives_id"]
            for a in svc.list_archives(
                since="2025-01-01T00:00:00Z", until="2026-01-01T00:00:00Z"
            )
        ]
        self.assertEqual(ids, ["arc-2"])

    def test_get_archive_and_detail(self):
        svc = self._service()
        self.assertEqual(svc.get_archive("arc-2")["name"], "Fes场")
        self.assertEqual(svc.get_detail("arc-2")["total_gift_pt"], 20)
        self.assertIsNone(svc.get_archive("unknown"))
        self.assertIsNone(svc.get_detail("unknown"))

    def test_character_ids(self):
        svc = self._service()
        self.assertEqual(svc.character_ids("arc-2"), [1031, 1021])
        self.assertEqual(svc.character_ids("unknown"), [])

    def test_cover_path(self):
        svc = self._service()
        hit = svc.cover_path(svc.get_archive("arc-1"))
        self.assertIsNotNone(hit)
        self.assertTrue(hit.endswith(f"{UUID_A}.jpg"))
        self.assertIsNone(svc.cover_path(svc.get_archive("arc-2")))
        self.assertIsNone(svc.cover_path({"thumbnail_image_url": "not-a-url"}))

    def test_comment_count(self):
        svc = self._service()
        self.assertEqual(svc.comment_count("arc-1"), 123)
        self.assertEqual(svc.comment_count("arc-2"), 0)
        self.assertIsNone(svc.comment_count("arc-3"))

    def test_corrupt_json_degrades(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad_dir = Path(tmp)
            (bad_dir / "archive.json").write_text("{broken", encoding="utf-8")
            svc = LiveArchiveService(
                data_dir=str(bad_dir),
                covers_dir=str(self.covers_dir),
                comment_counts_path=str(self.counts_path),
            )
            self.assertFalse(svc.available())


if __name__ == "__main__":
    unittest.main()
