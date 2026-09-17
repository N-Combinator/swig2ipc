"""Checks every mapping entry against the real kicad-python package.

Resolving each non-null ``ipc`` dotted path is what keeps a `mapped`/`partial`
claim from silently rotting into a lie. kicad-python is a test-only dependency
(the ``dev`` extra); swig2ipc itself never imports it.
"""

from __future__ import annotations

import importlib
from importlib.metadata import version
from pathlib import Path

import pytest

from swig2ipc import mapping

pytest.importorskip(
    "kipy", reason="install the dev extra (kicad-python) to verify the mapping table"
)

ENTRIES = mapping.entries()

#: Prefix of a source_url pointing into the kicad-python repository.
SOURCE_PREFIX = "https://gitlab.com/kicad/code/kicad-python/-/blob/"

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


@pytest.mark.parametrize("symbol", sorted(ENTRIES))
def test_source_url_points_at_a_file_that_exists(symbol: str):
    """A source_url into kicad-python must name a file the package really ships.

    Checked against the installed package rather than over the network, so a link
    that rotted (or that never existed at the pinned ref) fails CI offline.
    """
    url = ENTRIES[symbol]["source_url"]
    if not url.startswith(SOURCE_PREFIX):
        pytest.skip("documentation URL, not a kicad-python source file")
    ref, _, relpath = url[len(SOURCE_PREFIX) :].partition("/")
    assert ref == mapping.meta()["kicad_python_version"], f"{symbol}: unpinned source_url"
    site_packages = Path(importlib.import_module("kipy").__file__).parent.parent
    assert (site_packages / relpath).is_file(), f"{symbol}: {relpath} is not in kicad-python {ref}"
