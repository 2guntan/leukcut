from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from leukcut.manifest import APPROVED, collect_findings, has_errors, load_manifest, relative_display, status_counts
from leukcut.render import render


EXIT_OK = 0
EXIT_STRICT_WARNING = 1
EXIT_VALIDATION = 2
EXIT_GATE = 3
EXIT_RUNTIME = 4


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="leukcut", description="Deterministic Waraba shot-manifest assembler")
    parser.add_argument("--version", action="version", version="leukcut 1.0.0")
    subparsers = parser.add_subparsers(dest="command", required=True)

    check = subparsers.add_parser("check", help="validate a shot manifest and its inputs")
    check.add_argument("manifest", nargs="?", help="manifest path (default: the sole *.manifest.yaml in cwd)")
    check.add_argument("--strict", action="store_true", help="exit 1 when warnings are present")

    status = subparsers.add_parser("status", help="print the shot status table")
    status.add_argument("manifest", nargs="?", help="manifest path (default: the sole *.manifest.yaml in cwd)")

    animatic = subparsers.add_parser("animatic", help="render an animatic with burn-ins")
    animatic.add_argument("manifest", nargs="?", help="manifest path (default: the sole *.manifest.yaml in cwd)")
    animatic.add_argument("-o", "--output", required=True, help="target .mp4 path")
    animatic.add_argument("--allow-pending", action="store_true", help="render unapproved shots as indigo slates")

    final = subparsers.add_parser("final", help="render a final cut without burn-ins")
    final.add_argument("manifest", nargs="?", help="manifest path (default: the sole *.manifest.yaml in cwd)")
    final.add_argument("-o", "--output", required=True, help="target .mp4 path")
    return parser


def _print_findings(findings: list) -> None:
    for finding in findings:
        print(finding.format())


def _print_summary(manifest) -> None:
    counts = status_counts(manifest)
    print("STATUS      COUNT")
    for status in ("pending", "generated", "approved", "locked"):
        print(f"{status:<11} {counts[status]:>5}")
    print(f"TOTAL       {len(manifest.shots):>5}")


def _check(manifest_value: str | None, strict: bool) -> int:
    manifest = load_manifest(manifest_value)
    findings = collect_findings(manifest)
    _print_findings(findings)
    _print_summary(manifest)
    if has_errors(findings):
        return EXIT_VALIDATION
    if strict and findings:
        return EXIT_STRICT_WARNING
    return EXIT_OK


def _status(manifest_value: str | None) -> int:
    manifest = load_manifest(manifest_value)
    if has_errors(manifest.findings):
        _print_findings(manifest.findings)
        return EXIT_VALIDATION
    print("ID       TIME              DURATION  STATUS     RESOLVED FILE                              VERSION")
    for shot in manifest.shots:
        print(
            f"{shot.id:<8} {str(shot.raw.get('t_in')):>7}-{str(shot.raw.get('t_out')):<7} "
            f"{float(shot.duration):>7.1f}s  {shot.status:<10} "
            f"{relative_display(shot.resolved_file, manifest.root):<42} v{shot.version:02d}"
        )
    return EXIT_OK


def _render_command(manifest_value: str | None, output_value: str, mode: str, allow_pending: bool) -> int:
    manifest = load_manifest(manifest_value)
    findings = collect_findings(manifest)
    errors = [finding for finding in findings if finding.level == "ERROR"]
    if errors:
        _print_findings(errors)
        return EXIT_VALIDATION
    blockers = [shot for shot in manifest.shots if shot.status not in APPROVED]
    if blockers and not allow_pending:
        for shot in blockers:
            print(f"GATE {shot.id} status is {shot.status}; requires approved or locked")
        return EXIT_GATE
    result = render(manifest, Path(output_value), mode, allow_pending)
    if not result.ok:
        print(f"RUNTIME ffmpeg {result.message}", file=sys.stderr)
        return EXIT_RUNTIME
    print(f"OK {Path(output_value).expanduser().resolve()}")
    print(f"OK {Path(output_value).expanduser().resolve().parent / (manifest.short_id + '.srt')}")
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "check":
        return _check(args.manifest, args.strict)
    if args.command == "status":
        return _status(args.manifest)
    if args.command == "animatic":
        return _render_command(args.manifest, args.output, "animatic", args.allow_pending)
    if args.command == "final":
        return _render_command(args.manifest, args.output, "final", False)
    return EXIT_RUNTIME


if __name__ == "__main__":
    raise SystemExit(main())
