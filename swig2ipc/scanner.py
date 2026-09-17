"""AST scan of a plugin source tree for uses of the SWIG ``pcbnew`` API."""

from __future__ import annotations

import ast
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Callable, Iterator

from . import mapping

SWIG_MODULE = "pcbnew"

#: Directory names never descended into.
SKIP_DIRS = frozenset({".git", ".venv", "venv", "__pycache__"})

#: Marker file that identifies a directory as a virtual environment.
VENV_MARKER = "pyvenv.cfg"

#: Warning text for a file whose syntax tree is too deep or too large to handle.
_TOO_LARGE = "file too deeply nested to analyse"

KIND_IMPORT = "import"
KIND_MODULE_CALL = "module-call"
KIND_ACTION_PLUGIN = "action-plugin"


@dataclass(frozen=True, order=True)
class Finding:
    """One use of the SWIG API.

    ``symbol`` is the SWIG symbol for ``import``/``module-call`` findings and the
    name of the subclass for ``action-plugin`` findings.

    ``heuristic`` marks a finding that could not be proven from the file's own
    bindings: after ``from pcbnew import *`` a bare name is only *assumed* to come
    from ``pcbnew``. Such findings carry ``"heuristic": true`` in the report;
    proven ones carry no such key.
    """

    file: str
    line: int
    symbol: str
    kind: str
    heuristic: bool = False

    def to_dict(self) -> dict:
        data = {"file": self.file, "line": self.line, "symbol": self.symbol, "kind": self.kind}
        if self.heuristic:
            data["heuristic"] = True
        return data


@dataclass
class ScanResult:
    findings: list[Finding] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    files_scanned: int = 0
    #: Files that could not be read or parsed, and directories that could not be
    #: listed, so the SWIG usage they hold is unknown.
    unparsed_files: list[str] = field(default_factory=list)


@lru_cache(maxsize=1)
def star_import_names() -> frozenset[str]:
    """Names attributed to ``pcbnew`` after ``from pcbnew import *``.

    A star import binds whatever the SWIG module exports, which cannot be known
    without importing KiCad itself. Every symbol the mapping table knows about is
    treated as ``pcbnew``'s, plus the ``ActionPlugin`` base class, which is the
    shape that matters most: ``from pcbnew import *`` followed by
    ``class X(ActionPlugin)`` is the common legacy plugin. Findings derived this
    way are marked heuristic.
    """
    return frozenset(mapping.entries()) | {"ActionPlugin"}


def bound_names(tree: ast.Module) -> set[str]:
    """Every name the module binds itself.

    Used to keep a star import from claiming a name the file defines on its own
    (``def GetBoard():`` after ``from pcbnew import *`` is the file's function).
    """
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and not isinstance(node.ctx, ast.Load):
            names.add(node.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)
        elif isinstance(node, ast.alias) and node.name != "*":
            names.add(node.asname or node.name.split(".")[0])
    return names


def printable(text: str) -> str:
    r"""Make a path safe to print and to serialise.

    Filenames need not be valid UTF-8; :func:`os.fsdecode` represents the
    undecodable bytes as lone surrogates, which raise ``UnicodeEncodeError`` when
    the Markdown report is written out and produce JSON that strict parsers
    reject. Going back through the filesystem encoding shows the original bytes
    as ``\xNN`` escapes instead.
    """
    try:
        raw = os.fsencode(text)
    except UnicodeEncodeError:  # pragma: no cover - only with an ASCII filesystem encoding
        raw = text.encode("utf-8", "backslashreplace")
    return raw.decode("utf-8", "backslashreplace")


class _PcbnewVisitor(ast.NodeVisitor):
    """Collects SWIG API uses in a single module.

    Tracks three kinds of name bindings: aliases of the ``pcbnew`` module itself
    (``import pcbnew as pcb``), names imported out of it
    (``from pcbnew import GetBoard as gb``) and, after ``from pcbnew import *``,
    the known SWIG names the file does not bind itself.
    """

    def __init__(self, relpath: str) -> None:
        self.relpath = relpath
        self.findings: list[Finding] = []
        self.warnings: list[str] = []
        self.module_aliases: set[str] = set()
        self.imported_names: dict[str, str] = {}
        #: Known SWIG names assumed to come from a ``from pcbnew import *``.
        self.star_names: frozenset[str] = frozenset()
        self._bound: set[str] = set()

    def visit_Module(self, node: ast.Module) -> None:
        # Needed before any star import is seen, because the names the module
        # binds itself win over the ones a star import would pull in.
        self._bound = bound_names(node)
        self.generic_visit(node)

    # -- imports ---------------------------------------------------------
    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.name == SWIG_MODULE or alias.name.startswith(SWIG_MODULE + "."):
                bound = alias.asname or alias.name.split(".")[0]
                self.module_aliases.add(bound)
                self._add(node.lineno, SWIG_MODULE, KIND_IMPORT)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.level == 0 and node.module == SWIG_MODULE:
            for alias in node.names:
                self._add(node.lineno, alias.name, KIND_IMPORT)
                if alias.name == "*":
                    self.star_names = star_import_names() - self._bound
                    self.warnings.append(
                        f"{self.relpath}:{node.lineno}: `from pcbnew import *` hides which "
                        "symbols are used; bare names known to the mapping table are "
                        "attributed to pcbnew heuristically, so statuses for this file "
                        "may be incomplete"
                    )
                else:
                    self.imported_names[alias.asname or alias.name] = alias.name
        self.generic_visit(node)

    # -- uses ------------------------------------------------------------
    def visit_Attribute(self, node: ast.Attribute) -> None:
        value = node.value
        if isinstance(value, ast.Name) and value.id in self.module_aliases:
            self._add(node.lineno, node.attr, KIND_MODULE_CALL)
            return  # do not re-report the alias itself as a bare name
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load):
            symbol = self.imported_names.get(node.id)
            if symbol is not None:
                self._add(node.lineno, symbol, KIND_MODULE_CALL)
            elif node.id in self.star_names:
                self._add(node.lineno, node.id, KIND_MODULE_CALL, heuristic=True)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        matches = [m for m in (self._action_plugin_base(base) for base in node.bases) if m]
        if matches:
            self._add(
                node.lineno, node.name, KIND_ACTION_PLUGIN, heuristic="explicit" not in matches
            )
        self.generic_visit(node)

    # -- helpers ---------------------------------------------------------
    def _action_plugin_base(self, base: ast.expr) -> str | None:
        """``"explicit"``, ``"heuristic"`` or ``None`` for one base class expression."""
        if isinstance(base, ast.Attribute):
            if (
                base.attr == "ActionPlugin"
                and isinstance(base.value, ast.Name)
                and base.value.id in self.module_aliases
            ):
                return "explicit"
            return None
        if isinstance(base, ast.Name):
            if self.imported_names.get(base.id) == "ActionPlugin":
                return "explicit"
            if base.id == "ActionPlugin" and base.id in self.star_names:
                return "heuristic"
        return None

    def _add(self, line: int, symbol: str, kind: str, heuristic: bool = False) -> None:
        self.findings.append(
            Finding(file=self.relpath, line=line, symbol=symbol, kind=kind, heuristic=heuristic)
        )


