"""Tests for Unity version resolution (local installs)."""

import os
import sys
import tempfile
import unittest
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from unity_docs_mcp.version_resolver import (
    InstalledVersion,
    parse_unity_version,
    normalize_to_major_minor,
    discover_versions,
    resolve_version,
    default_editor_root,
)
from tests.helpers import make_fake_unity_install


class TestParseUnityVersion(unittest.TestCase):
    def test_final_build(self):
        self.assertEqual(parse_unity_version("6000.5.7f1"), (6000, 5, 7, 3, 1, 0))
        self.assertEqual(parse_unity_version("2022.3.45f1"), (2022, 3, 45, 3, 1, 0))

    def test_alpha_beta_rc(self):
        self.assertEqual(parse_unity_version("2022.3.0b12"), (2022, 3, 0, 1, 12, 0))
        self.assertEqual(parse_unity_version("2021.3.0rc2"), (2021, 3, 0, 2, 2, 0))
        self.assertEqual(parse_unity_version("2021.3.0a5"), (2021, 3, 0, 0, 5, 0))

    def test_final_newer_than_beta(self):
        final = parse_unity_version("2022.3.0f1")
        beta = parse_unity_version("2022.3.0b99")
        self.assertGreater(final, beta)

    def test_revision(self):
        self.assertEqual(parse_unity_version("2019.4.0f1c2"), (2019, 4, 0, 3, 1, 2))

    def test_invalid(self):
        self.assertIsNone(parse_unity_version("GameObject"))
        self.assertIsNone(parse_unity_version("6000.5"))
        self.assertIsNone(parse_unity_version(""))
        self.assertIsNone(parse_unity_version("Editor"))


class TestNormalizeToMajorMinor(unittest.TestCase):
    def test_full_version(self):
        self.assertEqual(normalize_to_major_minor("6000.0.29f1"), "6000.0")
        self.assertEqual(normalize_to_major_minor("2022.3.45f1"), "2022.3")

    def test_prefixes(self):
        self.assertEqual(normalize_to_major_minor("Unity 6000.0.29f1"), "6000.0")
        self.assertEqual(normalize_to_major_minor("v2022.3.1f1"), "2022.3")

    def test_unchanged(self):
        self.assertEqual(normalize_to_major_minor("6000.0"), "6000.0")
        self.assertEqual(normalize_to_major_minor(""), "")


class TestDiscoverVersions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_discovers_and_sorts_newest_first(self):
        root, _ = make_fake_unity_install(self.tmp, ["2022.3.45f1", "6000.5.7f1", "2023.2.0a1"])
        installed = discover_versions(root)
        self.assertEqual([v.name for v in installed], ["6000.5.7f1", "2023.2.0a1", "2022.3.45f1"])

    def test_skips_non_version_dirs(self):
        root, _ = make_fake_unity_install(self.tmp, ["6000.5.7f1"])
        os.makedirs(os.path.join(root, "Editor"), exist_ok=True)
        os.makedirs(os.path.join(root, "Hub"), exist_ok=True)
        installed = discover_versions(root)
        self.assertEqual([v.name for v in installed], ["6000.5.7f1"])

    def test_skips_version_dirs_without_docs(self):
        root, _ = make_fake_unity_install(self.tmp, ["6000.5.7f1"])
        os.makedirs(os.path.join(root, "2022.3.0f1"), exist_ok=True)
        installed = discover_versions(root)
        self.assertEqual([v.name for v in installed], ["6000.5.7f1"])

    def test_empty_or_missing_root(self):
        self.assertEqual(discover_versions(""), [])
        self.assertEqual(discover_versions(os.path.join(self.tmp, "nope")), [])

    def test_macos_layout(self):
        version = "6000.5.7f1"
        docs_dir = os.path.join(
            self.tmp, version, "Unity.app", "Contents", "Documentation", "en",
            "ScriptReference",
        )
        os.makedirs(os.path.join(docs_dir, "docdata"), exist_ok=True)
        with open(os.path.join(docs_dir, "GameObject.html"), "w") as f:
            f.write("<h1>GameObject</h1>")
        installed = discover_versions(self.tmp)
        self.assertEqual([v.name for v in installed], [version])
        self.assertTrue(installed[0].docs_dir.endswith("Documentation" + os.sep + "en"))


class TestResolveVersion(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root, _ = make_fake_unity_install(
            self.tmp, ["2022.3.45f1", "6000.5.7f1", "2023.2.0a1"]
        )
        self.installed = discover_versions(self.root)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_none_returns_newest(self):
        self.assertEqual(resolve_version(None, self.installed).name, "6000.5.7f1")
        self.assertEqual(resolve_version("", self.installed).name, "6000.5.7f1")

    def test_exact_match(self):
        self.assertEqual(resolve_version("2022.3.45f1", self.installed).name, "2022.3.45f1")

    def test_case_insensitive(self):
        self.assertEqual(resolve_version("6000.5.7F1", self.installed).name, "6000.5.7f1")

    def test_prefix_match(self):
        self.assertEqual(resolve_version("6000", self.installed).name, "6000.5.7f1")
        self.assertEqual(resolve_version("6000.5", self.installed).name, "6000.5.7f1")
        self.assertEqual(resolve_version("6000.5.7", self.installed).name, "6000.5.7f1")
        self.assertEqual(resolve_version("2022.3", self.installed).name, "2022.3.45f1")

    def test_shared_prefix_picks_newest(self):
        root, _ = make_fake_unity_install(self.tmp, ["6000.1.0f1", "6000.5.7f1"])
        installed = discover_versions(root)
        self.assertEqual(resolve_version("6000", installed).name, "6000.5.7f1")

    def test_not_installed(self):
        self.assertIsNone(resolve_version("6000.0", self.installed))
        self.assertIsNone(resolve_version("2019.4", self.installed))
        self.assertIsNone(resolve_version("Foo.Bar", self.installed))

    def test_unity_prefix_input(self):
        self.assertEqual(
            resolve_version("Unity 6000.5", self.installed).name, "6000.5.7f1"
        )

    def test_empty_installed(self):
        self.assertIsNone(resolve_version("6000.5", []))
        self.assertIsNone(resolve_version(None, []))


class TestDefaultEditorRoot(unittest.TestCase):
    def test_returns_dir_or_none(self):
        root = default_editor_root()
        if root is not None:
            self.assertTrue(os.path.isdir(root))


if __name__ == "__main__":
    unittest.main()
