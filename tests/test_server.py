"""Tests for Unity Docs MCP Server."""

import unittest
import asyncio
from unittest.mock import Mock, patch, AsyncMock, MagicMock

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from unity_docs_mcp.server import UnityDocsMCPServer
from mcp.types import TextContent


class TestUnityDocsMCPServer(unittest.TestCase):
    """Test cases for UnityDocsMCPServer."""

    def setUp(self):
        """Set up test fixtures."""
        self.server = UnityDocsMCPServer()

    def test_server_initialization(self):
        """Test server initialization."""
        self.assertIsNotNone(self.server.server)
        self.assertIsNotNone(self.server.scraper)
        self.assertIsNotNone(self.server.parser)

    @patch("unity_docs_mcp.server.UnityDocScraper")
    @patch("unity_docs_mcp.server.UnityDocParser")
    async def test_get_unity_api_doc_success(
        self, mock_parser_class, mock_scraper_class
    ):
        """Test successful API documentation retrieval."""
        # Setup mocks
        mock_scraper = Mock()
        mock_parser = Mock()
        mock_scraper_class.return_value = mock_scraper
        mock_parser_class.return_value = mock_parser

        mock_scraper.validate_version.return_value = True
        mock_scraper.get_api_doc.return_value = {
            "status": "success",
            "html": "<html>Test content</html>",
            "url": "https://docs.unity3d.com/6000.0/Documentation/ScriptReference/GameObject.html",
        }
        mock_parser.parse_api_doc.return_value = {
            "title": "GameObject",
            "content": "# GameObject\n\nTest content",
            "url": "https://docs.unity3d.com/6000.0/Documentation/ScriptReference/GameObject.html",
        }

        # Create new server instance with mocked dependencies
        server = UnityDocsMCPServer()
        server.scraper = mock_scraper
        server.parser = mock_parser

        # Test the method
        result = await server._get_unity_api_doc("GameObject", None, "6000.0")

        # Assertions
        self.assertEqual(len(result), 1)
        self.assertIsInstance(result[0], TextContent)
        content = result[0].text
        self.assertIn("GameObject", content)
        self.assertIn("Test content", content)
        self.assertIn("https://docs.unity3d.com", content)

    @patch("unity_docs_mcp.server.UnityDocScraper")
    async def test_get_unity_api_doc_uninstalled_falls_back(self, mock_scraper_class):
        """An uninstalled version falls back to the newest installed with a note."""
        mock_scraper = Mock()
        mock_scraper_class.return_value = mock_scraper
        mock_scraper.installed = [Mock()]
        # "invalid" doesn't resolve; newest installed (6000.5.7f1) is returned.
        resolved = Mock()
        resolved.name = "6000.5.7f1"
        mock_scraper.resolve_version.side_effect = lambda v: (None if v == "invalid" else resolved)
        mock_scraper.get_api_doc.return_value = {
            "status": "success",
            "html": "<html>GameObject</html>",
            "url": "C:/docs/GameObject.html",
        }
        mock_scraper.search_docs.return_value = {"status": "success", "results": []}

        server = UnityDocsMCPServer()
        server.scraper = mock_scraper
        with patch.object(server.parser, "parse_api_doc") as mock_parse:
            mock_parse.return_value = {
                "title": "GameObject",
                "content": "Content",
                "url": "C:/docs/GameObject.html",
            }
            result = await server._get_unity_api_doc("GameObject", None, "invalid")

        self.assertEqual(len(result), 1)
        self.assertIn("invalid not installed; using 6000.5.7f1", result[0].text)
        self.assertNotIn("Error", result[0].text)

    @patch("unity_docs_mcp.server.UnityDocScraper")
    async def test_get_unity_api_doc_scraper_error(self, mock_scraper_class):
        """Test API documentation retrieval with scraper error."""
        mock_scraper = Mock()
        mock_scraper_class.return_value = mock_scraper
        mock_scraper.validate_version.return_value = True
        mock_scraper.get_api_doc.return_value = {
            "status": "error",
            "error": "Network error",
        }
        # Mock the normalize_version method that appears in error messages
        mock_scraper.normalize_version.return_value = "6000.0"

        server = UnityDocsMCPServer()
        server.scraper = mock_scraper

        result = await server._get_unity_api_doc("GameObject", None, "6000.0")

        self.assertEqual(len(result), 1)
        # The server formats API errors differently, check for the class name in error
        self.assertIn("GameObject", result[0].text)
        self.assertIn("not found", result[0].text)

    @patch("unity_docs_mcp.server.UnityDocScraper")
    @patch("unity_docs_mcp.server.UnityDocParser")
    async def test_search_unity_docs_success(
        self, mock_parser_class, mock_scraper_class
    ):
        """Test successful documentation search."""
        mock_scraper = Mock()
        mock_parser = Mock()
        mock_scraper_class.return_value = mock_scraper
        mock_parser_class.return_value = mock_parser

        mock_scraper.validate_version.return_value = True
        # Mock search using search index instead of HTML parsing
        mock_scraper.search_docs.return_value = {
            "status": "success",
            "results": [
                {
                    "title": "GameObject",
                    "url": "https://docs.unity3d.com/GameObject.html",
                    "description": "Base class",
                    "type": "class",
                },
                {
                    "title": "Transform",
                    "url": "https://docs.unity3d.com/Transform.html",
                    "description": "Position and rotation",
                    "type": "class",
                },
            ],
            "count": 2,
        }
        # Parser is not used for search results when using search index
        # mock_parser.parse_search_results.return_value not needed

        server = UnityDocsMCPServer()
        server.scraper = mock_scraper
        server.parser = mock_parser

        result = await server._search_unity_docs("game", "6000.0")

        self.assertEqual(len(result), 1)
        content = result[0].text
        self.assertIn("Unity Documentation Search Results", content)
        self.assertIn("GameObject", content)
        self.assertIn("Transform", content)
        self.assertIn("2 found", content)

    @patch("unity_docs_mcp.server.UnityDocScraper")
    @patch("unity_docs_mcp.server.UnityDocParser")
    async def test_search_unity_docs_no_results(
        self, mock_parser_class, mock_scraper_class
    ):
        """Test documentation search with no results."""
        mock_scraper = Mock()
        mock_parser = Mock()
        mock_scraper_class.return_value = mock_scraper
        mock_parser_class.return_value = mock_parser

        mock_scraper.validate_version.return_value = True
        mock_scraper.normalize_version.return_value = "6000.0"
        mock_scraper.search_docs.return_value = {
            "status": "success",
            "results": [],
            "count": 0,
        }

        server = UnityDocsMCPServer()
        server.scraper = mock_scraper
        server.parser = mock_parser

        result = await server._search_unity_docs("nonexistent", "6000.0")

        self.assertEqual(len(result), 1)
        self.assertIn("No results found", result[0].text)

    @patch("unity_docs_mcp.server.UnityDocScraper")
    async def test_list_unity_versions(self, mock_scraper_class):
        """Test listing Unity versions."""
        mock_scraper = Mock()
        mock_scraper_class.return_value = mock_scraper
        mock_scraper.get_supported_versions.return_value = [
            "6000.0",
            "2023.3",
            "2022.1",
        ]

        server = UnityDocsMCPServer()
        server.scraper = mock_scraper

        result = await server._list_unity_versions()

        self.assertEqual(len(result), 1)
        content = result[0].text
        self.assertIn("Supported Unity Versions", content)
        self.assertIn("6000.0", content)
        self.assertIn("2023.3", content)
        self.assertIn("2022.1", content)

    @patch("unity_docs_mcp.server.UnityDocScraper")
    async def test_suggest_unity_classes(self, mock_scraper_class):
        """Test Unity class suggestions."""
        mock_scraper = Mock()
        mock_scraper_class.return_value = mock_scraper
        mock_scraper.suggest_class_names.return_value = [
            "GameObject",
            "GameObjectUtility",
        ]

        server = UnityDocsMCPServer()
        server.scraper = mock_scraper

        result = await server._suggest_unity_classes("game")

        self.assertEqual(len(result), 1)
        content = result[0].text
        self.assertIn("Class Suggestions", content)
        self.assertIn("GameObject", content)
        self.assertIn("GameObjectUtility", content)

    @patch("unity_docs_mcp.server.UnityDocScraper")
    @patch("unity_docs_mcp.server.UnityDocParser")
    async def test_get_unity_manual_doc_success(
        self, mock_parser_class, mock_scraper_class
    ):
        """Reading a concrete manual page."""
        mock_scraper = Mock()
        mock_scraper_class.return_value = mock_scraper
        resolved = Mock()
        resolved.name = "6000.5.7f1"
        mock_scraper.installed = [Mock()]
        mock_scraper.resolve_version.return_value = resolved
        mock_scraper.get_manual_doc.return_value = {
            "status": "success",
            "html": "<html>URP content</html>",
            "url": "C:/docs/Manual/urp/urp-introduction.html",
            "title": "Universal Render Pipeline introduction",
        }
        mock_parser = Mock()
        mock_parser_class.return_value = mock_parser
        mock_parser.parse_api_doc.return_value = {
            "title": "Universal Render Pipeline introduction",
            "content": "URP is a Scriptable Render Pipeline.",
            "url": "C:/docs/Manual/urp/urp-introduction.html",
        }

        server = UnityDocsMCPServer()
        server.scraper = mock_scraper
        server.parser = mock_parser

        result = await server._get_unity_manual_doc("urp/urp-introduction", "6000.5")

        self.assertEqual(len(result), 1)
        content = result[0].text
        self.assertIn("Universal Render Pipeline introduction", content)
        self.assertIn("URP is a Scriptable Render Pipeline.", content)
        self.assertIn("6000.5.7f1", content)
        self.assertIn("**Source:**", content)

    @patch("unity_docs_mcp.server.UnityDocScraper")
    async def test_get_unity_manual_doc_search_fallback(self, mock_scraper_class):
        """When the page isn't found, the server returns manual search results."""
        mock_scraper = Mock()
        mock_scraper_class.return_value = mock_scraper
        resolved = Mock()
        resolved.name = "6000.5.7f1"
        mock_scraper.installed = [Mock()]
        mock_scraper.resolve_version.return_value = resolved
        mock_scraper.get_manual_doc.return_value = {
            "status": "search",
            "query": "navmesh",
            "results": [
                {
                    "title": "Navigation and Pathfinding",
                    "name": "navigation-and-pathfinding",
                    "url": "C:/docs/Manual/navigation-and-pathfinding.html",
                    "description": "Use NavMesh for navigation.",
                    "type": "manual",
                }
            ],
            "count": 1,
        }

        server = UnityDocsMCPServer()
        server.scraper = mock_scraper

        result = await server._get_unity_manual_doc("navmesh", "6000.5")

        self.assertEqual(len(result), 1)
        content = result[0].text
        self.assertIn("Unity Manual Search Results", content)
        self.assertIn("Navigation and Pathfinding", content)
        self.assertIn("get_unity_manual_doc(page:", content)


def run_async_test(test_func):
    """Helper to run async test functions."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(test_func())
    finally:
        loop.close()


# Wrap async test methods to run in event loop
for attr_name in dir(TestUnityDocsMCPServer):
    attr = getattr(TestUnityDocsMCPServer, attr_name)
    if (
        callable(attr)
        and attr_name.startswith("test_")
        and asyncio.iscoroutinefunction(attr)
    ):
        # Create a wrapper that runs the async function
        def make_wrapper(async_func):
            def wrapper(self):
                return run_async_test(lambda: async_func(self))

            return wrapper

        # Replace the async method with the wrapper
        setattr(TestUnityDocsMCPServer, attr_name, make_wrapper(attr))


if __name__ == "__main__":
    unittest.main()
