"""Integration tests for the offline Unity Docs MCP workflow."""

import asyncio
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from unity_docs_mcp.server import UnityDocsMCPServer
from unity_docs_mcp.search_index import UnitySearchIndex
from unity_docs_mcp.scraper import UnityDocScraper
from unity_docs_mcp.version_resolver import discover_versions
from tests.helpers import make_fake_unity_install


class TestIntegration(unittest.TestCase):
    """End-to-end offline flow: local install -> server tools."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root, _ = make_fake_unity_install(
            self.tmp, ["2022.3.45f1", "6000.5.7f1"]
        )
        versions = discover_versions(self.root)
        idx = UnitySearchIndex(
            docs_dirs={v.name: v.docs_dir for v in versions},
            db_dir=os.path.join(self.tmp, "db"),
        )
        self.scraper = UnityDocScraper(editor_root=self.root, search_index=idx)
        self.server = UnityDocsMCPServer()
        self.server.scraper = self.scraper

    def tearDown(self):
        self.scraper.search_index.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    async def test_get_api_doc_workflow(self):
        result = await self.server._get_unity_api_doc("GameObject", None, "6000.5.7f1")
        self.assertEqual(len(result), 1)
        content = result[0].text
        self.assertIn("GameObject", content)
        # Local absolute path is shown as the source.
        self.assertIn("**Source:**", content)
        self.assertIn("ScriptReference", content)
        self.assertIn("6000.5.7f1", content)

    async def test_get_api_doc_default_version(self):
        result = await self.server._get_unity_api_doc("Transform")
        content = result[0].text
        self.assertIn("6000.5.7f1", content)
        self.assertIn("**Unity Version:**", content)

    async def test_get_api_doc_prefix_resolution(self):
        result = await self.server._get_unity_api_doc("GameObject", version="6000.5")
        content = result[0].text
        self.assertIn("6000.5.7f1", content)
        self.assertIn("(from 6000.5)", content)

    async def test_get_api_doc_missing_version(self):
        result = await self.server._get_unity_api_doc("GameObject", version="6000.0")
        content = result[0].text
        self.assertIn("6000.0 not installed; using 6000.5.7f1", content)
        self.assertIn("GameObject", content)

    async def test_get_api_doc_missing_class(self):
        result = await self.server._get_unity_api_doc("NopeNotReal")
        content = result[0].text
        self.assertIn("not found in Unity 6000.5.7f1", content)

    async def test_search_workflow(self):
        result = await self.server._search_unity_docs("transform", "6000.5.7f1")
        content = result[0].text
        self.assertIn("Unity Documentation Search Results", content)
        self.assertIn("Transform", content)
        self.assertIn("found", content)

    async def test_search_no_results(self):
        result = await self.server._search_unity_docs("zzznothing", "6000.5.7f1")
        self.assertIn("No results found", result[0].text)

    async def test_list_versions(self):
        result = await self.server._list_unity_versions()
        content = result[0].text
        self.assertIn("Supported Unity Versions", content)
        self.assertIn("6000.5.7f1", content)
        self.assertIn("2022.3.45f1", content)

    async def test_suggest_classes(self):
        result = await self.server._suggest_unity_classes("game")
        self.assertIn("GameObject", result[0].text)

    async def test_no_install_graceful(self):
        server = UnityDocsMCPServer()
        server.scraper = UnityDocScraper(
            editor_root="",
            search_index=UnitySearchIndex(
                docs_dirs={}, db_dir=os.path.join(self.tmp, "dbnone")
            ),
        )
        result = await server._get_unity_api_doc("GameObject")
        self.assertIn("No local Unity documentation found", result[0].text)
        result = await server._list_unity_versions()
        self.assertIn("No local Unity documentation found", result[0].text)
        server.scraper.search_index.close()

    async def test_full_text_body_search_through_server(self):
        # "pathfinding" only appears in AI.NavMeshAgent's body.
        result = await self.server._search_unity_docs("pathfinding", "6000.5.7f1")
        self.assertIn("AI.NavMeshAgent", result[0].text)

    async def test_get_unity_manual_doc_exact(self):
        result = await self.server._get_unity_manual_doc("urp/urp-introduction", "6000.5.7f1")
        self.assertEqual(len(result), 1)
        content = result[0].text
        self.assertIn("Universal Render Pipeline introduction", content)
        self.assertIn("**Source:**", content)
        self.assertIn("6000.5.7f1", content)

    async def test_get_unity_manual_doc_search_fallback(self):
        result = await self.server._get_unity_manual_doc("navmesh", "6000.5.7f1")
        content = result[0].text
        self.assertIn("Unity Manual Search Results", content)
        self.assertIn("Navigation and Pathfinding", content)

    async def test_get_unity_manual_doc_prefix_version(self):
        result = await self.server._get_unity_manual_doc("urp/urp-introduction", "6000.5")
        content = result[0].text
        self.assertIn("(from 6000.5)", content)


def run_async_test(test_func):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(test_func())
    finally:
        loop.close()


for attr_name in dir(TestIntegration):
    attr = getattr(TestIntegration, attr_name)
    if (
        callable(attr)
        and attr_name.startswith("test_")
        and asyncio.iscoroutinefunction(attr)
    ):
        def make_wrapper(async_func):
            def wrapper(self):
                return run_async_test(lambda: async_func(self))

            return wrapper

        setattr(TestIntegration, attr_name, make_wrapper(attr))


if __name__ == "__main__":
    unittest.main()
