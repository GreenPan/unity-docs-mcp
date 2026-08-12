"""Local Unity documentation reader (fully offline).

Replaces the old web scraper: instead of HTTP requests to docs.unity3d.com, it
reads the offline documentation bundled with a locally installed Unity editor.
The server serves exactly one version, chosen from the ``UNITY_DOCS_VERSION``
env var; the docs directory is recovered from the built db's meta.source_dir.
"""

import os
from typing import Any, Dict, List, Optional

from .search_index import UnitySearchIndex, list_built_versions, read_db_source_dir
from .version_resolver import (
    InstalledVersion,
    normalize_to_major_minor,
    parse_unity_version,
    resolve_version,
)


class UnityDocScraper:
    """Read Unity API documentation for one locally installed version."""

    def __init__(self, docs_dir: Optional[str] = None, version: Optional[str] = None,
                 search_index: Optional[UnitySearchIndex] = None, db_dir: Optional[str] = None):
        self.version = version or os.environ.get("UNITY_DOCS_VERSION")

        if docs_dir is None:
            # Recover the docs dir from the built db for the selected version.
            if db_dir is None:
                db_dir = UnitySearchIndex().db_dir
            if not self.version:
                versions = list_built_versions(db_dir)
                self.version = versions[0] if versions else None
            if self.version:
                docs_dir = read_db_source_dir(db_dir, self.version)

        self.docs_dirs = {}
        if docs_dir and self.version:
            self.docs_dirs[self.version] = docs_dir

        installed = []
        if self.version and self.version in self.docs_dirs:
            version_key = parse_unity_version(self.version)
            if version_key is not None:
                installed.append(
                    InstalledVersion(
                        name=self.version,
                        editor_dir=docs_dir,  # not used for single-version serving
                        docs_dir=docs_dir,
                        version_key=version_key,
                    )
                )
        self.installed = installed

        self.search_index = search_index or UnitySearchIndex(docs_dirs=self.docs_dirs)

        # API availability cache (in-memory only; per-install docs are static).
        self._api_cache: Dict[str, Dict[str, List[str]]] = {}

    def resolve_version(self, version: Optional[str]):
        """Resolve a user-supplied version against the served version."""
        return resolve_version(version, self.installed)

    # ------------------------------------------------------------------ paths

    def _build_local_path(
        self,
        class_name: str,
        method_name: Optional[str],
        version: str,
        use_hyphen: bool = False,
    ) -> Optional[str]:
        """Build the local absolute path to a documentation HTML file."""
        resolved = self.resolve_version(version)
        if resolved is None:
            return None
        docs_dir = resolved.docs_dir
        script_ref = os.path.join(docs_dir, "ScriptReference")

        class_name = class_name.strip()
        if method_name:
            method_name = method_name.strip()
            if use_hyphen:
                page_name = f"{class_name}-{method_name}.html"
            else:
                page_name = f"{class_name}.{method_name}.html"
        else:
            page_name = f"{class_name}.html"

        return os.path.join(script_ref, page_name)

    def _read_page(self, path: str) -> Optional[str]:
        """Read an HTML file, returning its text or None if missing."""
        if not path:
            return None
        try:
            norm = os.path.normpath(path)
            with open(norm, encoding="utf-8", errors="ignore") as f:
                return f.read()
        except OSError:
            return None

    # ------------------------------------------------------------------ versions

    def get_supported_versions(self) -> List[str]:
        """List installed Unity versions, newest first."""
        return [v.name for v in self.installed]

    def get_latest_version(self) -> str:
        """Return the newest installed version."""
        return self.installed[0].name if self.installed else ""

    def normalize_version(self, version: str) -> str:
        """Normalize a version string to major.minor form."""
        return normalize_to_major_minor(version)

    def validate_version(self, version: str) -> bool:
        """True if the version resolves to an installed version."""
        return self.resolve_version(version) is not None

    # ------------------------------------------------------------------ lookup

    def get_api_doc(
        self,
        class_name: str,
        method_name: Optional[str] = None,
        version: Optional[str] = None,
        member_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Read Unity API documentation for a specific class or method."""
        resolved = self.resolve_version(version)
        if resolved is None:
            installed = ", ".join(self.get_supported_versions()) or "none"
            requested = version or "latest"
            return {
                "status": "error",
                "error": (
                    f"Unsupported Unity version '{requested}'. "
                    f"Installed versions: {installed}"
                ),
            }

        version_name = resolved.name
        try:
            actual_class_name = self._find_class_name(class_name, version_name)
        except Exception:
            actual_class_name = class_name

        if method_name:
            if member_type:
                use_hyphen = member_type in ("property", "constructor")
                path = self._build_local_path(
                    actual_class_name, method_name, version_name, use_hyphen=use_hyphen
                )
                html = self._read_page(path)
                if html:
                    return {"url": path, "html": html, "status": "success"}
            else:
                # Try dot notation first, then hyphen.
                for use_hyphen in (False, True):
                    path = self._build_local_path(
                        actual_class_name, method_name, version_name, use_hyphen=use_hyphen
                    )
                    html = self._read_page(path)
                    if html:
                        return {"url": path, "html": html, "status": "success"}
            return {
                "status": "error",
                "error": f"'{class_name}.{method_name}' not found in Unity {version_name} documentation.",
            }

        path = self._build_local_path(actual_class_name, None, version_name)
        html = self._read_page(path)
        if html:
            return {"url": path, "html": html, "status": "success"}
        return {
            "status": "error",
            "error": f"'{class_name}' not found in Unity {version_name} documentation.",
        }

    def _find_class_name(self, class_name: str, version: str) -> str:
        """Resolve a class name to its namespaced page name, if known."""
        found = self.search_index.get_page_name(class_name, version)
        return found if found else class_name

    def search_docs(self, query: str, version: Optional[str] = None) -> Dict[str, Any]:
        """Search the API reference using the local FTS5 index.

        An uninstalled requested version falls back to the newest installed.
        """
        resolved = self.resolve_version(version) or self.resolve_version(None)
        if resolved is None:
            return {
                "status": "error",
                "error": "No local Unity documentation found.",
            }
        try:
            results = self.search_index.search(query, resolved.name, kind="api")
            return {"results": results, "count": len(results), "status": "success"}
        except Exception as e:
            return {"error": f"Error searching docs: {str(e)}", "status": "error"}

    def get_manual_doc(self, page_query: str, version: Optional[str] = None) -> Dict[str, Any]:
        """Read a manual page, or fall back to a manual search.

        Returns ``{'status': 'success', url, html, title}`` when the page query
        resolves to a concrete manual page, or ``{'status': 'search', query,
        results, count}`` when it falls back to a manual search.
        """
        resolved = self.resolve_version(version) or self.resolve_version(None)
        if resolved is None:
            return {
                "status": "error",
                "error": "No local Unity documentation found.",
            }
        try:
            page = self.search_index.get_manual_page(page_query, resolved.name)
            if page:
                name, title, path = page
                html = self._read_page(path)
                if html:
                    return {
                        "status": "success",
                        "url": path,
                        "html": html,
                        "title": title,
                    }
            results = self.search_index.search(page_query, resolved.name, kind="manual")
            return {
                "status": "search",
                "query": page_query,
                "results": results,
                "count": len(results),
            }
        except Exception as e:
            return {"error": f"Error fetching manual doc: {str(e)}", "status": "error"}

    def suggest_class_names(self, partial_name: str) -> List[str]:
        """Suggest Unity class names based on partial input."""
        suggestions = self.search_index.suggest_classes(partial_name)
        return suggestions[:10]

    # ------------------------------------------------------------------ availability

    def check_api_availability_across_versions(
        self, class_name: str, method_name: Optional[str] = None
    ) -> Dict[str, List[str]]:
        """Check which installed versions have the API (local file existence)."""
        cache_key = f"{class_name}.{method_name}" if method_name else class_name
        if cache_key in self._api_cache:
            return self._api_cache[cache_key]

        available, unavailable = [], []
        for v in self.installed:
            actual = self._find_class_name(class_name, v.name)
            if method_name:
                path = self._build_local_path(actual, method_name, v.name)
                exists = self._read_page(path) is not None
                if not exists:
                    path = self._build_local_path(actual, method_name, v.name, use_hyphen=True)
                    exists = self._read_page(path) is not None
            else:
                path = self._build_local_path(actual, None, v.name)
                exists = self._read_page(path) is not None
            (available if exists else unavailable).append(v.name)

        result = {"available": available, "unavailable": unavailable}
        self._api_cache[cache_key] = result
        return result
