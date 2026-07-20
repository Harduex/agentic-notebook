#!/usr/bin/env python3
"""Multilingual behavior tests for build_index.py / search_index.py.

Self-contained, stdlib only: writes fixture sources into a temp folder,
builds the index, and asserts on tokenization, ranking, chunking, and the
scanned-PDF heuristic across scripts. Run with:
  python3 test_multilingual.py
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import build_index  # noqa: E402
import search_index  # noqa: E402
from search_index import bm25_search, normalize, tokenize  # noqa: E402

# Filler so each fixture has multiple distinct chunks and BM25 has to rank.
FILLER_EN = ("This is ordinary filler text about gardening tools and weather "
             "patterns that has nothing to do with the query topic. " * 6)

# language key -> (filename, planted target paragraph, native query)
LANGS = {
    "english": ("english.md",
                "Spaced repetition is the most effective memorization technique "
                "known to cognitive science, far better than cramming.",
                "spaced repetition memorization"),
    "bulgarian": ("bulgarian.md",
                  "Войната за сила на звука съсипа динамиката на съвременната "
                  "музика и направи записите уморителни за слушане.",
                  "войната за сила на звука"),
    "german": ("german.md",
               "Die Übermüdung der Studenten führt zu schlechteren Prüfungen "
               "und weniger Motivation im Hörsaal.",
               "Übermüdung der Studenten"),
    "spanish": ("spanish.md",
                "La canción más famosa del compositor fue escrita durante su "
                "exilio en la montaña.",
                "canción famosa del compositor"),
    "chinese": ("chinese.md",
                "响度战争摧毁了现代音乐的动态范围，让录音听起来疲惫不堪。",
                "响度战争"),
    "japanese": ("japanese.md",
                 "音圧競争は現代音楽のダイナミクスを破壊し、録音を聴き疲れするものにした。",
                 "音圧競争"),
    "hebrew": ("hebrew.md",
               "מלחמת העוצמה הרסה את הדינמיקה של המוזיקה המודרנית והפכה את "
               "ההקלטות למעייפות.",
               "מלחמת העוצמה"),
    "hindi": ("hindi.md",
              "ध्वनि युद्ध ने आधुनिक संगीत की गतिशीलता को नष्ट कर दिया और "
              "रिकॉर्डिंग को थकाऊ बना दिया।",
              "ध्वनि युद्ध"),
    "mixed": ("mixed.md",
              "The mastering engineer said: 響度戦争 ruined dynamics, или "
              "войната за звука, as Bulgarians call it.",
              "mastering engineer 響度戦争"),
}


def build_fixture_folder():
    folder = Path(tempfile.mkdtemp(prefix="nb_ml_"))
    for fname, target, _q in LANGS.values():
        (folder / fname).write_text(
            FILLER_EN + "\n\n" + target + "\n\n" + FILLER_EN, encoding="utf-8")
    return folder


class Fixture:
    folder = None
    chunks = None
    cache = None


def setUpModule():
    Fixture.folder = build_fixture_folder()
    out = subprocess.run([sys.executable, str(SCRIPTS / "build_index.py"),
                          str(Fixture.folder)], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    Fixture.chunks, cj = search_index.load_chunks(Fixture.folder)
    Fixture.cache = search_index.load_or_build_cache(Fixture.folder,
                                                     Fixture.chunks, cj)


class TestTokenize(unittest.TestCase):
    def test_all_languages_tokenize(self):
        for name, (_f, target, query) in LANGS.items():
            self.assertTrue(tokenize(target), f"{name}: no tokens for target")
            self.assertTrue(tokenize(query), f"{name}: no tokens for query")

    def test_cjk_bigrams(self):
        self.assertEqual(tokenize("响度战争"), ["响度", "度战", "战争"])
        self.assertIn("音圧", tokenize("音圧競争"))

    def test_cjk_unigram_kept(self):
        self.assertEqual(tokenize("水"), ["水"])

    def test_english_stemming_regression(self):
        self.assertEqual(tokenize("mixing wars"), ["mix", "war"])

    def test_no_stem_on_non_ascii(self):
        # Cyrillic word ending in a Latin-suffix-lookalike stays whole
        self.assertEqual(tokenize("записите"), ["записите"])

    def test_accent_folding_both_ways(self):
        self.assertEqual(tokenize("über"), tokenize("uber"))
        self.assertEqual(tokenize("canción"), tokenize("cancion"))

    def test_devanagari_marks_preserved(self):
        # vowel signs must survive normalize(); stripping them collapses words
        self.assertNotEqual(normalize("की"), normalize("क"))
        self.assertEqual(tokenize("ध्वनि"), tokenize("ध्वनि"))


class TestRanking(unittest.TestCase):
    def rank1(self, query):
        res = bm25_search(query, Fixture.chunks, Fixture.cache, k=3)
        self.assertTrue(res, f"no results for {query!r}")
        return res[0][1]

    def test_native_query_ranks_target_first(self):
        for name, (fname, target, query) in LANGS.items():
            top = self.rank1(query)
            self.assertIn(target[:20], top["text"],
                          f"{name}: top hit is not the planted target")

    def test_accent_insensitive_search(self):
        top = self.rank1("cancion famosa del compositor")  # unaccented query
        self.assertIn("canción más famosa", top["text"])
        top = self.rank1("Übermüdung")  # accented query vs same corpus
        self.assertIn("Übermüdung", top["text"])

    def test_cyrillic_phrase_bonus(self):
        phrase = bm25_search("войната за сила на звука",
                             Fixture.chunks, Fixture.cache, k=1)[0][0]
        shuffled = bm25_search("звука сила войната на за",
                               Fixture.chunks, Fixture.cache, k=1)[0][0]
        self.assertGreater(phrase, shuffled)

    def test_english_regression_queries(self):
        top = self.rank1("spaced repetition")
        self.assertIn("Spaced repetition", top["text"])
        top = self.rank1("cramming memorization techniques")
        self.assertIn("cramming", top["text"])


class TestChunking(unittest.TestCase):
    def test_count_units_cjk(self):
        self.assertEqual(build_index.count_units("响度战争"), 4)
        self.assertEqual(build_index.count_units("two words"), 2)
        self.assertEqual(build_index.count_units("mix 响度 mix"), 4)

    def test_cjk_chunks_stay_near_budget(self):
        # one giant spaceless paragraph must still split into sane chunks
        para = "音圧競争は現代音楽のダイナミクスを破壊した。" * 80  # ~1760 chars
        chunks = build_index.chunk_units([("p.1", para)])
        self.assertGreater(len(chunks), 2, "CJK text produced a mega-chunk")
        for c in chunks:
            self.assertLessEqual(c["words"], build_index.CHUNK_MAX_WORDS + 50)

    def test_cjk_pdf_not_flagged_as_scan(self):
        # text-rich CJK pages must exceed the scanned-PDF threshold
        page = "响度战争摧毁了现代音乐的动态范围。让录音听起来疲惫不堪。" * 5
        units = [(f"p.{i}", page) for i in range(1, 6)]
        total = sum(build_index.count_units(t) for _, t in units)
        self.assertGreaterEqual(total / len(units),
                                build_index.SCAN_WORDS_PER_PAGE)


class TestCacheAndVersions(unittest.TestCase):
    def test_versions_bumped(self):
        self.assertEqual(search_index.TOKENIZER_VERSION, 3)
        self.assertEqual(build_index.INDEX_VERSION, 4)

    def test_tokenizer_version_in_cache_key(self):
        self.assertTrue(Fixture.cache["key"].startswith("t3_"))
        # a cache written under a different version is ignored on load
        cj = Fixture.folder / ".notebook" / "chunks.jsonl"
        old = search_index.TOKENIZER_VERSION
        try:
            search_index.TOKENIZER_VERSION = old + 1
            fresh = search_index.load_or_build_cache(Fixture.folder,
                                                     Fixture.chunks, cj)
            self.assertTrue(fresh["key"].startswith(f"t{old + 1}_"))
        finally:
            search_index.TOKENIZER_VERSION = old
            search_index.load_or_build_cache(Fixture.folder, Fixture.chunks, cj)


class TestCLI(unittest.TestCase):
    def cli(self, *args):
        out = subprocess.run([sys.executable, str(SCRIPTS / "search_index.py"),
                              str(Fixture.folder), *args],
                             capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        return out.stdout

    def test_cyrillic_bm25_cli(self):
        out = self.cli("войната за сила на звука")
        self.assertIn("bulgarian", out)
        self.assertNotIn("NO_RESULTS", out)

    def test_chinese_cli(self):
        self.assertIn("chinese", self.cli("响度战争"))

    def test_hebrew_grep_ignorecase(self):
        self.assertIn("hebrew", self.cli("--grep", "מלחמת העוצמה"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
