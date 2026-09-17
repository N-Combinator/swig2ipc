# swig2ipc

Readiness report for KiCad plugins moving from the SWIG `pcbnew` API to the IPC API before
KiCad 11.

KiCad 11 removes the SWIG-based `pcbnew` Python module. Action plugins have to move to the
IPC API and its official bindings,
[`kicad-python`](https://gitlab.com/kicad/code/kicad-python) (`kipy`). `swig2ipc` reads a
plugin's source tree with Python's `ast` module — it never imports the plugin, never talks
to KiCad and never touches the network — and tells you, symbol by symbol, what already has
an IPC equivalent and what does not.

It also writes the manifest skeleton an IPC plugin needs (`plugin.json` +
`requirements.txt`).

## Install

```sh
pip install .
```

Or from a GitHub Release wheel (every `v*` tag publishes an sdist and a wheel):

```sh
pip install https://github.com/N-Combinator/swig2ipc/releases/download/v0.1.0/swig2ipc-0.1.0-py3-none-any.whl
```

Python 3.10 or newer. The runtime has no dependencies at all; `kicad-python` is only used by
the test suite (see [Mapping table](#mapping-table)).

## Usage

### `swig2ipc scan`

```sh
swig2ipc scan path/to/plugin                      # JSON report on stdout
swig2ipc scan path/to/plugin --format markdown    # Markdown report
swig2ipc scan path/to/plugin --fail-on unmapped   # exit 1 if anything is unmapped
swig2ipc scan path/to/plugin --fail-on unknown    # exit 1 if anything is unmapped or unknown
swig2ipc scan path/to/plugin --fail-on-warnings   # exit 1 if the scan was incomplete
```

Every `.py` file under the directory is parsed. `.git`, `.venv`, `venv`, `__pycache__` and
any directory holding a `pyvenv.cfg` are skipped. Sources are handed to `ast` as bytes, so a
UTF-8 BOM and a PEP 263 coding cookie (`# -*- coding: latin-1 -*-`) are honoured exactly as
CPython honours them. A file that still fails to parse — a syntax error, an unreadable file,
or one nested too deeply for the interpreter stack, as machine-generated code can be — is
listed under `warnings` as `path:line: reason`, and under `summary.unparsed_files`, instead
of aborting the scan.

Each use of the SWIG API is reported as `{"file", "line", "symbol", "kind"}`, sorted by file
then line, with `kind` one of:

| kind | what it means |
| --- | --- |
| `import` | `import pcbnew`, `import pcbnew as X`, `from pcbnew import Y` |
| `module-call` | attribute access on the module or an alias (`pcbnew.GetBoard()`, `X.FromMM(1)`) or use of a from-imported name |
| `action-plugin` | a class whose bases include `pcbnew.ActionPlugin` (or an `ActionPlugin` imported from `pcbnew`); here `symbol` is the name of *your* class |

The report also carries a `summary` (counts per status, the plugin's action plugin classes,
the lists of unmapped and unknown symbols, and `unparsed_files`), the per-symbol mapping
(`symbols`), and `warnings`.

Exit codes: `0` success, `1` the `--fail-on` threshold was hit, `2` usage error (missing
directory, bad option, …).

`--fail-on` looks only at symbol statuses: warnings never fail it on their own, because a
file the scanner could not read says nothing about the symbols it uses. If you want an
incomplete scan to be an error too — in CI, say — add `--fail-on-warnings`, or check that
`summary.unparsed_files` is empty in the JSON report.

#### Limitations

- Only module-level uses are tracked. Method calls on objects you got back from the API —
  `board.GetFootprints()`, `track.GetWidth()` — are not attributed to `pcbnew`, because
  static analysis cannot tell a KiCad object from any other object.
- `from pcbnew import *` is reported as an import of `*` plus a warning; the symbols it
  pulls in cannot be resolved statically.
- The scan is per-file: names re-exported through your own helper modules are not followed.

### `swig2ipc skeleton`

```sh
swig2ipc skeleton --name "Board Stats" --identifier com.example.boardstats --out ./boardstats
```

Writes `plugin.json` and a `requirements.txt` containing `kicad-python`. It never overwrites
an existing file (exit `2`). `--description`, `--entrypoint` (default `main.py`) and
`--action-identifier` (default `run`) are optional.

The manifest field set follows KiCad's add-on developer documentation,
<https://dev-docs.kicad.org/en/apis-and-binding/ipc-api/for-addon-developers/>, and the
`api.v1` plugin schema shipped inside `kicad-python`
(`kipy/packaging/schemas/api.v1.schema.json`), which the test suite validates the generated
manifest against:

```json
{
  "identifier": "com.example.boardstats",
  "name": "Board Stats",
  "description": "Board Stats, a KiCad IPC API plugin.",
  "runtime": { "type": "python", "min_version": "3.9" },
  "actions": [
    {
      "identifier": "run",
      "name": "Board Stats",
      "description": "Run Board Stats.",
      "show-button": true,
      "entrypoint": "main.py",
      "scopes": ["pcb"]
    }
  ]
}
```

You still write the entrypoint script yourself; it should connect with
`from kipy import KiCad`.

## Mapping table

The statuses come from a packaged table, `swig2ipc/data/mapping.json`:

| status | meaning |
| --- | --- |
| `mapped` | a direct IPC equivalent exists; `ipc` names it |
| `partial` | an equivalent exists but the semantics differ (different call shape, narrower coverage, extra step) — read the note before porting |
| `unmapped` | no equivalent in this version of `kicad-python`; the note suggests a workaround where one exists |
| `unknown` | the symbol is not in the table at all. Never reported as `mapped`; check it by hand and please open an issue |

Every entry carries a `note` and a `source_url` pointing at the `kicad-python` source (at the
pinned tag) or the KiCad IPC API documentation that justifies the status.

**The table is a best-effort snapshot.** It is tied to `_meta.kicad_python_version`
(currently `0.8.0`, checked on `_meta.checked_on`). The IPC API is still growing, so a
symbol that is `unmapped` or `partial` today may well be `mapped` in a later release —
re-check against the version you actually target. To keep the snapshot honest, the test
suite installs exactly that version of `kicad-python` and resolves every non-null `ipc`
dotted path with `importlib`/`getattr`, so a claim that does not exist in the real package
fails CI.

## Development

```sh
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest -q
```

The `dev` extra pulls in `pytest` and `kicad-python==0.8.0`. `kicad-python` is a test-only
dependency: nothing in `swig2ipc` imports it at runtime.

## Similar tools

There is, as far as we know, no other static SWIG→IPC readiness checker. What exists nearby:

- [`kicad-python`](https://gitlab.com/kicad/code/kicad-python) — the destination API itself.
  It ships a `kicad-python-packager` command that validates a `plugin.json` against KiCad's
  schema, which pairs well with `swig2ipc skeleton`.
- [KiCad IPC API documentation](https://dev-docs.kicad.org/en/apis-and-binding/ipc-api/for-addon-developers/)
  and the [`pcbnew` SWIG bindings page](https://dev-docs.kicad.org/en/apis-and-binding/pcbnew/) —
  the authoritative migration reading; `swig2ipc` links back into them per symbol.
- [`kiutils`](https://github.com/mvnmgrx/kiutils) and similar file-format libraries — an
  alternative to the API when you only need to read or write board files, no running KiCad.
- Generic codemod tooling (`libcst`, `pyupgrade`, `ruff`) — useful once you know *what* to
  rewrite, but none of them know anything about KiCad.

## License

MIT — see [LICENSE](LICENSE).
