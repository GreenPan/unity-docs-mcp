"""Tests for the SQLite FTS5-backed Unity search index."""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from unity_docs_mcp.search_index import UnitySearchIndex
from tests.helpers import make_fake_unity_install


def make_index(tmp, versions=None):
    """Build a UnitySearchIndex over a fake install and return it."""
    versions = versions if versions is not None else ["6000.5.7f1"]
    _root, created = make_fake_unity_install(tmp, versions)
    docs_dirs = {c["version"]: c["docs_dir"] for c in created}
    return UnitySearchIndex(
        docs_dirs=docs_dirs, db_dir=os.path.join(tmp, "db")
    )


class TestUnitySearchIndexInit(unittest.TestCase):
    def test_init_empty(self):
        index = UnitySearchIndex()
        self.assertEqual(index.docs_dirs, {})
        self.assertIsNone(index.default_version)
        self.assertEqual(index.pages, [])
        self.assertFalse(index._loaded)

    def test_default_version_picks_newest(self):
        tmp = tempfile.mkdtemp()
        try:
            index = make_index(tmp, ["2022.3.45f1", "6000.5.7f1"])
            self.assertEqual(index.default_version, "6000.5.7f1")
        finally:
            shutil.rmtree(tmp)

    def test_default_version_none_without_docs(self):
        tmp = tempfile.mkdtemp()
        try:
            _root, created = make_fake_unity_install(tmp, ["6000.5.7f1"])
            index = UnitySearchIndex(db_dir=os.path.join(tmp, "db"))
            self.assertIsNone(index.default_version)
            self.assertNotEqual(created, [])
        finally:
            shutil.rmtree(tmp)


