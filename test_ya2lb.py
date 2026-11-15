"""Tests for ya2lb. Run with: python -m unittest"""
import csv
import os
import tempfile
import unittest

import ya2lb


def entry(title, year, kind, list_id, rating=None, mal=None, fav=False):
    return {"anime_id": 1, "anime_url": "x", "title": title, "year": year, "type": {"alias": kind},
            "remote_ids": {"myanimelist_id": mal, "kp_id": None},
            "user": {"list": {"is_fav": fav, "list": {"id": list_id}}, "rating": rating}}


class UserIdTest(unittest.TestCase):
    def test_forms(self):
        for text in ["12345", "id12345", "https://yummyani.me/users/id12345", "https://yummyani.me/users/id12345/"]:
            self.assertEqual(ya2lb.user_id(text), "12345", text)

    def test_garbage(self):
        with self.assertRaises(SystemExit):
            ya2lb.user_id("https://yummyani.me/catalog")


class ConvertTest(unittest.TestCase):
    entries = [
        entry("The Garden of Words", 2013, "movie", ya2lb.WATCHED, 9, mal=16782),
        entry("Some OVA", 2010, "ova", ya2lb.WATCHED, 7, mal=111),
        entry("Another OVA", 2011, "ova", ya2lb.WATCHED, 6, mal=222),
        entry("Attack on Titan", 2013, "tv", ya2lb.WATCHED, 8, mal=16498),
        entry("Your Name.", 2016, "movie", ya2lb.PLANNED, mal=32281),
        entry("Planned Series", 2020, "tv", ya2lb.PLANNED, mal=333),
        entry("Dropped Movie", 2019, "movie", ya2lb.DROPPED, 4, mal=444),
    ]
    ids = {16782: ("198375", "tt2591814"), 111: ("1000", None), 32281: ("372058", "tt5311514")}

    def test_split(self):
        res = ya2lb.convert(self.entries, self.ids)
        self.assertEqual([r["Title"] for r in res["films"]], ["The Garden of Words", "Some OVA"])
        self.assertEqual([r["Title"] for r in res["series"]], ["Another OVA", "Attack on Titan"])
        self.assertEqual([r["Title"] for r in res["watchlist"]], ["Your Name."])

    def test_ids_and_rating(self):
        film = ya2lb.convert(self.entries, self.ids)["films"][0]
        self.assertEqual((film["tmdbID"], film["imdbID"], film["Rating10"]), ("198375", "tt2591814", 9))
        self.assertNotIn("Rating10", ya2lb.convert(self.entries, self.ids)["watchlist"][0])

    def test_without_wikidata(self):
        res = ya2lb.convert(self.entries)
        self.assertEqual([r["Title"] for r in res["films"]], ["The Garden of Words"])
        self.assertEqual(res["films"][0]["tmdbID"], "")

    def test_also_dropped(self):
        res = ya2lb.convert(self.entries, self.ids, (ya2lb.WATCHED, ya2lb.DROPPED))
        self.assertIn("Dropped Movie", [r["Title"] for r in res["films"]])


class OutputTest(unittest.TestCase):
    def test_quotes_are_backslash_escaped(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "films.csv")
            ya2lb.write_letterboxd_csv(path, [{"Title": 'Say "Hi", world', "Year": 2000}], ["Title", "Year"])
            with open(path, encoding="utf-8") as f:
                self.assertEqual(f.read().splitlines()[1], '"Say \\"Hi\\", world",2000')

    def test_split_into_parts(self):
        with tempfile.TemporaryDirectory() as d:
            old = ya2lb.MAX_CSV_BYTES
            ya2lb.MAX_CSV_BYTES = 100
            try:
                rows = [{"Title": f"Film number {i}", "Year": 2000} for i in range(30)]
                paths = ya2lb.write_letterboxd_csv(os.path.join(d, "films.csv"), rows, ["Title", "Year"])
            finally:
                ya2lb.MAX_CSV_BYTES = old
            self.assertGreater(len(paths), 1)
            total = 0
            for p in paths:
                with open(p, encoding="utf-8", newline="") as f:
                    total += len(list(csv.reader(f))) - 1
            self.assertEqual(total, 30)


if __name__ == "__main__":
    unittest.main()
