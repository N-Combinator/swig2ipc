import os
import sys
from pathlib import Path

import pytest

from swig2ipc.scanner import scan_tree


def findings_for(result, path):
    return [(f.line, f.symbol, f.kind) for f in result.findings if f.file == path]


def test_plain_import_and_module_calls(sample_plugin: Path):
    result = scan_tree(sample_plugin)
    found = findings_for(result, "plugin_actions.py")
    assert (1, "pcbnew", "import") in found
    assert (4, "BoardStats", "action-plugin") in found
    assert (4, "ActionPlugin", "module-call") in found
    assert (11, "GetBoard", "module-call") in found
    assert (13, "FromMM", "module-call") in found
    assert (14, "SomeMysteryHelper", "module-call") in found
    assert (15, "Refresh", "module-call") in found


def test_aliased_module_calls(sample_plugin: Path):
    result = scan_tree(sample_plugin)
    found = findings_for(result, "aliased.py")
    assert (1, "pcbnew", "import") in found
    assert (5, "LoadBoard", "module-call") in found
    assert (6, "VECTOR2I", "module-call") in found
    assert sum(1 for line, symbol, _ in found if line == 6 and symbol == "FromMM") == 2
    # methods called on a board object are out of scope, and the alias itself is
    # never reported as a bare name
    assert all(symbol != "pcb" for _, symbol, _ in found)
    assert all(symbol != "SetAuxOrigin" for _, symbol, _ in found)


def test_from_imports_and_aliased_base_class(sample_plugin: Path):
    result = scan_tree(sample_plugin)
    found = findings_for(result, "fromimports.py")
    assert (1, "ActionPlugin", "import") in found
    assert (2, "GetBoard", "import") in found
    assert (2, "ToMM", "import") in found
    # the alias BasePlugin resolves back to the SWIG symbol
    assert (5, "TrackReport", "action-plugin") in found
    assert (5, "ActionPlugin", "module-call") in found
    assert (7, "GetBoard", "module-call") in found
    assert (9, "ToMM", "module-call") in found


def test_star_import_is_recorded(sample_plugin: Path):
    result = scan_tree(sample_plugin)
    found = findings_for(result, "subdir/nested.py")
    assert (1, "*", "import") in found
    assert (2, "ZONE", "import") in found
    assert (6, "ZONE", "module-call") in found


def test_clean_file_has_no_findings(sample_plugin: Path):
    result = scan_tree(sample_plugin)
    assert findings_for(result, "clean.py") == []


def test_syntax_error_becomes_a_warning(sample_plugin: Path):
    result = scan_tree(sample_plugin)
    assert any(w.startswith("broken.py:") for w in result.warnings), result.warnings
    warning = next(w for w in result.warnings if w.startswith("broken.py:"))
    line = warning.split(":")[1]
    assert line.isdigit()
    assert findings_for(result, "broken.py") == []


def test_virtualenvs_are_skipped(sample_plugin: Path):
    result = scan_tree(sample_plugin)
    files = {f.file for f in result.findings}
    assert not any(f.startswith("venv/") for f in files)
    assert not any(f.startswith("tools_env/") for f in files)
    # broken.py still counts as scanned, the two venv files do not
    assert result.files_scanned == 6


def test_findings_are_sorted_by_file_then_line(sample_plugin: Path):
    result = scan_tree(sample_plugin)
    keys = [(f.file, f.line) for f in result.findings]
    assert keys == sorted(keys)


def test_skip_dirs_and_unreadable_file(tmp_path: Path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "hook.py").write_text("import pcbnew\n")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "cached.py").write_text("import pcbnew\n")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "lib.py").write_text("import pcbnew\n")
    (tmp_path / "real.py").write_text("import pcbnew\n")
    (tmp_path / "binary.py").write_bytes(b"import pcbnew\x00\n")

    result = scan_tree(tmp_path)
    assert [f.file for f in result.findings] == ["real.py"]
    assert result.files_scanned == 2
    assert any(w.startswith("binary.py:1:") for w in result.warnings)


def test_star_import_emits_a_warning(sample_plugin: Path):
    result = scan_tree(sample_plugin)
    assert any(w.startswith("subdir/nested.py:1:") and "import *" in w for w in result.warnings)


def test_utf8_bom_is_parsed(tmp_path: Path):
    """Windows-authored sources often start with a BOM; ast handles it, we must not strip it."""
    (tmp_path / "plugin.py").write_bytes(
        b"\xef\xbb\xbfimport pcbnew\npcbnew.LoadBoard('x')\n"
    )
    result = scan_tree(tmp_path)
    assert findings_for(result, "plugin.py") == [
        (1, "pcbnew", "import"),
        (2, "LoadBoard", "module-call"),
    ]
    assert result.warnings == []
    assert result.unparsed_files == []


