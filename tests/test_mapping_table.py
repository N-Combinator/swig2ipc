"""Integrity of the packaged mapping table (no kicad-python needed)."""

from __future__ import annotations

import datetime as dt
from urllib.parse import urlparse

import pytest

from swig2ipc import mapping

REQUIRED_SYMBOLS = [
    "GetBoard",
    "LoadBoard",
    "SaveBoard",
    "Refresh",
    "ActionPlugin",
    "FromMM",
    "ToMM",
    "VECTOR2I",
    "FOOTPRINT",
    "PCB_TRACK",
    "PCB_VIA",
    "ZONE",
    "GetFootprints",
    "GetTracks",
]

ALLOWED_SOURCE_HOSTS = {"gitlab.com", "dev-docs.kicad.org", "docs.kicad.org"}

ENTRIES = mapping.entries()


def test_meta_block():
    meta = mapping.meta()
    assert meta["kicad_python_version"]
    checked_on = dt.date.fromisoformat(meta["checked_on"])
    assert checked_on <= dt.date.today()


def test_table_size_and_required_symbols():
    assert len(ENTRIES) >= 25
    missing = [symbol for symbol in REQUIRED_SYMBOLS if symbol not in ENTRIES]
    assert missing == []


@pytest.mark.parametrize("symbol", sorted(ENTRIES))
def test_entry_shape(symbol: str):
    entry = ENTRIES[symbol]
    assert set(entry) == {"status", "ipc", "note", "source_url"}
    assert entry["status"] in mapping.TABLE_STATUSES
    assert entry["note"].strip()
    url = urlparse(entry["source_url"])
    assert url.scheme == "https"
    assert url.netloc in ALLOWED_SOURCE_HOSTS, entry["source_url"]
    if entry["status"] == mapping.STATUS_MAPPED:
        assert entry["ipc"], f"{symbol} is mapped but has no ipc equivalent"
    if entry["ipc"] is not None:
        assert entry["ipc"].startswith("kipy.")


def test_unknown_symbols_are_never_mapped():
    entry = mapping.lookup("NoSuchSwigSymbol")
    assert entry["status"] == mapping.STATUS_UNKNOWN
    assert entry["ipc"] is None
