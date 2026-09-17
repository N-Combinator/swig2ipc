from pathlib import Path

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
