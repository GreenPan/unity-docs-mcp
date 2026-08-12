# Unity Docs MCP Server - Detailed Guide

A Model Context Protocol (MCP) server that reads Unity documentation from **locally installed editors** (fully offline) and provides retrieval + search through MCP-compatible clients.

## How it works

Each Unity editor installed via Unity Hub ships with its offline documentation at:

```
{Hub Editor root}/{full version}/Editor/Data/Documentation/en/
  ├── ScriptReference/                  # 42,000+ API reference pages
  │   └── docdata/index.json            # pages/info metadata
  └── Manual/                           # ~3,500 handbook pages
      └── docdata/index.json            # pages/info metadata
```

The server discovers installed versions, builds a **SQLite FTS5 full-text index**
per version covering both the API reference and the Manual, and answers queries
entirely from local files. No network requests are made.

## Installation

### Prerequisites

- Python 3.10+
- A Unity editor installed via Unity Hub (with its Documentation folder)

### Install

```bash
pip install -e .
```

Or from the repo:

```bash
git clone https://github.com/Saqoosha/unity-docs-mcp
cd unity-docs-mcp
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -e .
```

## Setup: `build`

`unity-docs-mcp build` builds the offline search index:

```bash
unity-docs-mcp build --editor-root "C:\Program Files\Unity\Hub\Editor"
```

1. **Locate the editor directory** — pass `--editor-root`, or it prompts
   interactively (falls back to the platform default Hub path
   `C:\Program Files\Unity\Hub\Editor` on Windows).
2. **Build the search index** — a SQLite FTS5 index is built for every installed
   version (first run takes a minute or two; progress is printed to stderr).
   Indexes live in `~/.unity_docs_mcp/db/search_{version}.db`.
3. **Print a pointer** — it reminds you to point the server at a version via the
   `UNITY_DOCS_VERSION` env var. It does **not** write any IDE config.

Add `--force` to rebuild indexes that already exist.

## Manual server configuration

The MCP server is a stdio command. Every tool entry is the same shape; only the
config file and key differ:

```json
"command": "<venv python>",
"args": ["-m", "unity_docs_mcp.server"],
"env": { "UNITY_DOCS_VERSION": "6000.5.7f1" }
```

`UNITY_DOCS_VERSION` is the built version you want to serve (see
`ls ~/.unity_docs_mcp/db/` for what `build` produced).

### Supported tools and config locations

| Tool | Config file | Top-level key | Notes |
|---|---|---|---|
| Claude Desktop | `%APPDATA%\Claude\claude_desktop_config.json` | `mcpServers` | macOS: `~/Library/Application Support/Claude/...` |
| Claude Code | `{project}/.mcp.json` | `mcpServers` | |
| Cursor | `{project}/.cursor/mcp.json` | `mcpServers` | |
| VS Code (Copilot) | `{project}/.vscode/mcp.json` | `servers` | entry has `"type": "stdio"` |
| OpenCode | `{project}/opencode.json` | `mcp` | `"type": "local"`, array command, `environment` |
| Codex | `~/.codex/config.toml` | `[mcp_servers.unity-docs]` | `command` string + `args` array |

**Restart your AI tool after editing its config** so the MCP server is picked up.

## Switching to a different Unity version / install

```bash
unity-docs-mcp build --editor-root "D:\NewUnity\Hub\Editor" --force
```

then update `UNITY_DOCS_VERSION` in your tool configs. Indexes are also rebuilt
automatically when the source docs directory changes (the stored `source_dir`
in the db meta is checked against the current docs).

## Usage

The server exposes five tools:

### 1. get_unity_api_doc

```
- class_name: "GameObject" (required)
- method_name: "SetActive" (optional)
- version: "6000.5" (optional; defaults to the served version)
```

The server serves the single version from `UNITY_DOCS_VERSION`. Version params
are resolved against it via prefix matching:

| Input | Behavior |
|---|---|
| *(none)* | the served version (e.g. `6000.5.7f1`) |
| `6000.5.7f1` | exact match |
| `6000.5` / `6000` | prefix → `6000.5.7f1` |
| `6000.0` | not served → falls back to the served version, noted in the response |

The response shows `**Unity Version:** 6000.5.7f1 (6000.0 not installed; using 6000.5.7f1)`
when an unserved version falls back, and `(from 6000.5)` when a prefix resolves.
`**Source:**` is the local file path.

