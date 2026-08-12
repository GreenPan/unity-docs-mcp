# Unity Docs MCP Server

Provides Unity documentation access directly in Claude — **fully offline**, reading the documentation bundled with your locally installed Unity editors.

> **About this project**: this is a fork of an earlier `unity-docs-mcp` that scraped Unity's online documentation. We removed the online querying entirely and rebuilt it around a locally built offline database — the server only ever reads documentation that ships with your installed Unity editors, and makes no network requests at all.

**⚠️ Disclaimer**: This is an unofficial community project. Unity Technologies is not affiliated with and does not endorse or support this project.

> **Use case**: Tired of your agent scraping who-knows-how-many-hands-removed info from the web or communities? It's time to let it read the real, official documentation. With this MCP server installed, your AI assistant reads the official offline docs bundled with your local Unity editor — authoritative, exactly matching your engine version, and fully offline.

[中文版 README](README_zh.md) · [日本語版 README](README_ja.md)

## How it works

The MCP server reads Unity's offline documentation that ships with an installed
Unity editor (`.../Editor/Data/Documentation/en/`). `unity-docs-mcp build` turns
that documentation into a SQLite FTS5 full-text index per installed version
(`~/.unity_docs_mcp/db/search_{version}.db`). The MCP server then serves **exactly
one version**, chosen via the `UNITY_DOCS_VERSION` env var in your tool config,
and recovers the docs directory from the built database. No network requests are
made.

## Installation

> Once published to PyPI (see [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)), this is
> the install for end users:

```bash
pip install unity-docs-mcp
```

This gives you the `unity-docs-mcp` command.

### Step 1: Build the offline index

```bash
unity-docs-mcp build --editor-root "C:\Program Files\Unity\Hub\Editor"
```

`build` scans the Hub Editor directory, and for every installed Unity version
builds (or reuses) a SQLite FTS5 index. First run takes a minute or two; later
runs are instant. Pass `--force` to rebuild. It does **not** touch any IDE
config — you wire up the server manually (next step).

### Step 2: Add the server to your IDE manually

The MCP server is a stdio command. Add this entry to your tool's MCP config,
pointing `UNITY_DOCS_VERSION` at the version you want to serve (the one `build`
indexed — run `ls ~/.unity_docs_mcp/db/` to see them):

```json
{
  "mcpServers": {
    "unity-docs": {
      "command": "<path-to-python>",
      "args": ["-m", "unity_docs_mcp.server"],
      "env": { "UNITY_DOCS_VERSION": "6000.5.7f1" }
    }
  }
}
```

Where `<path-to-python>` is the Python interpreter that has `unity-docs-mcp`
installed (find it with `which python` on macOS/Linux, or `where python` on
Windows). Use a full absolute path to avoid "module not found" errors.

Per-tool config locations:

- **Claude Code** — `.mcp.json` in your project root:
  ```json
  { "mcpServers": { "unity-docs": {
    "command": "<path-to-python>", "args": ["-m", "unity_docs_mcp.server"],
    "env": { "UNITY_DOCS_VERSION": "6000.5.7f1" } } } }
  ```
- **Claude Desktop** — `%APPDATA%\Claude\claude_desktop_config.json` (Windows) or
  `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS), same
  `mcpServers` shape.
- **Cursor** — `.cursor/mcp.json` in your project, `mcpServers` key.
- **VS Code (Copilot)** — `.vscode/mcp.json` in your project, `servers` key, plus
  `"type": "stdio"`.
- **OpenCode** — `opencode.json` in your project, `mcp` key, `"type": "local"`,
  `command` as an array, and `environment` instead of `env`.
- **Codex** — `~/.codex/config.toml`, a `[mcp_servers.unity-docs]` table.

Restart the AI tool after editing its config so the MCP server is picked up.

> **Note**: if you skip `build`, the server still works — it builds the index
> lazily on the first query (a few minutes; progress printed to stderr). Running
> `build` up front just does it eagerly.

### Switching to a different Unity version / install

```bash
unity-docs-mcp build --editor-root "D:\NewUnity\Hub\Editor" --force
```

then update `UNITY_DOCS_VERSION` in your tool configs to the version you want.

## Usage

Ask Claude about Unity APIs:
- "Tell me about GameObject"
- "How do I use NavMeshAgent?"
- "Search for transform methods"

All lookups resolve to the **version you point the server at** (`UNITY_DOCS_VERSION`).
The server serves exactly that version's docs.

## Features

- 🚫 **Fully offline** — reads local Unity documentation, no network
- 🔍 **Full-text search** — FTS5 index over page bodies (ScriptReference API + Manual handbook)
- 📖 **Manual lookup** — `get_unity_manual_doc` reads Unity Manual pages or searches them
- 🎯 **Single version served** — `UNITY_DOCS_VERSION` env picks which built version the server reads
- 💾 **Persistent index** — `build` makes a per-version FTS5 db, reused across restarts
- 🛠️ **Manual IDE setup** — one stdio entry per tool; no auto-config magic

## Development

```bash
git clone https://github.com/Saqoosha/unity-docs-mcp
cd unity-docs-mcp
python -m venv venv
source venv/bin/activate
pip install -e .
python -m unittest discover tests/
```

## Documentation

For detailed documentation, see the [docs](docs/) directory.

## License

MIT
