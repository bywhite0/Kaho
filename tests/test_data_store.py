import tempfile
import unittest
from pathlib import Path
import os

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

        cls.db_path = cls.root / "kaho.db"
        cls._prev_db_path = os.getenv("KAHO_DB_PATH")
        os.environ["KAHO_DB_PATH"] = str(cls.db_path)
        cls.store = DataStore(str(cls.data_dir))

    @classmethod
    def tearDownClass(cls):
        cls.store._engine.dispose()
        if cls._prev_db_path is None:
            os.environ.pop("KAHO_DB_PATH", None)
        else:
            os.environ["KAHO_DB_PATH"] = cls._prev_db_path
        cls._tmp_dir.cleanup()

    def test_meta_roundtrip(self):
        self.store.set_meta("k1", "v1")
        self.assertEqual(self.store.get_meta("k1"), "v1")

    def test_load_yaml_file(self):
        data = self.store.load_yaml_file("CardDatas.yaml")
        self.assertIsInstance(data, list)
        self.assertGreaterEqual(len(data), 1)

    def test_sync_version_change_detection(self):
        self.version_path.write_text("v3", encoding="utf-8")
        changed = self.store.sync_version(str(self.version_path))
        self.assertTrue(changed)
        changed_again = self.store.sync_version(str(self.version_path))
        self.assertFalse(changed_again)

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
