import os
import tempfile
import unittest
from pathlib import Path

from src.core.data_manager import DataManager
from src.utils.formatters import build_skill_view


class SkillStructuredTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp_dir = tempfile.TemporaryDirectory()
        root = Path(cls._tmp_dir.name)
        cls.data_dir = root / "masterdata"
        cls.data_dir.mkdir(parents=True, exist_ok=True)
        cls.db_path = root / "data.db"
        cls._prev_db_path = os.getenv("KAHO_DB_PATH")
        os.environ["KAHO_DB_PATH"] = str(cls.db_path)

        (cls.data_dir / "CardSkillSeries.yaml").write_text(
            """
- Id: 100
  Name: 主技能
  SkillIcon: 1001
  SkillMainEffect: Voltage
- Id: 200
  Name: 追加技能
  SkillIcon: 2001
  SkillMainEffect: Heart
- Id: 300
  Name: 追加特性
  SkillIcon: 3001
  SkillMainEffect: Ability
""".strip(),
            encoding="utf-8",
        )

        (cls.data_dir / "CardSkills.yaml").write_text(
            """
- CardSkillSeriesId: 100
  SkillLevel: 1
  Description: 造成$100$点伤害
  CardSkillEffectId: 11100010010
- CardSkillSeriesId: 100
  SkillLevel: 2
  Description: 造成$120$点伤害
  CardSkillEffectId: 11100010010
- CardSkillSeriesId: 200
  SkillLevel: 1
  Description: 恢复$50$点
  CardSkillEffectId: 0
- CardSkillSeriesId: 300
  SkillLevel: 1
  Description: 提升$5$%
  CardSkillEffectId: 0
""".strip(),
            encoding="utf-8",
        )

        (cls.data_dir / "CardSkillEffectDetails.yaml").write_text(
            """
- Id: 111000100101
  SkillEffectDetailType: TOKEN_CARD_SKILL_CARD_SKILL_SERIES_ID
  EffectValue: 200
- Id: 111000100102
  SkillEffectDetailType: TOKEN_CARD_ABILITY_CARD_SKILL_SERIES_ID
  EffectValue: 300
""".strip(),
            encoding="utf-8",
        )

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
        token_entry = self.dm.token_skill_map.get("11100010010")
        self.assertIsNotNone(token_entry)
        self.assertEqual(token_entry["skill_series_id"], 200)
        self.assertEqual(token_entry["ability_series_id"], 300)

    def test_get_merged_skill_desc_returns_structured_token(self):
        skill_data = self.dm.get_all_skills_data(100)
        merged = self.dm.get_merged_skill_desc(skill_data)
        self.assertIsNotNone(merged)
        self.assertEqual(merged["name"], "主技能")
        self.assertTrue(merged["ranges"])
        self.assertIn("start_level", merged["ranges"][0])
        self.assertIn("end_level", merged["ranges"][0])
        self.assertIn("value", merged["ranges"][0])
        self.assertEqual(merged["token"]["skill"]["id"], 200)
        self.assertEqual(merged["token"]["ability"]["id"], 300)

    def test_build_skill_view_contains_token_branches(self):
        skill_data = self.dm.get_all_skills_data(100)
        view = build_skill_view(
            self.dm,
            skill_data,
            title_prefix="技能:",
            cost_str="（AP 消耗: 3）",
        )
        self.assertIsNotNone(view)
        self.assertEqual(view["name"], "主技能")
        self.assertEqual(view["cost"], "（AP 消耗: 3）")
        self.assertTrue(view["ranges"])
        self.assertTrue(view["ranges"][0]["label"].startswith("Lv."))
        self.assertIsNotNone(view["token"]["skill"])
        self.assertIsNotNone(view["token"]["ability"])
        self.assertEqual(view["token"]["skill"]["name"], "追加技能")
        self.assertEqual(view["token"]["ability"]["name"], "追加特性")


if __name__ == "__main__":
    unittest.main()
