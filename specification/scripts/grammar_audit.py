#!/usr/bin/env python3
"""Generate an independent syntax parser from weave.ebnf and compare corpus pipelines.

The generated front end is independent; semantic diagnostics are delegated to the
unchanged reference checker. This is not a second independent type checker.

Three comparisons are recorded in ``validation/grammar-report.json``:

* the corpus pipeline: generated syntax front end followed by reference semantics,
  against the reference checker and the manifest's expected result;
* syntax probes: small inputs on which the reference checker's hand-written parser
  and the EBNF are known to agree or to differ (the discrepancy list in the grammar
  chapter); each probe's documented verdicts are asserted;
* the Rust differential: the accept/reject verdict of the grammar-driven Rust parser
  (``crates/weave-syntax``) against the generated parser on every corpus file and
  probe, and its round trip on every accepted file. It runs when ``WEAVE_SYNTAX_BIN``
  names the ``weave-syntax`` binary or ``cargo`` is on ``PATH``; otherwise it is
  skipped and recorded as not established, never as a pass.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from lark import Lark, UnexpectedInput

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "reference/prototype"))
from checker import CheckError, check_flow, parse_net, prove, explore_order

TOKEN = re.compile(r'\s*(?:(\(\*[\s\S]*?\*\))|("(?:[^"\\]|\\.)*")|(\?[^?]*\?)|([A-Za-z][A-Za-z0-9-]*)|([=,;|{}\[\]()]))')
LEXICAL = {"IDENT", "UINT", "POSINT", "NL", "INDENT", "DEDENT"}
# Words and numerals end at a word boundary (lexical chapter, "Tokens"): without
# the lookahead the dynamic lexer would split ``letx`` into ``let x``.
END = r"(?![A-Za-z0-9_])"
SYNTAX_FAMILY = {"E001", "E002", "E003", "E200"}
START = {"flow": "flow-file", "net": "n0-file", "net_append": "n0-file", "n1": "n1-file"}
N1_NETS = {"nets/Inventory.coloured.weave", "nets/cross_order_read.weave"}


class LayoutError(ValueError):
    """A layout fault; the reference checker reports these as E001 (LEX-REQ-1)."""


def generate(text: str) -> tuple[str, int]:
    tokens = []
    pos = 0
    while pos < len(text):
        m = TOKEN.match(text, pos)
        if not m:
            if not text[pos:].strip(): break
            raise ValueError(f"Unrecognized EBNF near {text[pos:pos+60]!r}")
        pos = m.end()
        if not m[1]: tokens.append(next(x for x in m.groups()[1:] if x is not None))
    i = 0
    productions = {}
    while i < len(tokens):
        name = tokens[i]; i += 1
        if tokens[i] != "=": raise ValueError("Expected '='")
        i += 1
        body = []
        while tokens[i] != ";":
            body.append(tokens[i]); i += 1
        i += 1
        if name in productions: raise ValueError(f"Duplicate production {name}")
        productions[name] = body
    refs = {t for body in productions.values() for t in body if re.fullmatch(r"[A-Za-z][A-Za-z0-9-]*", t)}
    missing = refs - productions.keys()
    if missing: raise ValueError(f"Undefined EBNF nonterminals: {sorted(missing)}")
    def translate(body):
        output=[]
        for t in body:
            if t == ",": continue
            if t == "{": output.append("(")
            elif t == "}": output.append(")*")
            elif t == "[": output.append("(")
            elif t == "]": output.append(")?")
            elif re.fullmatch(r"[A-Za-z][A-Za-z0-9-]*",t):
                output.append(t if t in LEXICAL else t.replace("-","_"))
            elif re.fullmatch(r'"[A-Za-z0-9_]+"', t):
                output.append(f"/{t[1:-1]}{END}/")
            else: output.append(t)
        return " ".join(output)
    lines=[n.replace("-","_")+": "+translate(b) for n,b in productions.items() if n not in LEXICAL]
    lines += [
        f'IDENT: /[A-Za-z_][A-Za-z0-9_]*{END}/',
        f'UINT: /(0|[1-9][0-9]*){END}/',
        f'POSINT: /[1-9][0-9]*{END}/',
        r'NL: "\n"',
        'INDENT: "⟪"',
        'DEDENT: "⟫"',
        r'%ignore /[ ]+/',
    ]
    return "\n".join(lines)+"\n", len(productions)

def layout(source: str) -> str:
    """Independent four-space layout pass, not checker.tree.

    Lines end at LF or CRLF only; any other carriage return is a lexical error.
    Only spaces are whitespace: other characters reach the generated parser,
    which rejects them.
    """
    if "⟪" in source or "⟫" in source: raise ValueError("Internal layout marker in source")
    output=[]; levels=[0]; previous=None
    lines=source.split("\n")
    if lines and lines[-1]=="": lines.pop()
    for lineno, raw in enumerate(lines,1):
        if raw.endswith("\r"): raw=raw[:-1]
        if "\t" in raw: raise LayoutError(f"Tab on line {lineno}")
        if "\r" in raw: raise ValueError(f"Carriage return inside line {lineno}")
        line=raw.split("#",1)[0].rstrip(" ")
        if not line.strip(" "): continue
        indent=len(line)-len(line.lstrip(" "))
        if indent%4: raise LayoutError(f"Bad indent on line {lineno}")
        if previous is None and indent: raise LayoutError("Indented file root")
        if indent>levels[-1]:
            if indent!=levels[-1]+4 or not previous.endswith(":"): raise LayoutError("Bad nested block")
            levels.append(indent);output.append("⟪")
        while indent<levels[-1]:
            levels.pop();output.append("⟫")
        if indent!=levels[-1]: raise LayoutError("Unmatched dedent")
        output.append(line.strip(" ")+"\n");previous=line.strip(" ")
    while len(levels)>1: levels.pop();output.append("⟫")
    return "".join(output)

def parser():
    grammar,count=generate((ROOT/"grammar/weave.ebnf").read_text(encoding="utf-8"))
    return Lark(grammar,start=["flow_file","n0_file","n1_file"],parser="earley",lexer="dynamic"),grammar,count

def syntax(p, source: str, start: str) -> tuple[str, str | None]:
    """The generated front end's verdict and, for a rejection, the syntax-family code."""
    try:
        p.parse(layout(source), start=start.replace("-", "_"))
        return "ACCEPT", None
    except LayoutError:
        return "REJECT", "E001"
    except (UnexpectedInput, ValueError):
        return "REJECT", "E200" if start == "flow-file" else "E003"

