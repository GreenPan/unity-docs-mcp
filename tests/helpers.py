"""Shared test helpers: build a fake local Unity docs tree on disk.

The tree mirrors what Unity Hub produces:
  {root}/{version}/Editor/Data/Documentation/en/ScriptReference/*.html
  {root}/{version}/Editor/Data/Documentation/en/ScriptReference/docdata/index.json
  {root}/{version}/Editor/Data/Documentation/en/Manual/{slug}.html
  {root}/{version}/Editor/Data/Documentation/en/Manual/docdata/index.json
"""

import json
import os

DEFAULT_PAGES = [
    {
        "name": "GameObject",
        "title": "GameObject",
        "description": "Base class for all entities in Unity Scenes.",
        "body": (
            "<p>GameObject is the fundamental object in Unity that represents "
            "characters, props and scenery.</p>"
        ),
    },
    {
        "name": "GameObject.SetActive",
        "title": "GameObject.SetActive",
        "description": "Activates/Deactivates the GameObject.",
        "body": "<p>Set a GameObject active or inactive.</p>",
    },
    {
        "name": "Transform",
        "title": "Transform",
        "description": "Position, rotation and scale of an object.",
        "body": "<p>The Transform component determines the position and rotation of a GameObject.</p>",
    },
    {
        "name": "Transform.position",
        "title": "Transform.position",
        "description": "The world space position of the Transform.",
        "body": "<p>Gets or sets the world space position of the Transform.</p>",
    },
    {
        "name": "Vector3",
        "title": "Vector3",
        "description": "Representation of 3D vectors and points.",
        "body": "<p>Vector3 represents a point or vector in 3D space.</p>",
    },
    {
        "name": "AI.NavMeshAgent",
        "title": "AI.NavMeshAgent",
        "description": "Navigation mesh agent for pathfinding.",
        "body": "<p>NavMeshAgent moves the character towards a destination.</p>",
    },
    {
        "name": "Object",
        "title": "Object",
        "description": "Base class for all objects Unity can reference.",
        "body": "<p>Object is the base class for all built-in Unity objects.</p>",
    },
    {
        "name": "Object.GetInstanceID",
        "title": "Object.GetInstanceID",
        "description": "Gets the instance ID of the object.",
        "body": "<p>Returns a unique instance ID for the object.</p>",
    },
    {
        "name": "Object-transform",
        "title": "Object.transform",
        "description": "The Transform attached to this GameObject.",
        "body": "<p>The Transform attached to the same GameObject as this component.</p>",
    },
    {
        "name": "Object-ctor",
        "title": "Object.Object",
        "description": "Creates a new Object.",
        "body": "<p>Creates a new instance of a scriptable object.</p>",
    },
]

DEFAULT_MANUAL_PAGES = [
    {
        "name": "urp/urp-introduction",
        "title": "Universal Render Pipeline introduction",
        "description": "Overview of the Universal Render Pipeline (URP).",
        "body": "<p>URP is a Scriptable Render Pipeline built for performance and scalability.</p>",
    },
    {
        "name": "navigation-and-pathfinding",
        "title": "Navigation and Pathfinding",
        "description": "Use NavMesh to give characters the ability to navigate the game world.",
        "body": "<p>Unity provides a navigation system to let characters move intelligently.</p>",
    },
    {
        "name": "2d-game-creation-wokflow",
        "title": "2D game creation workflow",
        "description": "Overview of creating 2D games in Unity.",
        "body": "<p>This section describes the 2D game creation workflow in Unity.</p>",
    },
]


def _index_json(pages, common_words=None):
    names = [p["name"] for p in pages]
    return {
        "pages": [[p["name"], p["title"]] for p in pages],
        "info": [[p["description"], i] for i, p in enumerate(pages)],
        "common": {w: 1 for w in (common_words or [])},
        "searchIndex": {
            word: [i for i, name in enumerate(names) if word in name.lower()]
            for word in {"gameobject", "setactive", "transform", "position", "vector3", "navmeshagent", "class"}
        },
    }


def _write_pages(base_dir, pages):
    """Write a set of pages (HTML + docdata/index.json) under base_dir."""
    os.makedirs(os.path.join(base_dir, "docdata"), exist_ok=True)
    for page in pages:
        body = page.get("body", "")
        html = (
            "<html><head><title>{title}</title></head><body>"
            '<h1 class="heading inherit">{title}</h1>'
            '<div id="content-wrap"><div class="content">{body}</div></div>'
            "</body></html>"
        ).format(title=page["title"], body=body)
        target = os.path.join(base_dir, page["name"] + ".html")
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            f.write(html)
    with open(os.path.join(base_dir, "docdata", "index.json"), "w", encoding="utf-8") as f:
        json.dump(_index_json(pages), f)


def make_fake_unity_install(root, versions, pages=None, manual_pages=None):
    """Create a fake Unity docs tree under ``root`` for each version in ``versions``.

    Returns the editor_root and the list of {version, docs_dir} dirs created.
    """
    pages = pages if pages is not None else DEFAULT_PAGES
    manual_pages = manual_pages if manual_pages is not None else DEFAULT_MANUAL_PAGES
    created = []
    for version in versions:
        docs_dir = os.path.join(
            root, version, "Editor", "Data", "Documentation", "en", "ScriptReference"
        )
        _write_pages(docs_dir, pages)
        manual_dir = os.path.join(root, version, "Editor", "Data", "Documentation", "en", "Manual")
        _write_pages(manual_dir, manual_pages)
        created.append({"version": version, "docs_dir": os.path.dirname(docs_dir)})
    return root, created
