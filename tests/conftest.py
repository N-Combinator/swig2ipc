from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_plugin() -> Path:
    """A plugin tree covering every import form, plus a broken file and two venvs."""
    return FIXTURES / "sample_plugin"
