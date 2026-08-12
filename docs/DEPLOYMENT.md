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

### Build the offline index

```bash
unity-docs-mcp build --editor-root "C:\Program Files\Unity\Hub\Editor"
```

This builds (or reuses) the SQLite FTS5 index for every installed Unity version.
If you omit `--editor-root` it prompts interactively (or uses the platform
default Hub path). It does **not** write any IDE config — you wire up the server
manually (below).

### Manual server config (one entry per tool)

Add this stdio entry to your AI tool's MCP config, with `UNITY_DOCS_VERSION`
set to the version you built (run `ls ~/.unity_docs_mcp/db/` to see them):

```json
{
  "mcpServers": {
    "unity-docs": {
      "command": "C:\\path\\to\\venv\\Scripts\\python.exe",
      "args": ["-m", "unity_docs_mcp.server"],
      "env": { "UNITY_DOCS_VERSION": "6000.5.7f1" }
    }
  }
}
```

**Important:** Use the full absolute path to the virtual environment's python to
avoid "module not found" errors. **Restart your AI tool** after editing the config.
Per-tool file locations (Claude Desktop, Claude Code, Cursor, VS Code, OpenCode,
Codex) are in the README.

### Switching to a different Unity version / install

```bash
unity-docs-mcp build --editor-root "D:\NewUnity\Hub\Editor" --force
```

then update `UNITY_DOCS_VERSION` in your tool configs.

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

## Common Issues

**"ModuleNotFoundError: No module named 'mcp'"**
- Use the full path to the venv's python, not a bare `python`.

**"No local Unity documentation found"**
- No db exists for the requested version. Run `unity-docs-mcp build --editor-root <path>`,
  then set `UNITY_DOCS_VERSION` in the tool's config `env`.

**A version falls back unexpectedly**
- The requested version isn't the served one (e.g. `6000.0` vs `UNITY_DOCS_VERSION=6000.5.7f1`).
  The server serves the configured version with a note (`6000.0 not installed; using 6000.5.7f1`).
  Change `UNITY_DOCS_VERSION` to serve a different version.

**Stack traces on Ctrl+C**
- Handled gracefully: `🛑 Shutting down Unity Docs MCP Server...`

## Publishing to PyPI (Maintainers)

Before publishing, bump the version in `pyproject.toml` and `src/unity_docs_mcp/__init__.py`
(both must match). Then:

```bash
# 1. Install build tooling
pip install build twine

# 2. Build the wheel + sdist
python -m build

# 3. Upload to PyPI (authenticates via your PyPI token / keyring)
python -m twine upload dist/*

# 4. Verify it's installable in a clean environment
pip install unity-docs-mcp
```

**Release checklist before `twine upload`:**
- [ ] `python -m unittest discover tests/` green
- [ ] `python -m build` succeeds (wheel + sdist)
- [ ] No `requests` / `docs.unity3d.com` residue (`grep -r requests src/`)
- [ ] Version bumped in both `pyproject.toml` and `__init__.py`
- [ ] CHANGELOG entry added

After publishing, users install with:

```bash
pip install unity-docs-mcp
unity-docs-mcp build --editor-root "C:\Program Files\Unity\Hub\Editor"
```

(`pip install` provides the `unity-docs-mcp` command; `build` still turns your
local editor docs into the offline index — that step is inherent to the offline
design and can't be done at install time.)

Note: the offline mode requires a locally installed Unity editor — there is no
online fallback.
