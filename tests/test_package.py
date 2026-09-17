"""The distribution metadata and the package agree about the version."""

from __future__ import annotations

import tomllib
from importlib.metadata import version
from pathlib import Path

import pytest

import swig2ipc

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def test_version_comes_from_the_installed_distribution():
    assert swig2ipc.__version__ == version("swig2ipc")
    assert swig2ipc.__version__ != "0+unknown"


def test_version_matches_pyproject():
    """release.yml gates a tag on the pyproject version, so it must be the one source."""
    if not PYPROJECT.is_file():
        pytest.skip("not running from a source checkout")
    declared = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]["version"]
    assert swig2ipc.__version__ == declared
