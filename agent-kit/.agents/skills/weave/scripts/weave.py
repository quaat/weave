#!/usr/bin/env python3
"""Compact, dependency-free interface to the bundled Weave prototype and the kit's pure extension."""
from __future__ import annotations

import argparse
import io
import json
import os
import platform
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
PROTOTYPE = SKILL / "assets" / "prototype"
sys.dont_write_bytecode = True
sys.path.insert(0, str(PROTOTYPE))
sys.path.insert(0, str(SKILL / "scripts"))

from checker import CheckError, check_flow, explore_order, lower_flow_source, parse_net, prove
from simulate import simulate
from verify_certificate import verify
import weave_pure.cli as pure_cli
from weave_pure import PureError, check_source as check_pure_source


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def diagnostic(error: CheckError, path: Path, stage: str) -> dict:
    return {"code": error.code, "message": error.message, "file": str(path),
            "line": error.line, "stage": stage}


def checked_net(path: Path, max_states: int = 10000):
    net = parse_net(read(path))
    certificate = prove(net)
    ordering = explore_order(net, max_states)
    return net, certificate, ordering


def summary(certificate: dict, ordering: dict) -> dict:
    return {
        "accounting": {"status": "PROVED", "invariants": [r["name"] for r in certificate["invariants"]]},
        "ordering": {"status": "CHECKED WITHIN BOUNDS", "states": ordering["states"],
                     "edges": ordering["edges"], "orders": ordering["orders"],
                     "stock": ordering["stock"], "admission_limit": ordering["admission_limit"],
                     "place_bound": ordering["place_bound"], "max_states": ordering["max_states"],
                     "properties": [r["name"] for r in ordering["properties"]],
                     "assumptions": ordering["assumptions"]},
    }


def write_output(path: Path, text: str, inputs: list[Path]) -> None:
    if path.resolve() in {p.resolve() for p in inputs}:
        raise ValueError("Output path must differ from every input path")
    path.write_text(text, encoding="utf-8")


def default_manifest() -> Path:
    for parent in SKILL.parents:
        candidate = parent / "examples" / "manifest.json"
        if candidate.is_file():
            return candidate
    raise ValueError("No teaching manifest found; provide examples --manifest PATH")


def run_examples(path: Path) -> tuple[dict, int]:
    manifest = json.loads(read(path))
    base = path.parent
    net_path = base / manifest["net"]
    source = read(net_path)
    net, certificate, ordering = checked_net(net_path)
    results = []
    for item in manifest["cases"]:
        file = base / item["file"]
        actual, error_detail = "ACCEPT", None
        try:
            if item["kind"] == "flow":
                names = check_flow(net, read(file))
                if "flows" in item and names != item["flows"]:
                    raise ValueError(f"Unexpected flow names in {file}: {names}")
            elif item["kind"] == "net_append":
                mutated = parse_net(source + "\n" + read(file))
                prove(mutated)
                explore_order(mutated)
            elif item["kind"] == "net":
                checked_net(file)
            elif item["kind"] == "pure":
                check_pure_source(read(file))
            else:
                raise ValueError(f"Unknown example kind: {item['kind']}")
        except (CheckError, PureError) as error:
            actual = error.code
            error_detail = diagnostic(error, file, item["kind"])
        expected = item["expect"]
        results.append({"file": item["file"], "expected": expected, "actual": actual,
                        "ok": actual == expected, "lesson": item["lesson"],
                        **({"diagnostic": error_detail} if error_detail else {})})
    for item in manifest.get("scenarios", []):
        run = simulate(net, read(base / item["file"]), item["entry"], item["outcome"])
        actual = {p: run["marking"].get(p) for p in item["marking"]}
        results.append({"file": item["file"], "outcome": item["outcome"],
                        "expected": item["marking"], "actual": actual,
                        "ok": actual == item["marking"], "lesson": "Scripted final marking"})
    ok = all(r["ok"] for r in results)
    return {"command": "examples", "ok": ok, "checks": len(results),
            "passed": sum(r["ok"] for r in results), "results": results,
            **summary(certificate, ordering)}, 0 if ok else 1


