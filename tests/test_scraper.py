"""Tests for the local (offline) UnityDocScraper."""

import contextlib
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from unity_docs_mcp.scraper import UnityDocScraper
from unity_docs_mcp.search_index import UnitySearchIndex
from unity_docs_mcp.version_resolver import discover_versions
from tests.helpers import make_fake_unity_install


class TestUnityDocScraper(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._db_n = 0
        self.root, _ = make_fake_unity_install(
            self.tmp, ["2022.3.45f1", "6000.5.7f1"]
        )
        self.scraper = self._make_scraper(self.root)

    def tearDown(self):
        self.scraper.search_index.close()
        shutil.rmtree(self.tmp)

    # ------------------------------------------------------------- setup

    def test_initialization(self):
        self.assertIsNotNone(self.scraper)
        self.assertEqual(
            [v.name for v in self.scraper.installed], ["6000.5.7f1", "2022.3.45f1"]
        )
        self.assertEqual(
            self.scraper.get_supported_versions(), ["6000.5.7f1", "2022.3.45f1"]
        )

    def _make_scraper(self, editor_root):
        versions = discover_versions(editor_root)
        self._db_n += 1
        idx = UnitySearchIndex(
            docs_dirs={v.name: v.docs_dir for v in versions},
            db_dir=os.path.join(self.tmp, f"db{self._db_n}"),
        )
        return UnityDocScraper(editor_root=editor_root, search_index=idx)

    def test_editor_root_resolution_priority(self):
        other_root = os.path.join(self.tmp, "other")
        make_fake_unity_install(other_root, ["2023.2.0a1"])
        scraper = self._make_scraper(other_root)
        self.assertEqual(scraper.editor_root, other_root)
        self.assertEqual(scraper.get_supported_versions(), ["2023.2.0a1"])
        scraper.search_index.close()

    def test_env_var_resolution(self):
        other_root = os.path.join(self.tmp, "envroot")
        make_fake_unity_install(other_root, ["2023.2.0a1"])
        with self._env("UNITY_HUB_EDITOR_DIR", other_root):
            scraper = self._make_scraper(None)
            self.assertEqual(scraper.editor_root, other_root)
            scraper.search_index.close()

    def test_no_editor_root_no_install(self):
        # editor_root="" resolves to None (no install); a fresh empty db_dir
        # means no docs_dirs and no leftover index to fall back to.
        self._db_n += 1
        idx = UnitySearchIndex(
            docs_dirs={}, db_dir=os.path.join(self.tmp, f"db{self._db_n}")
        )
        scraper = UnityDocScraper(editor_root="", search_index=idx)
        self.assertEqual(scraper.get_supported_versions(), [])
        self.assertEqual(scraper.get_latest_version(), "")
        # Suggest still works (returns empty without an index).
        self.assertIsInstance(scraper.suggest_class_names("game"), list)
        scraper.search_index.close()

    # ------------------------------------------------------------- versions

    def test_get_latest_version(self):
        self.assertEqual(self.scraper.get_latest_version(), "6000.5.7f1")

    def test_normalize_version(self):
        self.assertEqual(self.scraper.normalize_version("6000.0.29f1"), "6000.0")
        self.assertEqual(self.scraper.normalize_version("2022.3.45f1"), "2022.3")
        self.assertEqual(self.scraper.normalize_version("6000.5"), "6000.5")

    def test_validate_version_exact_and_prefix(self):
        self.assertTrue(self.scraper.validate_version("6000.5.7f1"))
        self.assertTrue(self.scraper.validate_version("6000"))
        self.assertTrue(self.scraper.validate_version("2022.3"))
        self.assertFalse(self.scraper.validate_version("6000.0"))
        self.assertFalse(self.scraper.validate_version("2019.4"))
        self.assertFalse(self.scraper.validate_version("Foo"))

    def test_resolve_version(self):
        self.assertEqual(
            self.scraper.resolve_version("6000.5").name, "6000.5.7f1"
        )
        self.assertEqual(self.scraper.resolve_version(None).name, "6000.5.7f1")
        self.assertIsNone(self.scraper.resolve_version("6000.0"))

    # ------------------------------------------------------------- api doc

    def test_get_api_doc_class(self):
        result = self.scraper.get_api_doc("GameObject", version="6000.5.7f1")
        self.assertEqual(result["status"], "success")
        self.assertIn("GameObject", result["html"])
        self.assertTrue(os.path.exists(result["url"]))
        self.assertIn("ScriptReference", result["url"])

    def test_get_api_doc_method_dot_and_hyphen(self):
        result = self.scraper.get_api_doc(
            "GameObject", "SetActive", version="6000.5.7f1"
        )
        self.assertEqual(result["status"], "success")
        self.assertIn("GameObject.SetActive.html", result["url"])

    def test_get_api_doc_namespaced_class(self):
        result = self.scraper.get_api_doc("NavMeshAgent", version="6000.5.7f1")
        self.assertEqual(result["status"], "success")
        self.assertIn("AI.NavMeshAgent.html", result["url"])

    def test_get_api_doc_missing_class(self):
        result = self.scraper.get_api_doc("NopeNotReal", version="6000.5.7f1")
        self.assertEqual(result["status"], "error")

    def test_get_api_doc_uninstalled_version(self):
        result = self.scraper.get_api_doc("GameObject", version="6000.0")
        self.assertEqual(result["status"], "error")
        self.assertIn("Installed versions", result["error"])

    def test_get_api_doc_default_version(self):
        result = self.scraper.get_api_doc("GameObject")
        self.assertEqual(result["status"], "success")
        self.assertIn("6000.5.7f1", result["url"])

    # ------------------------------------------------------------- search

    def test_search_docs(self):
        result = self.scraper.search_docs("transform", version="6000.5.7f1")
        self.assertEqual(result["status"], "success")
        self.assertGreater(result["count"], 0)
        titles = [r["title"] for r in result["results"]]
        self.assertIn("Transform", titles)

    def test_search_docs_returns_local_paths(self):
        result = self.scraper.search_docs("transform", version="6000.5.7f1")
        first = result["results"][0]
        self.assertIn("path", first)
        self.assertTrue(os.path.exists(first["path"]))
        # Path is posix-style (forward slashes).
        self.assertNotIn("\\", first["path"])

    def test_search_docs_uninstalled_version_falls_back(self):
        # "6000.0" isn't installed -> falls back to newest installed.
        result = self.scraper.search_docs("transform", version="6000.0")
        self.assertEqual(result["status"], "success")
        titles = [r["title"] for r in result["results"]]
        self.assertIn("Transform", titles)

    # ------------------------------------------------------------- suggest

    def test_suggest_class_names(self):
        suggestions = self.scraper.suggest_class_names("game")
        self.assertIn("GameObject", suggestions)
        self.assertIsInstance(suggestions, list)

    # ------------------------------------------------------------- manual

    def test_get_manual_doc_exact_slug(self):
        result = self.scraper.get_manual_doc("urp/urp-introduction", version="6000.5.7f1")
        self.assertEqual(result["status"], "success")
        self.assertIn("Universal Render Pipeline", result["html"])
        self.assertTrue(os.path.exists(result["url"]))

    def test_get_manual_doc_title_match(self):
        result = self.scraper.get_manual_doc(
            "Navigation and Pathfinding", version="6000.5.7f1"
        )
        self.assertEqual(result["status"], "success")
        self.assertIn("navigation-and-pathfinding.html", result["url"])

    def test_get_manual_doc_falls_back_to_search(self):
        result = self.scraper.get_manual_doc("navmesh navigate", version="6000.5.7f1")
        self.assertEqual(result["status"], "search")
        self.assertGreater(result["count"], 0)
        titles = [r["title"] for r in result["results"]]
        self.assertTrue(any("Navigation" in t for t in titles))

    def test_get_manual_doc_no_install(self):
        self._db_n += 1
        idx = UnitySearchIndex(
            docs_dirs={}, db_dir=os.path.join(self.tmp, f"db{self._db_n}")
        )
        scraper = UnityDocScraper(editor_root="", search_index=idx)
        result = scraper.get_manual_doc("urp")
        self.assertEqual(result["status"], "error")
        scraper.search_index.close()

    # ------------------------------------------------------------- availability

    def test_check_api_availability_across_versions(self):
        info = self.scraper.check_api_availability_across_versions("GameObject")
        self.assertIn("6000.5.7f1", info["available"])
        self.assertIn("2022.3.45f1", info["available"])
        self.assertEqual(info["unavailable"], [])

    def test_check_api_availability_missing(self):
        info = self.scraper.check_api_availability_across_versions("NopeNotReal")
        self.assertEqual(info["available"], [])
        self.assertEqual(
            sorted(info["unavailable"]), ["2022.3.45f1", "6000.5.7f1"]
        )

    def test_check_api_availability_cached(self):
        info1 = self.scraper.check_api_availability_across_versions("GameObject")
        info2 = self.scraper.check_api_availability_across_versions("GameObject")
        self.assertEqual(info1, info2)

    # ------------------------------------------------------------- helpers

    @staticmethod
    def _env(key, value):
        @contextlib.contextmanager
        def ctx():
            old = os.environ.get(key)
            os.environ[key] = value
            try:
                yield
            finally:
                if old is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = old

        return ctx()


if __name__ == "__main__":
    unittest.main()
