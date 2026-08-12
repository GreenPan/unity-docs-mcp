# Unity Docs MCP Server - アーキテクチャドキュメント

## 📋 プロジェクト概要

**目的**: ローカルにインストールされた Unity エディタのオフラインドキュメントを（**完全オフライン**で）読み取り、クリーンな Markdown 形式で MCP (Model Context Protocol) 経由で提供するサーバー

**主な機能**:
- ローカルディスクから Unity API ドキュメントを読み取り（クラス、メソッド）
- 全文ドキュメント検索（ページ本文も対象の SQLite FTS5）
- インストール済み Unity バージョンへの正確な一致
- クリーンなテキスト出力（UI要素、フォーマット除去）
- ワンコマンドセットアップ（`start`）でインデックス構築と 6 ツール設定を一括実行

## 🏗️ アーキテクチャ

### ディレクトリ構造
```
unity-docs-mcp/
├── src/unity_docs_mcp/
│   ├── __init__.py           # バージョン
│   ├── server.py             # MCPサーバー (UnityDocsMCPServer)
│   ├── scraper.py            # ローカルドキュメント読み取り (UnityDocScraper)
│   ├── parser.py             # HTML解析&クリーニング (UnityDocParser)
│   ├── search_index.py       # SQLite FTS5 検索インデックス (UnitySearchIndex)
│   ├── version_resolver.py   # バージョン検出・解決
│   ├── mcp_config.py         # AIツールの設定書き込み
│   └── cli.py                # `unity-docs-mcp start` / `changesource`
├── tests/
│   ├── test_*.py             # ユニットテスト
│   └── helpers.py            # フェイクUnityインストールのfixture
├── pyproject.toml            # 依存関係&プロジェクト設定
└── config.json               # 手動MCP設定のリファレンス（Windowsパス）
```

### 実行時データ
```
~/.unity_docs_mcp/db/search_{version}.db   # インストール済みバージョンごとのSQLite FTS5インデックス
```

### コアコンポーネント

#### 1. **server.py** - MCPサーバー
```python
class UnityDocsMCPServer:
    # MCPツール:
    - list_unity_versions()      # インストール済みUnityバージョン
    - suggest_unity_classes()    # クラス名提案
    - get_unity_api_doc()       # APIドキュメント取得
    - search_unity_docs()       # APIリファレンス検索（kind='api'）
    - get_unity_manual_doc()    # マニュアルページの読み取り/検索
```
バージョンは `scraper.resolve_version()` で解決（前方一致）。未インストールのリクエストバージョンは最新のインストール済みにフォールバックして注記を付与します（`6000.0 not installed; using 6000.5.7f1`）。`**Source:**` はローカルの絶対パス。

#### 2. **scraper.py** - ローカルドキュメントリーダー
```python
class UnityDocScraper:
    # editor_root 解決: 引数 > UNITY_HUB_EDITOR_DIR 環境変数 > デフォルトHubパス
    - resolve_version(version)         # None -> 最新、前方一致
    - get_api_doc(class, method, version)
    - search_docs(query, version)      # search_index(kind='api') に委譲
    - get_manual_doc(page_query, version)  # ページ直接解決、なければManual検索
    - suggest_class_names(partial)     # search_index に委譲
    - check_api_availability_across_versions()  # ローカルファイル存在チェック
    # ページ名パターン（Unityサイトと同じ）:
    #   クラス:    {Class}.html
    #   メソッド:  {Class}.{method}.html        (ドット記法)
    #   プロパティ:{Class}-{property}.html      (ハイフン記法)
    #   Manual:    {slug}.html                  (サブディレクトリ可)
    # 自動フォールバック: ドット→ハイフンの順で試す
```

#### 3. **parser.py** - HTMLパーサー
```python
class UnityDocParser:
    # 重要な処理パイプライン:
    1. _remove_link_tags()          # <a>タグを削除（超重要！）
    2. _remove_unity_ui_elements()  # フィードバック/UI要素を削除
    3. trafilatura.extract()        # メインコンテンツを抽出
    4. _clean_trafilatura_content() # コードフォーマットを修正
    5. _remove_markdown_formatting() # 太字、リンクを削除
```