def reference(source, kind, base):
    try:
        if kind=="flow": check_flow(base,source)
        else:
            candidate=parse_net(source);prove(candidate);explore_order(candidate)
        return "ACCEPT"
    except CheckError as e: return e.code

def corpus(manifest) -> list[tuple[str, str, str]]:
    """Every corpus file as (file, start symbol, text to parse), manifest cases first."""
    base_source=(ROOT/"examples"/manifest["net"]).read_text(encoding="utf-8")
    kinds={c["file"]:c["kind"] for c in manifest["cases"]}
    files=list(kinds)+sorted(str(p.relative_to(ROOT/"examples")) for p in (ROOT/"examples").rglob("*.weave")
                             if str(p.relative_to(ROOT/"examples")) not in kinds)
    out=[]
    for f in files:
        source=(ROOT/"examples"/f).read_text(encoding="utf-8")
        directory=f.split("/")[0]
        kind=kinds.get(f) or {"valid":"flow","invalid":"flow","mutations":"net_append"}.get(directory) or (
            "n1" if f in N1_NETS else "net")
        if kind=="net" and f in N1_NETS: kind="n1"
        if kind=="net_append": source=base_source.rstrip()+"\n\n"+source
        out.append((f,START[kind],source))
    return out

# Syntax probes: the reference checker's hand-written parser against the EBNF.
# "reference" is ACCEPT when the reference checker reports no syntax-family code
# (E001, E002, E003, E200); "ebnf" is the verdict of the EBNF read through the
# lexical chapter. The grammar chapter's discrepancy table lists the probes on
# which they differ; tests/test_grammar_audit.py keeps the table and this list equal.
_HOLD = "flow f(hold: Hold[t, o]) -> Hold[t, o]:\n    return hold\n"
_ARM = "flow f(hold: Hold[t, o]) -> Escrow[t, o]:\n    let escrow = await Inventory.arm(hold)\n    return escrow\n"
_LEASE = (ROOT/"examples/nets/Lease.weave").read_text(encoding="utf-8")
PROBES = [
    ("SD-01", "flow-file", _HOLD.replace(") -> ", ")  ->  "), "REJECT", "ACCEPT",
     "Extra spaces between tokens of a flow header"),
    ("SD-02", "flow-file", "flow f(hold:Hold[t,o])->Hold[t,o]:\n    return hold\n", "REJECT", "ACCEPT",
     "No spaces between tokens of a flow header"),
    ("SD-03", "flow-file", _HOLD.replace("return hold", "return  hold"), "REJECT", "ACCEPT",
     "Two spaces after return"),
    ("SD-04", "flow-file", "flow f(hold: Hold[t, o]) -> ChargeOutcome[t, o]:\n    let x = ( await Payments.charge(t, o, a, e) )?\n    return x\n",
     "REJECT", "ACCEPT", "Spaces inside the parentheses of a propagated call"),
    ("SD-05", "n0-file", _LEASE.replace("place free = 1", "place free  = 1"), "REJECT", "ACCEPT",
     "Two spaces in a place declaration"),
    ("SD-06", "n0-file", _LEASE.replace("net Lease(stock: Nat):", "net Lease( stock : Nat ):"), "REJECT", "ACCEPT",
     "Spaces inside a net header's parentheses"),
    ("SD-07", "flow-file", _HOLD.replace("hold", "höld"), "ACCEPT", "REJECT",
     "Non-ASCII identifier (the reference uses Unicode-aware \\w)"),
    ("SD-08", "flow-file", _HOLD.replace("flow f(", "flow 1f("), "ACCEPT", "REJECT",
     "Flow name starting with a digit"),
    ("SD-09", "n0-file", _LEASE.replace("free + leased == 1", "free + leased == 0x1"), "ACCEPT", "REJECT",
     "Hexadecimal integer in an invariant (read by the host AST reader)"),
    ("SD-10", "flow-file", _HOLD.replace("return hold", "return hold "), "ACCEPT", "REJECT",
     "Trailing no-break space (Python strips Unicode whitespace)"),
    ("SD-11", "flow-file", _HOLD.replace("return hold", "return hold\x0c"), "ACCEPT", "REJECT",
     "Trailing form feed"),
    ("SD-12", "flow-file", _HOLD.replace(":\n", ":\r", 1), "ACCEPT", "REJECT",
     "Carriage return alone as a line break (Python splitlines)"),
    ("SA-01", "flow-file", _HOLD.replace(":\n", ":  # comment\n", 1), "ACCEPT", "ACCEPT",
     "Comment after a block header"),
    ("SA-02", "flow-file", _HOLD.replace("return hold", "return hold   "), "ACCEPT", "ACCEPT",
     "Trailing spaces"),
    ("SA-03", "flow-file", _HOLD.replace(":\n", ":\n\n\n", 1), "ACCEPT", "ACCEPT",
     "Blank lines at the start of a block"),
    ("SA-04", "flow-file", _HOLD.replace(":\n", ":\n  # odd indentation\n", 1), "ACCEPT", "ACCEPT",
     "Comment-only line at an indentation that is not a level"),
    ("SA-05", "flow-file", _HOLD.replace(":\n", ":  #\ttab\n", 1), "REJECT", "REJECT",
     "Tab inside a comment (E001)"),
    ("SA-06", "flow-file", _ARM.replace("let escrow", "letescrow"), "REJECT", "REJECT",
     "Keyword glued to an identifier"),
    ("SA-07", "flow-file", _ARM.replace("arm(hold)", "arm( hold )"), "ACCEPT", "ACCEPT",
     "Spaces inside call parentheses"),
    ("SA-08", "flow-file", "flow f(hold: Hold[t, o]) -> Hold[t, o]:\n    let x = await()\n    return hold\n",
     "ACCEPT", "ACCEPT", "Operation named await without the await keyword (reference E212 is static)"),
    ("SA-09", "n0-file", _LEASE.replace("take 1 free", "take 01 free", 1), "REJECT", "REJECT",
     "Arc count with a leading zero"),
    ("SA-10", "n0-file", _LEASE.replace("net Lease(stock: Nat):", "net Lease(stock: Nat):  # header"), "ACCEPT", "ACCEPT",
     "Comment after a net header"),
]

