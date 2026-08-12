# Unity Docs MCP Server

ClaudeでUnityのドキュメントに直接アクセスできるようにします — **完全オフライン**で、Unity Hub でインストールしたローカルエディタに同梱のドキュメントを読み取ります。

**⚠️ 免責事項**: これは非公式のコミュニティプロジェクトです。Unity Technologiesは本プロジェクトと提携しておらず、支援や承認も行っていません。

[English README](README.md)

## 仕組み

この MCP サーバーは、Unity Hub でインストールされた各エディタに同梱のオフラインドキュメント（`.../Editor/Data/Documentation/en/`）を読み取ります。ネットワーク通信は一切行いません。SQLite FTS5 全文検索インデックスをバージョンごとに一度だけ構築し、42,000 ページ以上の ScriptReference 全体を高速に全文検索できます。

## インストール

```bash
pip install -e .
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
