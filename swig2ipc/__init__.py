"""Static readiness report for KiCad plugins moving from SWIG pcbnew to the IPC API."""

from importlib.metadata import PackageNotFoundError, version as _version

#: Single source of truth is the version in pyproject.toml, read back from the
#: installed distribution metadata so a release can never ship a report that
#: claims a different version than the wheel it came from.
try:
    __version__ = _version("swig2ipc")
except PackageNotFoundError:  # running straight from a source tree, not installed
    __version__ = "0+unknown"

__all__ = ["__version__"]