> **Note on index/query mismatch**: the search index and the docs directory it was
> built from must match. If the docs move (e.g. you switch editors), the server
> detects it and rebuilds the index automatically, printing a warning that suggests
> `unity-docs-mcp build --force` to rebuild explicitly.

### 2. search_unity_docs

```
- query: "transform" (required)
- version: "6000.5" (optional)
```

Searches the **Scripting API reference** (`ScriptReference/`) only. Because the
index covers page **bodies**, searching a word that only appears inside a page's
body text will find it. Results include a local path and a `**Type:**` label
(class / method / property / constructor).

### 3. get_unity_manual_doc

```
- page: "urp/urp-introduction" (required) — a Manual slug, title, or search query
- version: "6000.5" (optional)
```

Reads a **Unity Manual** page (`Manual/`) or searches it. Resolution order:

| Input | Behavior |
|---|---|
| `urp/urp-introduction` | exact slug → reads the page |
| `URP/URP-Introduction` | case-insensitive slug match |
| `Navigation and Pathfinding` | exact title match |
| `navigation-and-path` | slug prefix match |
| anything else | falls back to a full-text **Manual search**, returning the top matches |

A matched page returns its content with a local `**Source:**` path; a search
fallback returns `# Unity Manual Search Results` with one-click
`get_unity_manual_doc(page="<slug>")` hints.

### 4. list_unity_versions

Lists installed versions, newest first.

### 5. suggest_unity_classes

```
- partial_name: "game" (required)
```

Suggests class names (member_type = class) matching the partial input.

## Version model

- **Served version**: the server reads exactly one built version, chosen by the
  `UNITY_DOCS_VERSION` env var in your tool config (e.g. `6000.5.7f1`). It
  recovers the docs directory from that version's db `meta.source_dir`.
- **Prefix matching**: `6000` / `6000.5` / `6000.5.7` resolve to the served version.
- **Unserved fallback**: a requested version that isn't the served one falls back
  to it with a note in the response (e.g. `6000.0 not installed; using 6000.5.7f1`).
- **No network**: nothing is fetched; there is no online version list.
- **Index/docs consistency**: the per-version index records the docs directory it
  was built from (`source_dir`). If the docs move, the server rebuilds the index
  automatically and warns to run `build --force`.

## Configuration reference (manual)

`config.json` in the repo root is a manual reference. Configure any MCP client with:

```json
{
  "mcpServers": {
    "unity-docs": {
      "command": "C:\\path\\to\\venv\\Scripts\\python.exe",
      "args": ["-m", "unity_docs_mcp.server"],
      "env": {
        "UNITY_DOCS_VERSION": "6000.5.7f1"
      }
    }
  }
}
```

## Running the server directly

```bash
# Via the entry point (starts the stdio MCP server)
unity-docs-mcp
# 🚀 Unity Docs MCP Server v0.3.0
# 📚 Offline mode - reading local Unity installation docs
# 📦 Serving Unity version: 6000.5.7f1
# 🔌 Starting MCP server...
```

Or directly:

```bash
python -m unity_docs_mcp.server
```

`UNITY_DOCS_VERSION` can be set as an environment variable instead of hardcoding
the version in the config `env`.

## Testing

```bash
python -m unittest discover tests/
```

The suite covers: version parsing/resolution, FTS5 index build + search, the
db helpers (`read_db_source_dir` / `list_built_versions`), scraper local reads,
CLI `build`, and server end-to-end. Tests use a fake Unity install fixture
(`tests/helpers.py`) so they run without Unity installed.

## Troubleshooting

1. **"No local Unity documentation found"** — no db exists for the requested
   version. Run `unity-docs-mcp build --editor-root <path>` to build it, then set
   `UNITY_DOCS_VERSION` in the tool's config env.
2. **Version falls back unexpectedly** — the requested version isn't the served
   one, so the server served the configured version with a note like
   `6000.0 not installed; using 6000.5.7f1`. Change `UNITY_DOCS_VERSION` to serve
   a different version.
3. **Slow first search / `build`** — the FTS5 index build over ~45,000 pages takes
   a minute or two the first time; afterwards it's reused instantly.
4. **Empty search results** — check that `build` ran (an index exists); search
   matches page bodies, and FTS5 defaults to AND across words.
5. **Config not picked up** — restart the AI tool after editing its config, and
   check the tool's config file contains the `unity-docs` entry.
6. **Class not found but should exist** — it may live in a namespace (`AI.NavMeshAgent`, `UI.Button`). Search for the plain name to find the full name; the server resolves it automatically where possible.

## License

MIT