#### 4. **search_index.py** - SQLite FTS5 検索インデックス
```python
class UnitySearchIndex:
    - ensure_index(version, force)   # meta検証、必要ならビルド
    - build_index(version, progress) # API + Manual ページを並列本文抽出でインデックス化
    - search(query, version, max_results, kind)  # FTS5 MATCH + bm25、クラス優先スコア
    - suggest_classes(partial_name)  # 前方一致 + member_type='class'
    - get_page_name(query, version)  # API名前空間解決
    - get_manual_page(page_query, version)  # Manual slug/タイトル解決
    - clear_cache(version)           # バージョンのdbを削除
    # バージョンごとのスキーマ:
    #   meta  (version, page_count, built_at, source_dir)
    #   pages (id, name, title, member_type, path, kind)  # kind: 'api' | 'manual'
    #   ft    (FTS5: name, title, description, content)
```
`build_index` は `ScriptReference/docdata` と `Manual/docdata` の両方を解析し
（`index.json`、フォールバック `index.js`）、一つの FTS5 db にインデックス化します。
`member_type` はハイフン/ドット命名規則と、ドットの基底が既知クラスかどうかで
class / method / property / constructor を判定します
（例：`Object.GetInstanceID` → method、`AI.NavMeshAgent` → class）。
インデックスは遅延ビルド（`ensure_index`）し、`start`/`changesource` で明示的にトリガー。
meta の `source_dir` 不一致またはスキーマ更新（`kind` 列なし）で自動再ビルド。

#### 5. **version_resolver.py** - バージョンモデル
```python
@dataclass InstalledVersion: name, editor_dir, docs_dir, version_key
parse_unity_version("6000.5.7f1") -> (6000, 5, 7, type_rank, build, revision)
discover_versions(editor_root)     # Hub Editorディレクトリを走査、新しい順
resolve_version(version, installed) # None->最新、完全一致、前方一致、それ以外はNone
default_editor_root()              # プラットフォーム既定のHubパス
```
異なる major.minor バージョンで未インストールの場合は、エラーにするのではなく最新のインストール済みにフォールバックし注記を付与します。

#### 6. **mcp_config.py** - ツール設定
```python
write_all(editor_root, python_exe, project_dir, tools) -> {tool: status}
```
同一の stdio サーバーエントリ（`command` = venv の python、`args = ["-m", "unity_docs_mcp.server"]`、`env = {"UNITY_HUB_EDITOR_DIR": editor_root}`）を以下に書き込みます:

| ツール | 設定ファイル | キー |
|---|---|---|
| Claude Desktop | `%APPDATA%\Claude\claude_desktop_config.json` | `mcpServers` |
| Claude Code | `{project}/.mcp.json` | `mcpServers` |
| Cursor | `{project}/.cursor/mcp.json` | `mcpServers` |
| VS Code (Copilot) | `{project}/.vscode/mcp.json` | `servers` (`type: stdio`) |
| OpenCode | `{project}/opencode.json` | `mcp` (`type: local`、command配列) |
| Codex | `~/.codex/config.toml` | `[mcp_servers.unity-docs]` |

JSON設定は読み込み→マージ→書き込み（他エントリ保持、`.bak` バックアップ）。Codex の TOML はテキスト編集し、既存テーブルを保護します。

#### 7. **cli.py** - コマンド
```bash
unity-docs-mcp start          # エディタ特定 -> インデックス構築 -> 設定書き込み
unity-docs-mcp changesource   # 新しいエディタ -> インデックス再構築 -> 設定更新
```

## 🔧 主要な依存関係

```toml
dependencies = [
    "mcp>=1.0.0",              # MCPプロトコル
    "beautifulsoup4>=4.12.0",  # HTML解析
    "trafilatura>=1.8.0",      # コンテンツ抽出
    "lxml>=4.9.0",             # XML/HTML処理
    "markdownify>=0.11.6",     # HTMLからMarkdownへの変換
]
```
`sqlite3`（FTS5）は Python 標準ライブラリ — ネットワークライブラリは使用しません。

## 🐛 問題と解決策

