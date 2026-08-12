# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 🚨 IMPORTANT: Documentation Update Rule 🚨

**When making ANY code changes, you MUST update ALL related documentation:**

1. **Code Change → Documentation Update Checklist:**
   - [ ] README.md - If it affects installation or basic usage
   - [ ] docs/DETAILED_GUIDE.md - If it affects detailed usage or configuration
   - [ ] docs/ARCHITECTURE.md - If it changes technical design
   - [ ] docs/CHANGELOG.md - ALWAYS add an entry for changes
   - [ ] CLAUDE.md - If it affects development workflow

2. **Never commit code changes without updating docs**

3. **Documentation lives in:**
   - Root: User-facing (README.md, CLAUDE.md, LICENSE)
   - docs/: Technical and detailed documentation

## Unity Docs MCP Server v0.3.0 - Development Guide

### Commands

**Testing & Development**:
```bash
# Run full test suite
python run_tests.py

# Run tests directly (no Inspector needed)
source venv/bin/activate && python -m unittest discover tests/

# Build the offline index + write MCP configs for AI tools
unity-docs-mcp start --editor-root "C:\Program Files\Unity\Hub\Editor"

# Switch to a different Unity install (rebuild index + refresh configs)
unity-docs-mcp changesource --editor-root "D:\NewUnity\Hub\Editor"
```

**Running the Server**:
```bash
# Via entry point (after installation) - starts the stdio MCP server
unity-docs-mcp
# Output (stderr):
# 🚀 Unity Docs MCP Server v0.3.0
# 📚 Offline mode - reading local Unity installation docs
# 📦 Installed Unity versions: 6000.5.7f1
# 🔌 Starting MCP server...

# Direct module execution
python -m unity_docs_mcp.server
```

### Architecture Overview

The project consists of seven main modules that process local Unity documentation:

1. **server.py** - MCP server implementation providing 5 tools:
   - `list_unity_versions` - Lists **installed** Unity versions
   - `suggest_unity_classes` - Provides class name suggestions
   - `get_unity_api_doc` - Reads API documentation for a resolved local version
   - `search_unity_docs` - Searches local API docs (SQLite FTS5) in a specified version
   - `get_unity_manual_doc` - Reads a Manual page, or searches the Manual

2. **scraper.py** - Local documentation reader (fully offline):
   - Resolves editor root: arg > `UNITY_HUB_EDITOR_DIR` env > platform default
   - Resolves versions against installed editors (prefix matching)
   - Reads local HTML files (no network, no rate limiting)
   - Uses search_index.py for search and namespace resolution

3. **parser.py** - Critical HTML processing pipeline:
   - **MUST remove `<a>` tags BEFORE Trafilatura** (prevents bracket issues)
   - Removes Unity UI elements (feedback forms, etc.)
   - Converts to clean Markdown