def probe_reference(source: str, start: str, net) -> str:
    try:
        if start == "flow-file": check_flow(net, source)
        else: prove(parse_net(source))
        return "ACCEPT"
    except CheckError as e:
        return "REJECT" if e.code in SYNTAX_FAMILY else "ACCEPT"

def rust_binary() -> tuple[Path | None, str]:
    """The weave-syntax binary and how it was found, or None and why the comparison is skipped."""
    named = os.environ.get("WEAVE_SYNTAX_BIN")
    if named:
        path = Path(named)
        if not path.is_file(): raise FileNotFoundError(f"WEAVE_SYNTAX_BIN={named} is not a file")
        return path, "WEAVE_SYNTAX_BIN"
    cargo = shutil.which("cargo")
    if cargo is None:
        return None, "cargo is not on PATH and WEAVE_SYNTAX_BIN is not set"
    if not (REPO/"Cargo.toml").is_file():
        return None, "no Cargo workspace next to the specification"
    subprocess.run([cargo, "build", "--quiet", "--offline", "--locked", "-p", "weave-syntax", "--bin", "weave-syntax"],
                   cwd=REPO, check=True)
    suffix = ".exe" if os.name == "nt" else ""
    return REPO/"target"/"debug"/f"weave-syntax{suffix}", "cargo build --offline --locked"

