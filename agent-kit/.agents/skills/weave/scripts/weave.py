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
from weave_diagnostics import from_check_error, from_pure_error, location, tool_error
from weave_labels import BOUNDED, FLOW, NOT_ESTABLISHED, PROVED, SCRIPTED, VIOLATED, claim_line, labelled
from weave_pure import PureError, check_source as check_pure_source


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def diagnostic(error: CheckError, path: Path, stage: str, source: str | None = None) -> dict:
    """A weave-diagnostic-v1 document for a checker error found in ``path``."""
    if source is None:
        try:
            source = read(Path(path))
        except (OSError, UnicodeDecodeError):
            source = ""
    return from_check_error(error, str(path), source, stage)


def appended_diagnostic(error: CheckError, net_path: Path, net_source: str, file: Path, fragment: str,
                        stage: str) -> dict:
    """A diagnostic for a fragment appended to a net: spans in the fragment refer to the fragment's file."""
    combined = net_source + "\n" + fragment
    document = from_check_error(error, str(file), combined, stage)
    offset = len((net_source + "\n").splitlines())
    for span in [document["span"]] + [r["span"] for r in document["related"]]:
        if span["start"]["line"] > offset:
            for point in (span["start"], span["end"]):
                point["line"] -= offset
        else:
            span["file"] = str(net_path)
    return document


class NetFailure(Exception):
    """A checker error in a net, with the claims established before it (accounting, a failed ordering check)."""

    def __init__(self, error: CheckError, claims: dict):
        super().__init__(str(error))
        self.error, self.claims = error, claims


# Ordering-check diagnostics that decide the ordering claim (specification, diagnostics
# chapter): E320 is a modeled counterexample, so the claim is VIOLATED; E321 is an exhausted
# bound or state budget, reported as NOT ESTABLISHED, never as a successful check.
ORDERING_FAILURES = {"E320": (VIOLATED, "counterexample in the diagnostic"),
                     "E321": (NOT_ESTABLISHED, "token bound or state budget exhausted")}


def accounting_claim(certificate: dict) -> dict:
    return labelled(PROVED, invariants=[r["name"] for r in certificate["invariants"]])


def ordering_claim(ordering: dict) -> dict:
    return labelled(BOUNDED, states=ordering["states"], edges=ordering["edges"], orders=ordering["orders"],
                    stock=ordering["stock"], admission_limit=ordering["admission_limit"],
                    place_bound=ordering["place_bound"], max_states=ordering["max_states"],
                    properties=[r["name"] for r in ordering["properties"]],
                    assumptions=ordering["assumptions"])


def checked_net(path: Path, max_states: int = 10000):
    """Parse, prove and explore a net. Returns ``(net, claims)``; raises NetFailure on a checker error."""
    net = parse_net(read(path))
    certificate = prove(net)
    claims = {"accounting": accounting_claim(certificate)}
    try:
        ordering = explore_order(net, max_states)
    except CheckError as error:
        if error.code in ORDERING_FAILURES:
            label, reason = ORDERING_FAILURES[error.code]
            claims["ordering"] = labelled(label, diagnostic_code=error.code, reason=reason, max_states=max_states)
        raise NetFailure(error, claims) from error
    claims["ordering"] = ordering_claim(ordering)
    return net, certificate, claims


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
    net, _, claims = checked_net(net_path)
    results = []
    for item in manifest["cases"]:
        file = base / item["file"]
        actual, error_detail = "ACCEPT", None
        text = read(file)
        try:
            if item["kind"] == "flow":
                names = check_flow(net, text)
                if "flows" in item and names != item["flows"]:
                    raise ValueError(f"Unexpected flow names in {file}: {names}")
            elif item["kind"] == "net_append":
                mutated = parse_net(source + "\n" + text)
                prove(mutated)
                explore_order(mutated)
            elif item["kind"] == "net":
                try:
                    checked_net(file)
                except NetFailure as failure:
                    raise failure.error from None
            elif item["kind"] == "pure":
                check_pure_source(text)
            else:
                raise ValueError(f"Unknown example kind: {item['kind']}")
        except PureError as error:
            actual, error_detail = error.code, from_pure_error(error, str(file), text)
        except CheckError as error:
            actual = error.code
            if item["kind"] == "net_append":
                error_detail = appended_diagnostic(error, net_path, source, file, text, "net")
            else:
                error_detail = diagnostic(error, file, "net" if item["kind"] == "net" else item["kind"], text)
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
    # Each result is an expectation of the teaching corpus (step status ``ok``), not a claim;
    # the claims are those about the manifest's net.
    return {"command": "examples", "ok": ok, "checks": len(results),
            "passed": sum(r["ok"] for r in results), "results": results, **claims}, 0 if ok else 1


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


