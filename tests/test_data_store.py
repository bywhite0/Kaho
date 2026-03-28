import tempfile
import unittest
from pathlib import Path

from src.core.services.data_store import DataStore
from tests.realdata_utils import build_index_fixture


class DataStoreTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp_dir = tempfile.TemporaryDirectory()
        cls.root = Path(cls._tmp_dir.name)
        cls.data_dir = cls.root / "masterdata"
        cls.data_dir.mkdir(parents=True, exist_ok=True)
        build_index_fixture(cls.data_dir)

        cls.version_path = cls.root / "currentVersion.txt"
        cls.version_path.write_text("v1", encoding="utf-8")

        cls.store = DataStore(str(cls.data_dir))

    @classmethod
    def tearDownClass(cls):
        cls.store.close()
        cls._tmp_dir.cleanup()

    def test_meta_roundtrip(self):
        self.store.set_meta("k1", "v1")
        self.assertEqual(self.store.get_meta("k1"), "v1")

    def test_load_yaml_file(self):
        data = self.store.load_yaml_file("CardDatas.yaml")
        self.assertIsInstance(data, list)
        self.assertGreaterEqual(len(data), 1)

    def test_load_yaml_file_refresh_when_file_changed(self):
        yaml_path = self.data_dir / "TempCards.yaml"
        yaml_path.write_text(
            """
- Id: 1
  Name: 初始名
""".strip(),
            encoding="utf-8",
        )
        first = self.store.load_yaml_file("TempCards.yaml")
        self.assertEqual(first[0]["Name"], "初始名")

        yaml_path.write_text(
            """
- Id: 1
  Name: 新名字
""".strip(),
            encoding="utf-8",
        )
        second = self.store.load_yaml_file("TempCards.yaml")
        self.assertEqual(second[0]["Name"], "新名字")

    def test_sync_version_change_detection(self):
        self.version_path.write_text("v3", encoding="utf-8")
        changed = self.store.sync_version(str(self.version_path))
        self.assertTrue(changed)
        changed_again = self.store.sync_version(str(self.version_path))
        self.assertFalse(changed_again)

    def test_sync_version_cleans_removed_yaml_cache(self):
        temp_yaml = self.data_dir / "TempCleanup.yaml"
        temp_yaml.write_text(
            """
- Id: 1
  Name: A
- Id: 2
  Name: B
""".strip(),
            encoding="utf-8",
        )
        self.version_path.write_text("cleanup-v1", encoding="utf-8")
        self.assertTrue(self.store.sync_version(str(self.version_path)))

        cache_file = (
            Path(self.store.masterdata_cache_dir) / "TempCleanup.yaml.json"
        )
        self.assertTrue(cache_file.exists())

        temp_yaml.unlink()
        self.version_path.write_text("cleanup-v2", encoding="utf-8")
        self.assertTrue(self.store.sync_version(str(self.version_path)))

        self.assertFalse(cache_file.exists())
        files_state = self.store._state_db.get_copy("masterdata.files", {})
        self.assertNotIn("TempCleanup.yaml", files_state)

    def test_rebuild_updates_version(self):
        self.version_path.write_text("v2", encoding="utf-8")
        changed = self.store.rebuild(str(self.version_path))
        self.assertGreaterEqual(changed, 0)
        self.assertEqual(self.store.get_meta("current_version"), "v2")

    def test_music_chart_roundtrip(self):
        payload = {"total_time": 1000, "sections": [{"index": 1}]}
        self.store.save_music_chart(123, payload)
        loaded = self.store.get_music_chart(123)
        self.assertEqual(loaded["total_time"], 1000)
        self.assertEqual(loaded["sections"][0]["index"], 1)


if __name__ == "__main__":
    unittest.main()
