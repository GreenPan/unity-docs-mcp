# Unity Docs MCP Server - アーキテクチャドキュメント

## 📋 プロジェクト概要

**目的**: ローカルにインストールされた Unity エディタのオフラインドキュメントを（**完全オフライン**で）読み取り、クリーンな Markdown 形式で MCP (Model Context Protocol) 経由で提供するサーバー

**主な機能**:
- ローカルディスクから Unity API ドキュメントを読み取り（クラス、メソッド）
- 全文ドキュメント検索（ページ本文も対象の SQLite FTS5）
- サービス対象バージョンへの正確一致
- クリーンなテキスト出力（UI要素、フォーマット除去）
- `build` CLI でローカルドキュメントをオフラインインデックス化、IDE は手動設定

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
│   ├── version_resolver.py   # バージョン解析・解決
│   └── cli.py                # `unity-docs-mcp build`
├── tests/
│   ├── test_*.py             # ユニットテスト
│   └── helpers.py            # フェイクUnityインストールのfixture
├── pyproject.toml            # 依存関係&プロジェクト設定
└── config.json               # 手動MCP設定のリファレンス（Windowsパス）
```

### 実行時データ
```
~/.unity_docs_mcp/db/search_{version}.db   # ビルド済みバージョンごとのSQLite FTS5インデックス
```

### コアコンポーネント

#### 1. **server.py** - MCPサーバー
```python
class UnityDocsMCPServer:
    # MCPツール:
    - list_unity_versions()      # サービス対象バージョン
    - suggest_unity_classes()    # クラス名提案
    - get_unity_api_doc()       # APIドキュメント取得
    - search_unity_docs()       # APIリファレンス検索（kind='api'）
    - get_unity_manual_doc()    # マニュアルページの読み取り/検索
```
サーバーは `UNITY_DOCS_VERSION` 環境変数で選ばれた**1 つのビルド済みバージョン**だけを提供します。scraper はそのバージョンの db `meta.source_dir` からドキュメントディレクトリを復元します。サービス対象以外のリクエストバージョンは注記付きでフォールバック（`6000.0 not installed; using 6000.5.7f1`）。`**Source:**` はローカルの絶対パス。

#### 2. **scraper.py** - ローカルドキュメントリーダー
```python
class UnityDocScraper:
    # 単一バージョン: docs_dir はビルド済み db から UNITY_DOCS_VERSION で復元
    - resolve_version(version)         # None -> サービス対象、前方一致
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
インデックスは遅延ビルド（`ensure_index`）し、`build` で明示的にトリガー。
meta の `source_dir` 不一致またはスキーマ更新（`kind` 列なし）で自動再ビルド。

サーバーがビルド済みバージョンのドキュメントを復元するためのモジュール関数:
- `read_db_source_dir(db_dir, version)` → バージョン db の `meta.source_dir`
- `list_built_versions(db_dir)` → ビルド済み db があるバージョン（新しい順）

#### 5. **version_resolver.py** - バージョンモデル
```python
@dataclass InstalledVersion: name, editor_dir, docs_dir, version_key
parse_unity_version("6000.5.7f1") -> (6000, 5, 7, type_rank, build, revision)
discover_versions(editor_root)     # Hub Editorディレクトリを走査（`build` で使用）
resolve_version(version, installed) # None->サービス対象、完全一致、前方一致、それ以外はNone
default_editor_root()              # プラットフォーム既定のHubパス
```
`build` は `discover_versions` で何をインデックス化するか決定します。サーバーは単一の `InstalledVersion`（`UNITY_DOCS_VERSION` で選ばれたもの）だけを提供します。

#### 6. **cli.py** - コマンド
```bash
unity-docs-mcp build --editor-root <hub>   # インストール済みバージョンごとにインデックス構築（または再利用）
                     [--force]             # 既存インデックスを再構築
```
`build` は IDE 設定には一切触れません。サーバーは各ツールの MCP 設定に手動で追加します（`command` = venv の python、`args = ["-m", "unity_docs_mcp.server"]`、`env = {"UNITY_DOCS_VERSION": "<バージョン>"}`）— ツールごとのファイル場所は README / DETAILED_GUIDE を参照（Claude Desktop、Claude Code、Cursor、VS Code、OpenCode、Codex）。

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

### インデックス構築
```bash
unity-docs-mcp build --editor-root "C:\Program Files\Unity\Hub\Editor"
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

1. **完全オフライン** — データソースはローカルインストール。サーバーは `UNITY_DOCS_VERSION` で選ばれたビルド済みバージョンを提供し、docs ディレクトリは db の `meta.source_dir` から復元。
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
- **CLI**: `src/unity_docs_mcp/cli.py`
- **CLI**: `src/unity_docs_mcp/cli.py`
- **インデックスDB**: `~/.unity_docs_mcp/db/`