### 問題0: オンラインドキュメントが不要
旧サーバーは `docs.unity3d.com` をスクレイピングしていましたが、本プロジェクトは完全オフラインです。ドキュメントは各エディタに同梱される `.../Editor/Data/Documentation/en/` から読み取ります。

### 問題1: コードのブラケット問題
**症状**:
```csharp
public class Example :[MonoBehaviour]{
    private[GameObject][] cubes = new[GameObject][10];
```
**原因**: HTMLの`<a>`タグがTrafilaturaによって`[text]`形式に変換される
**解決策**: HTMLレベルでリンクタグを事前除去
```python
for link in soup.find_all('a'):
    link.replace_with(link.get_text())
```

### 問題2: コンテンツ内のUI要素
「Leave feedback」、「Success!」、「Submission failed」などのテキストを除去。

### 問題3: 太字フォーマット
`<strong>`/`<b>` タグと Markdown の `**` を除去。

### 問題4: Markdownリンク
正規表現で `[text](url)` を除去。

### 問題5: プロパティvsメソッドのページ名
- メソッドはドット記法: `GameObject.SetActive.html`
- プロパティはハイフン記法: `GameObject-transform.html`
- 自動フォールバックでドット→ハイフンの順に試す。

## 🚀 起動とテスト

### インデックス構築 + ツール設定
```bash
unity-docs-mcp start --editor-root "C:\Program Files\Unity\Hub\Editor"
```

### MCP Inspector
```bash
./start_inspector.sh
# http://localhost:6274 を開く
```

### テスト例
```json
// GameObjectドキュメントを取得（最新のインストール済みバージョン）
{"class_name": "GameObject"}

// 前方一致バージョンで特定のメソッドを取得
{"class_name": "GameObject", "method_name": "SetActive", "version": "6000.5"}

// 全文検索（本文も対象）
{"query": "transform", "version": "6000.5"}

// クラス提案を取得
{"partial_name": "game"}

// 未インストールバージョン -> インストール済み一覧つきでエラー
{"class_name": "AsyncGPUReadback", "version": "6000.0"}
```

### テスト実行
```bash
python -m unittest discover tests/
```

## 💡 重要な洞察

1. **完全オフライン** — データソースはローカルインストール。`UNITY_HUB_EDITOR_DIR` でサーバーに Hub Editor ルートを指定。
2. **FTS5 全文インデックス** — タイトルだけでなく**本文**も検索対象。インデックスは `~/.unity_docs_mcp/db/` に保存。
3. **遅延ビルド** — `ensure_index` が `meta` テーブルを検証し、存在しないか古い（`source_dir` 不一致）場合のみビルド。
4. **バージョンモデル** — 完全なインストールディレクトリ名（`6000.5.7f1`）が基準。前方一致で解決し、未インストール版はエラー。
5. **設定の安全性** — 読み込み→マージ→書き込みで他エントリを保持、`.bak` バックアップ、Codex TOML はテキスト編集。
6. **Windowsパス** — 検索結果の `path` は前方スラッシュ（`as_posix()`）。ファイル読み取りは `normpath`。

## 📝 将来の改善点

1. Unity Package ドキュメントのサポート
2. インデックスの増分更新（デルタビルド）

## ⚠️ 重要な注意事項

- **常にvenvをアクティベート**してから実行
- **MCP Inspectorポート**: 6274（Web UI）、6277（プロキシ）
- **Python 3.10以上**が必要

---

**覚えておくこと**: クリーンな出力の鍵は、マークダウン変換の前に問題のあるHTML要素を削除することです！🎯

## クイックリファレンス

### ファイルの場所
- **メインサーバー**: `src/unity_docs_mcp/server.py`
- **ローカルドキュメントリーダー**: `src/unity_docs_mcp/scraper.py`
- **パーサー/クリーナー**: `src/unity_docs_mcp/parser.py`
- **検索インデックス**: `src/unity_docs_mcp/search_index.py`
- **バージョン解決**: `src/unity_docs_mcp/version_resolver.py`
- **設定書き込み**: `src/unity_docs_mcp/mcp_config.py`
- **CLI**: `src/unity_docs_mcp/cli.py`
- **インデックスDB**: `~/.unity_docs_mcp/db/`
