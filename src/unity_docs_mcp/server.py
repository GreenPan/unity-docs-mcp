"""Unity Docs MCP Server - Main server implementation (offline, local docs)."""

import sys
import asyncio
import os
from typing import Any
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

try:
    from .scraper import UnityDocScraper
    from .parser import UnityDocParser
except ImportError:
    # Handle direct execution
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from unity_docs_mcp.scraper import UnityDocScraper
    from unity_docs_mcp.parser import UnityDocParser


class UnityDocsMCPServer:
    """MCP Server for Unity documentation (local offline mode)."""

    def __init__(self, editor_root=None, scraper=None):
        self.server = Server("unity-docs-mcp")
        self.scraper = scraper or UnityDocScraper()
        self.parser = UnityDocParser()
        self._setup_handlers()

    def _resolve_or_error(self, version):
        """Resolve a version to an installed one.

        A requested version that isn't installed falls back to the newest
        installed version; the caller renders ``annotation`` to stay
        transparent. The only hard error is when no local docs exist at all.
        Returns (resolved, annotation, error).
        """
        if not self.scraper.installed:
            return None, None, (
                "Error: No local Unity documentation found. "
                "Run `unity-docs-mcp build --editor-root <path>` to build the "
                "docs index, then set UNITY_DOCS_VERSION in the MCP server "
                "config env to the version you want to serve."
            )
        resolved = self.scraper.resolve_version(version)
        version_str = str(version).strip() if version else ""
        if resolved is None:
            # Requested version isn't installed -> serve the newest installed.
            fallback = self.scraper.resolve_version(None)
            annotation = f"{version_str} not installed; using {fallback.name}" if version_str else None
            return fallback, annotation, None
        if version_str and version_str.lower() != resolved.name.lower():
            annotation = f"from {version_str}"
        else:
            annotation = None
        return resolved, annotation, None

    def _setup_handlers(self):
        """Setup MCP server handlers."""

        @self.server.list_tools()
        async def handle_list_tools() -> list[Tool]:
            """List available tools."""
            return [
                Tool(
                    name="get_unity_api_doc",
                    description="Get Unity API documentation for a specific class or method",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "class_name": {
                                "type": "string",
                                "description": "Unity class name (e.g., 'GameObject', 'Transform')",
                            },
                            "method_name": {
                                "type": "string",
                                "description": "Optional method name (e.g., 'Instantiate', 'SetActive')",
                            },
                            "version": {
                                "type": "string",
                                "description": "Unity version (optional - defaults to latest installed version if not specified)",
                            },
                        },
                        "required": ["class_name"],
                    },
                ),
                Tool(
                    name="search_unity_docs",
                    description="Search the Unity Scripting API reference",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search query (e.g., 'transform', 'rigidbody physics')",
                            },
                            "version": {
                                "type": "string",
                                "description": "Unity version (optional - defaults to latest installed version if not specified)",
                            },
                        },
                        "required": ["query"],
                    },
                ),
                Tool(
                    name="get_unity_manual_doc",
                    description="Read a Unity Manual page, or search the Manual when the page isn't found",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "page": {
                                "type": "string",
                                "description": "Manual page slug, title, or a search query (e.g., 'urp/urp-introduction', 'navigation and pathfinding')",
                            },
                            "version": {
                                "type": "string",
                                "description": "Unity version (optional - defaults to latest installed version if not specified)",
                            },
                        },
                        "required": ["page"],
                    },
                ),
                Tool(
                    name="list_unity_versions",
                    description="List installed Unity versions",
                    inputSchema={"type": "object", "properties": {}},
                ),
                Tool(
                    name="suggest_unity_classes",
                    description="Get suggestions for Unity class names",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "partial_name": {
                                "type": "string",
                                "description": "Partial class name to get suggestions for",
                            }
                        },
                        "required": ["partial_name"],
                    },
                ),
            ]

        @self.server.call_tool()
        async def handle_call_tool(
            name: str, arguments: dict[str, Any]
        ) -> list[TextContent]:
            """Handle tool calls."""

            if name == "get_unity_api_doc":
                return await self._get_unity_api_doc(
                    arguments.get("class_name"),
                    arguments.get("method_name"),
                    arguments.get("version"),
                )

            elif name == "search_unity_docs":
                return await self._search_unity_docs(
                    arguments.get("query"), arguments.get("version")
                )

            elif name == "get_unity_manual_doc":
                return await self._get_unity_manual_doc(
                    arguments.get("page"), arguments.get("version")
                )

            elif name == "list_unity_versions":
                return await self._list_unity_versions()

            elif name == "suggest_unity_classes":
                return await self._suggest_unity_classes(arguments.get("partial_name"))

            else:
                return [TextContent(type="text", text=f"Unknown tool: {name}")]

    async def _get_unity_api_doc(
        self, class_name: str, method_name: str = None, version: str = None
    ) -> list[TextContent]:
        """Get Unity API documentation for the specified version only."""
        if not class_name:
            return [TextContent(type="text", text="Error: class_name is required")]

        resolved, annotation, error = self._resolve_or_error(version)
        if error:
            return [TextContent(type="text", text=error)]

        version_name = resolved.name

        # Try to detect member type using the search index if available.
        member_type = None
        if method_name and hasattr(self.scraper, "search_index"):
            query = f"{class_name} {method_name}"
            search_results = self.scraper.search_docs(query, version_name)
            if search_results.get("status") == "success" and search_results.get("results"):
                for result in search_results["results"]:
                    if (
                        result.get("title") == f"{class_name}.{method_name}"
                        or result.get("title") == f"{class_name}-{method_name}"
                    ):
                        member_type = result.get("type")
                        break

        result = self.scraper.get_api_doc(
            class_name, method_name, version_name, member_type=member_type
        )

        if result.get("status") == "error":
            if method_name:
                base_error = f"'{class_name}.{method_name}' not found in Unity {version_name} documentation."
            else:
                base_error = f"'{class_name}' not found in Unity {version_name} documentation."

            try:
                version_info = self.scraper.check_api_availability_across_versions(
                    class_name, method_name
                )
                if version_info["available"]:
                    error_msg = f"{base_error}\n\n**Available in versions:** {', '.join(version_info['available'])}"
                    if version_info["unavailable"]:
                        error_msg += f"\n**Not available in:** {', '.join(version_info['unavailable'])}"
                else:
                    error_msg = f"{base_error}\n\n"
                    if "." not in class_name:
                        error_msg += "**Troubleshooting tips:**\n"
                        error_msg += f"1. This class might exist in a namespace. Try searching for '{class_name}' to find the full name.\n"
                        error_msg += "2. Common Unity namespaces: AI, UI, VFX, Rendering, Audio, etc.\n"
                        error_msg += "3. Example: 'NavMeshAgent' is actually 'AI.NavMeshAgent'\n\n"
                    error_msg += "**Note:** The API might exist but wasn't found in the installed versions."
            except Exception:
                error_msg = base_error

            return [TextContent(type="text", text=error_msg)]

        parsed_result = self.parser.parse_api_doc(result["html"], result["url"])
        if "error" in parsed_result:
            return [
                TextContent(
                    type="text",
                    text=f"Error parsing documentation: {parsed_result['error']}",
                )
            ]

        content = f"# {parsed_result['title']}\n\n"
        if annotation:
            content += f"**Unity Version:** {version_name} ({annotation})\n"
        else:
            content += f"**Unity Version:** {version_name}\n"
        content += f"**Source:** {result['url']}\n\n"
        content += parsed_result["content"]

        return [TextContent(type="text", text=content)]

    async def _search_unity_docs(
        self, query: str, version: str = None
    ) -> list[TextContent]:
        """Search Unity documentation."""
        if not query:
            return [TextContent(type="text", text="Error: query is required")]

        resolved, annotation, error = self._resolve_or_error(version)
        if error:
            return [TextContent(type="text", text=error)]

        version_name = resolved.name

        result = self.scraper.search_docs(query, version_name)

        if result.get("status") == "error":
            return [TextContent(type="text", text=f"Error: {result.get('error')}")]

        search_results = result.get("results", [])

        if not search_results:
            return [
                TextContent(type="text", text=f"No results found for query: '{query}'")
            ]

        content = "# Unity Documentation Search Results\n\n"
        content += f"**Query:** {query}\n"
        if annotation:
            content += f"**Version:** {version_name} ({annotation})\n"
        else:
            content += f"**Version:** {version_name}\n"
        content += f"**Results:** {result.get('count', len(search_results))} found\n\n"
        content += "💡 **Tip:** For detailed documentation, use `get_unity_api_doc` with the exact class name from results below.\n\n"

        for i, res in enumerate(search_results[:10], 1):
            content += f"## {i}. {res['title']}\n"
            if res.get("type"):
                content += f"**Type:** {res['type']}\n"

            title = res.get("title", "")
            result_type = res.get("type", "")
            if result_type in ["class", "property", "method", "function"]:
                if result_type in ["property", "method", "function"] and "." in title:
                    parts = title.split(".")
                    class_name = ".".join(parts[:-1])
                    member_name = parts[-1]
                    content += f'**📋 Use:** `get_unity_api_doc(class_name: "{class_name}", method_name: "{member_name}", version: "{version_name}")`\n'
                else:
                    content += f'**📋 Use:** `get_unity_api_doc(class_name: "{title}", version: "{version_name}")`\n'

            if res.get("url"):
                content += f"**URL:** {res['url']}\n"
            if res.get("description"):
                content += f"**Description:** {res['description']}\n"
            content += "\n"

        return [TextContent(type="text", text=content)]

    async def _list_unity_versions(self) -> list[TextContent]:
        """List installed Unity versions."""
        versions = self.scraper.get_supported_versions()
        if not versions:
            return [
                TextContent(
                    type="text",
                    text="No local Unity documentation found. Run `unity-docs-mcp build` to build the docs index, then set UNITY_DOCS_VERSION.",
                )
            ]
        content = "# Supported Unity Versions\n\n"
        for version in versions:
            content += f"- {version}\n"

        return [TextContent(type="text", text=content)]

    async def _suggest_unity_classes(self, partial_name: str) -> list[TextContent]:
        """Suggest Unity class names."""
        if not partial_name:
            return [TextContent(type="text", text="Error: partial_name is required")]

        suggestions = self.scraper.suggest_class_names(partial_name)

        if not suggestions:
            return [
                TextContent(
                    type="text", text=f"No suggestions found for '{partial_name}'"
                )
            ]

        content = f"# Unity Class Suggestions for '{partial_name}'\n\n"
        for suggestion in suggestions:
            content += f"- {suggestion}\n"

        return [TextContent(type="text", text=content)]

    async def _get_unity_manual_doc(self, page: str, version: str = None) -> list[TextContent]:
        """Read a Unity Manual page, or fall back to a Manual search."""
        if not page:
            return [TextContent(type="text", text="Error: page is required")]

        resolved, annotation, error = self._resolve_or_error(version)
        if error:
            return [TextContent(type="text", text=error)]

        version_name = resolved.name
        result = self.scraper.get_manual_doc(page, version_name)

        if result.get("status") == "error":
            return [TextContent(type="text", text=f"Error: {result.get('error')}")]

        if result.get("status") == "search":
            search_results = result.get("results", [])
            if not search_results:
                return [
                    TextContent(
                        type="text",
                        text=f"No Manual results found for: '{page}'",
                    )
                ]
            content = "# Unity Manual Search Results\n\n"
            content += f"**Query:** {page}\n"
            if annotation:
                content += f"**Version:** {version_name} ({annotation})\n"
            else:
                content += f"**Version:** {version_name}\n"
            content += f"**Results:** {result.get('count', len(search_results))} found\n\n"
            for i, res in enumerate(search_results[:10], 1):
                content += f"## {i}. {res['title']}\n"
                content += f'**📋 Use:** `get_unity_manual_doc(page: "{res["name"]}", version: "{version_name}")`\n'
                if res.get("url"):
                    content += f"**URL:** {res['url']}\n"
                if res.get("description"):
                    content += f"**Description:** {res['description']}\n"
                content += "\n"
            return [TextContent(type="text", text=content)]

        # status == success: read the page.
        parsed = self.parser.parse_api_doc(result["html"], result["url"])
        if "error" in parsed:
            return [
                TextContent(
                    type="text",
                    text=f"Error parsing documentation: {parsed['error']}",
                )
            ]
        content = f"# {result['title']}\n\n"
        if annotation:
            content += f"**Unity Version:** {version_name} ({annotation})\n"
        else:
            content += f"**Unity Version:** {version_name}\n"
        content += f"**Source:** {result['url']}\n\n"
        content += parsed["content"]
        return [TextContent(type="text", text=content)]

    async def run(self):
        """Run the MCP server."""
        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream, write_stream, self.server.create_initialization_options()
            )


