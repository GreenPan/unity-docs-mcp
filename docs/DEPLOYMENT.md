# Unity Docs MCP Server - Deployment Guide

## For End Users

### Prerequisites

- Python 3.10+
- A Unity editor installed via Unity Hub (its offline Documentation folder is required)
- One of the supported AI tools: Claude Desktop, Claude Code, Cursor, VS Code (Copilot), OpenCode, or Codex

### Quick Installation

```bash
pip install -e .
```

### One-command setup

```bash
unity-docs-mcp start --editor-root "C:\Program Files\Unity\Hub\Editor"
```

This builds the offline search index and writes MCP config entries for all six
supported tools. If you omit `--editor-root` it prompts interactively (or uses
`UNITY_HUB_EDITOR_DIR` / the platform default Hub path).

**Restart your AI tool** after running `start`.

To configure only some tools:

```bash
unity-docs-mcp start --tools claude-desktop,claude-code
```

### Switching Unity installs

```bash
unity-docs-mcp changesource --editor-root "D:\NewUnity\Hub\Editor"
```

Rebuilds the index from the new directory and refreshes all tool configs.

## For Developers

### Local Development Setup

```bash
git clone https://github.com/Saqoosha/unity-docs-mcp
cd unity-docs-mcp
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
pip install -e .
python -m unittest discover tests/
```

### Manual config (if you prefer not to run `start`)

`config.json` in the repo root is a manual reference:

```json
{
  "mcpServers": {
    "unity-docs": {
      "command": "C:\\path\\to\\venv\\Scripts\\python.exe",
      "args": ["-m", "unity_docs_mcp.server"],
      "cwd": "C:\\path\\to\\unity-docs-mcp",
      "env": {
        "UNITY_HUB_EDITOR_DIR": "C:\\Program Files\\Unity\\Hub\\Editor"
      }
    }
  }
}
```

**Important:** Use the full absolute path to the virtual environment's python to avoid "module not found" errors.

## Common Issues

**"ModuleNotFoundError: No module named 'mcp'"**
- Use the full path to the venv's python, not a bare `python`.

**"No local Unity documentation found"**
- The server can't find an editor root. Run `unity-docs-mcp start --editor-root <path>`
  or set `UNITY_HUB_EDITOR_DIR` in the tool's config `env`.

**"Unsupported Unity version 'X'"** (or the version falls back unexpectedly)
- X isn't installed locally (e.g. `6000.0` vs installed `6000.5.7f1`). The server now
  falls back to the newest installed version with a note (`6000.0 not installed;
  using 6000.5.7f1`). Use `list_unity_versions` to see what's installed.

**Stack traces on Ctrl+C**
- Handled gracefully: `🛑 Shutting down Unity Docs MCP Server...`

## Publishing to PyPI (Maintainers)

```bash
# Update version in pyproject.toml and __init__.py
pip install build twine
python -m build
python -m twine upload dist/*
```

After publishing, users install with:

```bash
pip install unity-docs-mcp
```

Note: the offline mode requires a locally installed Unity editor — there is no
online fallback.
