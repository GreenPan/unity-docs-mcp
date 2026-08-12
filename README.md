# Unity Docs MCP Server

Provides Unity documentation access directly in Claude — **fully offline**, reading the documentation bundled with your locally installed Unity editors.

> **About this project**: this is a fork of an earlier `unity-docs-mcp` that scraped Unity's online documentation. We removed the online querying entirely and rebuilt it around a locally built offline database — the server only ever reads documentation that ships with your installed Unity editors, and makes no network requests at all.

**⚠️ Disclaimer**: This is an unofficial community project. Unity Technologies is not affiliated with and does not endorse or support this project.

[日本語版 README](README_ja.md)

## How it works

The MCP server reads Unity's offline documentation that ships with every editor installed via Unity Hub (`.../Editor/Data/Documentation/en/`). No network requests are made. A SQLite FTS5 full-text index is built once per installed version, giving fast full-body search across all 42,000+ script reference pages.

## Installation

```bash
pip install -e .
```

### Step 1: Start (build index + configure AI tools)

```bash
unity-docs-mcp start
```

`start` walks through two steps:

1. **Locate the docs** — it prompts for your Unity Hub Editor directory (e.g. `C:\Program Files\Unity\Hub\Editor`), or you can pass it directly:
   ```bash
   unity-docs-mcp start --editor-root "C:\Program Files\Unity\Hub\Editor"
   ```
2. **Build the search index** — a SQLite FTS5 index is built for every installed Unity version (first run takes a minute or two; afterwards it is reused instantly).
3. **Write MCP configs** — `unity-docs-mcp` writes its server entry into the config files of the supported AI tools below.

### Manual configuration (no `start`)

If you prefer to configure an MCP client by hand instead of running `start`,
add the server entry directly to your tool's config. The server command is
always the same:

```json
{
  "mcpServers": {
    "unity-docs": {
      "command": "<path-to-python>",
      "args": ["-m", "unity_docs_mcp.server"],
      "env": { "UNITY_HUB_EDITOR_DIR": "<Unity Hub Editor directory>" }
    }
  }
}
```

Where:
- `<path-to-python>` is the Python interpreter that has `unity-docs-mcp` installed
  (find it with `which python` on macOS/Linux, or `where python` on Windows).
  Use a full absolute path to avoid "module not found" errors.
- `<Unity Hub Editor directory>` is the parent of your installed editor folders,
  e.g. `C:\Program Files\Unity\Hub\Editor`. You can point to it instead with an
  environment variable (skip the `env` block) by setting `UNITY_HUB_EDITOR_DIR`.

Then place it in your client:

**Claude Code** — `.mcp.json` in your project root (top-level key `mcpServers`):
```json
{ "mcpServers": { "unity-docs": {
  "command": "<path-to-python>", "args": ["-m", "unity_docs_mcp.server"],
  "env": { "UNITY_HUB_EDITOR_DIR": "C:\\Program Files\\Unity\\Hub\\Editor" } } } }
```

**Claude Desktop** — `%APPDATA%\Claude\claude_desktop_config.json` (Windows) or
`~/Library/Application Support/Claude/claude_desktop_config.json` (macOS), same
`mcpServers` shape as above.

> **Note**: without `start`, the search index is built **lazily** on the first
> query (it can take a few minutes for the initial build; progress is printed to
> stderr). Running `start` up front builds it eagerly and also auto-writes configs
> for Cursor, VS Code (Copilot), OpenCode, and Codex — see
> [docs/DETAILED_GUIDE.md](docs/DETAILED_GUIDE.md) for their exact file paths.

### Switching Unity installs

If you move to a different editor directory (new install, different drive):

```bash
unity-docs-mcp changesource --editor-root "D:\NewUnity\Hub\Editor"
```

`changesource` rebuilds the index from the new directory and refreshes all tool configs.

### Supported AI tools

`start` writes MCP configuration for: **Claude Desktop**, **Claude Code** (`.mcp.json`), **Cursor**, **VS Code (Copilot)**, **OpenCode**, and **Codex**.

Use `--tools` to select a subset:

```bash
unity-docs-mcp start --tools claude-desktop,claude-code
```

Valid tool names: `claude-desktop`, `claude-code`, `cursor`, `vscode`, `opencode`, `codex`.

## Usage

Ask Claude about Unity APIs:
- "Tell me about GameObject"
- "How do I use NavMeshAgent?"
- "Search for transform methods"

All lookups resolve to your **installed Unity versions**. Requesting a version
that isn't installed falls back to the newest installed version with a note
(e.g. `6000.0 not installed; using 6000.5.7f1`).

## Features

- 🚫 **Fully offline** — reads local Unity documentation, no network
- 🔍 **Full-text search** — FTS5 index over page bodies (ScriptReference API + Manual handbook)
- 📖 **Manual lookup** — `get_unity_manual_doc` reads Unity Manual pages or searches them
- 🎯 **Exact installed versions** — prefix matching resolves `6000.5` → `6000.5.7f1`; uninstalled versions fall back to the newest installed with a note
- 💾 **Persistent index** — built once per version, reused across restarts
- ⚙️ **One-command setup** — `start` builds the index and wires up all 6 AI tools

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
