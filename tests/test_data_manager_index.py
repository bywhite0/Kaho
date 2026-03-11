import os
import tempfile
import unittest
from pathlib import Path

from src.core.data_manager import DataManager


class DataManagerIndexTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp_dir = tempfile.TemporaryDirectory()
        root = Path(cls._tmp_dir.name)
        cls.data_dir = root / "masterdata"
        cls.data_dir.mkdir(parents=True, exist_ok=True)
        cls.db_path = root / "data.db"
        cls._prev_db_path = os.getenv("KAHO_DB_PATH")
        os.environ["KAHO_DB_PATH"] = str(cls.db_path)

        (cls.data_dir / "Characters.yaml").write_text(
            """
- Id: 101
  NameFirst: 小鈴
  NameLast: 日野下
  LatinAlphabetNameFirst: Kosuzu
  LatinAlphabetNameLast: Hinoshita
  DisplayFullName: 日野下小鈴
- Id: 102
  NameFirst: さやか
  NameLast: 村野
  LatinAlphabetNameFirst: Sayaka
  LatinAlphabetNameLast: Murano
  DisplayFullName: 村野さやか
""".strip(),
            encoding="utf-8",
        )

        (cls.data_dir / "CardDatas.yaml").write_text(
            """
- Id: 20011
  CardSeriesId: 2001
  CharactersId: 101
  Name: 花咲く朝
  State: 1
  Rarity: 5
- Id: 20010
  CardSeriesId: 2001
  CharactersId: 101
  Name: 花咲く朝
  State: 0
  Rarity: 5
- Id: 30010
  CardSeriesId: 3001
  CharactersId: 102
  Name: 夜空のステージ
  State: 0
  Rarity: 4
- Id: 40010
  CardSeriesId: 4001
  CharactersId: 101
  Name: 朝焼けメロディ
  State: 0
  Rarity: 3
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

    def test_character_alias_lookup(self):
        self.assertEqual(self.dm.get_character_id_by_name("日野下 小鈴"), 101)
        self.assertEqual(self.dm.get_character_id_by_name("hinoshita"), 101)
        self.assertEqual(self.dm.get_character_id_by_name("102"), 102)

    def test_get_card_series_data_uses_index(self):
        cards = self.dm.get_card_series_data(2001)
        self.assertEqual([c["Id"] for c in cards], [20010, 20011])

    def test_get_cards_by_character_uses_index(self):
        cards = self.dm.get_cards_by_character(101)
        self.assertEqual([c["Id"] for c in cards], [20010, 20011, 40010])

    def test_search_card_series_limit(self):
        results = self.dm.search_card_series("朝", limit=1)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["CardSeriesId"], 2001)

    def test_search_card_series_exact_id(self):
        results = self.dm.search_card_series("3001", limit=10)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["CardSeriesId"], 3001)


if __name__ == "__main__":
    unittest.main()