class TestBuildAndEnsure(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.index = make_index(self.tmp, ["2022.3.45f1", "6000.5.7f1"])

    def tearDown(self):
        self.index.close()
        shutil.rmtree(self.tmp)

    def test_build_index_creates_db(self):
        self.assertTrue(self.index.ensure_index("6000.5.7f1"))
        db = self.index._db_path("6000.5.7f1")
        self.assertTrue(os.path.exists(db))
        # meta records the version and a positive page count
        conn = self.index._connect("6000.5.7f1")
        row = conn.execute(
            "SELECT version, page_count FROM meta WHERE version = ?",
            ("6000.5.7f1",),
        ).fetchone()
        self.assertEqual(row["version"], "6000.5.7f1")
        self.assertGreater(row["page_count"], 0)

    def test_ensure_index_reuses_existing_db(self):
        self.assertTrue(self.index.ensure_index("6000.5.7f1"))
        built_at = self.index._connect("6000.5.7f1").execute(
            "SELECT built_at FROM meta"
        ).fetchone()["built_at"]
        # Second ensure must not rebuild (built_at unchanged).
        self.assertTrue(self.index.ensure_index("6000.5.7f1"))
        again = self.index._connect("6000.5.7f1").execute(
            "SELECT built_at FROM meta"
        ).fetchone()["built_at"]
        self.assertEqual(built_at, again)

    def test_ensure_index_unknown_version(self):
        self.assertFalse(self.index.ensure_index("6000.0"))

    def test_build_index_missing_docs_dir(self):
        index = UnitySearchIndex(
            docs_dirs={"6000.5.7f1": os.path.join(self.tmp, "missing")},
            db_dir=os.path.join(self.tmp, "db2"),
        )
        self.assertFalse(index.build_index("6000.5.7f1"))

    def test_build_index_progress_cb(self):
        seen = []

        def cb(done, total):
            seen.append((done, total))

        index = make_index(self.tmp, ["2022.3.45f1"])
        self.assertTrue(index.build_index("2022.3.45f1", progress_cb=cb))
        self.assertTrue(seen)
        # last progress equals (page_count, page_count)
        conn = index._connect("2022.3.45f1")
        count = conn.execute("SELECT page_count FROM meta").fetchone()["page_count"]
        self.assertEqual(seen[-1][0], count)
        self.assertEqual(seen[-1][1], count)
        index.close()

    def test_index_js_fallback(self):
        # Remove index.json; index.js-only installs must still work.
        docdata = os.path.join(
            self.tmp, "6000.5.7f1", "Editor", "Data", "Documentation", "en",
            "ScriptReference", "docdata",
        )
        os.remove(os.path.join(docdata, "index.json"))
        index = make_index(self.tmp, ["6000.5.7f1"])
        self.assertTrue(index.ensure_index("6000.5.7f1"))
        index.close()


class TestSearch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.index = make_index(self.tmp, ["6000.5.7f1"])
        self.index.ensure_index("6000.5.7f1")

    def tearDown(self):
        self.index.close()
        shutil.rmtree(self.tmp)

    def test_search_class_by_name(self):
        results = self.index.search("GameObject", version="6000.5.7f1")
        self.assertGreater(len(results), 0)
        titles = [r["title"] for r in results]
        self.assertIn("GameObject", titles)

    def test_search_returns_expected_fields(self):
        results = self.index.search("GameObject", version="6000.5.7f1")
        self.assertGreater(len(results), 0)
        r = results[0]
        self.assertIn("title", r)
        self.assertIn("description", r)
        self.assertIn("type", r)
        self.assertIn("path", r)
        self.assertTrue(os.path.exists(r["path"]))

    def test_search_full_body_text(self):
        # "pathfinding" only appears in AI.NavMeshAgent's body, not its title.
        results = self.index.search("pathfinding", version="6000.5.7f1")
        titles = [r["title"] for r in results]
        self.assertIn("AI.NavMeshAgent", titles)

    def test_search_multiple_terms(self):
        results = self.index.search("world space position", version="6000.5.7f1")
        titles = [r["title"] for r in results]
        self.assertIn("Transform.position", titles)

    def test_search_no_results(self):
        self.assertEqual(self.index.search("zzznothing", version="6000.5.7f1"), [])

    def test_search_unknown_version_returns_empty(self):
        self.assertEqual(self.index.search("GameObject", version="6000.0"), [])

    def test_search_without_any_docs_does_not_crash(self):
        index = UnitySearchIndex()
        self.assertEqual(index.search("GameObject", "6000.0", max_results=5), [])

    def test_search_default_version(self):
        results = self.index.search("Vector3")
        self.assertGreater(len(results), 0)


class TestSuggestClasses(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.index = make_index(self.tmp, ["6000.5.7f1"])
        self.index.ensure_index("6000.5.7f1")

    def tearDown(self):
        self.index.close()
        shutil.rmtree(self.tmp)

    def test_suggest_classes_substring(self):
        suggestions = self.index.suggest_classes("game")
        self.assertIn("GameObject", suggestions)
        self.assertNotIn("Transform", suggestions)

    def test_suggest_classes_empty(self):
        self.assertEqual(self.index.suggest_classes(""), [])
        self.assertEqual(self.index.suggest_classes("  "), [])

    def test_suggest_classes_no_index(self):
        index = UnitySearchIndex()
        self.assertEqual(index.suggest_classes("game"), [])


class TestGetPageName(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.index = make_index(self.tmp, ["6000.5.7f1"])
        self.index.ensure_index("6000.5.7f1")

    def tearDown(self):
        self.index.close()
        shutil.rmtree(self.tmp)

    def test_namespaced_class(self):
        self.assertEqual(self.index.get_page_name("NavMeshAgent"), "AI.NavMeshAgent")

    def test_member_resolution(self):
        self.assertEqual(self.index.get_page_name("SetActive"), "GameObject.SetActive")

    def test_exact_class(self):
        self.assertEqual(self.index.get_page_name("GameObject"), "GameObject")

    def test_unknown(self):
        self.assertIsNone(self.index.get_page_name("DoesNotExist"))

    def test_no_index(self):
        self.assertIsNone(UnitySearchIndex().get_page_name("GameObject"))


class TestClearCache(unittest.TestCase):
    def test_clear_removes_db(self):
        tmp = tempfile.mkdtemp()
        try:
            index = make_index(tmp, ["6000.5.7f1"])
            index.ensure_index("6000.5.7f1")
            db = index._db_path("6000.5.7f1")
            self.assertTrue(os.path.exists(db))
            index.clear_cache("6000.5.7f1")
            self.assertFalse(os.path.exists(db))
        finally:
            shutil.rmtree(tmp)


class TestMemberType(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.index = make_index(self.tmp, ["6000.5.7f1"])
        self.index.ensure_index("6000.5.7f1")

    def tearDown(self):
        self.index.close()
        shutil.rmtree(self.tmp)

    def _type(self, name):
        conn = self.index._connect("6000.5.7f1")
        row = conn.execute("SELECT member_type FROM pages WHERE name = ?", (name,)).fetchone()
        return row["member_type"] if row else None

    def test_class_bare(self):
        self.assertEqual(self._type("GameObject"), "class")
        self.assertEqual(self._type("Object"), "class")

    def test_namespaced_class(self):
        self.assertEqual(self._type("AI.NavMeshAgent"), "class")

    def test_method_dotted(self):
        self.assertEqual(self._type("Object.GetInstanceID"), "method")
        self.assertEqual(self._type("GameObject.SetActive"), "method")

    def test_property_hyphen(self):
        self.assertEqual(self._type("Object-transform"), "property")

    def test_constructor(self):
        self.assertEqual(self._type("Object-ctor"), "constructor")

    def test_manual_member_type(self):
        self.assertEqual(self._type("urp/urp-introduction"), "manual")


class TestManualIndex(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.index = make_index(self.tmp, ["6000.5.7f1"])
        self.index.ensure_index("6000.5.7f1")

    def tearDown(self):
        self.index.close()
        shutil.rmtree(self.tmp)

    def test_manual_pages_are_indexed(self):
        conn = self.index._connect("6000.5.7f1")
        count = conn.execute(
            "SELECT COUNT(*) AS c FROM pages WHERE kind = 'manual'"
        ).fetchone()["c"]
        self.assertGreater(count, 0)

    def test_search_kind_manual(self):
        results = self.index.search("navigation", version="6000.5.7f1", kind="manual")
        titles = [r["title"] for r in results]
        self.assertIn("Navigation and Pathfinding", titles)

    def test_search_kind_api_excludes_manual(self):
        results = self.index.search("navigation", version="6000.5.7f1", kind="api")
        titles = [r["title"] for r in results]
        self.assertNotIn("Navigation and Pathfinding", titles)

    def test_search_unfiltered_includes_manual(self):
        results = self.index.search("navigation", version="6000.5.7f1")
        titles = [r["title"] for r in results]
        self.assertIn("Navigation and Pathfinding", titles)

    def test_manual_body_text_searchable(self):
        # "pathfinding" appears in the manual body and NavMeshAgent's body.
        results = self.index.search("pathfinding", version="6000.5.7f1", kind="manual")
        self.assertGreater(len(results), 0)

    def test_search_default_kind_none(self):
        results = self.index.search("navigation")
        self.assertGreater(len(results), 0)


class TestGetManualPage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.index = make_index(self.tmp, ["6000.5.7f1"])
        self.index.ensure_index("6000.5.7f1")

    def tearDown(self):
        self.index.close()
        shutil.rmtree(self.tmp)

    def test_exact_slug(self):
        name, title, path = self.index.get_manual_page("urp/urp-introduction")
        self.assertEqual(name, "urp/urp-introduction")
        self.assertEqual(title, "Universal Render Pipeline introduction")
        self.assertTrue(os.path.exists(path))

    def test_case_insensitive_name(self):
        name, _t, _p = self.index.get_manual_page("URP/URP-Introduction")
        self.assertEqual(name, "urp/urp-introduction")

    def test_title_exact(self):
        name, _t, _p = self.index.get_manual_page("Navigation and Pathfinding")
        self.assertEqual(name, "navigation-and-pathfinding")

    def test_name_prefix(self):
        name, _t, _p = self.index.get_manual_page("navigation-and-path")
        self.assertEqual(name, "navigation-and-pathfinding")

    def test_unknown(self):
        self.assertIsNone(self.index.get_manual_page("zzz-does-not-exist"))

    def test_empty(self):
        self.assertIsNone(self.index.get_manual_page(""))

    def test_no_index(self):
        self.assertIsNone(UnitySearchIndex().get_manual_page("urp"))


if __name__ == "__main__":
    unittest.main()
