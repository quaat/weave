#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
# SPDX-License-Identifier: MIT
"""Run the modules-1 conformance corpus (docs/chapters/names.rst, quaat/weave#12).

The corpus is ``examples/modules/manifest.json`` (format
``weave-modules-conformance-v1``), kept apart from the F0/N0 manifest and the P0
manifest, whose formats are unchanged.

* **check** and **run** cases are P0 programs of several modules. They run through
  the ``weave`` binary named by ``WEAVE_BIN`` or built with ``cargo build --offline
  --locked`` (as in ``p0_differential.py``), the only modules-1 implementation of
  P0 programs. Each result must be the case's code (or ACCEPT, or VALUE with the
  value), the primary span must be in the case's file at its line, the related
  spans must be the listed imports, and every diagnostic must be a valid
  ``weave-diagnostic-v1`` document. Without a binary these cases are recorded as
  not established in ``validation/modules-conformance.json``, never as agreement.
* **flow** cases select a net with a ``use net`` header. This script resolves the
  header itself (an implementation independent of the agent kit's runner), blanks
  the header line and checks the flow with the unchanged reference checker in
  ``reference/prototype/``. Where ``same_as_net`` is given, the result and its
  location must equal those of the ``--net`` form: the same flow with a comment in
  place of the header, checked against that net.

Any disagreement fails.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
EXAMPLES = ROOT / "examples"
MANIFEST = EXAMPLES / "modules/manifest.json"
FORMAT = "weave-modules-conformance-v1"
REPORT = ROOT / "validation/modules-conformance.json"
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "reference/prototype"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(REPO))
from checker import CheckError, check_flow, parse_net  # noqa: E402
from p0_differential import rust_binary  # noqa: E402
from spec_checks import as_diagnostic  # noqa: E402

try:  # The evidence reader validates the binary's diagnostics when it is present.
    from evidence.weave_evidence.documents import assess  # noqa: E402
except ImportError:  # pragma: no cover - the repository always ships it
    assess = None

IDENT = r"[A-Za-z_][A-Za-z0-9_]*"
HEADER = re.compile(rf"use[ ]+net[ ]+(?P<path>{IDENT}(?:[ ]*\.[ ]*{IDENT})*)[ ]*(?:#.*)?", re.ASCII)
TWIN_LINE = "# net given with --net"


def manifest() -> dict:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if data.get("format") != FORMAT:
        raise ValueError(f"{MANIFEST}: unsupported format {data.get('format')!r}; expected {FORMAT}")
    return data


# ---------------------------------------------------------------- use net (flow cases)

class ModuleFailure(Exception):
    """A modules-1 failure of a flow header: code, line and column."""

    def __init__(self, code: str, line: int, column: int, message: str):
        super().__init__(message)
        self.code, self.line, self.column = code, line, column


def header(text: str) -> tuple[int, str, int] | None:
    """(line, dotted path, column of the path) of the use net header, or None.

    The header is the first line that is neither blank nor a comment, when it is not
    indented and its first word is ``use``; such a line that is not ``use net a.b``
    is E600 (MOD-FILE-1)."""
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.rstrip("\r")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not re.match(r"use(?![A-Za-z0-9_])", line):
            return None
        found = HEADER.fullmatch(line.rstrip(" "))
        if found is None:
            raise ModuleFailure("E600", number, 1, "malformed use net header")
        return number, re.sub(r"[ ]+", "", found["path"]), found.start("path") + 1
    return None


def resolve(root: Path, dotted: str, line: int, column: int) -> Path:
    """<root>/a/b.weave, by exact names, inside the root once links are resolved."""
    segments = dotted.split(".")
    path, base = root, root.resolve()
    for i, segment in enumerate(segments):
        last = i == len(segments) - 1
        name = segment + ".weave" if last else segment
        names = os.listdir(path) if path.is_dir() else []
        if name not in names:
            code = "E602" if any(n.lower() == name.lower() for n in names) else "E601"
            raise ModuleFailure(code, line, column, f"cannot resolve {dotted}")
        path = path / name
        canonical = path.resolve()
        if canonical != base and base not in canonical.parents:
            raise ModuleFailure("E603", line, column, f"{dotted} leaves the root")
        if last != canonical.is_file():
            raise ModuleFailure("E601", line, column, f"{dotted} is not a file")
    return path


def replace_line(text: str, line: int, new: str) -> str:
    lines = text.splitlines(keepends=True)
    ending = lines[line - 1][len(lines[line - 1].rstrip("\r\n")):]
    lines[line - 1] = new + ending
    return "".join(lines)


def check_with(net_path: Path, text: str, label: str) -> dict:
    """ACCEPT, or the code and primary span of the reference checker's diagnostic."""
    try:
        check_flow(parse_net(net_path.read_text(encoding="utf-8")), text)
    except CheckError as error:
        document = as_diagnostic(error, label, text, "flow")
        return {"code": error.code, "start": document["span"]["start"], "end": document["span"]["end"]}
    return {"code": "ACCEPT"}


