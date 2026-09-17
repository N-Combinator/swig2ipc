import json
from pathlib import Path

import pytest

from swig2ipc.cli import main


def run(argv, capsys):
    code = main(argv)
    return code, capsys.readouterr().out


def test_json_report_shape(sample_plugin: Path, capsys):
    code, out = run(["scan", str(sample_plugin)], capsys)
    assert code == 0
    report = json.loads(out)

    assert report["tool"]["name"] == "swig2ipc"
    assert report["mapping_table"]["kicad_python_version"]
    for finding in report["findings"]:
        assert set(finding) == {"file", "line", "symbol", "kind"}
        assert finding["kind"] in {"import", "module-call", "action-plugin"}

    summary = report["summary"]
    assert summary["counts"]["mapped"] >= 1
    assert summary["counts"]["unknown"] == 1
    assert summary["unknown_symbols"] == ["SomeMysteryHelper"]
    assert "ActionPlugin" in summary["unmapped_symbols"]
    assert summary["action_plugin_classes"] == [
        "fromimports.py:5 TrackReport",
        "plugin_actions.py:4 BoardStats",
    ]
    assert any(w.startswith("broken.py:") for w in report["warnings"])

    # the user's own subclass names never get a mapping status
    assert "BoardStats" not in report["symbols"]
    assert report["symbols"]["GetBoard"]["status"] == "mapped"
    assert report["symbols"]["GetBoard"]["ipc"].startswith("kipy.")
    assert report["symbols"]["SomeMysteryHelper"]["status"] == "unknown"


def test_markdown_report(sample_plugin: Path, capsys):
    code, out = run(["scan", str(sample_plugin), "--format", "markdown"], capsys)
    assert code == 0
    assert out.startswith("# SWIG -> IPC readiness report")
    for heading in ("## Summary", "## Action plugin classes", "## Unmapped symbols",
                    "## Unknown symbols", "## Findings", "## Warnings"):
        assert heading in out
    assert "`GetBoard`" in out
    assert "kipy.kicad.KiCad.get_board" in out


def test_exit_codes_for_fail_on(sample_plugin: Path, capsys):
    assert run(["scan", str(sample_plugin)], capsys)[0] == 0
    assert run(["scan", str(sample_plugin), "--fail-on", "unmapped"], capsys)[0] == 1
    assert run(["scan", str(sample_plugin), "--fail-on", "unknown"], capsys)[0] == 1


def test_fail_on_unmapped_passes_when_only_unknown(tmp_path: Path, capsys):
    (tmp_path / "plugin.py").write_text("import pcbnew\n\npcbnew.NotARealCall()\n")
    code, out = run(["scan", str(tmp_path), "--fail-on", "unmapped"], capsys)
    assert code == 0
    assert json.loads(out)["summary"]["unknown_symbols"] == ["NotARealCall"]

    assert run(["scan", str(tmp_path), "--fail-on", "unknown"], capsys)[0] == 1


def test_clean_tree_passes_both_modes(tmp_path: Path, capsys):
    (tmp_path / "plugin.py").write_text("import pcbnew\n\npcbnew.GetBoard()\n")
    assert run(["scan", str(tmp_path), "--fail-on", "unmapped"], capsys)[0] == 0
    assert run(["scan", str(tmp_path), "--fail-on", "unknown"], capsys)[0] == 0


def test_missing_directory_is_a_usage_error(tmp_path: Path, capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["scan", str(tmp_path / "nope")])
    assert excinfo.value.code == 2
    assert "no such directory" in capsys.readouterr().err


def test_file_instead_of_directory_is_a_usage_error(tmp_path: Path, capsys):
    target = tmp_path / "plugin.py"
    target.write_text("import pcbnew\n")
    with pytest.raises(SystemExit) as excinfo:
        main(["scan", str(target)])
    assert excinfo.value.code == 2
    assert "not a directory" in capsys.readouterr().err


def test_unknown_format_is_a_usage_error(sample_plugin: Path):
    with pytest.raises(SystemExit) as excinfo:
        main(["scan", str(sample_plugin), "--format", "xml"])
    assert excinfo.value.code == 2


def test_no_subcommand_is_a_usage_error():
    with pytest.raises(SystemExit) as excinfo:
        main([])
    assert excinfo.value.code == 2
