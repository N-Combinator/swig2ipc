"""Generates the file set for a KiCad IPC API plugin.

Field names follow KiCad's add-on developer documentation and the plugin schema
shipped with kicad-python (``kipy/packaging/schemas/api.v1.schema.json``):
https://dev-docs.kicad.org/en/apis-and-binding/ipc-api/for-addon-developers/
"""

from __future__ import annotations

import json
import re
from pathlib import Path

#: Identifier patterns taken verbatim from KiCad's plugin schema (api.v1).
PLUGIN_IDENTIFIER_RE = re.compile(r"^[a-zA-Z][-_a-zA-Z0-9.]{0,98}[a-zA-Z0-9]$")
ACTION_IDENTIFIER_RE = re.compile(r"^[a-zA-Z][-_a-zA-Z0-9.]{0,48}[a-zA-Z0-9]$")

DEFAULT_ENTRYPOINT = "main.py"
DEFAULT_ACTION_IDENTIFIER = "run"
REQUIREMENTS = "kicad-python\n"


class SkeletonError(Exception):
    """Raised for invalid input or files that already exist."""


def build_manifest(
    *,
    name: str,
    identifier: str,
    description: str | None = None,
    entrypoint: str = DEFAULT_ENTRYPOINT,
    action_identifier: str = DEFAULT_ACTION_IDENTIFIER,
) -> dict:
    """Build the ``plugin.json`` content for a single-action PCB plugin."""
    if not name.strip():
        raise SkeletonError("--name must not be empty")
    if not PLUGIN_IDENTIFIER_RE.match(identifier):
        raise SkeletonError(
            f"invalid plugin identifier {identifier!r}: KiCad requires a reverse-DNS style "
            "identifier matching ^[a-zA-Z][-_a-zA-Z0-9.]{0,98}[a-zA-Z0-9]$"
        )
    if not ACTION_IDENTIFIER_RE.match(action_identifier):
        raise SkeletonError(
            f"invalid action identifier {action_identifier!r}: KiCad requires "
            "^[a-zA-Z][-_a-zA-Z0-9.]{0,48}[a-zA-Z0-9]$"
        )
    return {
        "identifier": identifier,
        "name": name,
        "description": description or f"{name}, a KiCad IPC API plugin.",
        "runtime": {"type": "python", "min_version": "3.9"},
        "actions": [
            {
                "identifier": action_identifier,
                "name": name,
                "description": f"Run {name}.",
                "show-button": True,
                "entrypoint": entrypoint,
                "scopes": ["pcb"],
            }
        ],
    }


def write_skeleton(
    out_dir: Path,
    *,
    name: str,
    identifier: str,
    description: str | None = None,
    entrypoint: str = DEFAULT_ENTRYPOINT,
    action_identifier: str = DEFAULT_ACTION_IDENTIFIER,
) -> list[Path]:
    """Write ``plugin.json`` and ``requirements.txt`` into ``out_dir``.

    Never overwrites: if either file exists, nothing is written.
    """
    manifest = build_manifest(
        name=name,
        identifier=identifier,
        description=description,
        entrypoint=entrypoint,
        action_identifier=action_identifier,
    )
    out_dir = Path(out_dir)
    files = {
        out_dir / "plugin.json": json.dumps(manifest, indent=2) + "\n",
        out_dir / "requirements.txt": REQUIREMENTS,
    }
    existing = [path for path in files if path.exists()]
    if existing:
        raise SkeletonError(
            "refusing to overwrite: " + ", ".join(str(path) for path in sorted(existing))
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    for path, content in files.items():
        path.write_text(content, encoding="utf-8")
    return sorted(files)
