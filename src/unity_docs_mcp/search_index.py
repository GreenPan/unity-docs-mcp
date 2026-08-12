"""Unity documentation search index backed by SQLite FTS5.

Indexes both the API reference (ScriptReference/) and the Manual/ handbook
into a single per-version SQLite FTS5 database. ``pages.kind`` distinguishes
'api' from 'manual' rows so API search and manual search stay separate.
"""

import json
import os
import re
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from bs4 import BeautifulSoup

from .version_resolver import parse_unity_version


class UnitySearchIndex:
    """Search Unity documentation using a local SQLite FTS5 index."""

    def __init__(self, docs_dirs: Optional[Dict[str, str]] = None, db_dir: Optional[str] = None):
        self.docs_dirs = docs_dirs or {}  # {full version name: Documentation/en dir}
        if db_dir:
            self.db_dir = db_dir
        else:
            self.db_dir = os.path.join(os.path.expanduser("~"), ".unity_docs_mcp", "db")
        os.makedirs(self.db_dir, exist_ok=True)

        # Newest installed version, used when no version is requested.
        self.default_version = self._pick_default_version()

        # Loaded versions in this process (avoid re-checking the same db).
        self._loaded_versions = set()
        # Lazy sqlite connections per version.
        self._conns: Dict[str, sqlite3.Connection] = {}

    # ------------------------------------------------------------------ paths

    def _pick_default_version(self) -> Optional[str]:
        if not self.docs_dirs:
            return None
        versions = [v for v in self.docs_dirs if parse_unity_version(v) is not None]
        if not versions:
            return None
        versions.sort(key=lambda v: parse_unity_version(v), reverse=True)
        return versions[0]

    def _db_path(self, version: str) -> str:
        return os.path.join(self.db_dir, f"search_{version}.db")

    def _connect(self, version: str) -> sqlite3.Connection:
        conn = self._conns.get(version)
        if conn is None:
            conn = sqlite3.connect(self._db_path(version))
            conn.execute("PRAGMA journal_mode=WAL")
            conn.row_factory = sqlite3.Row
            self._conns[version] = conn
        return conn

    # ------------------------------------------------------------------ build

    def _meta_state(self, version: str) -> str:
        """Classify the existing db: 'valid', 'missing', or 'stale'.

        - missing: no db, empty meta, or an outdated schema (no kind column)
        - stale: db exists but its source_dir differs from the current docs dir
        """
        db_path = self._db_path(version)
        if not os.path.exists(db_path):
            return "missing"
        docs_dir = self.docs_dirs.get(version, "")
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                cols = {r["name"] for r in conn.execute("PRAGMA table_info(pages)")}
                if "kind" not in cols:
                    return "missing"  # pre-manual schema -> rebuild
                row = conn.execute(
                    "SELECT source_dir FROM meta "
                    "WHERE version = ? AND page_count > 0",
                    (version,),
                ).fetchone()
                if row is None:
                    return "missing"
                return "valid" if row["source_dir"] == docs_dir else "stale"
            finally:
                conn.close()
        except sqlite3.Error:
            return "missing"

    def ensure_index(self, version: Optional[str] = None, force: bool = False) -> bool:
        """Make sure a valid index exists for ``version``, building if needed.

        Returns True if a usable index is available afterwards.
        """
        version = version or self.default_version
        if not version or version not in self.docs_dirs:
            return False
        state = "stale" if force else self._meta_state(version)
        if state == "valid":
            self._loaded_versions.add(version)
            return True
        if state == "stale" and not force:
            # Only warn when we rebuild unprompted (docs moved); a user-triggered
            # `changesource --force` rebuild needs no hint.
            print(
                f"警告: {version} 的文档索引与实际文档不一致，正在自动重建。"
                "若经常发生，可运行 `unity-docs-mcp changesource` 明确重建。",
                file=sys.stderr,
            )
        ok = self.build_index(version)
        if ok:
            self._loaded_versions.add(version)
        return ok

    def load_index(self, version: Optional[str] = None, force_refresh: bool = False) -> bool:
        """Compatibility shim for the old API; delegates to ensure_index."""
        return self.ensure_index(version, force=force_refresh)

    def build_index(self, version: str, progress_cb=None) -> bool:
        """Build the FTS5 index for one version (API + Manual)."""
        docs_dir = self.docs_dirs.get(version)
        if not docs_dir:
            return False

        script_ref = os.path.join(docs_dir, "ScriptReference")
        manual_dir = os.path.join(docs_dir, "Manual")

        api_pages, api_info = self._load_metadata_for(os.path.join(script_ref, "docdata"))
        if not api_pages:
            return False
        manual_pages, manual_info = self._load_metadata_for(os.path.join(manual_dir, "docdata"))

        class_names = self._compute_class_names(api_pages)

        api_total = len(api_pages)
        manual_total = len(manual_pages)
        total = api_total + manual_total

        db_path = self._db_path(version)
        tmp_path = db_path + ".tmp"
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

        conn = sqlite3.connect(tmp_path)
        try:
            self._create_schema(conn)
            chunk = 200
            done = 0

            # API reference rows.
            for start in range(0, api_total, chunk):
                chunk_rows = self._build_chunk(
                    conn, api_pages, api_info, script_ref, "api", class_names,
                    start, min(start + chunk, api_total), start_id=0,
                )
                self._insert_chunk(conn, chunk_rows)
                done = min(start + chunk, api_total)
                if progress_cb:
                    progress_cb(done, total)

            # Manual rows (id continues after the api ids).
            for start in range(0, manual_total, chunk):
                chunk_rows = self._build_chunk(
                    conn, manual_pages, manual_info, manual_dir, "manual", None,
                    start, min(start + chunk, manual_total), start_id=api_total,
                )
                self._insert_chunk(conn, chunk_rows)
                done = api_total + min(start + chunk, manual_total)
                if progress_cb:
                    progress_cb(done, total)

            conn.execute(
                "INSERT INTO meta (version, page_count, built_at, source_dir) "
                "VALUES (?,?,?,?)",
                (version, total, datetime.now().isoformat(), docs_dir),
            )
            conn.commit()
        finally:
            conn.close()

        os.replace(tmp_path, db_path)
        # Drop the cached connection so subsequent queries see the new db.
        self._conns.pop(version, None)
        return True

    def _insert_chunk(self, conn, chunk_rows) -> None:
        conn.executemany(
            "INSERT INTO pages (id, name, title, description, member_type, path, kind) "
            "VALUES (?,?,?,?,?,?,?)",
            chunk_rows["pages"],
        )
        conn.executemany(
            "INSERT INTO ft (rowid, name, title, description, content) "
            "VALUES (?,?,?,?,?)",
            chunk_rows["ft"],
        )
        conn.commit()

    def _build_chunk(self, conn, pages, info, base_dir, kind, class_names,
                     start, end, start_id=0):
        """Extract body text for a slice of pages in parallel and return insert rows."""
        names = []
        for i in range(start, end):
            name = pages[i][0]
            if len(pages[i]) > 1 and pages[i][1]:
                title = pages[i][1]
            else:
                title = name
            names.append((i, name, title))

        texts = {}
        with ThreadPoolExecutor(max_workers=8) as ex:
            futures = {
                ex.submit(self._extract_body_text, os.path.join(base_dir, name + ".html")): i
                for i, name, _title in names
            }
            for future in as_completed(futures):
                texts[futures[future]] = future.result()

        page_rows = []
        ft_rows = []
        for i, name, title in names:
            description = ""
            if i < len(info) and info[i]:
                description = info[i][0]
            if kind == "manual":
                member_type = "manual"
            else:
                member_type = self._detect_member_type(name, class_names)
            path = os.path.join(base_dir, name + ".html")
            row_id = start_id + i
            page_rows.append((row_id, name, title, description, member_type, path, kind))
            ft_rows.append((row_id, name, title, description, texts.get(i, "")))
        return {"pages": page_rows, "ft": ft_rows}

    def _create_schema(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            "CREATE TABLE meta (version TEXT, page_count INT, built_at TEXT, "
            "source_dir TEXT)"
        )
        conn.execute(
            "CREATE TABLE pages (id INT PRIMARY KEY, name TEXT, title TEXT, "
            "description TEXT, member_type TEXT, path TEXT, kind TEXT)"
        )
        conn.execute(
            "CREATE VIRTUAL TABLE ft USING fts5(name, title, description, content)"
        )

    def _load_metadata_for(self, docdata_dir: str) -> Tuple[List, List]:
        """Return (pages, info) parsed from a docdata directory (index.json, then index.js)."""
        index_json = os.path.join(docdata_dir, "index.json")
        if os.path.exists(index_json):
            try:
                with open(index_json, encoding="utf-8") as f:
                    data = json.load(f)
                pages = data.get("pages") or []
                info = data.get("info") or []
                if pages:
                    return pages, info
            except (json.JSONDecodeError, OSError):
                pass
        index_js = os.path.join(docdata_dir, "index.js")
        if os.path.exists(index_js):
            try:
                return self._parse_index_js(index_js)
            except (json.JSONDecodeError, OSError):
                pass
        return [], []

    def _parse_index_js(self, path: str) -> Tuple[List, List]:
        """Line-by-line parser for Unity's four-variable index.js (pages/info/common/searchIndex)."""
        with open(path, encoding="utf-8", errors="ignore") as f:
            lines = f.read().split("\n")
        pages = []
        info = []
        current_var = None
        current_content = []

        def flush_pages():
            nonlocal pages
            if current_content:
                pages = json.loads("".join(current_content).strip().rstrip(";"))

        def flush_info():
            nonlocal info
            if current_content:
                info = json.loads("".join(current_content).strip().rstrip(";"))

        for line in lines:
            if line.startswith("var pages = "):
                flush_pages()
                current_var = "pages"
                current_content = []
            elif line.startswith("var info = "):
                flush_pages()
                current_var = "info"
                current_content = []
            elif line.startswith("var common = "):
                flush_info()
                current_var = "common"
                current_content = []
            elif line.startswith("var searchIndex = "):
                flush_info()
                current_var = "searchIndex"
                current_content = []
            elif current_var:
                current_content.append(line)
        # Handle a trailing variable (pages/info come before common/searchIndex,
        # so this only matters for the final searchIndex which we ignore).
        return pages, info

    def _extract_body_text(self, path: str) -> str:
        """Lightweight body text extraction for indexing (no trafilatura)."""
        try:
            with open(path, encoding="utf-8", errors="ignore") as f:
                html = f.read()
        except OSError:
            return ""
        try:
            soup = BeautifulSoup(html, "html.parser")
            content = soup.select_one("#content-wrap") or soup.select_one(
                "#content-wrap .content"
            ) or soup
            text = content.get_text(separator=" ", strip=True)
            return re.sub(r"\s+", " ", text).strip()
        except Exception:
            return ""

    # ------------------------------------------------------------------ member type

    @staticmethod
    def _compute_class_names(pages: List) -> set:
        """Collect every page name that is a class (incl. namespaced classes).

        Seeds with bare names (no dot / no hyphen). A dotted name whose base
        is NOT a known class is a namespaced class (e.g. AI.NavMeshAgent);
        propagate until a fixed point.
        """
        class_names = {n[0] for n in pages if "." not in n[0] and "-" not in n[0]}
        changed = True
        while changed:
            changed = False
            for n in pages:
                name = n[0]
                if "." not in name or "-" in name or name in class_names:
                    continue
                base = name.rsplit(".", 1)[0]
                if base not in class_names:
                    class_names.add(name)
                    changed = True
        return class_names

    def _detect_member_type(self, url_name: str, class_names: set) -> str:
        """Detect whether an API entry is a property, method, constructor, or class.

        - ``Class-prop`` (hyphen) -> property; ``Class-ctor`` -> constructor
        - bare name -> class
        - dotted name whose base is a known class -> method (e.g. Object.GetInstanceID)
        - dotted name whose base is a namespace -> class (e.g. AI.NavMeshAgent)
        """
        if "-ctor" in url_name:
            return "constructor"
        if "-" in url_name:
            return "property"
        if "." not in url_name:
            return "class"
        if url_name.rsplit(".", 1)[0] in class_names:
            return "method"
        return "class"

    # ------------------------------------------------------------------ query

    def _fts_query(self, query: str) -> Optional[str]:
        """Build a safe FTS5 MATCH expression (space-separated quoted words = AND)."""
        words = re.findall(r"[\w.]+", query.lower())
        if not words:
            return None
        return " ".join('"{}"'.format(w) for w in words)

    def search(self, query: str, version: Optional[str] = None, max_results: int = 20,
               kind: Optional[str] = None) -> List[Dict[str, str]]:
        """Search the local index using FTS5 + BM25, with class-name boosting.

        ``kind`` restricts results to 'api' or 'manual' pages; None = both.
        """
        version = version or self.default_version
        if not self.ensure_index(version):
            return []

        match_query = self._fts_query(query)
        if not match_query:
            return []

        conn = self._connect(version)
        if kind:
            sql = (
                "SELECT p.id, p.name, p.title, p.description, p.member_type, p.path, bm25(ft) "
                "FROM ft JOIN pages p ON p.id = ft.rowid "
                "WHERE ft MATCH ? AND p.kind = ? ORDER BY bm25(ft) LIMIT 500"
            )
            rows = conn.execute(sql, (match_query, kind)).fetchall()
        else:
            sql = (
                "SELECT p.id, p.name, p.title, p.description, p.member_type, p.path, bm25(ft) "
                "FROM ft JOIN pages p ON p.id = ft.rowid "
                "WHERE ft MATCH ? ORDER BY bm25(ft) LIMIT 500"
            )
            rows = conn.execute(sql, (match_query,)).fetchall()

        q_lower = query.strip().lower()
        scored = []
        for row in rows:
            name = row["name"]
            title = row["title"]
            member_type = row["member_type"]
            score = 0.0
            name_lower = name.lower()
            if name_lower == q_lower:
                score += 1_000_000
            if member_type == "class" and name_lower.rsplit(".", 1)[-1] == q_lower:
                score += 500_000
            if name_lower.startswith(q_lower):
                score += 200_000
            if member_type in ("class", "manual"):
                score += 1_000
            scored.append((score, row))

        scored.sort(key=lambda item: item[0], reverse=True)
        results = []
        for _score, row in scored[:max_results]:
            description = row["description"] or ""
            if len(description) > 200:
                description = description[:200] + "..."
            path = row["path"].replace(os.sep, "/")
            results.append(
                {
                    "name": row["name"],
                    "title": row["title"],
                    "url": path,
                    "path": path,
                    "description": description,
                    "type": row["member_type"],
                }
            )
        return results

    def suggest_classes(self, partial_name: str, max_results: int = 10) -> List[str]:
        """Suggest class names matching a partial input (substring match)."""
        version = self.default_version
        if not self.ensure_index(version):
            return []
        partial = partial_name.strip()
        if not partial:
            return []
        conn = self._connect(version)
        rows = conn.execute(
            "SELECT DISTINCT title FROM pages "
            "WHERE member_type = 'class' AND (name LIKE ? OR title LIKE ?) "
            "ORDER BY title LIMIT ?",
            ("%" + partial + "%", "%" + partial + "%", max_results),
        ).fetchall()
        return [row["title"] for row in rows]

    def get_page_name(self, query: str, version: Optional[str] = None) -> Optional[str]:
        """Resolve a class or member name to its full API page name
        (e.g. 'NavMeshAgent' -> 'AI.NavMeshAgent', 'SetActive' -> 'GameObject.SetActive')."""
        version = version or self.default_version
        if not self.ensure_index(version):
            return None
        query = query.strip()
        if not query:
            return None
        conn = self._connect(version)
        row = conn.execute(
            "SELECT name FROM pages WHERE kind = 'api' AND (name = ? "
            "OR name LIKE ?) "
            "ORDER BY CASE WHEN name = ? THEN 0 ELSE 1 END, LENGTH(name) LIMIT 1",
            (query, "%" + query, query),
        ).fetchone()
        return row["name"] if row else None

    def get_manual_page(self, page_query: str, version: Optional[str] = None) -> Optional[Tuple[str, str, str]]:
        """Resolve a manual page (slug, name, or title prefix) to (name, title, path)."""
        version = version or self.default_version
        if not self.ensure_index(version):
            return None
        query = page_query.strip().lower()
        if not query:
            return None
        conn = self._connect(version)
        rows = conn.execute(
            "SELECT name, title, path FROM pages WHERE kind = 'manual'",
        ).fetchall()
        best = None
        best_rank = 4  # 0=exact name, 1=exact title, 2=name prefix, 3=title prefix
        for row in rows:
            name_l = row["name"].lower()
            title_l = row["title"].lower()
            if name_l == query:
                rank = 0
            elif title_l == query:
                rank = 1
            elif name_l.startswith(query):
                rank = 2
            elif title_l.startswith(query):
                rank = 3
            else:
                continue
            if rank < best_rank:
                best, best_rank = row, rank
        if best is None:
            return None
        return best["name"], best["title"], best["path"]

    def clear_cache(self, version: Optional[str] = None) -> None:
        """Delete the search database for one version or all versions."""
        if version:
            conn = self._conns.pop(version, None)
            if conn is not None:
                conn.close()
            path = self._db_path(version)
            if os.path.exists(path):
                os.remove(path)
            self._loaded_versions.discard(version)
        else:
            for entry in os.listdir(self.db_dir):
                if entry.startswith("search_") and entry.endswith(".db"):
                    os.remove(os.path.join(self.db_dir, entry))
            self._loaded_versions.clear()
            self._conns.clear()

    def close(self) -> None:
        """Close all open SQLite connections (releases file locks on Windows)."""
        for conn in self._conns.values():
            conn.close()
        self._conns.clear()
        self._loaded_versions.clear()
