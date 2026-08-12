"""Tests for caching: API availability cache and SQLite search index reuse."""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from unity_docs_mcp.search_index import UnitySearchIndex
from unity_docs_mcp.scraper import UnityDocScraper
from unity_docs_mcp.version_resolver import discover_versions
from tests.helpers import make_fake_unity_install


class TestAPICaching(unittest.TestCase):
    """The API availability cache is now in-memory (per-install docs are static)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root, _ = make_fake_unity_install(self.tmp, ["6000.5.7f1"])
        idx = UnitySearchIndex(
            docs_dirs={v.name: v.docs_dir for v in discover_versions(self.root)},
            db_dir=os.path.join(self.tmp, "db"),
        )
        self.scraper = UnityDocScraper(editor_root=self.root, search_index=idx)
        self.scraper._api_cache = {}

    def tearDown(self):
        self.scraper.search_index.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_availability_result_cached(self):
        info1 = self.scraper.check_api_availability_across_versions("GameObject")
        self.assertIn("6000.5.7f1", info1["available"])
        # Second call should come from the in-memory cache.
        info2 = self.scraper.check_api_availability_across_versions("GameObject")
        self.assertEqual(info1, info2)

    def test_missing_api_uncached_across_versions(self):
        info = self.scraper.check_api_availability_across_versions("NopeNotReal")
        self.assertEqual(info["available"], [])
        self.assertEqual(info["unavailable"], ["6000.5.7f1"])


class TestSearchIndexCaching(unittest.TestCase):
    """SQLite FTS5 is the persistence layer; meta validity gates reuse."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root, _created = make_fake_unity_install(
            self.tmp, ["2022.3.45f1", "6000.5.7f1"]
        )
        self.index = UnitySearchIndex(
            docs_dirs={
                c["version"]: c["docs_dir"]
                for c in make_fake_unity_install(self.tmp, ["2022.3.45f1", "6000.5.7f1"])[1]
            },
            db_dir=os.path.join(self.tmp, "db"),
        )

    def tearDown(self):
        self.index.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_build_then_reuse(self):
        self.assertTrue(self.index.ensure_index("6000.5.7f1"))
        db = self.index._db_path("6000.5.7f1")
        self.assertTrue(os.path.exists(db))
        # Second ensure_index should reuse the existing db (fast path).
        self.assertTrue(self.index.ensure_index("6000.5.7f1"))

    def test_same_version_new_location_rebuilds(self):
        a = os.path.join(self.tmp, "a")
        make_fake_unity_install(a, ["6000.5.7f1"])
        idx = UnitySearchIndex(
            docs_dirs={c["version"]: c["docs_dir"]
                       for c in make_fake_unity_install(a, ["6000.5.7f1"])[1]},
            db_dir=os.path.join(self.tmp, "dbm"),
        )
        self.assertTrue(idx.ensure_index("6000.5.7f1"))
        b = os.path.join(self.tmp, "b")
        make_fake_unity_install(b, ["6000.5.7f1"])
        idx.docs_dirs = {c["version"]: c["docs_dir"]
                         for c in make_fake_unity_install(b, ["6000.5.7f1"])[1]}
        # Same version name, different source dir -> must rebuild (meta check).
        self.assertTrue(idx.ensure_index("6000.5.7f1", force=False))
        conn = idx._connect("6000.5.7f1")
        row = conn.execute("SELECT source_dir FROM meta").fetchone()
        self.assertEqual(row["source_dir"], idx.docs_dirs["6000.5.7f1"])
        idx.close()

    def test_clear_removes_db(self):
        self.index.ensure_index("6000.5.7f1")
        self.index.clear_cache("6000.5.7f1")
        self.assertFalse(os.path.exists(self.index._db_path("6000.5.7f1")))


if __name__ == "__main__":
    unittest.main()
