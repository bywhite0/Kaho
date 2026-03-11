import re


class DataManagerSearchMixin:
    def _normalize_name_key(self, text):
        return re.sub(r"\s+", "", str(text or "")).lower()

    def get_character_id_by_name(self, name):
        self._ensure("characters")
        target = self._normalize_name_key(name)
        if not target:
            return None
        return self.character_alias_map.get(target)

    def get_card_series_data(self, series_id):
        self._ensure("card_datas")
        return list(self.card_series_index.get(series_id, []))

    def get_cards_by_character(self, char_id):
        self._ensure("card_datas")
        return list(self.cards_by_character_index.get(char_id, []))

    def get_all_card_datas(self):
        self._ensure("card_datas")
        return self.card_datas

    def search_card_series(self, query, limit=30):
        self._ensure("card_datas")
        target = str(query or "").strip().lower()
        if not target:
            return []
        if target.isdigit():
            series_id = int(target)
            cards = self.card_series_index.get(series_id, [])
            return [cards[0]] if cards else []
        max_results = max(int(limit or 0), 1)
        results = []
        for card in self.card_series_heads:
            if target in str(card.get("Name") or "").lower():
                results.append(card)
                if len(results) >= max_results:
                    break
        return results

    def _apply_limit(self, results, limit):
        if limit is None:
            return results
        try:
            max_items = int(limit)
        except (TypeError, ValueError):
            return results
        if max_items <= 0:
            return []
        if len(results) <= max_items:
            return results
        return results[:max_items]

    def search_comics(self, query, limit=None):
        self._ensure("comics", "characters")
        if query is None:
            query = ""
        query = str(query).strip()
        results = []
        if query == "":
            return results
        if query.isdigit():
            target_id = int(query)
            matched = self.comic_by_id.get(target_id)
            if matched:
                results.append(matched)
            return self._apply_limit(results, limit)
        char_id = self.get_character_id_by_name(query)
        if char_id:
            return self._apply_limit(
                list(self.comics_by_character.get(char_id, [])),
                limit,
            )
        q_lower = query.lower()
        for entry in self.comics:
            name = str(entry.get("Name") or "")
            if q_lower in name.lower():
                results.append(entry)
        return self._apply_limit(results, limit)

    def search_musics(self, query, limit=None):
        self._ensure("musics", "characters")
        if query is None:
            query = ""
        query = str(query).strip()
        results = []
        if query == "":
            return results
        if query.isdigit() and len(query) > 5:
            target_id = int(query)
            matched = self.music_by_id.get(target_id)
            if matched:
                results.append(matched)
            return self._apply_limit(results, limit)
        char_id = self.get_character_id_by_name(query)
        if char_id:
            return self._apply_limit(
                list(self.musics_by_character.get(char_id, [])),
                limit,
            )
        q_lower = query.lower()
        for entry in self.musics:
            title = str(entry.get("Title") or "")
            if q_lower in title.lower():
                results.append(entry)
        return self._apply_limit(results, limit)
