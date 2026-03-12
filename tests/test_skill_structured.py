import os
import tempfile
import unittest
from pathlib import Path

from src.core.data_manager import DataManager
from src.utils.formatters import build_skill_view
from tests.realdata_utils import build_skill_fixture


class SkillStructuredTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp_dir = tempfile.TemporaryDirectory()
        root = Path(cls._tmp_dir.name)
        cls.data_dir = root / "masterdata"
        cls.data_dir.mkdir(parents=True, exist_ok=True)
        cls.meta = build_skill_fixture(cls.data_dir)

        cls.db_path = root / "data.db"
        cls._prev_db_path = os.getenv("KAHO_DB_PATH")
        os.environ["KAHO_DB_PATH"] = str(cls.db_path)
        cls.dm = DataManager(str(cls.data_dir))

    @classmethod
    def tearDownClass(cls):
        cls.dm.store._engine.dispose()
        if cls._prev_db_path is None:
            os.environ.pop("KAHO_DB_PATH", None)
        else:
            os.environ["KAHO_DB_PATH"] = cls._prev_db_path
        cls._tmp_dir.cleanup()

    def test_token_map_contains_skill_and_ability(self):
        self.dm._ensure("token_skill_map")
        token_entry = self.dm.token_skill_map.get(self.meta["token_prefix"])
        self.assertIsNotNone(token_entry)
        self.assertEqual(token_entry["skill_series_id"], self.meta["skill_series_id"])
        self.assertEqual(
            token_entry["ability_series_id"],
            self.meta["ability_series_id"],
        )

    def test_get_merged_skill_desc_returns_structured_token(self):
        skill_data = self.dm.get_all_skills_data(self.meta["root_series_id"])
        merged = self.dm.get_merged_skill_desc(skill_data)
        self.assertIsNotNone(merged)
        self.assertIsNotNone(merged.get("token"))
        self.assertIsNotNone(merged["token"].get("skill"))
        self.assertIsNotNone(merged["token"].get("ability"))
        self.assertGreaterEqual(len(merged.get("token_cards") or []), 1)

    def test_build_skill_view_contains_token(self):
        skill_data = self.dm.get_all_skills_data(self.meta["root_series_id"])
        view = build_skill_view(
            self.dm,
            skill_data,
            title_prefix="技能:",
            cost_str="（AP 消耗: 3）",
        )
        self.assertIsNotNone(view)
        self.assertTrue(view.get("name"))
        self.assertEqual(view.get("cost"), "（AP 消耗: 3）")
        self.assertIsNotNone((view.get("token") or {}).get("skill"))
        self.assertIsNotNone((view.get("token") or {}).get("ability"))


if __name__ == "__main__":
    unittest.main()

