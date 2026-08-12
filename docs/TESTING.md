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
python -m unittest tests.test_cache -v
python -m unittest tests.test_cli -v
```

The suite builds a **fake Unity install on disk** (`tests/helpers.make_fake_unity_install`)
so all tests run without a real Unity installation and make **no network requests**.

## CLI test (`build`)

```bash
python -m unittest tests.test_cli -v
```

Real-world smoke test against your actual install:

```bash
unity-docs-mcp build --editor-root "C:\Program Files\Unity\Hub\Editor"
```

Expected:
- Progress output building `~/.unity_docs_mcp/db/search_{version}.db`
- A second run completes instantly (index reused)
- **No IDE config files are touched**

Rebuild explicitly with `--force`. After building, the server serves the version
from the `UNITY_DOCS_VERSION` env var in your tool config (see README).

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
✅ **`build` builds the index and touches no configs**
✅ **`list_unity_versions` shows the served version**
✅ **`get_unity_api_doc` returns markdown with a local `**Source:**` path**
✅ **`search_unity_docs` returns local paths; body-text terms are findable**
✅ **Unserved versions fall back to the served version with a note**
✅ **`UNITY_DOCS_VERSION` server serves exactly one version, recovering docs from the db**
✅ **No network access is attempted**

Example outputs:

```markdown
# Supported Unity Versions

- 6000.5.7f1
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
2. **"No local Unity documentation found"** — no db for the requested version. Run
   `unity-docs-mcp build --editor-root <path>`, then set `UNITY_DOCS_VERSION` in the
   tool config env. The server still starts (tools are listable); tool calls return
   the setup error.
3. **Stale index after moving installs** — run `build --force`. The index is also
   auto-rebuilt when the stored `source_dir` no longer matches.
4. **MCP Inspector won't connect** — check Node/npm: `node --version && npm --version`.
5. **Config not picked up** — restart the AI tool after editing its config.

### Index locations

```bash
ls ~/.unity_docs_mcp/db/        # search_{version}.db per built version
ls ~/.unity_docs_mcp/cache/     # legacy (no longer used for the index)
```

To force a rebuild, delete the matching db:

```bash
rm -f ~/.unity_docs_mcp/db/search_6000.5.7f1.db
# then `unity-docs-mcp build --editor-root <path>` rebuilds it
```

## Integration test checklist

- [ ] Full suite passes offline (no network)
- [ ] `build` builds the index and touches no configs
- [ ] Server with `UNITY_DOCS_VERSION` serves that one version
- [ ] MCP Inspector connects and shows 5 tools
- [ ] `get_unity_api_doc` works with default / prefix / exact versions
- [ ] Unserved version falls back to the served one with a note
- [ ] `search_unity_docs` finds body-text terms
- [ ] `suggest_unity_classes` returns class names
- [ ] `get_unity_manual_doc` reads a Manual page and falls back to search
