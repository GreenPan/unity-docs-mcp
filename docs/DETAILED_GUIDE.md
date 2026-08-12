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

## Setup: `start`

`unity-docs-mcp start` performs the two-step setup:

1. **Locate the editor directory** — it prompts interactively, or you pass `--editor-root`. Resolution order: `--editor-root` flag → `UNITY_HUB_EDITOR_DIR` env → platform default Hub path (`C:\Program Files\Unity\Hub\Editor` on Windows).
2. **Build the search index** — a SQLite FTS5 index is built for every installed version (first run takes a minute or two; progress is printed to stderr). Indexes live in `~/.unity_docs_mcp/db/search_{version}.db`.
3. **Write MCP configs** — the server entry is written into the supported AI tools' config files.

```bash
unity-docs-mcp start --editor-root "C:\Program Files\Unity\Hub\Editor"
```

Use `--tools` to limit which tools are configured (comma-separated):

```bash
unity-docs-mcp start --tools claude-desktop,claude-code
```

Valid tool names: `claude-desktop`, `claude-code`, `cursor`, `vscode`, `opencode`, `codex`.

### Supported tools and config locations

| Tool | Config file | Top-level key | Notes |
|---|---|---|---|
| Claude Desktop | `%APPDATA%\Claude\claude_desktop_config.json` | `mcpServers` | macOS: `~/Library/Application Support/Claude/...` |
| Claude Code | `{project}/.mcp.json` | `mcpServers` | |
| Cursor | `{project}/.cursor/mcp.json` | `mcpServers` | |
| VS Code (Copilot) | `{project}/.vscode/mcp.json` | `servers` | entry has `"type": "stdio"` |
| OpenCode | `{project}/opencode.json` | `mcp` | `"type": "local"`, array command, `environment` |
| Codex | `~/.codex/config.toml` | `[mcp_servers.unity-docs]` | `command` string + `args` array |

Every entry runs the same server:

```json
"command": "<venv python>",
"args": ["-m", "unity_docs_mcp.server"],
"env": { "UNITY_HUB_EDITOR_DIR": "<editor root>" }
```

Existing config contents are preserved (read-merge-write with a `.bak` backup). Tools that aren't installed are skipped. **Restart your AI tool after running `start`** so the MCP server is picked up.

## Switching editor installs: `changesource`

When you install Unity elsewhere (new drive, different version), rerun:

```bash
unity-docs-mcp changesource --editor-root "D:\NewUnity\Hub\Editor"
```

`changesource` rebuilds the index from the new directory and refreshes the `UNITY_HUB_EDITOR_DIR` in every tool config. Indexes are automatically rebuilt when the source docs directory changes (the stored `source_dir` is checked against the current install).

## Usage

The server exposes four tools:

### 1. get_unity_api_doc

```
- class_name: "GameObject" (required)
- method_name: "SetActive" (optional)
- version: "6000.5" (optional; defaults to newest installed)
```

Versions are resolved against **installed** editors via prefix matching:

| Input | Behavior |
|---|---|
| *(none)* | newest installed (e.g. `6000.5.7f1`) |
| `6000.5.7f1` | exact match |
| `6000.5` / `6000` | prefix → `6000.5.7f1` |
| `6000.0` | not installed → falls back to newest installed, noted in the response |

The response shows `**Unity Version:** 6000.5.7f1 (6000.0 not installed; using 6000.5.7f1)`
when an uninstalled version falls back, and `(from 6000.5)` when a prefix resolves.
`**Source:**` is the local file path.

> **Note on index/query mismatch**: the search index and the docs directory it was
> built from must match. If the docs move (e.g. you switch editors), the server
> detects it and rebuilds the index automatically, printing a warning that suggests
> `unity-docs-mcp changesource` to rebuild explicitly.

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

- **Source of truth**: full install directory names, e.g. `6000.5.7f1`, `2022.3.45f1`.
- **Prefix matching**: `6000` / `6000.5` / `6000.5.7` all resolve to `6000.5.7f1`; among several installs sharing a prefix, the newest wins.
- **Uninstalled fallback**: a requested major.minor that isn't installed falls back to the newest installed version, with a note in the response (e.g. `6000.0 not installed; using 6000.5.7f1`).
- **No network**: nothing is fetched; there is no online version list and no automatic "latest from Unity".
- **Index/docs consistency**: the per-version index records the docs directory it was built from (`source_dir`). If the docs move, the server rebuilds the index automatically and warns to run `changesource`.

## Configuration reference (manual)

`config.json` in the repo root is a manual reference. If you prefer not to run `start`, configure any MCP client with:

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

## Running the server directly

```bash
# Via the entry point (starts the stdio MCP server)
unity-docs-mcp
# 🚀 Unity Docs MCP Server v0.3.0
# 📚 Offline mode - reading local Unity installation docs
# 📦 Installed Unity versions: 6000.5.7f1
# 🔌 Starting MCP server...
```

Or directly:

```bash
python -m unity_docs_mcp.server
```

`UNITY_HUB_EDITOR_DIR` can be set as an environment variable instead of hardcoding the editor root.

## Testing

```bash
python -m unittest discover tests/
```

The suite covers: version parsing/resolution, FTS5 index build + search, config writing for all 6 tools, CLI `start`/`changesource`, scraper local reads, and server end-to-end. Tests use a fake Unity install fixture (`tests/helpers.py`) so they run without Unity installed.

## Troubleshooting

1. **"No local Unity documentation found"** — the editor root wasn't found or contains no installs. Run `unity-docs-mcp start --editor-root <path>` or set `UNITY_HUB_EDITOR_DIR`.
2. **Version falls back unexpectedly** — the requested version isn't installed, so the server served the newest installed with a note like `6000.0 not installed; using 6000.5.7f1`. Use `list_unity_versions` to see what's installed.
3. **Slow first search / `start`** — the FTS5 index build over 42,000 pages takes a minute or two the first time; afterwards it's reused instantly.
4. **Empty search results** — check that `start` ran (an index exists); search matches page bodies, and FTS5 defaults to AND across words.
5. **Config not picked up** — restart the AI tool after `start`, and check the tool's config file contains the `unity-docs` entry.
6. **Class not found but should exist** — it may live in a namespace (`AI.NavMeshAgent`, `UI.Button`). Search for the plain name to find the full name; the server resolves it automatically where possible.

## License

MIT
