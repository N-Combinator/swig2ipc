import json
from pathlib import Path

import pytest

from swig2ipc.cli import main

ARGS = ["skeleton", "--name", "Board Stats", "--identifier", "com.example.boardstats"]


def test_writes_manifest_and_requirements(tmp_path: Path):
    out = tmp_path / "boardstats"
    assert main(ARGS + ["--out", str(out)]) == 0

    manifest = json.loads((out / "plugin.json").read_text())
    assert set(manifest) == {"identifier", "name", "description", "runtime", "actions"}
    assert manifest["identifier"] == "com.example.boardstats"
    assert manifest["name"] == "Board Stats"
    assert manifest["description"]
    assert manifest["runtime"] == {"type": "python", "min_version": "3.9"}

    assert len(manifest["actions"]) == 1
    action = manifest["actions"][0]
    assert {"identifier", "name", "description", "entrypoint", "scopes"} <= set(action)
    assert action["entrypoint"] == "main.py"
    assert action["scopes"] == ["pcb"]

    assert (out / "requirements.txt").read_text().splitlines() == ["kicad-python"]


def test_entrypoint_and_description_are_overridable(tmp_path: Path):
    out = tmp_path / "plugin"
    code = main(
        ARGS
        + [
            "--out",
            str(out),
            "--entrypoint",
            "run_plugin.py",
            "--description",
            "Counts footprints.",
            "--action-identifier",
            "count",
        ]
    )
    assert code == 0
    manifest = json.loads((out / "plugin.json").read_text())
    assert manifest["description"] == "Counts footprints."
    assert manifest["actions"][0]["entrypoint"] == "run_plugin.py"
    assert manifest["actions"][0]["identifier"] == "count"


def test_refuses_to_overwrite(tmp_path: Path, capsys):
    out = tmp_path / "plugin"
    out.mkdir()
    (out / "plugin.json").write_text('{"keep": "me"}\n')

    with pytest.raises(SystemExit) as excinfo:
        main(ARGS + ["--out", str(out)])
    assert excinfo.value.code == 2
    assert "refusing to overwrite" in capsys.readouterr().err
    # nothing was touched, and the second file was not created either
    assert json.loads((out / "plugin.json").read_text()) == {"keep": "me"}
    assert not (out / "requirements.txt").exists()


def test_rejects_invalid_identifier(tmp_path: Path, capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(
            [
                "skeleton",
                "--name",
                "Bad",
                "--identifier",
                "1-not-valid!",
                "--out",
                str(tmp_path / "plugin"),
            ]
        )
    assert excinfo.value.code == 2
    assert "invalid plugin identifier" in capsys.readouterr().err
    assert not (tmp_path / "plugin").exists()


def test_missing_required_option_is_a_usage_error(tmp_path: Path):
    with pytest.raises(SystemExit) as excinfo:
        main(["skeleton", "--name", "Board Stats", "--out", str(tmp_path / "plugin")])
    assert excinfo.value.code == 2


def test_manifest_validates_against_kicad_schema(tmp_path: Path):
    """The plugin schema ships inside kicad-python; use it when available."""
    jsonschema = pytest.importorskip("jsonschema")
    resources = pytest.importorskip("importlib.resources")
    pytest.importorskip("kipy")

    out = tmp_path / "plugin"
    assert main(ARGS + ["--out", str(out)]) == 0
    schema = json.loads(
        resources.files("kipy.packaging.schemas")
        .joinpath("api.v1.schema.json")
        .read_text(encoding="utf-8")
    )
    jsonschema.validate(json.loads((out / "plugin.json").read_text()), schema)