def positive_int(text: str) -> int:
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return value


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--json", action="store_true", help="Emit one JSON result; put before the command")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="Inspect Python and bundled files")
    for name in ("analyze", "check", "lower", "simulate"):
        s = sub.add_parser(name)
        s.add_argument("--net", type=Path, default=PROTOTYPE / "Inventory.weave")
        if name != "simulate":
            s.add_argument("--max-states", type=int, default=10000)
        if name == "analyze":
            s.add_argument("--certificate", type=Path)
        if name == "check":
            s.add_argument("files", nargs="+", type=Path)
        if name in {"lower", "simulate"}:
            s.add_argument("file", type=Path)
        if name == "lower":
            s.add_argument("--output", required=True, type=Path)
        if name == "simulate":
            s.add_argument("--entry", required=True)
            s.add_argument("--outcome", choices=["Ok", "Err", "Unknown", "all"], default="all")
            s.add_argument("--trace", action="store_true", help="Include all marking snapshots")
    s = sub.add_parser("verify", help="Recheck accounting certificate only")
    s.add_argument("certificate", type=Path)
    s.add_argument("--net", type=Path, default=PROTOTYPE / "Inventory.weave")
    s = sub.add_parser("examples", help="Check teaching examples against expected outcomes")
    s.add_argument("--manifest", type=Path)
    s = sub.add_parser("test", help="Run bundled prototype regression tests")
    s.add_argument("--pattern", default="test_*.py", help="unittest file pattern")
    s.add_argument("--verbose", action="store_true")
    pure_cli.add_commands(sub, positive_int)
    return p


