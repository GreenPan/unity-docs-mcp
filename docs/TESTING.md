# Testing Unity Docs MCP Server

This document describes how to test the Unity Docs MCP Server (offline mode).

## Prerequisites

Make sure you have installed the server correctly:

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -e .
```

Verify the CLI entry point is available:

```bash
which unity-docs-mcp
```

## Running the test suite

```bash
# Full suite
python -m unittest discover tests/

# Or run a single module
python -m unittest tests.test_search_index -v
python -m unittest tests.test_scraper -v
python -m unittest tests.test_version_resolver -v
python -m unittest tests.test_mcp_config -v
python -m unittest tests.test_cli -v
```

The suite builds a **fake Unity install on disk** (`tests/helpers.make_fake_unity_install`)
so all tests run without a real Unity installation and make **no network requests**.

## CLI setup test (`start` / `changesource`)

Point `start` at any directory containing a Unity-style docs tree:

```bash
python -m unittest tests.test_cli -v
```

Real-world smoke test against your actual install:

```bash
unity-docs-mcp start --editor-root "C:\Program Files\Unity\Hub\Editor"
```

Expected:
- Progress output building `~/.unity_docs_mcp/db/search_{version}.db`
- Config entries written for the supported tools
- A second run completes instantly (index reused)

Switching source:

```bash
unity-docs-mcp changesource --editor-root "D:\NewUnity\Hub\Editor"
```

## MCP Inspector testing

The MCP Inspector provides a web interface to exercise the MCP server:

```bash
npm install -g @modelcontextprotocol/inspector
mcp-inspector src/unity_docs_mcp/server.py
```

**What to test:**

1. **List Tools** — should show 5 tools: `get_unity_api_doc`, `search_unity_docs`,
   `get_unity_manual_doc`, `list_unity_versions`, `suggest_unity_classes`.

2. **Tool calls** (adjust versions to your installed ones):

   ```json
   { "name": "list_unity_versions", "arguments": {} }
   ```
   ```json
   {
     "name": "get_unity_api_doc",
     "arguments": { "class_name": "GameObject" }
   }
   ```
   ```json
   {
     "name": "get_unity_api_doc",
     "arguments": { "class_name": "GameObject", "method_name": "SetActive", "version": "6000.5" }
   }
   ```
   ```json
   {
     "name": "search_unity_docs",
     "arguments": { "query": "transform" }
   }
   ```
   ```json
   { "name": "suggest_unity_classes", "arguments": { "partial_name": "transform" } }
   ```
   ```json
   {
     "name": "get_unity_manual_doc",
     "arguments": { "page": "urp/urp-introduction" }
   }
   ```
   ```json
   {
     "name": "get_unity_manual_doc",
     "arguments": { "page": "navmesh" }
   }
   // -> Manual search results fallback
   ```
   ```json
   {
     "name": "get_unity_api_doc",
     "arguments": { "class_name": "GameObject", "version": "6000.0" }
   }
   // -> "**Unity Version:** 6000.5.7f1 (6000.0 not installed; using 6000.5.7f1)"
   ```

## Expected results

✅ **Full suite passes** (`python -m unittest discover tests/`)
✅ **`start` builds the index and writes configs**
✅ **`list_unity_versions` shows installed versions**
✅ **`get_unity_api_doc` returns markdown with a local `**Source:**` path**
✅ **`search_unity_docs` returns local paths; body-text terms are findable**
✅ **Uninstalled versions fall back to newest with a note**
✅ **Config files preserve existing entries and create `.bak` backups**
✅ **No network access is attempted**

Example outputs:

```markdown
# Supported Unity Versions

- 6000.5.7f1
- 2022.3.45f1
```

```markdown
# Unity Class Suggestions for 'game'

- GameObject
```

```markdown
# GameObject

**Unity Version:** 6000.5.7f1
**Source:** C:\Program Files\Unity\Hub\Editor\6000.5.7f1\Editor\Data\Documentation\en\ScriptReference\GameObject.html

Base class for all entities in Unity Scenes...
```

## Troubleshooting

1. **Import errors** — ensure `pip install -e .` completed and you're in the venv.
2. **"No local Unity documentation found"** — run `unity-docs-mcp start --editor-root <path>`
   or set `UNITY_HUB_EDITOR_DIR`. The server still starts (tools are listable); tool calls
   return the setup error.
3. **Stale index after moving installs** — run `changesource`. The index is also
   auto-rebuilt when the stored `source_dir` no longer matches.
4. **MCP Inspector won't connect** — check Node/npm: `node --version && npm --version`.
5. **Config not picked up** — restart the AI tool after `start`.

### Index locations

```bash
ls ~/.unity_docs_mcp/db/        # search_{version}.db per installed version
ls ~/.unity_docs_mcp/cache/     # legacy (no longer used for the index)
```

To force a rebuild, delete the matching db:

```bash
rm -f ~/.unity_docs_mcp/db/search_6000.5.7f1.db
# then `unity-docs-mcp start` rebuilds it
```

## Integration test checklist

- [ ] Full suite passes offline (no network)
- [ ] `start` builds the index and writes all 6 tool configs
- [ ] `changesource` switches the editor root and rebuilds
- [ ] MCP Inspector connects and shows 5 tools
- [ ] `get_unity_api_doc` works with default / prefix / exact versions
- [ ] Uninstalled version falls back to newest with a note
- [ ] `search_unity_docs` finds body-text terms
- [ ] `suggest_unity_classes` returns class names
- [ ] `get_unity_manual_doc` reads a Manual page and falls back to search
- [ ] Existing config entries are preserved on re-run