def test_pep263_coding_cookie_is_honoured(tmp_path: Path):
    (tmp_path / "plugin.py").write_bytes(
        b"# -*- coding: latin-1 -*-\n# caf\xe9 \xa9\nimport pcbnew as pcb\npcb.FromMM(1)\n"
    )
    result = scan_tree(tmp_path)
    assert findings_for(result, "plugin.py") == [
        (3, "pcbnew", "import"),
        (4, "FromMM", "module-call"),
    ]
    assert result.warnings == []
    assert result.unparsed_files == []


def test_unparsed_files_are_tracked(tmp_path: Path):
    (tmp_path / "good.py").write_text("import pcbnew\n")
    (tmp_path / "broken.py").write_text("def f(:\n")
    (tmp_path / "unknown_codec.py").write_bytes(b"# -*- coding: nosuchcodec -*-\nimport pcbnew\n")

    result = scan_tree(tmp_path)
    assert result.unparsed_files == ["broken.py", "unknown_codec.py"]
    assert len(result.warnings) == 2


def _deep_elif_chain(branches: int) -> str:
    """Source for a ``if/elif`` chain nested ``branches`` deep (machine-generated code)."""
    lines = ["def f(x):", "    if x == 0:", "        return 0"]
    for i in range(1, branches):
        lines += [f"    elif x == {i}:", f"        return {i}"]
    return "\n".join(lines) + "\n"


def test_deeply_nested_file_is_a_warning_not_a_crash(tmp_path: Path):
    # Deep enough that both ast.parse and the visitor exhaust the interpreter stack,
    # whatever the ambient recursion limit is.
    (tmp_path / "generated_table.py").write_text(_deep_elif_chain(sys.getrecursionlimit() * 2))
    (tmp_path / "plugin.py").write_text("import pcbnew\npcbnew.GetBoard()\n")

    result = scan_tree(tmp_path)

    assert result.unparsed_files == ["generated_table.py"]
    assert result.warnings == ["generated_table.py:1: file too deeply nested to analyse (RecursionError)"]
    # The rest of the tree is still reported.
    assert findings_for(result, "plugin.py") == [
        (1, "pcbnew", "import"),
        (2, "GetBoard", "module-call"),
    ]


def test_star_import_finds_action_plugin_and_known_names(star_plugin: Path):
    result = scan_tree(star_plugin)
    found = findings_for(result, "wireit.py")

    # `from pcbnew import *` binds no name the AST can see, so the class base and
    # the bare calls are attributed to pcbnew heuristically.
    assert (3, "*", "import") in found
    assert (11, "StarPlugin", "action-plugin") in found
    assert (11, "ActionPlugin", "module-call") in found
    assert (17, "GetBoard", "module-call") in found
    assert (18, "SaveBoard", "module-call") in found

    heuristic = {(f.line, f.symbol) for f in result.findings if f.heuristic}
    assert heuristic == {
        (11, "StarPlugin"),
        (11, "ActionPlugin"),
        (17, "GetBoard"),
        (18, "SaveBoard"),
    }
    assert any("from pcbnew import *" in warning for warning in result.warnings)


def test_star_import_does_not_claim_names_the_file_defines(star_plugin: Path):
    result = scan_tree(star_plugin)
    # wireit.py defines its own GetTracks(), so its two uses are not pcbnew's.
    assert [f for f in result.findings if f.symbol == "GetTracks"] == []
    # explicit.py has no star import at all, so its bare GetBoard() is nobody's.
    assert findings_for(result, "explicit.py") == []


def test_bare_names_need_a_star_import(tmp_path: Path):
    (tmp_path / "plain.py").write_text("board = GetBoard()\n")
    assert scan_tree(tmp_path).findings == []


def test_unreadable_directory_is_a_warning_not_a_silent_gap(tmp_path: Path):
    if os.geteuid() == 0:
        pytest.skip("root can read a 0o000 directory")
    (tmp_path / "plugin.py").write_text("import pcbnew\npcbnew.GetBoard()\n")
    secret = tmp_path / "secret"
    secret.mkdir()
    (secret / "hidden.py").write_text("import pcbnew\npcbnew.LoadBoard('x')\n")
    secret.chmod(0o000)
    try:
        result = scan_tree(tmp_path)
    finally:
        secret.chmod(0o755)

    assert result.unparsed_files == ["secret"]
    assert len(result.warnings) == 1
    assert result.warnings[0].startswith("secret:1: could not list directory (PermissionError")
    # The readable part of the tree is still scanned.
    assert findings_for(result, "plugin.py") == [
        (1, "pcbnew", "import"),
        (2, "GetBoard", "module-call"),
    ]


def test_undecodable_filename_is_escaped_not_a_surrogate(tmp_path: Path, undecodable_file):
    undecodable_file(tmp_path)
    result = scan_tree(tmp_path)

    assert result.files_scanned == 1
    (name,) = {f.file for f in result.findings}
    assert name == "caf\\xe9_plugin.py"
    # The whole point: every path in the result survives a UTF-8 encode.
    name.encode("utf-8")
