"""CLI entry point: `unity-docs-mcp start` / `unity-docs-mcp changesource`.

Both commands:
  1. Locate the Unity Hub Editor directory (flag > env > default > prompt).
  2. Build the FTS5 search index for every installed version.
  3. Write MCP server config entries for the supported AI tools.
"""

import argparse
import os
import sys
from typing import List, Optional

from . import __version__
from .mcp_config import write_all
from .version_resolver import default_editor_root, discover_versions

ALL_TOOLS = ["claude-desktop", "claude-code", "cursor", "vscode", "opencode", "codex"]


def _resolve_editor_root(flag_value: Optional[str], allow_prompt: bool = True) -> Optional[str]:
    """Return a valid Unity Hub Editor root, or None if none can be found."""
    candidate = flag_value or os.environ.get("UNITY_HUB_EDITOR_DIR") or default_editor_root()
    if candidate:
        if os.path.isdir(candidate) and discover_versions(candidate):
            return os.path.abspath(candidate)

    if not allow_prompt or not sys.stdin.isatty():
        return None

    print("没有找到 Unity Hub 的 Editor 目录。", file=sys.stderr)
    print("请输入 Unity Hub 的 Editor 目录路径（例如 C:\\Program Files\\Unity\\Hub\\Editor）：",
          file=sys.stderr, end=" ")
    try:
        answer = input().strip().strip('"')
    except (EOFError, KeyboardInterrupt):
        return None
    if answer and os.path.isdir(answer) and discover_versions(answer):
        return os.path.abspath(answer)
    return None


def _build_indexes(editor_root: str, force: bool) -> bool:
    """Build the search index for every installed version. Returns True if all built."""
    from .search_index import UnitySearchIndex

    installed = discover_versions(editor_root)
    docs_dirs = {v.name: v.docs_dir for v in installed}
    index = UnitySearchIndex(docs_dirs=docs_dirs)
    all_ok = True
    try:
        for v in installed:
            ok = index.ensure_index(v.name, force=force)
            print(
                f"{'重建' if force else '构建'}搜索索引: {v.name} - "
                f"{'完成' if ok else '失败'}",
                file=sys.stderr,
            )
            all_ok = all_ok and ok
    finally:
        index.close()
    return all_ok


def _write_configs(editor_root: str, project_dir: str, tools: List[str]) -> None:
    print(f"更新 MCP 配置（Editor 目录: {editor_root}）...", file=sys.stderr)
    results = write_all(editor_root, project_dir=project_dir, tools=tools)
    for tool, status in results.items():
        label = {"written": "已写入", "skipped": "已是最新/跳过", "error": "失败"}.get(
            status, status
        )
        print(f"  - {tool}: {label}", file=sys.stderr)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="unity-docs-mcp",
        description="Unity Docs MCP Server - build local docs index and configure AI tools",
    )
    parser.add_argument("--version", action="version", version=f"unity-docs-mcp {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    start = sub.add_parser("start", help="建库并写入 MCP 配置")
    start.add_argument("--editor-root", help="Unity Hub 的 Editor 目录路径")
    start.add_argument("--project-dir", help="项目目录（用于写项目级 MCP 配置，默认当前目录）")
    start.add_argument("--tools", help="要配置的工具，逗号分隔", default=",".join(ALL_TOOLS))

    cs = sub.add_parser("changesource", help="更换 Editor 目录后重新建库并更新配置")
    cs.add_argument("--editor-root", help="新的 Unity Hub 的 Editor 目录路径")
    cs.add_argument("--project-dir", help="项目目录（用于写项目级 MCP 配置，默认当前目录）")
    cs.add_argument("--tools", help="要配置的工具，逗号分隔", default=",".join(ALL_TOOLS))

    return parser


def _run(editor_root: str, project_dir: str, tools: List[str], force: bool) -> int:
    if not _build_indexes(editor_root, force):
        return 1
    _write_configs(editor_root, project_dir, tools)
    print(
        "\n完成。请重启对应的 AI 工具（Claude Desktop / Codex 等）使 MCP 生效。",
        file=sys.stderr,
    )
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    tools = [t.strip() for t in (args.tools or "").split(",") if t.strip()]
    project_dir = args.project_dir or os.getcwd()
    force = args.command == "changesource"

    editor_root = _resolve_editor_root(args.editor_root)
    if not editor_root:
        print(
            "错误: 未找到有效的 Unity Hub Editor 目录。"
            "请用 --editor-root 指定，例如：\n"
            '  unity-docs-mcp start --editor-root "C:\\Program Files\\Unity\\Hub\\Editor"',
            file=sys.stderr,
        )
        return 2

    return _run(editor_root, project_dir, tools, force)


if __name__ == "__main__":
    sys.exit(main())