def flow_case(case: dict) -> dict:
    """The result of a flow case: code and, for a rejection, its location."""
    file = EXAMPLES / case["file"]
    text = file.read_text(encoding="utf-8")
    root = EXAMPLES / case["root"]
    explicit = EXAMPLES / case["net"] if "net" in case else None
    try:
        # A case's root is explicit (--root): it must contain the flow file (MOD-ROOT-1).
        base = root.resolve()
        if file.resolve() != base and base not in file.resolve().parents:
            raise ModuleFailure("E605", 1, 1, "the flow file is outside the root")
        found = header(text)
        if found is None:
            selected, prepared = explicit, text
        else:
            line, dotted, column = found
            selected = resolve(root, dotted, line, column)
            if explicit is not None and explicit.resolve() != selected.resolve():
                raise ModuleFailure("E610", line, 1, "header and --net select different nets")
            prepared = replace_line(text, line, "")
    except ModuleFailure as failure:
        return {"code": failure.code, "start": {"line": failure.line, "column": failure.column}}
    if selected is None:
        raise ValueError(f"{case['id']}: a flow case needs a header or a net")
    result = check_with(selected, prepared, case["file"])
    if "same_as_net" in case:
        twin = text if found is None else replace_line(text, found[0], TWIN_LINE)
        result["net_form"] = check_with(EXAMPLES / case["same_as_net"], twin, case["file"])
    return result


def assert_flow(case: dict, result: dict) -> None:
    if result["code"] != case["expect"]:
        raise AssertionError(f"{case['id']}: {result['code']}, expected {case['expect']}")
    if "line" in case:
        want = {"line": case["line"], "column": case["column"]}
        if result["start"] != want:
            raise AssertionError(f"{case['id']}: at {result['start']}, expected {want}")
    if "net_form" in result:
        same = {k: v for k, v in result.items() if k != "net_form"}
        if same != result["net_form"]:
            raise AssertionError(f"{case['id']}: header form {same}, --net form {result['net_form']}")


# ---------------------------------------------------------------- P0 programs (Rust)

def rust_case(binary: Path, case: dict) -> dict:
    argv = [str(binary), case["kind"], str(EXAMPLES / case["entry"]), "--json"]
    if "root" in case:
        argv += ["--root", str(EXAMPLES / case["root"])]
    if case["kind"] == "run":
        argv += ["--entry", case["function"], "--args", json.dumps(case["args"])]
    done = subprocess.run(argv, capture_output=True, timeout=300, cwd=ROOT)
    if done.returncode not in (0, 1, 3, 4):
        raise RuntimeError(f"{case['id']}: weave exited {done.returncode}: {done.stderr.decode(errors='replace')}")
    return json.loads(done.stdout)


def where(span: dict) -> list:
    """[file relative to examples/, line] of a diagnostic span."""
    path = Path(span["file"])
    path = (ROOT / path if not path.is_absolute() else path).resolve()
    return [path.relative_to(EXAMPLES.resolve()).as_posix(), span["start"]["line"]]


def assert_rust(case: dict, out: dict) -> dict:
    diagnostics = out["diagnostics"]
    for d in diagnostics:
        if assess is not None:
            verdict = assess(d)
            if not verdict.accepted:
                raise AssertionError(f"{case['id']}: invalid diagnostic: {verdict.errors}")
    if diagnostics:
        actual = diagnostics[0]["code"]
    else:
        actual = "VALUE" if case["kind"] == "run" else "ACCEPT"
    if actual != case["expect"]:
        raise AssertionError(f"{case['id']}: {actual}, expected {case['expect']}")
    row = {"id": case["id"], "expected": case["expect"], "actual": actual}
    if actual == "VALUE":
        if out.get("value") != case["value"]:
            raise AssertionError(f"{case['id']}: value {out.get('value')}, expected {case['value']}")
        row["value"] = case["value"]
    if "file" in case:
        got = where(diagnostics[0]["span"])
        if got != [case["file"], case["line"]]:
            raise AssertionError(f"{case['id']}: at {got}, expected {[case['file'], case['line']]}")
        row["at"] = got
    if "related" in case:
        got = [where(r["span"]) for r in diagnostics[0]["related"]]
        if got != case["related"]:
            raise AssertionError(f"{case['id']}: related {got}, expected {case['related']}")
        row["related"] = got
    return row


def build_report(binary: Path | None, how: str) -> dict:
    data = manifest()
    flows, programs = [], []
    for case in data["cases"]:
        if case["kind"] == "flow":
            result = flow_case(case)
            assert_flow(case, result)
            flows.append({"id": case["id"], "expected": case["expect"], "actual": result["code"],
                          **({"at": result["start"]} if "start" in result else {}),
                          **({"same_as_net_form": True} if "net_form" in result else {})})
        elif case["kind"] in ("check", "run"):
            programs.append(case)
        else:
            raise ValueError(f"{case['id']}: unknown kind {case['kind']}")
    if binary is None:
        rust = {"status": "skipped", "compared": 0,
                "note": f"modules-1 P0 cases not established: {how}."}
    else:
        rows = [assert_rust(case, rust_case(binary, case)) for case in programs]
        rust = {"status": "compared", "binary": how, "compared": len(rows), "rows": rows}
    return {"format": "weave-modules-conformance-report-v1", "manifest": FORMAT,
            "scope": "modules-1 corpus: P0 programs through the weave binary; use net flow cases through "
                     "this script's header resolution and the unchanged reference checker.",
            "cases": len(data["cases"]), "flow_cases": flows, "rust": rust}


def main() -> int:
    binary, how = rust_binary()
    report = build_report(binary, how)
    REPORT.parent.mkdir(exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"PASS: {len(report['flow_cases'])} use net flow cases with the reference checker, "
          f"each at the location of the --net form where required")
    rust = report["rust"]
    if rust["status"] == "compared":
        print(f"PASS: weave agrees with {rust['compared']} modules-1 check and run cases (codes, files, lines, related imports)")
    else:
        print(f"SKIP: {rust['note']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
