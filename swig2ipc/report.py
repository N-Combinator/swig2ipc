"""Builds the readiness report from a scan and the mapping table."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from . import __version__, mapping
from .scanner import KIND_ACTION_PLUGIN, ScanResult, printable, scan_tree


def build_report(root: Path) -> dict[str, Any]:
    """Scan ``root`` and annotate every finding with its mapping status."""
    scan: ScanResult = scan_tree(root)

    findings: list[dict[str, Any]] = [f.to_dict() for f in scan.findings]

    # Only import/module-call findings name SWIG symbols; an action-plugin
    # finding names the user's own subclass, and `from pcbnew import *` names no
    # symbol at all (it is reported as a warning instead), so neither is looked up.
    symbols: dict[str, dict[str, Any]] = {}
    for finding in scan.findings:
        if finding.kind == KIND_ACTION_PLUGIN or finding.symbol == "*":
            continue
        entry = symbols.setdefault(finding.symbol, {**mapping.lookup(finding.symbol), "uses": 0})
        entry["uses"] += 1

    counts = Counter(entry["status"] for entry in symbols.values())
    by_status = {
        status: sorted(name for name, entry in symbols.items() if entry["status"] == status)
        for status in mapping.ALL_STATUSES
    }

    action_plugin_classes = sorted(
        {f"{f.file}:{f.line} {f.symbol}" for f in scan.findings if f.kind == KIND_ACTION_PLUGIN}
    )

    return {
        "tool": {"name": "swig2ipc", "version": __version__},
        "root": printable(str(Path(root))),
        "mapping_table": mapping.meta(),
        "summary": {
            "files_scanned": scan.files_scanned,
            "findings": len(findings),
            "symbols": len(symbols),
            "counts": {status: counts.get(status, 0) for status in mapping.ALL_STATUSES},
            "action_plugin_classes": action_plugin_classes,
            "unmapped_symbols": by_status[mapping.STATUS_UNMAPPED],
            "unknown_symbols": by_status[mapping.STATUS_UNKNOWN],
            # Files whose SWIG usage could not be determined: the counts above do
            # not cover them, so a report with a non-empty list is incomplete.
            "unparsed_files": scan.unparsed_files,
        },
        "symbols": {name: symbols[name] for name in sorted(symbols)},
        "findings": findings,
        "warnings": scan.warnings,
    }


def render_markdown(report: dict[str, Any]) -> str:
    """Render a report as Markdown."""
    summary = report["summary"]
    meta = report["mapping_table"]
    lines: list[str] = [
        "# SWIG -> IPC readiness report",
        "",
        f"- Source tree: `{report['root']}`",
        f"- Python files scanned: {summary['files_scanned']} "
        f"({len(summary['unparsed_files'])} could not be parsed)",
        f"- SWIG API uses found: {summary['findings']} "
        f"({summary['symbols']} distinct symbols)",
        f"- Mapping table: kicad-python {meta['kicad_python_version']}, "
        f"checked on {meta['checked_on']}",
        "",
        "## Summary",
        "",
        "| status | symbols |",
        "| --- | --- |",
    ]
    for status in mapping.ALL_STATUSES:
        lines.append(f"| {status} | {summary['counts'][status]} |")

    lines += ["", "## Action plugin classes", ""]
    if summary["action_plugin_classes"]:
        lines += [f"- `{item}`" for item in summary["action_plugin_classes"]]
    else:
        lines.append("_None found._")

    for title, key in (
        ("Unmapped symbols", "unmapped_symbols"),
        ("Unknown symbols", "unknown_symbols"),
        ("Unparsed files", "unparsed_files"),
    ):
        lines += ["", f"## {title}", ""]
        if summary[key]:
            lines += [f"- `{name}`" for name in summary[key]]
        else:
            lines.append("_None._")

    lines += ["", "## Symbols", "", "| symbol | status | IPC equivalent | uses | note |",
              "| --- | --- | --- | --- | --- |"]
    if report["symbols"]:
        for name, entry in report["symbols"].items():
            ipc = f"`{entry['ipc']}`" if entry["ipc"] else "-"
            note = str(entry["note"]).replace("|", "\\|")
            lines.append(f"| `{name}` | {entry['status']} | {ipc} | {entry['uses']} | {note} |")
    else:
        lines.append("| _none_ | | | | |")

    lines += ["", "## Findings", "", "| file | line | symbol | kind |", "| --- | --- | --- | --- |"]
    if report["findings"]:
        for finding in report["findings"]:
            lines.append(
                f"| `{finding['file']}` | {finding['line']} | "
                f"`{finding['symbol']}` | {finding['kind']} |"
            )
    else:
        lines.append("| _none_ | | | |")

    lines += ["", "## Warnings", ""]
    if report["warnings"]:
        lines += [f"- {warning}" for warning in report["warnings"]]
    else:
        lines.append("_None._")

    lines.append("")
    return "\n".join(lines)
