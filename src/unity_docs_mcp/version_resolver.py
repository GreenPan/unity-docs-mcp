"""Unity version resolution for locally installed editor documentation."""

import os
import re
import sys
from dataclasses import dataclass
from typing import List, Optional, Tuple

# Unity version dir names: 6000.5.7f1, 2022.3.45f1, 2022.3.0b12, 2021.3.0rc2, 2019.4.0f1c2
_UNITY_VERSION_RE = re.compile(
    r"^(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)"
    r"(?P<type>a|b|f|rc)(?P<build>\d+)"
    r"(?:c(?P<revision>\d+))?$",
    re.IGNORECASE,
)

# alpha < beta < release candidate < final
_TYPE_RANK = {"a": 0, "b": 1, "rc": 2, "f": 3}

VersionKey = Tuple[int, int, int, int, int, int]


@dataclass(frozen=True)
class InstalledVersion:
    """A Unity editor installation with a local documentation tree."""

    name: str  # e.g. "6000.5.7f1"
    editor_dir: str  # absolute path to the version directory under the Hub Editor root
    docs_dir: str  # absolute path to the Documentation/en directory
    version_key: VersionKey  # sortable tuple; higher = newer


def parse_unity_version(name: str) -> Optional[VersionKey]:
    """Parse a version dir name into a sortable key, or None if not a version.

    ``6000.5.7f1`` -> ``(6000, 5, 7, 3, 1, 0)`` (type_rank: a=0, b=1, rc=2, f=3).
    """
    match = _UNITY_VERSION_RE.match(name.strip())
    if not match:
        return None
    groups = match.groupdict()
    return (
        int(groups["major"]),
        int(groups["minor"]),
        int(groups["patch"]),
        _TYPE_RANK[groups["type"].lower()],
        int(groups["build"]),
        int(groups["revision"] or 0),
    )


def normalize_to_major_minor(name: str) -> str:
    """Reduce a version string to major.minor form, e.g. ``6000.0.29f1`` -> ``6000.0``."""
    if not name:
        return name
    version = name.strip()
    lowered = version.lower()
    if lowered.startswith("unity "):
        version = version[6:]
    elif lowered.startswith("v"):
        version = version[1:]
    match = re.match(r"^(\d+\.\d+)", version)
    return match.group(1) if match else version


def find_docs_dir(editor_dir: str) -> Optional[str]:
    """Return the Documentation/en dir inside an editor install, or None."""
    candidates = (
        os.path.join(editor_dir, "Editor", "Data", "Documentation", "en"),  # Windows / Linux
        os.path.join(editor_dir, "Unity.app", "Contents", "Documentation", "en"),  # macOS
    )
    for candidate in candidates:
        if os.path.isdir(os.path.join(candidate, "ScriptReference")):
            return candidate
    return None


def discover_versions(editor_root: str) -> List[InstalledVersion]:
    """List installed Unity versions under a Hub Editor root, newest first.

    A directory only counts when its name parses as a Unity version AND it
    contains a local ScriptReference documentation tree.
    """
    if not editor_root or not os.path.isdir(editor_root):
        return []
    installed: List[InstalledVersion] = []
    for entry in sorted(os.listdir(editor_root)):
        editor_dir = os.path.join(editor_root, entry)
        if not os.path.isdir(editor_dir):
            continue
        version_key = parse_unity_version(entry)
        if version_key is None:
            continue
        docs_dir = find_docs_dir(editor_dir)
        if docs_dir is None:
            continue
        installed.append(
            InstalledVersion(
                name=entry,
                editor_dir=editor_dir,
                docs_dir=docs_dir,
                version_key=version_key,
            )
        )
    installed.sort(key=lambda v: v.version_key, reverse=True)
    return installed


def resolve_version(
    version: Optional[str], installed: List[InstalledVersion]
) -> Optional[InstalledVersion]:
    """Resolve a user-supplied version against installed versions.

    - ``None`` / empty -> newest installed (installed is newest-first)
    - exact name match (case-insensitive) -> that install
    - prefix match (``6000`` / ``6000.5`` / ``6000.5.7`` match ``6000.5.7f1``) ->
      newest install with that prefix
    - otherwise -> ``None`` (not installed)
    """
    if not installed:
        return None
    if version is None or not str(version).strip():
        return installed[0]

    needle = str(version).strip()
    needle_lower = needle.lower()

    for v in installed:
        if v.name.lower() == needle_lower:
            return v

    matches = [v for v in installed if v.name.lower().startswith(needle_lower)]
    if not matches:
        # Tolerate "Unity 6000.5" / "v6000.5" style input.
        normalized = normalize_to_major_minor(needle)
        if normalized != needle:
            matches = [
                v for v in installed if v.name.lower().startswith(normalized.lower())
            ]
    if not matches:
        return None
    matches.sort(key=lambda v: v.version_key, reverse=True)
    return matches[0]


def default_editor_root() -> Optional[str]:
    """Return the platform default Unity Hub Editor root if it exists."""
    if sys.platform.startswith("win"):
        candidate = r"C:\Program Files\Unity\Hub\Editor"
    elif sys.platform == "darwin":
        candidate = "/Applications/Unity/Hub/Editor"
    else:
        candidate = os.path.expanduser("~/Unity/Hub/Editor")
    return candidate if os.path.isdir(candidate) else None
