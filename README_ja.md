# Unity Docs MCP Server

ClaudeでUnityのドキュメントに直接アクセスできるようにします — **完全オフライン**で、Unity Hub でインストールしたローカルエディタに同梱のドキュメントを読み取ります。

> **このプロジェクトについて**: かつて Unity のオンラインドキュメントをスクレイピングしていた旧 `unity-docs-mcp` からのフォークです。オンラインでの照会機能を完全に削除し、ローカルに構築したオフラインデータベースを照会する形に作り直しました — サーバーはインストール済みエディタに同梱のドキュメントのみを読み取り、ネットワーク通信は一切行いません。

**⚠️ 免責事項**: これは非公式のコミュニティプロジェクトです。Unity Technologiesは本プロジェクトと提携しておらず、支援や承認も行っていません。

> **想定される利用シーン**: エージェントがネットやコミュニティで何手も加工された情報を拾ってくることに悩んでいませんか？ 本当の公式ドキュメントを参照させる時が来ました。この MCP サーバーを導入すれば、AI アシスタントはローカルの Unity エディタに同梱される公式オフラインドキュメントを直接読み取ります —— 権威があり、エンジン版と完全に一致し、完全オフラインです。

[English README](README.md) · [中文版 README](README_zh.md)

## 仕組み

この MCP サーバーは、Unity Hub でインストールされた各エディタに同梱のオフラインドキュメント（`.../Editor/Data/Documentation/en/`）を読み取ります。ネットワーク通信は一切行いません。SQLite FTS5 全文検索インデックスをバージョンごとに一度だけ構築し、42,000 ページ以上の ScriptReference 全体を高速に全文検索できます。

## インストール

```bash
# PyPI に公開後（docs/DEPLOYMENT.md 参照）は直接インストール:
pip install unity-docs-mcp

# それまではソースツリーからインストール:
pip install -e .
```

どちらでも `unity-docs-mcp` コマンドが使えます。次に `start` を実行して、Unity エディタのドキュメントを特定し、オフラインインデックスを構築し、MCP 設定を書き込みます：

```bash
unity-docs-mcp start
```

### ステップ 1: 開始（インデックス構築 + AI ツール設定）

```bash
unity-docs-mcp start
```

`start` は以下の手順を実行します：

1. **ドキュメントの場所を指定** — Unity Hub の Editor ディレクトリ（例：`C:\Program Files\Unity\Hub\Editor`）を入力するか、直接渡します：
   ```bash
   unity-docs-mcp start --editor-root "C:\Program Files\Unity\Hub\Editor"
   ```
2. **検索インデックスを構築** — インストール済みの各 Unity バージョンについて SQLite FTS5 インデックスを構築します（初回は数分かかります。以降は即座に再利用されます）。
3. **MCP 設定を書き込み** — 対応する各 AI ツールの設定ファイルに MCP サーバーエントリを書き込みます。

### 手動設定（`start` を使わない場合）

`start` を実行せずに MCP クライアントへ手動で設定する場合は、サーバーエントリを直接追加します。サーバーコマンドは常に同じです：

```json
{
  "mcpServers": {
    "unity-docs": {
      "command": "<pythonへのパス>",
      "args": ["-m", "unity_docs_mcp.server"],
      "env": { "UNITY_HUB_EDITOR_DIR": "<Unity Hub Editorディレクトリ>" }
    }
  }
}
```

- `<pythonへのパス>`：`unity-docs-mcp` がインストールされている Python インタプリタの**絶対パス**（macOS/Linux は `which python`、Windows は `where python` で確認）。「module not found」エラーを避けるため絶対パスを使います。
- `<Unity Hub Editorディレクトリ>`：インストール済みエディタフォルダの親ディレクトリ（例：`C:\Program Files\Unity\Hub\Editor`）。`env` ブロックを省略し、環境変数 `UNITY_HUB_EDITOR_DIR` で指定しても構いません。

**Claude Code** — プロジェクト直下の `.mcp.json`（トップレベルキー `mcpServers`）：
```json
{ "mcpServers": { "unity-docs": {
  "command": "<pythonへのパス>", "args": ["-m", "unity_docs_mcp.server"],
  "env": { "UNITY_HUB_EDITOR_DIR": "C:\\Program Files\\Unity\\Hub\\Editor" } } } }
```

**Claude Desktop** — `%APPDATA%\Claude\claude_desktop_config.json`（Windows）または
`~/Library/Application Support/Claude/claude_desktop_config.json`（macOS）に、同じ `mcpServers` 形式で追加。

> **注意**: `start` を実行しない場合、検索インデックスは**初回クエリ時に遅延ビルド**されます（初回は数分かかり、進捗は stderr に出力）。`start` を先に実行するとインデックスを事前に構築し、Cursor / VS Code (Copilot) / OpenCode / Codex の設定も自動で書き込みます — 正確なファイルパスは [docs/DETAILED_GUIDE.md](docs/DETAILED_GUIDE.md) を参照。

### Unity のインストール先を変更した場合

別のエディタディレクトリ（新しいインストールや別ドライブなど）に移動した場合：

```bash
unity-docs-mcp changesource --editor-root "D:\NewUnity\Hub\Editor"
```

`changesource` は新しいディレクトリからインデックスを再構築し、すべてのツール設定を更新します。

### 対応 AI ツール

`start` は以下の設定を書き込みます：**Claude Desktop**、**Claude Code**（`.mcp.json`）、**Cursor**、**VS Code (Copilot)**、**OpenCode**、**Codex**。

`--tools` で絞り込めます：

```bash
unity-docs-mcp start --tools claude-desktop,claude-code
```

指定できるツール名：`claude-desktop`, `claude-code`, `cursor`, `vscode`, `opencode`, `codex`。

## 使い方

ClaudeにUnity APIについて質問してください：
- 「GameObjectについて教えて」
- 「NavMeshAgentの使い方は？」
- 「transformメソッドを検索して」

すべての参照は**インストール済みの Unity バージョン**に解決されます。未インストールのバージョンを指定すると、最新のインストール済みにフォールバックし、注記を付与します（例：`6000.0 not installed; using 6000.5.7f1`）。

## 機能

- 🚫 **完全オフライン** — ローカルの Unity ドキュメントを読み取り、ネットワーク不要
- 🔍 **全文検索** — タイトルだけでなく本文も FTS5 インデックス対象（ScriptReference API + Manual ハンドブック）
- 📖 **マニュアル参照** — `get_unity_manual_doc` で Unity マニュアルのページを読む、または検索
- 🎯 **インストール済みバージョンに正確一致** — `6000.5` は `6000.5.7f1` に前方一致解決。未インストール版は最新インストール済みにフォールバックし注記
- 💾 **永続インデックス** — バージョンごとに一度構築し、再起動後も再利用
- ⚙️ **ワンコマンドセットアップ** — `start` でインデックス構築と 6 ツールの設定を一括実行

## 開発

```bash
git clone https://github.com/Saqoosha/unity-docs-mcp
cd unity-docs-mcp
python -m venv venv
source venv/bin/activate
pip install -e .
python -m unittest discover tests/
```

## ドキュメント

詳細なドキュメントは [docs](docs/) ディレクトリを参照してください。

## ライセンス

MIT
