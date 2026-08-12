# Unity Docs MCP Server - Architecture Documentation

## 📋 Project Overview

**Purpose**: An MCP (Model Context Protocol) server that reads Unity API documentation from **locally installed editors** (fully offline) and provides it in clean Markdown format.

**Key Features**:
- Read Unity API documentation (classes, methods) from local disk
- Full-text document search (SQLite FTS5 over page bodies)
- Exact matching against the served Unity version
- Clean text output (UI elements and formatting removed)
- `build` CLI that turns local docs into an offline index; manual IDE config

## 🏗️ Architecture

### Directory Structure
```
unity-docs-mcp/
├── src/unity_docs_mcp/
│   ├── __init__.py           # Version
│   ├── server.py             # MCP server (UnityDocsMCPServer)
│   ├── scraper.py            # Local doc reader (UnityDocScraper)
│   ├── parser.py             # HTML parsing & cleaning (UnityDocParser)
│   ├── search_index.py       # SQLite FTS5 search index (UnitySearchIndex)
│   ├── version_resolver.py   # Version parsing & resolution
│   └── cli.py                # `unity-docs-mcp build`
├── tests/
│   ├── test_*.py             # Unit tests
│   └── helpers.py            # Fake Unity install fixture
├── pyproject.toml            # Dependencies & project config
└── config.json               # Manual MCP config reference (Windows paths)
```

### Runtime Data
```
~/.unity_docs_mcp/db/search_{version}.db   # SQLite FTS5 index per built version
```

### Core Components

#### 1. **server.py** - MCP Server
```python
class UnityDocsMCPServer:
    # MCP tools:
    - list_unity_versions()      # The served version
    - suggest_unity_classes()    # Class name suggestions
    - get_unity_api_doc()       # Get API documentation
    - search_unity_docs()       # Search the API reference (kind='api')
    - get_unity_manual_doc()    # Read/search a Manual page
```
The server serves exactly one built version, chosen by the `UNITY_DOCS_VERSION`
env var. The scraper recovers the docs directory from that version's db
`meta.source_dir`. A requested version other than the served one falls back to
it with a note (`6000.0 not installed; using 6000.5.7f1`); the `**Source:**`
field is a local absolute path.

#### 2. **scraper.py** - Local Documentation Reader
```python
class UnityDocScraper:
    # Single-version: docs_dir recovered from the built db for UNITY_DOCS_VERSION
    - resolve_version(version)         # None -> served version; prefix match
    - get_api_doc(class, method, version)
    - search_docs(query, version)      # delegates to search_index(kind='api')
    - get_manual_doc(page_query, version)  # exact page, else Manual search
    - suggest_class_names(partial)     # delegates to search_index
    - check_api_availability_across_versions()  # local file existence
    # Page name patterns (same as Unity's site):
    #   Class:     {Class}.html
    #   Method:    {Class}.{method}.html        (dot notation)
    #   Property:  {Class}-{property}.html      (hyphen notation)
    #   Manual:    {slug}.html                  (may contain subdirs)
    # Automatic fallback: try dot, then hyphen.
```

#### 3. **parser.py** - HTML Parser
```python
class UnityDocParser:
    # Critical processing pipeline:
    1. _remove_link_tags()          # Remove <a> tags (CRUCIAL!)
    2. _remove_unity_ui_elements()  # Remove feedback/UI elements
    3. trafilatura.extract()        # Extract main content
    4. _clean_trafilatura_content() # Fix code formatting
    5. _remove_markdown_formatting() # Remove bold, links
```

#### 4. **search_index.py** - SQLite FTS5 Search Index
```python
class UnitySearchIndex:
    - ensure_index(version, force)   # Validate meta, build if needed
    - build_index(version, progress) # API + Manual pages, parallel body extraction
    - search(query, version, max_results, kind)  # FTS5 MATCH + bm25, class-boosted
    - suggest_classes(partial_name)  # prefix + member_type='class'
    - get_page_name(query, version)  # API namespace resolution
    - get_manual_page(page_query, version)  # Manual slug/title resolution
    - clear_cache(version)           # delete a version's db
    # Schema per version:
    #   meta  (version, page_count, built_at, source_dir)
    #   pages (id, name, title, member_type, path, kind)  # kind: 'api' | 'manual'
    #   ft    (FTS5: name, title, description, content)
```
`build_index` parses both `ScriptReference/docdata` and `Manual/docdata`
(`index.json`, fallback `index.js`), indexing both into the one FTS5 db.
`member_type` distinguishes class / method / property / constructor via the
hyphen/dot naming rules plus whether the dotted base is a known class
(e.g. `Object.GetInstanceID` → method, `AI.NavMeshAgent` → class). Indexing is
lazy (`ensure_index` on first query) and explicitly triggered by `build`.
The db is rebuilt automatically when the `source_dir` in meta no longer matches
or the schema is outdated (no `kind` column).

Module-level helpers used by the server to recover a built version's docs:
- `read_db_source_dir(db_dir, version)` → the `meta.source_dir` from a version's db
- `list_built_versions(db_dir)` → versions with a built db, newest first

