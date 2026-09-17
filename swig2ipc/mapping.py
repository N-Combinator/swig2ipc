"""Access to the packaged SWIG -> IPC mapping table."""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from typing import Any

STATUS_MAPPED = "mapped"
STATUS_PARTIAL = "partial"
STATUS_UNMAPPED = "unmapped"
STATUS_UNKNOWN = "unknown"

#: Statuses that may appear in the packaged table (``unknown`` never does: it is
#: what the report assigns to a symbol the table does not cover).
TABLE_STATUSES = (STATUS_MAPPED, STATUS_PARTIAL, STATUS_UNMAPPED)

#: Order used for summary counts and report sections.
ALL_STATUSES = (STATUS_MAPPED, STATUS_PARTIAL, STATUS_UNMAPPED, STATUS_UNKNOWN)

UNKNOWN_NOTE = "Not in the swig2ipc mapping table; check the kicad-python docs by hand."


@lru_cache(maxsize=1)
def load_table() -> dict[str, Any]:
    """Return the raw packaged mapping table, including its ``_meta`` block."""
    text = resources.files("swig2ipc.data").joinpath("mapping.json").read_text(encoding="utf-8")
    return json.loads(text)


def meta() -> dict[str, Any]:
    return dict(load_table()["_meta"])


def entries() -> dict[str, dict[str, Any]]:
    """The mapping entries, without ``_meta``."""
    return {k: v for k, v in load_table().items() if k != "_meta"}


def lookup(symbol: str) -> dict[str, Any]:
    """Return the entry for ``symbol``; symbols absent from the table are ``unknown``."""
    entry = entries().get(symbol)
    if entry is None:
        return {
            "status": STATUS_UNKNOWN,
            "ipc": None,
            "note": UNKNOWN_NOTE,
            "source_url": None,
        }
    return dict(entry)