def execute(args) -> tuple[dict, int]:
    label = getattr(args, "net", PROTOTYPE)
    stage = "net"
    try:
        if args.command == "doctor":
            files = ["checker.py", "simulate.py", "Inventory.weave", "verify_certificate.py", "tests/test_checker.py"]
            missing = [f for f in files if not (PROTOTYPE / f).is_file()]
            ok = sys.version_info >= (3, 11) and not missing
            return {"command": "doctor", "ok": ok, "python": platform.python_version(),
                    "minimum_python": "3.11", "reference_python": "3.12.14",
                    "third_party_dependencies": [], "prototype": str(PROTOTYPE), "missing": missing}, 0 if ok else 2
        if args.command == "test":
            command = [sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-p", args.pattern,
                       "-v" if args.verbose else "-q"]
            result = subprocess.run(command, cwd=PROTOTYPE, capture_output=True, text=True,
                                    timeout=120, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
            output = (result.stdout + result.stderr).strip()
            # unittest reports success even when a pattern selects zero tests.
            ok = result.returncode == 0 and "Ran 0 tests" not in output
            return {"command": "test", "ok": ok, "output": output}, 0 if ok else 1
        if args.command in ("check-pure", "run-pure"):
            stage, label = "pure", getattr(args, "file", None) or args.files[0]
            return pure_cli.execute(args)
        if args.command == "examples":
            stage = "examples"
            label = args.manifest or default_manifest()
            return run_examples(label)
        if args.command == "verify":
            stage = "certificate"
            source = read(args.net)
            label = args.certificate
            count = verify(source, json.loads(read(args.certificate)))
            return {"command": "verify", "ok": True, "status": "RECHECKED",
                    "invariants": count, "scope": "Accounting only; shared parser, not an independent formal proof"}, 0
        net, certificate, ordering = checked_net(args.net, getattr(args, "max_states", 10000))
        result = {"command": args.command, "ok": True, "net": str(args.net), **summary(certificate, ordering)}
        if args.command == "analyze":
            if args.certificate:
                write_output(args.certificate, json.dumps(certificate, indent=2) + "\n", [args.net])
                result["certificate"] = str(args.certificate)
        elif args.command == "check":
            result["files"] = []
            for file in args.files:
                stage, label = "flow", file
                try:
                    names = check_flow(net, read(file))
                    result["files"].append({"file": str(file), "ok": True, "flows": names})
                except CheckError as error:
                    result["ok"] = False
                    result["files"].append({"file": str(file), "ok": False,
                                            "diagnostic": diagnostic(error, file, "flow")})
        elif args.command == "lower":
            stage, label = "flow", args.file
            source = read(args.file)
            names = check_flow(net, source)
            lowered = lower_flow_source(source)
            if check_flow(net, lowered) != names:
                raise ValueError("Lowered declarations differ from source")
            write_output(args.output, lowered, [args.net, args.file])
            result.update({"output": str(args.output), "flows": names, "status": "CHECKED LOWERING"})
        elif args.command == "simulate":
            stage, label = "flow", args.file
            source = read(args.file)
            check_flow(net, source)
            stage = "execution"
            outcomes = ["Ok", "Err", "Unknown"] if args.outcome == "all" else [args.outcome]
            result["status"] = "SCRIPTED"
            result["runs"] = []
            for outcome in outcomes:
                run = simulate(net, source, args.entry, outcome)
                if not args.trace:
                    run.pop("events")
                result["runs"].append(run)
        return result, 0 if result["ok"] else 1
    except CheckError as error:
        return {"command": args.command, "ok": False, "diagnostic": diagnostic(error, label, stage)}, 1
    except (OSError, ValueError, KeyError, TypeError, AssertionError, subprocess.TimeoutExpired) as error:
        return {"command": args.command, "ok": False,
                "diagnostic": {"code": "TOOL_ERROR", "stage": stage, "file": str(label),
                               "line": 0, "message": str(error)}}, 2


def print_diagnostic(d: dict) -> None:
    where = f"{d['file']}:{d['line']}" if d.get("line") else d["file"]
    print(f"{where}: {d['code']} [{d['stage']}]\n  " + d["message"].replace("\n", "\n  "))


def render(result: dict) -> None:
    if "diagnostic" in result:
        print_diagnostic(result["diagnostic"])
        return
    command = result["command"]
    if command in ("check-pure", "run-pure"):
        pure_cli.render(result, print_diagnostic)
    elif command == "doctor":
        print(f"{'READY' if result['ok'] else 'NOT READY'} Python {result['python']}; no third-party dependencies")
        print(f"Prototype: {result['prototype']}")
        if result["missing"]:
            print("Missing: " + ", ".join(result["missing"]))
    elif command == "test":
        print(result["output"])
        if not result["ok"]:
            print("FAILED: tests failed or no tests were selected")
    elif command == "examples":
        print(f"{'PASS' if result['ok'] else 'FAIL'} {result['passed']}/{result['checks']} example expectations")
        for item in result["results"]:
            if not item["ok"]:
                print(json.dumps(item, ensure_ascii=False))
    elif command == "verify":
        print(f"RECHECKED {result['invariants']} accounting invariants; ordering not rechecked")
    else:
        if "ordering" in result:
            order = result["ordering"]
            print(f"PROVED {len(result['accounting']['invariants'])} accounting invariants; "
                  f"CHECKED WITHIN BOUNDS {order['states']} states/{order['edges']} edges "
                  f"(orders=1, stock=1, admission<=1, tokens/place<={order['place_bound']})")
        for item in result.get("files", []):
            if item["ok"]:
                print(f"CHECKED {item['file']}: {', '.join(item['flows'])}")
            else:
                print_diagnostic(item["diagnostic"])
        if "output" in result:
            print(f"CHECKED LOWERING -> {result['output']}")
        if "certificate" in result:
            print(f"CERTIFICATE -> {result['certificate']}")
        for run in result.get("runs", []):
            occupied = ", ".join(f"{k}={v}" for k, v in run["marking"].items() if v)
            print(f"SCRIPTED {run['outcome']} via {run['entry']}: {occupied}")
            for event in run.get("events", []):
                print("  " + json.dumps(event, ensure_ascii=False))


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    # Keep upstream incidental output from corrupting the JSON protocol.
    captured = io.StringIO()
    with redirect_stdout(captured), redirect_stderr(captured):
        result, status = execute(args)
    if captured.getvalue():
        result["upstream_output"] = captured.getvalue()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    else:
        render(result)
    return status


if __name__ == "__main__":
    raise SystemExit(main())