def iter_python_files(
    root: Path, on_error: Callable[[OSError], None] | None = None
) -> Iterator[Path]:
    """Yield every ``.py`` file under ``root``, skipping VCS dirs and virtualenvs.

    ``os.walk`` swallows every listing error by default, which would drop an
    unreadable subtree from the scan in complete silence. Errors are handed to
    ``on_error`` instead, and the walk continues with the rest of the tree.
    """

    def _report(exc: OSError) -> None:
        if on_error is not None:
            on_error(exc)

    for dirpath, dirnames, filenames in os.walk(root, onerror=_report):
        if VENV_MARKER in filenames:
            dirnames[:] = []
            continue
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for name in sorted(filenames):
            if name.endswith(".py"):
                yield Path(dirpath) / name


def scan_file(path: Path, relpath: str) -> tuple[list[Finding], list[str], bool]:
    """Scan one file.

    Returns its findings, any warnings (``path:line: reason``) and whether the file
    could be parsed at all.

    The source is handed to :func:`ast.parse` as bytes so that the interpreter's own
    decoding rules apply: a UTF-8 BOM and a PEP 263 coding cookie
    (``# -*- coding: latin-1 -*-``) are honoured exactly as CPython would honour them.
    Decoding the bytes ourselves would turn both into unparseable files.

    Both building and walking the tree recurse once per nesting level, so a deeply
    nested file (a machine-generated ``elif`` chain, a long ``a + b + c + ...``
    expression) can exhaust the interpreter stack. That is reported like any other
    unreadable file rather than aborting the whole scan.
    """
    try:
        source = path.read_bytes()
    except OSError as exc:
        return [], [f"{relpath}:1: could not read file ({exc.__class__.__name__}: {exc})"], False
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        return [], [f"{relpath}:{exc.lineno or 1}: syntax error ({exc.msg})"], False
    except ValueError as exc:  # e.g. source containing null bytes
        return [], [f"{relpath}:1: could not parse file ({exc})"], False
    except (RecursionError, MemoryError) as exc:
        return [], [f"{relpath}:1: {_TOO_LARGE} ({exc.__class__.__name__})"], False
    visitor = _PcbnewVisitor(relpath)
    try:
        visitor.visit(tree)
    except (RecursionError, MemoryError) as exc:
        return [], [f"{relpath}:1: {_TOO_LARGE} ({exc.__class__.__name__})"], False
    return visitor.findings, visitor.warnings, True


def _relpath(path: Path, root: Path) -> str:
    try:
        relpath = path.relative_to(root).as_posix()
    except ValueError:
        relpath = path.as_posix()
    return printable(relpath)


def scan_tree(root: Path) -> ScanResult:
    """Scan every Python file under ``root``. Findings are sorted by file, then line."""
    result = ScanResult()
    root = Path(root)

    def on_walk_error(exc: OSError) -> None:
        relpath = _relpath(Path(os.fsdecode(exc.filename or root)), root)
        result.warnings.append(
            f"{relpath}:1: could not list directory ({exc.__class__.__name__}: {exc.strerror or exc})"
        )
        result.unparsed_files.append(relpath)

    for path in iter_python_files(root, on_error=on_walk_error):
        relpath = _relpath(path, root)
        result.files_scanned += 1
        findings, warnings, parsed = scan_file(path, relpath)
        result.warnings.extend(warnings)
        result.findings.extend(findings)
        if not parsed:
            result.unparsed_files.append(relpath)
    result.findings.sort(key=lambda f: (f.file, f.line, f.kind, f.symbol))
    result.warnings.sort()
    result.unparsed_files.sort()
    return result