def flow_claim(file: Path, names: list[str], **extra) -> dict:
    """One CHECKED flow claim: the F0 checks passed for every flow declared in ``file``."""
    return {"file": str(file), "ok": True, **labelled(FLOW, flows=names, **extra)}


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
            certificate = json.loads(read(args.certificate))
            count = verify(source, certificate)
            names = [r["name"] for r in certificate["invariants"]]
            if len(names) != count:
                raise ValueError("Certificate invariant count disagrees with the recheck")
            # Rechecking the certificate's arithmetic against the source discharges the same
            # invariant obligations again, so the claim is PROVED, within the stated scope.
            return {"command": "verify", "ok": True, "certificate": str(args.certificate),
                    "accounting": labelled(PROVED, invariants=names, method="certificate recheck",
                                           scope="Accounting only; verify_certificate.py shares the parser, "
                                                 "not an independent formal proof; ordering not rechecked")}, 0
        net, certificate, claims = checked_net(args.net, getattr(args, "max_states", 10000))
        result = {"command": args.command, "ok": True, "net": str(args.net), **claims}
        if args.command == "analyze":
            if args.certificate:
                write_output(args.certificate, json.dumps(certificate, indent=2) + "\n", [args.net])
                result["certificate"] = str(args.certificate)
        elif args.command == "check":
            result["files"] = []
            for file in args.files:
                stage, label = "flow", file
                text = read(file)
                try:
                    names = check_flow(net, text)
                    result["files"].append(flow_claim(file, names))
                except CheckError as error:
                    result["ok"] = False
                    result["files"].append({"file": str(file), "ok": False,
                                            "diagnostic": diagnostic(error, file, "flow", text)})
        elif args.command == "lower":
            stage, label = "flow", args.file
            source = read(args.file)
            names = check_flow(net, source)
            lowered = lower_flow_source(source)
            if check_flow(net, lowered) != names:
                raise ValueError("Lowered declarations differ from source")
            write_output(args.output, lowered, [args.net, args.file])
            result.update({"output": str(args.output), "flows": names,
                           "files": [flow_claim(args.file, names),
                                     flow_claim(args.output, names, lowered_from=str(args.file))]})
        elif args.command == "simulate":
            stage, label = "flow", args.file
            source = read(args.file)
            check_flow(net, source)
            stage = "execution"
            outcomes = ["Ok", "Err", "Unknown"] if args.outcome == "all" else [args.outcome]
            result["runs"] = []
            for outcome in outcomes:
                run = simulate(net, source, args.entry, outcome)
                if not args.trace:
                    run.pop("events")
                # simulate() raises on a disabled transition or failed assertion, so a returned run
                # is one passed scenario. Its scripted outcome (Ok, Err, Unknown) is an application
                # outcome, and runtime_status is the status of the run; neither is a label.
                result["runs"].append({"claim_label": SCRIPTED, "runtime_status": "completed", **run})
        return result, 0 if result["ok"] else 1
    except NetFailure as failure:
        # Claims established before the failure stay attached; E320 and E321 add the ordering claim.
        return {"command": args.command, "ok": False, **failure.claims,
                "diagnostic": diagnostic(failure.error, label, stage)}, 1
    except CheckError as error:
        return {"command": args.command, "ok": False, "diagnostic": diagnostic(error, label, stage)}, 1
    except (OSError, ValueError, KeyError, TypeError, AssertionError, subprocess.TimeoutExpired) as error:
        return {"command": args.command, "ok": False, "diagnostic": tool_error(str(error), label, stage)}, 2


def print_diagnostic(d: dict) -> None:
    rule = f" ({d['rule']})" if d.get("rule") else ""
    print(f"{location(d)}: {d['code']}{rule} [{d['stage']}]\n  " + d["message"].replace("\n", "\n  "))
    for item in d.get("related", []):
        start = item["span"]["start"]
        print(f"  {item['span']['file']}:{start['line']}:{start['column']}: {item['role']}: {item['label']}")


def net_claim_lines(result: dict) -> None:
    if "accounting" in result:
        acc = result["accounting"]
        if acc.get("method") == "certificate recheck":
            print(claim_line(acc["claim_label"], f"{len(acc['invariants'])} accounting invariants rechecked from "
                                                 f"{result['certificate']} ({acc['scope']})"))
        else:
            print(claim_line(acc["claim_label"], f"{len(acc['invariants'])} accounting invariants"))
    if "ordering" in result:
        order = result["ordering"]
        if "diagnostic_code" in order:
            print(claim_line(order["claim_label"], f"ordering: {order['reason']} ({order['diagnostic_code']} below)"))
        else:
            print(claim_line(order["claim_label"],
                             f"{order['states']} states/{order['edges']} edges "
                             f"(orders=1, stock=1, admission<=1, tokens/place<={order['place_bound']})"))


def render(result: dict) -> None:
    """Text output: claims as ``LABEL statement`` lines, everything else under a lower-case name."""
    command = result["command"]
    if command in ("check-pure", "run-pure"):
        pure_cli.render(result, print_diagnostic)
        return
    net_claim_lines(result)
    if "diagnostic" in result:
        print_diagnostic(result["diagnostic"])
        return
    if command == "doctor":
        print(f"tool status: {'READY' if result['ok'] else 'NOT READY'} Python {result['python']}; "
              "no third-party dependencies")
        print(f"prototype: {result['prototype']}")
        if result["missing"]:
            print("missing: " + ", ".join(result["missing"]))
    elif command == "test":
        print("raw output (bundled prototype unittest; not a claim):")
        for line in result["output"].splitlines():
            print("  " + line if line else "")
        print(f"tool status: {'PASS bundled prototype regression tests' if result['ok'] else 'FAIL tests failed or no tests were selected'}")
    elif command == "verify":
        pass
    elif command == "examples":
        print(f"tool status: {'PASS' if result['ok'] else 'FAIL'} {result['passed']}/{result['checks']} example expectations")
        for item in result["results"]:
            if not item["ok"]:
                print(json.dumps(item, ensure_ascii=False))
    else:
        for item in result.get("files", []):
            if item["ok"]:
                lowered = f" (lowered from {item['lowered_from']})" if "lowered_from" in item else ""
                print(claim_line(item["claim_label"], f"{item['file']}{lowered}: {', '.join(item['flows'])}"))
            else:
                print_diagnostic(item["diagnostic"])
        if "certificate" in result:
            print(f"certificate: written to {result['certificate']}")
        for run in result.get("runs", []):
            occupied = ", ".join(f"{k}={v}" for k, v in run["marking"].items() if v)
            print(claim_line(run["claim_label"], f"{run['outcome']} via {run['entry']}: {occupied}"))
            print(f"  runtime status: {run['runtime_status']}")
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
