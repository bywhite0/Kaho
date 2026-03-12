import os
import tempfile
import unittest
from pathlib import Path

from src.core.data_manager import DataManager
from tests.realdata_utils import build_index_fixture


class DataManagerIndexTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp_dir = tempfile.TemporaryDirectory()
        root = Path(cls._tmp_dir.name)
        cls.data_dir = root / "masterdata"
        cls.data_dir.mkdir(parents=True, exist_ok=True)
        cls.meta = build_index_fixture(cls.data_dir)

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

    def test_character_alias_lookup(self):
        char_id = self.meta["first_char_id"]
        self.assertEqual(self.dm.get_character_id_by_name(str(char_id)), char_id)

        full_name = self.meta.get("first_char_name")
        if full_name:
            self.assertEqual(self.dm.get_character_id_by_name(full_name), char_id)

        latin_last = self.meta.get("first_char_latin_last")
        if latin_last:
            self.assertEqual(self.dm.get_character_id_by_name(latin_last), char_id)

    def test_get_card_series_data_uses_index(self):
        series_id = self.meta["first_series_id"]
        cards = self.dm.get_card_series_data(series_id)
        self.assertGreaterEqual(len(cards), 1)
        self.assertEqual(cards[0]["CardSeriesId"], series_id)

    def test_get_cards_by_character_uses_index(self):
        char_id = self.meta["first_char_id"]
        cards = self.dm.get_cards_by_character(char_id)
        self.assertGreaterEqual(len(cards), 1)
        self.assertTrue(all(c.get("CharactersId") == char_id for c in cards))

    def test_search_card_series_limit(self):
        query = str(self.meta.get("first_card_name") or "")[:2]
        self.assertTrue(query)
        results = self.dm.search_card_series(query, limit=1)
        self.assertEqual(len(results), 1)

    def test_search_card_series_exact_id(self):
        series_id = self.meta["first_series_id"]
        results = self.dm.search_card_series(str(series_id), limit=10)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["CardSeriesId"], series_id)

    def test_search_musics_by_id(self):
        music_id = self.meta["first_music_id"]
        results = self.dm.search_musics(str(music_id), limit=10)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["Id"], music_id)

    def test_search_musics_by_character_and_limit(self):
        query = self.meta.get("music_query_char") or str(self.meta["first_char_id"])
        results = self.dm.search_musics(query, limit=1)
        self.assertLessEqual(len(results), 1)

    def test_search_comics_by_id(self):
        comic_id = self.meta["first_comic_id"]
        results = self.dm.search_comics(str(comic_id), limit=10)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["Id"], comic_id)

    def test_search_comics_by_character(self):
        query = self.meta.get("comic_query_char") or str(self.meta["first_char_id"])
        results = self.dm.search_comics(query, limit=10)
        self.assertGreaterEqual(len(results), 1)


if __name__ == "__main__":
    unittest.main()
