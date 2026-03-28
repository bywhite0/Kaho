import tempfile
import unittest
from pathlib import Path

from src.core.data_manager import DataManager
from src.utils.formatters import build_skill_view, parse_intro, print_merged_skill
from tests.realdata_utils import build_skill_fixture, load_real_yaml


class FormattersTest(unittest.TestCase):
    def test_parse_intro_from_real_data(self):
        characters = load_real_yaml("Characters.yaml")
        intro = ""
        parsed = {}
        for character in characters:
            text = str(character.get("Introduction") or "")
            if not text:
                continue
            result = parse_intro(text)
            if result:
                intro = text
                parsed = result
                break
        if not intro:
            self.skipTest("真实角色简介中缺少可解析字段")
        self.assertIsInstance(parsed, dict)
        self.assertTrue(parsed)

    def test_skill_view_and_text_from_real_data(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            data_dir = root / "masterdata"
            data_dir.mkdir(parents=True, exist_ok=True)
            meta = build_skill_fixture(data_dir)
            dm = DataManager(str(data_dir))
            try:
                skill_data = dm.get_all_skills_data(meta["root_series_id"])
                view = build_skill_view(dm, skill_data, title_prefix="技能:", cost_str="（AP 6）")
                text = print_merged_skill(dm, skill_data, title_prefix="技能:", cost_str="（AP 6）")
                self.assertIsNotNone(view)
                self.assertTrue(view.get("name"))
                self.assertIsInstance(text, str)
                self.assertTrue(text.strip())
            finally:
                dm.close()


if __name__ == "__main__":
    unittest.main()
