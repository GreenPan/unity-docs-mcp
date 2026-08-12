"""CLI entry point: `unity-docs-mcp build`.

Builds the SQLite FTS5 search index for every installed Unity version from the
Hub Editor directory, writing ``~/.unity_docs_mcp/db/search_{version}.db``. It
does not write any IDE MCP config — see the README for manual per-tool setup
(the server is pointed at a built version via the ``UNITY_DOCS_VERSION`` env var).
"""

import argparse
import os
import sys
from typing import List, Optional

from . import __version__
from .version_resolver import default_editor_root, discover_versions


def _resolve_editor_root(flag_value: Optional[str], allow_prompt: bool = True) -> Optional[str]:
    """Return a valid Unity Hub Editor root, or None if none can be found."""
    candidate = flag_value or default_editor_root()
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


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="unity-docs-mcp",
        description="Unity Docs MCP Server - build the local offline docs index",
    )
    parser.add_argument("--version", action="version", version=f"unity-docs-mcp {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="从本地 Unity 文档构建搜索数据库")
    build.add_argument("--editor-root", help="Unity Hub 的 Editor 目录路径")
    build.add_argument("--force", action="store_true", help="强制重建已有索引")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    force = args.force
    editor_root = _resolve_editor_root(args.editor_root)
    if not editor_root:
        print(
            "错误: 未找到有效的 Unity Hub Editor 目录。"
            "请用 --editor-root 指定，例如：\n"
            '  unity-docs-mcp build --editor-root "C:\\Program Files\\Unity\\Hub\\Editor"',
            file=sys.stderr,
        )
        return 2

    if not _build_indexes(editor_root, force):
        return 1

    installed = discover_versions(editor_root)
    versions = ", ".join(v.name for v in installed)
    print(
        f"\n已为以下版本构建索引: {versions}",
        file=sys.stderr,
    )
    print(
        "服务器通过 env `UNITY_DOCS_VERSION=<版本>` 指定服务哪个版本的文档。\n"
        "各 IDE 的手动 MCP 配置方式见 README。",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