def rust_verdict(binary: Path, command: str, start: str, source: str) -> tuple[str, str | None]:
    done = subprocess.run([str(binary), command, "--start", start, "-"], input=source.encode("utf-8"),
                          capture_output=True, timeout=60)
    if done.returncode == 0: return "ACCEPT", None
    if done.returncode == 1 and command == "parse":
        return "REJECT", json.loads(done.stdout)[0]["code"]
    if done.returncode == 1: return "REJECT", None
    raise RuntimeError(f"weave-syntax {command} failed: {done.stderr.decode(errors='replace')}")

def rust_differential(inputs: list[tuple[str, str, str, str, str | None]]) -> dict:
    """Compare the Rust parser with the generated parser on (name, start, source, verdict, code) inputs."""
    binary, how = rust_binary()
    if binary is None:
        return {"status": "skipped", "compared": 0,
                "note": f"Rust/generated-parser agreement not established: {how}."}
    rows = []
    for name, start, source, verdict, code in inputs:
        rust, rust_code = rust_verdict(binary, "parse", start, source)
        row = {"input": name, "start": start, "generated": verdict, "rust": rust}
        if rust == "ACCEPT":
            row["round_trip"] = rust_verdict(binary, "roundtrip", start, source)[0] == "ACCEPT"
            if not row["round_trip"]: raise AssertionError(f"{name}: Rust round trip failed")
        else:
            row["rust_code"] = rust_code
            if code is not None and rust_code != code:
                raise AssertionError(f"{name}: Rust code {rust_code}, generated pipeline {code}")
        if rust != verdict:
            raise AssertionError(f"{name}: Rust parser {rust}, generated parser {verdict}")
        rows.append(row)
    return {"status": "compared", "binary": how, "compared": len(rows),
            "agreements": sum(r["rust"] == r["generated"] for r in rows), "rows": rows}

def main():
    p,grammar,count=parser()
    manifest=json.loads((ROOT/"examples/manifest.json").read_text(encoding="utf-8"))
    base_source=(ROOT/"examples"/manifest["net"]).read_text(encoding="utf-8")
    base=parse_net(base_source); rows=[]
    for c in manifest["cases"]:
        source=(ROOT/"examples"/c["file"]).read_text(encoding="utf-8")
        if c["kind"]=="net_append": source=base_source.rstrip()+"\n\n"+source
        verdict,code=syntax(p, source, "flow-file" if c["kind"]=="flow" else "n0-file")
        ref=reference(source,c["kind"],base)
        # Syntax failures map to the reference's layout or unsupported-source family, not
        # a claim that the generated parser implements semantic diagnostics.
        pipeline=ref if verdict=="ACCEPT" else code
        if pipeline != ref or ref!=c["expect"]:
            raise AssertionError(f"{c['file']}: generated pipeline={pipeline}, reference={ref}, expected={c['expect']}")
        rows.append({"file":c["file"],"syntax":verdict,"pipeline":pipeline,"reference":ref,"expected":c["expect"]})
    inputs=[]
    for f,start,source in corpus(manifest):
        verdict,code=syntax(p, source, start)
        if f not in {r["file"] for r in rows} and verdict!="ACCEPT":
            raise AssertionError(f"{f}: supplementary corpus file rejected by the generated parser")
        inputs.append((f,start,source,verdict,code))
    probes=[]
    for pid,start,source,want_ref,want_ebnf,what in PROBES:
        ref=probe_reference(source,start,base)
        verdict,code=syntax(p,source,start)
        if (ref,verdict)!=(want_ref,want_ebnf):
            raise AssertionError(f"{pid}: reference {ref}, generated {verdict}; documented {want_ref}, {want_ebnf}")
        probes.append({"id":pid,"start":start,"probe":what,"reference":ref,"ebnf":verdict,
                       "discrepancy":ref!=verdict})
        inputs.append((pid,start,source,verdict,None))
    rust=rust_differential(inputs)
    out=ROOT/"validation";out.mkdir(exist_ok=True)
    (out/"generated-weave.lark").write_text(grammar,encoding="utf-8")
    report={"productions":count,"cases":rows,"agreement":len(rows),
            "scope":"Independent generated syntax front end plus shared reference semantic checks; not independent semantic equivalence.",
            "corpus_files_parsed":len(inputs)-len(probes),
            "probes":probes,
            "rust_differential":rust}
    (out/"grammar-report.json").write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(f"PASS: {count} EBNF productions; {len(rows)}/{len(rows)} corpus pipeline agreements; "
          f"{len(inputs)-len(probes)} corpus files parsed; {len(probes)} syntax probes as documented "
          f"({sum(p['discrepancy'] for p in probes)} reference discrepancies)")
    if rust["status"]=="compared":
        print(f"PASS: Rust parser agrees with the generated parser on {rust['agreements']}/{rust['compared']} inputs; "
              "accepted inputs round-trip")
    else:
        print(f"SKIP: {rust['note']}")
    return 0

if __name__=="__main__": raise SystemExit(main())
