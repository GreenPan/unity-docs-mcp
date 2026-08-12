"""Write MCP server config entries for supported AI tools.

Every tool points at the same stdio MCP server:

    command = <venv python>, args = ["-m", "unity_docs_mcp.server"],
    env = {"UNITY_HUB_EDITOR_DIR": <editor root>}

JSON-based configs are read-merge-written (other entries preserved, a .bak
backup is written before any change). The Codex config.toml is edited as
text so the user's existing tables and comments survive.
"""

import json
import os
import re
import shutil
import sys
from typing import Dict, List, Optional

# --------------------------------------------------------------------------- layout

# Tool name -> (is_json, top_level_key, entry_kwargs)
_TOOL_LAYOUT = {
    "claude-desktop": {
        "json": True,
        "top_key": "mcpServers",
        "entry": {},
    },
    "claude-code": {
        "json": True,
        "top_key": "mcpServers",
        "entry": {},
    },
    "cursor": {
        "json": True,
        "top_key": "mcpServers",
        "entry": {},
    },
    "vscode": {
        "json": True,
        "top_key": "servers",
        "entry": {"type": "stdio"},
    },
    "opencode": {
        "json": True,
        "top_key": "mcp",
        "entry": {"type": "local", "enabled": True},
    },
    "codex": {
        "json": False,
        "top_key": None,
        "entry": {"type": "stdio"},
    },
}

# Files only written inside an explicit project dir.
_PROJECT_LEVEL = {"claude-code", "cursor", "vscode", "opencode"}

# Non-project tools that may not be installed (and then get skipped).
_DESKTOP_TOOLS = {"claude-desktop", "codex"}


def _entry(editor_root: str, python_exe: str, project_dir: str, layout: dict) -> dict:
    """Build the tool-specific config entry (already fully materialized)."""
    if not layout["json"]:  # codex -> TOML handled separately
        return {}
    if layout["entry"].get("type") == "local":
        # OpenCode expects an array command and an `environment` env map.
        return {
            "type": "local",
            "command": [python_exe, "-m", "unity_docs_mcp.server"],
            "environment": {"UNITY_HUB_EDITOR_DIR": editor_root},
            "enabled": True,
        }
    entry = dict(layout["entry"])
    entry["command"] = python_exe
    entry["args"] = ["-m", "unity_docs_mcp.server"]
    entry["env"] = {"UNITY_HUB_EDITOR_DIR": editor_root}
    if layout["entry"].get("type") == "stdio" and layout["top_key"] == "servers":
        # VS Code (Copilot) also needs a `cwd`.
        entry["cwd"] = project_dir
    return entry


def _tool_path(tool: str, project_dir: str) -> Optional[str]:
    """Return the config file path for a tool, or None if it cannot be targeted."""
    if tool in _PROJECT_LEVEL:
        if not project_dir:
            return None
        rel = {
            "claude-code": ".mcp.json",
            "cursor": os.path.join(".cursor", "mcp.json"),
            "vscode": os.path.join(".vscode", "mcp.json"),
            "opencode": "opencode.json",
        }[tool]
        return os.path.join(project_dir, rel)
    if tool == "claude-desktop":
        if sys.platform == "darwin":
            base = os.path.expanduser("~/Library/Application Support/Claude")
        else:
            base = os.environ.get("APPDATA")
            if not base:
                return None
            base = os.path.join(base, "Claude")
        return os.path.join(base, "claude_desktop_config.json")
    if tool == "codex":
        return os.path.join(os.path.expanduser("~"), ".codex", "config.toml")
    return None


# --------------------------------------------------------------------------- JSON


def _write_json(tool: str, path: str, editor_root: str, python_exe: str, project_dir: str, entry_kwargs: dict) -> str:
    """Write/merge one JSON-based tool config. Returns 'written' or 'skipped'."""
    top_key = _TOOL_LAYOUT[tool]["top_key"]
    data = {}
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                data = loaded
        except (json.JSONDecodeError, OSError):
            return "skipped"  # existing but unreadable -> do not clobber

    section = data.get(top_key)
    if not isinstance(section, dict):
        section = {}
    entry = dict(entry_kwargs)
    if section.get("unity-docs") == entry:
        return "skipped"  # already up to date

    if os.path.exists(path):
        shutil.copy2(path, path + ".bak")

    section["unity-docs"] = entry
    data[top_key] = section
    parent = os.path.dirname(path)
    os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    return "written"


# --------------------------------------------------------------------------- codex toml


def _write_codex_toml(path: str, editor_root: str, python_exe: str, project_dir: str) -> str:
    """Write/merge the [mcp_servers.unity-docs] block in config.toml (text edit)."""
    block = (
        "\n[mcp_servers.unity-docs]\n"
        "type = \"stdio\"\n"
        'command = "{}"\n'
        "args = [\"-m\", \"unity_docs_mcp.server\"]\n"
        'cwd = "{}"\n'
        "env = {{ UNITY_HUB_EDITOR_DIR = \"{}\" }}\n"
    ).format(python_exe.replace("\\", "\\\\"), project_dir.replace("\\", "\\\\"), editor_root.replace("\\", "\\\\"))

    content = ""
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                content = f.read()
        except OSError:
            return "skipped"

    # Replace an existing [mcp_servers.unity-docs] table block, if present.
    pattern = re.compile(
        r"^\[mcp_servers\.unity-docs\][^\n]*(?:\n(?!\[).*)*",
        re.MULTILINE,
    )
    if pattern.search(content):
        new_content = pattern.sub(lambda _m: block.strip(), content, count=1)
        if new_content == content:
            return "skipped"
        if os.path.exists(path):
            shutil.copy2(path, path + ".bak")
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)
        return "written"

    # Append a new block.
    if os.path.exists(path):
        shutil.copy2(path, path + ".bak")
    with open(path, "a", encoding="utf-8") as f:
        f.write("\n" + block)
    return "written"


# --------------------------------------------------------------------------- public


def write_all(
    editor_root: str,
    python_exe: Optional[str] = None,
    project_dir: Optional[str] = None,
    tools: Optional[List[str]] = None,
) -> Dict[str, str]:
    """Write config entries for each tool. Returns {tool: status}.

    status is one of ``written``, ``skipped`` (already current), or ``error``.
    Tools whose config file cannot be targeted (no project dir / not installed)
    are reported as ``skipped``.
    """
    python_exe = python_exe or sys.executable
    project_dir = project_dir or os.getcwd()
    tools = tools or list(_TOOL_LAYOUT.keys())
    results: Dict[str, str] = {}

    for tool in tools:
        if tool not in _TOOL_LAYOUT:
            results[tool] = "error"
            continue
        path = _tool_path(tool, project_dir)
        if path is None:
            results[tool] = "skipped"
            continue
        if tool in _DESKTOP_TOOLS and not os.path.exists(os.path.dirname(path)):
            results[tool] = "skipped"  # app not installed
            continue
        layout = _TOOL_LAYOUT[tool]
        try:
            if not layout["json"]:
                status = _write_codex_toml(path, editor_root, python_exe, project_dir)
            else:
                entry = _entry(editor_root, python_exe, project_dir, layout)
                status = _write_json(tool, path, editor_root, python_exe, project_dir, entry)
            results[tool] = status
        except Exception:
            results[tool] = "error"
    return results
