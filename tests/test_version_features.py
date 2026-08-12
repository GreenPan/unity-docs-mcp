"""Tests for version-related features in the offline Unity Docs MCP Server."""

import asyncio
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from unity_docs_mcp.server import UnityDocsMCPServer
from unity_docs_mcp.scraper import UnityDocScraper
from tests.helpers import make_fake_unity_install


class TestVersionFeatures(unittest.TestCase):
    """Server-level version handling (offline resolution)."""

    def setUp(self):
        self.server = UnityDocsMCPServer()
        self.scraper = Mock()
        self.scraper.installed = [Mock()]
        self.resolved = Mock()
        self.resolved.name = "6000.5.7f1"
        self.scraper.resolve_version.return_value = self.resolved
        self.scraper.get_supported_versions.return_value = ["6000.5.7f1", "2022.3.45f1"]
        self.server.scraper = self.scraper

    async def _call(self, fn, *args):
        return await fn(*args)

    def test_default_version_uses_latest_installed(self):
        # resolve_version(None) resolves to newest installed.
        with patch.object(self.server.scraper, "get_api_doc") as mock_get:
            mock_get.return_value = {
                "status": "success",
                "html": "<html>GameObject</html>",
                "url": "C:/docs/GameObject.html",
            }
            with patch.object(
                self.server.parser, "parse_api_doc"
            ) as mock_parse:
                mock_parse.return_value = {
                    "title": "GameObject",
                    "content": "Content",
                    "url": "C:/docs/GameObject.html",
                }
                result = asyncio.run(
                    self._call(self.server._get_unity_api_doc, "GameObject", None, None)
                )
        self.assertIn("**Unity Version:** 6000.5.7f1", result[0].text)

    def test_version_prefix_display_from_original(self):
        # A full version that resolves is shown as the resolved install name.
        with patch.object(self.server.scraper, "get_api_doc") as mock_get:
            mock_get.return_value = {
                "status": "success",
                "html": "<html>GameObject</html>",
                "url": "C:/docs/GameObject.html",
            }
            with patch.object(self.server.parser, "parse_api_doc") as mock_parse:
                mock_parse.return_value = {
                    "title": "GameObject",
                    "content": "Content",
                    "url": "C:/docs/GameObject.html",
                }
                result = asyncio.run(
                    self.server._get_unity_api_doc("GameObject", None, "6000.5")
                )
        self.assertIn("**Unity Version:** 6000.5.7f1 (from 6000.5)", result[0].text)

    def test_uninstalled_version_falls_back(self):
        # "6000.0" isn't installed -> falls back to newest with a note.
        def resolve(v):
            return None if v == "6000.0" else self.resolved

        self.scraper.resolve_version.side_effect = resolve
        with patch.object(self.server.scraper, "get_api_doc") as mock_get:
            mock_get.return_value = {
                "status": "success",
                "html": "<html>GameObject</html>",
                "url": "C:/docs/GameObject.html",
            }
            with patch.object(self.server.parser, "parse_api_doc") as mock_parse:
                mock_parse.return_value = {
                    "title": "GameObject",
                    "content": "Content",
                    "url": "C:/docs/GameObject.html",
                }
                result = asyncio.run(
                    self.server._get_unity_api_doc("GameObject", None, "6000.0")
                )
        self.assertIn("6000.0 not installed; using 6000.5.7f1", result[0].text)
        self.assertNotIn("Error", result[0].text)

    def test_no_install_error(self):
        self.scraper.installed = []
        result = asyncio.run(self.server._get_unity_api_doc("GameObject", None, None))
        self.assertIn("No local Unity documentation found", result[0].text)

    def test_error_with_version_availability_info(self):
        # resolve_version returns an installed version (has a real .name).
        self.scraper.resolve_version.return_value = self.resolved
        with patch.object(self.server.scraper, "get_api_doc") as mock_get:
            mock_get.return_value = {"status": "error"}
            self.scraper.check_api_availability_across_versions.return_value = {
                "available": ["6000.5.7f1"],
                "unavailable": ["2022.3.45f1"],
            }
            result = asyncio.run(
                self.server._get_unity_api_doc("AsyncGPUReadback", None, "6000.5")
            )
        content = result[0].text
        self.assertIn("not found in Unity 6000.5.7f1", content)
        self.assertIn("**Available in versions:** 6000.5.7f1", content)
        self.assertIn("**Not available in:** 2022.3.45f1", content)


class TestVersionDetection(unittest.TestCase):
    """Local version detection (newest installed)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root, _ = make_fake_unity_install(
            self.tmp, ["2022.3.45f1", "6000.5.7f1", "2023.2.0a1"]
        )

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_get_latest_version_newest_installed(self):
        scraper = UnityDocScraper(editor_root=self.root)
        self.assertEqual(scraper.get_latest_version(), "6000.5.7f1")
        scraper.search_index.close()

    def test_get_supported_versions_sorted(self):
        scraper = UnityDocScraper(editor_root=self.root)
        self.assertEqual(
            scraper.get_supported_versions(), ["6000.5.7f1", "2023.2.0a1", "2022.3.45f1"]
        )
        scraper.search_index.close()

    def test_get_latest_version_no_install(self):
        scraper = UnityDocScraper(editor_root="")
        self.assertEqual(scraper.get_latest_version(), "")
        scraper.search_index.close()


class TestVersionFormatEdgeCases(unittest.TestCase):
    """normalize_version still reduces full versions to major.minor."""

    def setUp(self):
        self.scraper = UnityDocScraper(editor_root="")

    def tearDown(self):
        self.scraper.search_index.close()

    def test_normalize_invalid_formats(self):
        test_cases = [
            "invalid",
            "abc.def",
            ".",
            "..",
            "2023.",
            ".2023",
            "",
            "!@#$",
        ]
        for version in test_cases:
            with self.subTest(version=version):
                self.assertEqual(self.scraper.normalize_version(version), version)

        # Whitespace-only strings get stripped to empty string.
        self.assertEqual(self.scraper.normalize_version("   "), "")

    def test_normalize_full_versions(self):
        self.assertEqual(self.scraper.normalize_version("6000.0.29f1"), "6000.0")
        self.assertEqual(self.scraper.normalize_version("2022.3.45f1"), "2022.3")
        self.assertEqual(self.scraper.normalize_version("Unity 6000.5"), "6000.5")


if __name__ == "__main__":
    unittest.main()
