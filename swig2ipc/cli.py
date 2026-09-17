"""Command line interface for swig2ipc."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from . import __version__, mapping
from .report import build_report, render_markdown
from .skeleton import DEFAULT_ACTION_IDENTIFIER, DEFAULT_ENTRYPOINT, SkeletonError, write_skeleton

EXIT_OK = 0
EXIT_FAIL_ON = 1
EXIT_USAGE = 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="swig2ipc",
        description="Readiness report for KiCad plugins moving from SWIG pcbnew to the IPC API.",
    )
    parser.add_argument("--version", action="version", version=f"swig2ipc {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan = subparsers.add_parser("scan", help="report SWIG pcbnew usage in a plugin source tree")
    scan.add_argument("directory", type=Path, help="plugin source tree to scan")
    scan.add_argument(
        "--format", choices=("json", "markdown"), default="json", help="output format"
    )
    scan.add_argument(
        "--fail-on",
        choices=("none", "unmapped", "unknown"),
        default="none",
        help="exit 1 when unmapped symbols (or, with 'unknown', unmapped or unknown ones) are found",
    )

    skeleton = subparsers.add_parser("skeleton", help="write an IPC plugin manifest skeleton")
    skeleton.add_argument("--name", required=True, help="human readable plugin name")
    skeleton.add_argument("--identifier", required=True, help="reverse-DNS plugin identifier")
    skeleton.add_argument("--out", required=True, type=Path, help="output directory")
    skeleton.add_argument("--description", help="plugin description (defaults to the name)")
    skeleton.add_argument(
        "--entrypoint", default=DEFAULT_ENTRYPOINT, help="script KiCad runs for the action"
    )
    skeleton.add_argument(
        "--action-identifier",
        default=DEFAULT_ACTION_IDENTIFIER,
        help="identifier of the generated action",
    )
    return parser


def _cmd_scan(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    directory: Path = args.directory
    if not directory.exists():
        parser.error(f"no such directory: {directory}")
    if not directory.is_dir():
        parser.error(f"not a directory: {directory}")

    report = build_report(directory)
    if args.format == "markdown":
        sys.stdout.write(render_markdown(report))
    else:
        json.dump(report, sys.stdout, indent=2)
        sys.stdout.write("\n")

    counts = report["summary"]["counts"]
    failing = counts[mapping.STATUS_UNMAPPED]
    if args.fail_on == "unknown":
        failing += counts[mapping.STATUS_UNKNOWN]
    if args.fail_on != "none" and failing:
        return EXIT_FAIL_ON
    return EXIT_OK


def _cmd_skeleton(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    try:
        written = write_skeleton(
            args.out,
            name=args.name,
            identifier=args.identifier,
            description=args.description,
            entrypoint=args.entrypoint,
            action_identifier=args.action_identifier,
        )
    except SkeletonError as exc:
        parser.error(str(exc))
    except OSError as exc:
        parser.error(f"could not write skeleton: {exc}")
    for path in written:
        print(f"wrote {path}")
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)  # argparse exits 2 on usage errors
    if args.command == "scan":
        return _cmd_scan(args, parser)
    return _cmd_skeleton(args, parser)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
