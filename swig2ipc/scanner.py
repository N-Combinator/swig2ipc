"""AST scan of a plugin source tree for uses of the SWIG ``pcbnew`` API."""

from __future__ import annotations

import ast
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

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
    """

    file: str
    line: int
    symbol: str
    kind: str

    def to_dict(self) -> dict:
        return {"file": self.file, "line": self.line, "symbol": self.symbol, "kind": self.kind}


@dataclass
class ScanResult:
    findings: list[Finding] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    files_scanned: int = 0
    #: Files that could not be read or parsed, so their SWIG usage is unknown.
    unparsed_files: list[str] = field(default_factory=list)


class _PcbnewVisitor(ast.NodeVisitor):
    """Collects SWIG API uses in a single module.

    Tracks two kinds of name bindings: aliases of the ``pcbnew`` module itself
    (``import pcbnew as pcb``) and names imported out of it
    (``from pcbnew import GetBoard as gb``).
    """

    def __init__(self, relpath: str) -> None:
        self.relpath = relpath
        self.findings: list[Finding] = []
        self.warnings: list[str] = []
        self.module_aliases: set[str] = set()
        self.imported_names: dict[str, str] = {}

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
                    self.warnings.append(
                        f"{self.relpath}:{node.lineno}: `from pcbnew import *` hides which "
                        "symbols are used; statuses for this file may be incomplete"
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
        symbol = self.imported_names.get(node.id)
        if symbol is not None and isinstance(node.ctx, ast.Load):
            self._add(node.lineno, symbol, KIND_MODULE_CALL)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        if any(self._is_action_plugin_base(base) for base in node.bases):
            self._add(node.lineno, node.name, KIND_ACTION_PLUGIN)
        self.generic_visit(node)

    # -- helpers ---------------------------------------------------------
    def _is_action_plugin_base(self, base: ast.expr) -> bool:
        if isinstance(base, ast.Attribute):
            return (
                base.attr == "ActionPlugin"
                and isinstance(base.value, ast.Name)
                and base.value.id in self.module_aliases
            )
        if isinstance(base, ast.Name):
            return self.imported_names.get(base.id) == "ActionPlugin"
        return False

    def _add(self, line: int, symbol: str, kind: str) -> None:
        self.findings.append(Finding(file=self.relpath, line=line, symbol=symbol, kind=kind))


def iter_python_files(root: Path) -> Iterator[Path]:
    """Yield every ``.py`` file under ``root``, skipping VCS dirs and virtualenvs."""
    for dirpath, dirnames, filenames in os.walk(root):
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


def scan_tree(root: Path) -> ScanResult:
    """Scan every Python file under ``root``. Findings are sorted by file, then line."""
    result = ScanResult()
    root = Path(root)
    for path in iter_python_files(root):
        relpath = path.relative_to(root).as_posix()
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