4. **search_index.py** - SQLite FTS5 full-text index:
   - Per-version persistent index at `~/.unity_docs_mcp/db/search_{version}.db`
   - `ensure_index(version)` validates meta, builds lazily if missing
   - `build_index(version, progress)` parses `docdata/index.json` for **both**
     ScriptReference and Manual, extracts page bodies in parallel
   - `pages.kind` distinguishes `api` vs `manual` rows; `search(kind=...)` filters
   - Search matches **page bodies** (stronger than Unity's title/description search)
   - Index auto-rebuilds when the docs source dir moves (`source_dir` in meta) or the schema is outdated

5. **version_resolver.py** - Version model for local installs:
   - `parse_unity_version` / `discover_versions` / `resolve_version` / `default_editor_root`
   - Full install dir names (`6000.5.7f1`) are the source of truth
   - Prefix matching (`6000.5` → `6000.5.7f1`); uninstalled versions error

6. **mcp_config.py** - Writes MCP configs for 6 AI tools:
   - Claude Desktop, Claude Code (`.mcp.json`), Cursor, VS Code (Copilot),
     OpenCode, Codex
   - Read-merge-write JSON (preserves other entries, `.bak` backup); Codex TOML edited as text

7. **cli.py** - Entry point: `start` (build index + write configs) / `changesource` (new dir → rebuild + refresh)

### Version-Specific Behavior

**Important**: The MCP server handles **locally installed** Unity versions:

#### Version Resolution
- **Fallback**: an uninstalled requested version (different major.minor) falls back to the newest installed, with a note like `6000.0 not installed; using 6000.5.7f1`
- **Prefix matching**: `6000` / `6000.5` / `6000.5.7` all resolve to installed `6000.5.7f1`
- **Newest default**: when no version specified, uses the newest installed
- **No network**: there is no online version list and no "latest from Unity"

#### Version Availability Information
- **404 with context**: when an API is not found, shows which installed versions have it
- **Local checking**: checks file existence per installed version (no HEAD requests)
- **Helpful suggestions**: "Available in versions: 6000.5.7f1" for upgrade decisions
- **No caching of version lists**: versions come from the local install each time

#### Index/Docs Consistency
- **source_dir recorded in meta**: each db remembers the docs dir it was built from
- **Auto-rebuild on mismatch**: when the docs move, `ensure_index` rebuilds and warns to run `changesource`
- **User control**: developers get docs for their exact installed Unity version; uninstalled requests degrade gracefully

### Critical Implementation Details

1. **HTML Link Removal is CRUCIAL** - Must remove `<a>` tags BEFORE Trafilatura
2. **Processing Pipeline Order**: HTML → Remove Links → Remove UI → Trafilatura → Clean
3. **Trafilatura's `include_links=False` is NOT enough** - it leaves `[text]` brackets
4. **Search Algorithm**: Implements Unity's exact scoring system for 100% accuracy
5. **Namespace Resolution**: Dynamic discovery using search index, no hardcoding
6. **Pre-commit Testing**: Basic functionality tests run automatically before commits

### Common Issues & Solutions

- **Brackets in code**: `[GameObject]` → Remove `<a>` tags at HTML level
- **UI elements**: "Leave feedback" → Remove with `_remove_unity_ui_elements()`
- **Bold text**: `**text**` → Remove `<strong>`, `<b>` tags and markdown formatting
- **Markdown links**: `[ComputeBuffer](ComputeBuffer.html)` → Strip with regex
- **Local-only search**: docs come from the local install; `UNITY_HUB_EDITOR_DIR` points the server at the Hub Editor root

### Development Workflow

**Before Committing:**
1. Run tests: `python -m unittest discover tests/`
2. Pre-commit hook automatically runs basic tests
3. Check for IndentationError and import issues

**Testing Search Accuracy:**
```python
# Test with problematic class names
test_cases = ["NavMeshAgent", "Button", "Text", "Canvas"]
for case in test_cases:
    result = scraper.get_api_doc(case, version="6000.5")  # your installed version
    # Should resolve AI.NavMeshAgent, UI.Button, etc. via the local index
```

### Testing MCP Tools

Use the MCP Inspector to test tools with these example inputs:

```json
// Get latest installed Unity documentation
{"class_name": "GameObject"}

// Get documentation for a specific installed version (prefix match ok)
{"class_name": "GameObject", "version": "6000.5"}

// Get specific method
{"class_name": "GameObject", "method_name": "SetActive", "version": "6000.5"}

// Search in latest installed version
{"query": "transform"}

// Search in a specific installed version
{"query": "rigidbody physics", "version": "6000.5"}

// Get class suggestions
{"partial_name": "game"}

// Get a Manual page by slug / title, or search the Manual
{"page": "urp/urp-introduction"}
{"page": "navigation and pathfinding"}

// Test fallback with installed-version availability info
{"class_name": "AsyncGPUReadback", "version": "6000.0"}
```

### Supported Unity Versions

The MCP server lists **locally installed** Unity versions (no network):

#### Local Version Detection
- **Discoveries**: scans the Unity Hub Editor root for version dirs with a docs tree
- **No Manual Maintenance**: version list updates automatically when you install new editors
- **Prefix resolution**: `6000` / `6000.5` / `6000.5.7` all resolve to installed `6000.5.7f1`
- **No fallback**: a different major.minor than installed is an error

#### Current Installed Versions
Determined at runtime from your machine, e.g.:
- **6000.5.7f1** (your installed Unity 6)
- **2022.3.45f1** (your installed LTS)

#### Version Support Features

- **Newest default**: no version specified → newest installed
- **Prefix matching**: accepts `6000.5`, `6000`, full `6000.5.7f1`
- **No network**: no online version list, no Unity redirects, no "latest from Unity"

### Enhanced Error Handling

The MCP server provides error handling with installed-version context:

1. **Availability Context**: when an API is not found, shows which installed versions have it
2. **Local Checking**: checks file existence per installed version (no HEAD requests)
3. **Upgrade Guidance**: lists installed versions for missing APIs
4. **Transparent Resolution**: shows `6000.5.7f1 (from 6000.5)` when a prefix resolves
5. **No Silent Failures**: clear messaging about version compatibility issues

#### Example Error Output
```
'AsyncGPUReadback' not found in Unity 6000.5.7f1 documentation.

**Available in versions:** 6000.5.7f1
**Not available in:** 2022.3.45f1
```

### Project Structure

```
src/unity_docs_mcp/
├── server.py           # MCP server implementation
├── scraper.py          # Local doc reader (offline)
├── parser.py           # HTML parsing and cleaning
├── search_index.py     # SQLite FTS5 search index
├── version_resolver.py # Version discovery & resolution
├── mcp_config.py       # Writes configs for 6 AI tools
└── cli.py              # start / changesource commands

tests/
├── helpers.py                 # Fake Unity install fixture
├── test_version_resolver.py   # Version parsing/resolution
├── test_search_index.py       # FTS5 index build/search
├── test_scraper.py            # Local doc reader
├── test_mcp_config.py         # Tool config writing
├── test_cli.py                # start / changesource
├── test_server.py             # MCP server tests
├── test_integration.py        # End-to-end offline tests
└── test_parser.py             # HTML parsing tests
```

### Testing

The project includes comprehensive unit tests covering all local/offline functionality:

```bash
# Run all tests
source venv/bin/activate && python -m unittest discover tests/

# Run specific test modules
python tests/test_version_resolver.py  # Version resolution (22 tests)
python tests/test_search_index.py      # FTS5 search index
python tests/test_scraper.py           # Local doc reader
python tests/test_mcp_config.py        # Tool config writing
python tests/test_cli.py               # CLI start/changesource

# Run with coverage
python run_tests.py
```

#### Test Coverage

- **Version Resolution**: parsing, discovery, prefix matching, newest default
- **FTS5 Index**: build, reuse, body-text search, index.js fallback
- **Offline Scraper**: local reads, namespace resolution, availability by file existence
- **Config Writing**: all 6 tools, merge preserves entries, .bak backups
- **CLI**: start builds + writes, changesource refreshes, no-install non-zero
- **Server Integration**: end-to-end offline workflow
- **Zero Network**: all tests run against a fake local install (no Unity required)

Total: **162 unit tests** ensuring robust offline functionality.

### Performance & Storage

The offline server persists a per-version SQLite FTS5 index:

#### Index Storage
- **Search Index DB**: `~/.unity_docs_mcp/db/search_{version}.db` per installed version
- **Lazy Build**: `ensure_index` validates meta, builds only when missing or stale
- **Auto-Rebuild**: when the docs `source_dir` changes (changesource), the index rebuilds
- **Full-Text**: indexes page **bodies** for stronger search than Unity's own

#### Index Benefits
- **Instant queries**: FTS5 MATCH + bm25 on local SQLite
- **Zero network**: everything is read from disk
- **Reuse**: built once per version, reused across restarts
- **No legacy cache**: `~/.unity_docs_mcp/cache/` is no longer used for the index

#### Index Locations
```
~/.unity_docs_mcp/db/
├── search_6000.5.7f1.db   # FTS5 index for Unity 6000.5.7f1
└── search_2022.3.45f1.db  # FTS5 index for Unity 2022.3.45f1
```

### Startup Information

The server displays helpful information on startup (via stderr, safe for MCP protocol):

```
🚀 Unity Docs MCP Server v0.3.0          # From __init__.py __version__
📚 Offline mode - reading local Unity installation docs
📦 Installed Unity versions: 6000.5.7f1  # Discovered locally
🔌 Starting MCP server...

# When stopping with Ctrl+C (graceful shutdown):
🛑 Shutting down Unity Docs MCP Server...
```

**Server Features:**
- **Graceful Shutdown**: Handles Ctrl+C (SIGINT) and SIGTERM signals cleanly
- **No Stack Traces**: Signal trapping prevents ugly error output on exit
- **Server Version**: Automatically reads from `src/unity_docs_mcp/__init__.py`
- **Unity Versions**: discovered from the local install (no network)
- **No Hardcoding**: version info updates automatically from the local Hub root

### Important Notes

- Always activate virtual environment before development
- MCP Inspector runs on ports 6274 (UI) and 6277 (proxy)  
- **CRITICAL: Update ALL related documentation when making code changes:**
  - README.md - Update if user-facing features change
  - docs/DETAILED_GUIDE.md - Update for installation/usage changes
  - docs/ARCHITECTURE.md - Update for design/technical changes
  - docs/CHANGELOG.md - Add entry for every significant change
  - CLAUDE.md - Update this file if development process changes
- All new version-related features are fully tested
- Startup messages appear in Claude Desktop logs for debugging
- Documentation structure:
  - Root: Simple user docs (README.md, CLAUDE.md, LICENSE)
  - docs/: Detailed technical documentation