#### 5. **version_resolver.py** - Version Model
```python
@dataclass InstalledVersion: name, editor_dir, docs_dir, version_key
parse_unity_version("6000.5.7f1") -> (6000, 5, 7, type_rank, build, revision)
discover_versions(editor_root)     # scans Hub Editor dir (used by `build`)
resolve_version(version, installed) # None->served, exact, prefix, else None
default_editor_root()              # platform default Hub path
```
`build` uses `discover_versions` to find what to index. The server serves a
single `InstalledVersion` (the one from `UNITY_DOCS_VERSION`).

#### 6. **cli.py** - Commands
```bash
unity-docs-mcp build --editor-root <hub>   # build (or reuse) index per installed version
                     [--force]             # rebuild existing indexes
```
`build` never touches IDE configs. The server is configured manually in each
tool's MCP config (`command` = venv python, `args = ["-m", "unity_docs_mcp.server"]`,
`env = {"UNITY_DOCS_VERSION": "<version>"}`) — see README / DETAILED_GUIDE for
per-tool file locations (Claude Desktop, Claude Code, Cursor, VS Code, OpenCode,
Codex).

## 🔧 Key Dependencies

```toml
dependencies = [
    "mcp>=1.0.0",              # MCP protocol
    "beautifulsoup4>=4.12.0",  # HTML parsing
    "trafilatura>=1.8.0",      # Content extraction
    "lxml>=4.9.0",             # XML/HTML processing
    "markdownify>=0.11.6",     # HTML to Markdown conversion
]
```
`sqlite3` (FTS5) is the Python standard library — no network libraries are used.

## 🐛 Problems & Solutions

### Problem 0: No Online Documentation
The old server scraped `docs.unity3d.com`. This project is now fully offline: docs come from the local `.../Editor/Data/Documentation/en/` tree shipped with each installed editor.

### Problem 1: Code Bracket Issues
**Symptom**:
```csharp
public class Example :[MonoBehaviour]{
    private[GameObject][] cubes = new[GameObject][10];
```
**Cause**: HTML `<a>` tags are converted to `[text]` format by Trafilatura
**Solution**: Remove link tags at HTML level before processing
```python
for link in soup.find_all('a'):
    link.replace_with(link.get_text())
```

### Problem 2: UI Elements in Content
Remove feedback/UI text like "Leave feedback", "Success!", "Submission failed".

### Problem 3: Bold Formatting
Remove `<strong>`/`<b>` tags and Markdown `**`.

### Problem 4: Markdown Links
Remove leftover `[text](url)` with regex.

### Problem 5: Property vs Method Page Names
- Methods use dot notation: `GameObject.SetActive.html`
- Properties use hyphen notation: `GameObject-transform.html`
- Automatic fallback tries dot then hyphen.

## 🚀 Launch & Test

### Build index
```bash
unity-docs-mcp build --editor-root "C:\Program Files\Unity\Hub\Editor"
```

### MCP Inspector
```bash
./start_inspector.sh
# Opens http://localhost:6274
```

### Test Examples
```json
// Get GameObject documentation (served version)
{"class_name": "GameObject"}

// Get specific method with prefix version
{"class_name": "GameObject", "method_name": "SetActive", "version": "6000.5"}

// Search documentation (full-text, includes body text)
{"query": "transform", "version": "6000.5"}

// Get class suggestions
{"partial_name": "game"}

// Unserved version -> falls back to the served version with a note
{"class_name": "AsyncGPUReadback", "version": "6000.0"}
```

### Run tests
```bash
python -m unittest discover tests/
```

## 💡 Critical Insights

1. **Fully offline** — data source is the local install, not the network. The server serves one built version chosen by `UNITY_DOCS_VERSION`; docs dir is recovered from the db's `meta.source_dir`.
2. **FTS5 full-text index** — searches match page **bodies**, not just titles/descriptions. Indexes live in `~/.unity_docs_mcp/db/`.
3. **Lazy build** — `ensure_index` validates the `meta` table and builds only when missing or stale (`source_dir` mismatch).
4. **Version model** — full install dirs (`6000.5.7f1`) are the source of truth; `build` indexes them, and the server serves exactly one.
5. **Manual config** — no auto-config; each tool gets one stdio entry with `env.UNITY_DOCS_VERSION`.
6. **Windows paths** — search-result `path` uses forward slashes (`as_posix()`); file reads use `normpath`.

## 📝 Future Improvements

1. Support Unity Package docs
2. Incremental index updates (delta builds)

## ⚠️ Important Notes

- **Always activate venv** before running
- **MCP Inspector ports**: 6274 (web UI), 6277 (proxy)
- **Python 3.10+** required

---

**Remember**: The key to clean output is removing problematic HTML elements BEFORE any markdown conversion! 🎯

## Quick Reference

### File Locations
- **Main server**: `src/unity_docs_mcp/server.py`
- **Local doc reader**: `src/unity_docs_mcp/scraper.py`
- **Parser/cleaner**: `src/unity_docs_mcp/parser.py`
- **Search index**: `src/unity_docs_mcp/search_index.py`
- **Version resolution**: `src/unity_docs_mcp/version_resolver.py`
- **CLI**: `src/unity_docs_mcp/cli.py`
- **Index databases**: `~/.unity_docs_mcp/db/`
