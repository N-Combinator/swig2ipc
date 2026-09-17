"""Checks every mapping entry against the real kicad-python package.

Resolving each non-null ``ipc`` dotted path is what keeps a `mapped`/`partial`
claim from silently rotting into a lie. kicad-python is a test-only dependency
(the ``dev`` extra); swig2ipc itself never imports it.
"""

from __future__ import annotations

import importlib
from importlib.metadata import version

import pytest

from swig2ipc import mapping

pytest.importorskip(
    "kipy", reason="install the dev extra (kicad-python) to verify the mapping table"
)

ENTRIES = mapping.entries()
IPC_PATHS = sorted(
    (symbol, entry["ipc"]) for symbol, entry in ENTRIES.items() if entry["ipc"] is not None
)


def resolve(path: str):
    """Import the longest importable module prefix, then walk attributes."""
    parts = path.split(".")
    module = None
    index = len(parts)
    while index > 0:
        try:
            module = importlib.import_module(".".join(parts[:index]))
            break
        except ImportError:
            index -= 1
    assert module is not None, f"no importable module in {path}"
    obj = module
    for attribute in parts[index:]:
        obj = getattr(obj, attribute)
    return obj


def test_installed_kicad_python_matches_meta():
    assert version("kicad-python") == mapping.meta()["kicad_python_version"]


def test_every_mapped_or_partial_entry_is_checked():
    checked = {symbol for symbol, _ in IPC_PATHS}
    claimed = {
        symbol
        for symbol, entry in ENTRIES.items()
        if entry["status"] in (mapping.STATUS_MAPPED, mapping.STATUS_PARTIAL)
    }
    assert claimed - checked == set(), "mapped/partial entries must name an ipc path"


@pytest.mark.parametrize(("symbol", "path"), IPC_PATHS, ids=[s for s, _ in IPC_PATHS])
def test_ipc_path_resolves(symbol: str, path: str):
    assert resolve(path) is not None
