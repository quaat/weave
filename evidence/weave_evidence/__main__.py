# SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
# SPDX-License-Identifier: MIT
"""Command line: python3 -m evidence.weave_evidence <command> (run from the repository root).

Exit status: 0 when every input is accepted or every step succeeds; 1 when a
document is refused or invalid, a hash does not recompute, or a conversion is
refused; 2 for a usage error.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .documents import (ENVELOPE, TRACE, assess, assess_file, canonical_bytes, implemented_formats, parse,
                        sha256_bytes, verify_hashes)
from .netexport import ExportError, export
from .traces import ConversionError
from .wrap import WRAPPERS, Context, wrap

ROOT = Path(__file__).resolve().parents[2]


def report(path, assessment) -> bool:
    if assessment.accepted:
        print(f"valid {path} ({assessment.format})")
    else:
        word = "refused" if assessment.refused else "invalid"
        print(f"{word} {path}")
        for error in assessment.errors:
            print(f"  {error}")
    return assessment.accepted


def cmd_formats(args) -> int:
    for fmt in implemented_formats():
        print(fmt)
    return 0


def cmd_validate(args) -> int:
    ok = True
    for path in args.files:
        ok = report(path, assess_file(Path(path))) and ok
    return 0 if ok else 1


def slug(rel: str, pointer: str) -> str:
    return rel.replace("/", "__") + pointer.replace("/", "_")


def cmd_wrap(args) -> int:
    root = Path(args.root).resolve()
    files = args.files or list(WRAPPERS)
    out = Path(args.out) if args.out else None
    try:
        results = [wrap(root, rel) for rel in files]
    except ConversionError as error:
        print(f"refused: {error}", file=sys.stderr)
        return 1
    ok = True
    for result in results:
        print(f"{result.path}: {len(result.envelopes)} envelopes, {len(result.traces)} traces")
        for pointer, reason in result.not_wrapped:
            print(f"  not wrapped {pointer}: {reason}")
        for document in result.envelopes + result.traces:
            assessment = assess(document)
            if not assessment.accepted:
                ok = report(result.path, assessment) and ok
        if out is None:
            continue
        (out / "envelopes").mkdir(parents=True, exist_ok=True)
        (out / "traces").mkdir(parents=True, exist_ok=True)
        for env in result.envelopes:
            (out / "envelopes" / f"{slug(result.path, env['claim']['pointer'])}.json").write_bytes(canonical_bytes(env))
        for trace in result.traces:
            data = canonical_bytes(trace)
            (out / "traces" / f"{sha256_bytes(data)}.json").write_bytes(data)
    return 0 if ok else 1


def cmd_verify(args) -> int:
    root = Path(args.root).resolve()
    ok = True
    for name in args.files:
        path = Path(name)
        assessment = assess_file(path)
        if assessment.accepted and assessment.format != ENVELOPE:
            assessment.errors.append(f"verify reads {ENVELOPE} documents, not {assessment.format}")
        if not assessment.accepted:
            ok = report(path, assessment) and ok
            continue
        envelope = parse(path.read_text(encoding="utf-8"))
        errors = verify_hashes(envelope, root)
        if envelope["trace"] is not None:
            trace_path = path.parent.parent / "traces" / f"{envelope['trace']['sha256']}.json"
            if not trace_path.is_file():
                errors.append(f"trace {trace_path} not found")
            else:
                data = trace_path.read_bytes()
                trace = assess(parse(data.decode("utf-8")))
                if sha256_bytes(data) != envelope["trace"]["sha256"] or trace.format != TRACE or not trace.accepted:
                    errors.append(f"trace {trace_path} does not hash to the recorded sha256 or is not a valid {TRACE}")
        if errors:
            ok = False
            print(f"mismatch {path}")
            for error in errors:
                print(f"  {error}")
        else:
            print(f"hashes recompute {path}")
    return 0 if ok else 1


def cmd_export_net(args) -> int:
    root = Path(args.root).resolve()
    try:
        document = export(Path(args.source), args.profile, root, Context(root).revision)
    except ExportError as error:
        print(f"refused: {error}", file=sys.stderr)
        return 1
    assessment = assess(document)
    if not assessment.accepted:
        report(args.source, assessment)
        return 1
    data = canonical_bytes(document)
    if args.out:
        Path(args.out).write_bytes(data)
    else:
        sys.stdout.buffer.write(data)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m evidence.weave_evidence", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", action="version", version=f"weave_evidence {__version__}")
    parser.add_argument("--root", default=str(ROOT), help="repository root (default: this checkout)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("formats", help="list the format identifiers this reader implements").set_defaults(func=cmd_formats)
    p = sub.add_parser("validate", help="check documents; unknown or missing formats are refused")
    p.add_argument("files", nargs="+")
    p.set_defaults(func=cmd_validate)
    p = sub.add_parser("wrap", help="wrap existing evidence files in envelopes")
    p.add_argument("files", nargs="*", help=f"repository-relative paths (default: all of {', '.join(WRAPPERS)})")
    p.add_argument("--out", help="write envelopes/ and traces/ under this directory")
    p.set_defaults(func=cmd_wrap)
    p = sub.add_parser("verify", help="validate envelopes and recompute their hashes")
    p.add_argument("files", nargs="+", help="envelope files written by 'wrap --out'")
    p.set_defaults(func=cmd_verify)
    p = sub.add_parser("export-net", help="export a canonical net from a prototype net source")
    p.add_argument("source")
    p.add_argument("--profile", choices=["N0", "N1"], required=True)
    p.add_argument("--out")
    p.set_defaults(func=cmd_export_net)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
