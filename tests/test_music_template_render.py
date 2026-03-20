import unittest
from pathlib import Path

import jinja2


class MusicTemplateRenderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        template_dir = Path(__file__).resolve().parents[1] / "src" / "templates"
        cls.env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(template_dir)),
            autoescape=jinja2.select_autoescape(["html", "xml"]),
        )
        cls.env.globals["config"] = {
            "ASSETS_ICON_URL": "file:///assets/icons",
            "ICON_BASE_URL": "file:///exports/icons/skill",
            "ICON_SECTION_URL": "file:///exports/icons/section",
            "ICON_ITEM_URL": "file:///exports/icons/item",
            "ICON_FACE_URL": "file:///exports/icons/face",
            "IMG_MUSIC_THUMBNAIL_URL": "file:///exports/images/music/thumbnail",
            "IMG_COMIC_THUMBNAIL_URL": "file:///exports/images/comic_thumbnail",
            "IMG_CARD_FULL_URL": "file:///exports/images/card_full",
            "IMG_CARD_HALF_URL": "file:///exports/images/card_half",
            "IMG_CARD_MIDDLE_VERTICAL_URL": "file:///exports/images/card_middle_vertical",
            "IMG_DECK_FRAME_CHARA_URL": "file:///exports/images/deck_frame_chara",
            "IMG_PROF_CUSTOM_URL": "file:///exports/images/prof_custom",
            "IMG_STICKER_URL": "file:///exports/images/sticker",
            "IMG_GACHA_CARDINFO_URL": "file:///exports/images/gacha_cardinfo",
        }

    def _build_music(self, **kwargs):
        data = {
            "music_id": 205103,
            "title": "37.5℃のファンタジー",
            "title_len": 13,
            "title_size_class": "lg",
            "description": "",
            "song_type": 1,
            "song_type_label": "原创曲",
            "mood_name": "Happy",
            "music_type_icon_key": "smile",
            "play_time_ms": 97500,
            "duration_text": "1:37",
            "generations_id": 105,
            "generation_label": "105期",
            "center_name": "角色A",
            "center_id": 1021,
            "singers": ["角色A", "角色B"],
            "supports": ["角色C"],
            "singer_ids": [1021, 1022],
            "support_ids": [1031, 1032],
            "fever_section_no": 2,
            "mood_key": "smile",
            "score": {
                "NormalLevel": 12,
                "HardLevel": 18,
                "ExpertLevel": 26,
                "MasterLevel": 28,
                "NormalMaxCombo": 323,
                "HardMaxCombo": 415,
                "ExpertMaxCombo": 737,
                "MasterMaxCombo": 892,
            },
            "chart": {
                "total_time_sec": 97.5,
                "sections": [
                    {"index": 1, "percentage": 25, "beat_count": 80, "duration_sec": 24.0},
                    {"index": 2, "percentage": 25, "beat_count": 81, "duration_sec": 24.0},
                    {"index": 3, "percentage": 25, "beat_count": 82, "duration_sec": 24.0},
                    {"index": 4, "percentage": 25, "beat_count": 83, "duration_sec": 25.5},
                ],
                "moods": [{"x": 0, "y": 50}, {"x": 100, "y": 40}],
            },
            "quest_live_stages": [],
            "grade_live_stages": [],
            "grand_prix_stages": [],
            "mastery_levels": [],
        }
        data.update(kwargs)
        return data

    def test_render_title_size_classes(self):
        template = self.env.get_template("music.html")
        cases = [
            ("短歌", "xl"),
            ("普通长度歌曲名", "lg"),
            ("这是一个长度适中的歌曲名字用于中等字号", "md"),
            ("这是一个明显偏长的歌曲标题用于验证小字号策略", "sm"),
            ("这是一个超超超超超超超超超超超超超超超超超超超超长标题用于测试最小字号", "xs"),
        ]
        for title, size_class in cases:
            with self.subTest(size_class=size_class):
                html = template.render(
                    query="测试",
                    musics=[
                        self._build_music(
                            title=title,
                            title_len=len(title),
                            title_size_class=size_class,
                        )
                    ],
                    is_limited=False,
                    max_results=12,
                )
                self.assertIn(f"music-name-{size_class}", html)
                self.assertIn('<div class="music-id">#205103</div>', html)

    def test_render_music_type_and_fallback(self):
        template = self.env.get_template("music.html")
        icon_cases = [("smile", "icon_smile.png"), ("pure", "icon_pure.png"), ("cool", "icon_cool.png")]
        for icon_key, icon_name in icon_cases:
            with self.subTest(icon_key=icon_key):
                html = template.render(
                    query="测试",
                    musics=[self._build_music(music_type_icon_key=icon_key)],
                    is_limited=False,
                    max_results=12,
                )
                self.assertIn(icon_name, html)

        fallback_html = template.render(
            query="测试",
            musics=[
                self._build_music(
                    generations_id=None,
                    generation_label="",
                    music_type_icon_key=None,
                    singer_ids=[],
                    support_ids=[],
                    chart=None,
                )
            ],
            is_limited=False,
            max_results=12,
        )
        self.assertIn("无分析数据", fallback_html)
        self.assertIn("暂无", fallback_html)
        self.assertNotIn("icon_None.png", fallback_html)


if __name__ == "__main__":
    unittest.main()