async def main():
    """Main entry point."""
    import signal
    from . import __version__

    def signal_handler(signum, frame):
        print("🛑 Shutting down Unity Docs MCP Server...", file=sys.stderr)
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    print(f"🚀 Unity Docs MCP Server v{__version__}", file=sys.stderr)
    print("📚 Offline mode - reading local Unity installation docs", file=sys.stderr)
    scraper = UnityDocScraper()
    if scraper.installed:
        print(f"📦 Serving Unity version: {scraper.get_latest_version()}", file=sys.stderr)
    else:
        print(
            "⚠️ No local Unity documentation found. Run `unity-docs-mcp build` "
            "to build the index, then set UNITY_DOCS_VERSION in the config env.",
            file=sys.stderr,
        )
    print("🔌 Starting MCP server...", file=sys.stderr)
    print("", file=sys.stderr)

    try:
        server = UnityDocsMCPServer(scraper=scraper)
        await server.run()
    except KeyboardInterrupt:
        print("🛑 Shutting down Unity Docs MCP Server...", file=sys.stderr)
    except Exception as e:
        print(f"❌ Server error: {e}", file=sys.stderr)
        sys.exit(1)


def cli_main():
    """CLI entry point for setuptools."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("🛑 Shutting down Unity Docs MCP Server...", file=sys.stderr)
        sys.exit(0)


if __name__ == "__main__":
    cli_main()
