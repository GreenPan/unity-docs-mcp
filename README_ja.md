# Unity Docs MCP Server

ClaudeでUnityのドキュメントに直接アクセスできるようにします — **完全オフライン**で、Unity Hub でインストールしたローカルエディタに同梱のドキュメントを読み取ります。

> **このプロジェクトについて**: かつて Unity のオンラインドキュメントをスクレイピングしていた旧 `unity-docs-mcp` からのフォークです。オンラインでの照会機能を完全に削除し、ローカルに構築したオフラインデータベースを照会する形に作り直しました — サーバーはインストール済みエディタに同梱のドキュメントのみを読み取り、ネットワーク通信は一切行いません。

**⚠️ 免責事項**: これは非公式のコミュニティプロジェクトです。Unity Technologiesは本プロジェクトと提携しておらず、支援や承認も行っていません。

> **想定される利用シーン**: エージェントがネットやコミュニティで何手も加工された情報を拾ってくることに悩んでいませんか？ 本当の公式ドキュメントを参照させる時が来ました。この MCP サーバーを導入すれば、AI アシスタントはローカルの Unity エディタに同梱される公式オフラインドキュメントを直接読み取ります —— 権威があり、エンジン版と完全に一致し、完全オフラインです。

[English README](README.md) · [中文版 README](README_zh.md)

## 仕組み

この MCP サーバーは、Unity Hub でインストールされたエディタに同梱のオフラインドキュメント（`.../Editor/Data/Documentation/en/`）を読み取ります。`unity-docs-mcp build` がドキュメントをバージョンごとの SQLite FTS5 全文インデックス（`~/.unity_docs_mcp/db/search_{version}.db`）に変換します。MCP サーバーは設定ファイルの env `UNITY_DOCS_VERSION` で指定された**1 つのバージョン**だけを提供し、ドキュメントディレクトリはビルド済み DB から復元します。ネットワーク通信は一切行いません。

## インストール

> PyPI に公開後（[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) 参照）、エンドユーザー向けのインストールはこれです：

```bash
pip install unity-docs-mcp
```

これで `unity-docs-mcp` コマンドが使えます。（ソースツリーで開発する場合のみ `pip install -e .` を使用 — [開発](#開発) 参照）

### ステップ 1: オフラインインデックスを構築

```bash
unity-docs-mcp build --editor-root "C:\Program Files\Unity\Hub\Editor"
```

`build` は Hub Editor ディレクトリを走査し、インストール済みの各 Unity バージョンについて SQLite FTS5 インデックスを構築（または再利用）します。初回は数分かかります。`--force` で再構築。**IDE 設定には一切触れません** — サーバーは次の手順で手動設定します。

### ステップ 2: サーバーを IDE に手動追加

MCP サーバーは stdio コマンドです。`UNITY_DOCS_VERSION` に提供したいバージョン（`build` がインデックス化したもの）を指定して、各ツールの MCP 設定に追加します：

```json
{
  "mcpServers": {
    "unity-docs": {
      "command": "<pythonへのパス>",
      "args": ["-m", "unity_docs_mcp.server"],
      "env": { "UNITY_DOCS_VERSION": "6000.5.7f1" }
    }
  }
}
```

`<pythonへのパス>` は `unity-docs-mcp` がインストールされている Python インタプリタの**絶対パス**（macOS/Linux は `which python`、Windows は `where python` で確認）。「module not found」エラーを避けるため絶対パスを使います。

各ツールの設定場所：

- **Claude Code** — プロジェクト直下の `.mcp.json`：
  ```json
  { "mcpServers": { "unity-docs": {
    "command": "<pythonへのパス>", "args": ["-m", "unity_docs_mcp.server"],
    "env": { "UNITY_DOCS_VERSION": "6000.5.7f1" } } } }
  ```
- **Claude Desktop** — `%APPDATA%\Claude\claude_desktop_config.json`（Windows）または `~/Library/Application Support/Claude/claude_desktop_config.json`（macOS）に、同じ `mcpServers` 形式。
- **Cursor** — プロジェクトの `.cursor/mcp.json`（`mcpServers` キー）。
- **VS Code (Copilot)** — プロジェクトの `.vscode/mcp.json`（`servers` キー、`"type": "stdio"` も追加）。
- **OpenCode** — プロジェクトの `opencode.json`（`mcp` キー、`"type": "local"`、`command` は配列、`env` ではなく `environment`）。
- **Codex** — `~/.codex/config.toml` の `[mcp_servers.unity-docs]` テーブル。

設定編集後は AI ツールを再起動してください。

> **注意**: `build` を省略してもサーバーは動作します — 初回クエリ時にインデックスを遅延ビルドします（初回は数分、進捗は stderr に出力）。`build` を先に実行すれば事前に構築されます。

### Unity のバージョン / インストール先を変更した場合

```bash
unity-docs-mcp build --editor-root "D:\NewUnity\Hub\Editor" --force
```

その後、各ツール設定の `UNITY_DOCS_VERSION` を提供したいバージョンに更新します。

## 使い方

ClaudeにUnity APIについて質問してください：
- 「GameObjectについて教えて」
- 「NavMeshAgentの使い方は？」
- 「transformメソッドを検索して」

すべての参照は、サーバーが提供する**1 つのバージョン**（`UNITY_DOCS_VERSION` で指定）に解決されます。

## 機能

- 🚫 **完全オフライン** — ローカルの Unity ドキュメントを読み取り、ネットワーク不要
- 🔍 **全文検索** — タイトルだけでなく本文も FTS5 インデックス対象（ScriptReference API + Manual ハンドブック）
- 📖 **マニュアル参照** — `get_unity_manual_doc` で Unity マニュアルのページを読む、または検索
- 🎯 **1 バージョンのみ提供** — env `UNITY_DOCS_VERSION` で提供するビルド済みバージョンを選択
- 💾 **永続インデックス** — `build` でバージョンごとの FTS5 DB を作成し、再起動後も再利用
- 🛠️ **手動 IDE 設定** — ツールごとに stdio エントリを 1 つ追加。自動設定のマジックなし

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
