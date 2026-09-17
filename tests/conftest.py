import os
from pathlib import Path
from typing import Callable

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_plugin() -> Path:
    """A plugin tree covering every import form, plus a broken file and two venvs."""
    return FIXTURES / "sample_plugin"


@pytest.fixture
def star_plugin() -> Path:
    """A plugin using `from pcbnew import *` with a bare `ActionPlugin` base."""
    return FIXTURES / "star_plugin"


@pytest.fixture
def late_import_plugin() -> Path:
    """A plugin whose `pcbnew` imports sit below the code that uses them."""
    return FIXTURES / "late_import_plugin"


@pytest.fixture
def undecodable_file() -> Callable[[Path], Path]:
    """Writes a .py file whose name is not valid UTF-8 (a Windows zip classic)."""

    def make(directory: Path) -> Path:
        path = Path(os.fsdecode(os.fsencode(str(directory)) + b"/caf\xe9_plugin.py"))
        try:
            path.write_bytes(b"import pcbnew\npcbnew.GetBoard()\n")
        except (OSError, UnicodeError) as exc:  # pragma: no cover - filesystem dependent
            pytest.skip(f"filesystem rejects non-UTF-8 filenames: {exc}")
        return path

    return make
