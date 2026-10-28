#!/usr/bin/env python3
"""Generate an independent syntax parser from weave.ebnf and compare corpus pipelines.

The generated front end is independent; semantic diagnostics are delegated to the
unchanged reference checker. This is not a second independent type checker.
"""
from __future__ import annotations
import json
from pathlib import Path
import re
import sys
from lark import Lark, UnexpectedInput

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "reference/prototype"))
from checker import CheckError, check_flow, parse_net, prove, explore_order

TOKEN = re.compile(r'\s*(?:(\(\*[\s\S]*?\*\))|("(?:[^"\\]|\\.)*")|(\?[^?]*\?)|([A-Za-z][A-Za-z0-9-]*)|([=,;|{}\[\]()]))')
LEXICAL = {"IDENT", "UINT", "POSINT", "NL", "INDENT", "DEDENT"}

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
            else: output.append(t)
        return " ".join(output)
    lines=[n.replace("-","_")+": "+translate(b) for n,b in productions.items() if n not in LEXICAL]
    lines += [
        'IDENT: /[A-Za-z_][A-Za-z0-9_]*/',
        'UINT: /0|[1-9][0-9]*/',
        'POSINT: /[1-9][0-9]*/',
        r'NL: "\n"',
        'INDENT: "⟪"',
        'DEDENT: "⟫"',
        r'%ignore /[ ]+/',
    ]
    return "\n".join(lines)+"\n", len(productions)

def layout(source: str) -> str:
    """Independent four-space layout pass, not checker.tree."""
    if "⟪" in source or "⟫" in source: raise ValueError("Internal layout marker in source")
    output=[]; levels=[0]; previous=None
    for lineno, raw in enumerate(source.splitlines(),1):
        if "\t" in raw: raise ValueError(f"Tab on line {lineno}")
        line=raw.split("#",1)[0].rstrip()
        if not line.strip(): continue
        indent=len(line)-len(line.lstrip(" "))
        if indent%4: raise ValueError(f"Bad indent on line {lineno}")
        if previous is None and indent: raise ValueError("Indented file root")
        if indent>levels[-1]:
            if indent!=levels[-1]+4 or not previous.endswith(":"): raise ValueError("Bad nested block")
            levels.append(indent);output.append("⟪")
        while indent<levels[-1]:
            levels.pop();output.append("⟫")
        if indent!=levels[-1]: raise ValueError("Unmatched dedent")
        output.append(line.strip()+"\n");previous=line.strip()
    while len(levels)>1: levels.pop();output.append("⟫")
    return "".join(output)

def parser():
    grammar,count=generate((ROOT/"grammar/weave.ebnf").read_text(encoding="utf-8"))
    return Lark(grammar,start=["flow_file","n0_file","n1_file"],parser="earley",lexer="dynamic"),grammar,count

def reference(source, kind, base):
    try:
        if kind=="flow": check_flow(base,source)
        else:
            candidate=parse_net(source);prove(candidate);explore_order(candidate)
        return "ACCEPT"
    except CheckError as e: return e.code

def main():
    p,grammar,count=parser()
    manifest=json.loads((ROOT/"examples/manifest.json").read_text())
    base_source=(ROOT/"examples"/manifest["net"]).read_text()
    base=parse_net(base_source); rows=[]
    for c in manifest["cases"]:
        source=(ROOT/"examples"/c["file"]).read_text()
        if c["kind"]=="net_append": source=base_source.rstrip()+"\n\n"+source
        syntax="ACCEPT"
        try: p.parse(layout(source), start="flow_file" if c["kind"]=="flow" else "n0_file")
        except (UnexpectedInput,ValueError): syntax="REJECT"
        ref=reference(source,c["kind"],base)
        # Syntax failures map to the reference's unsupported-source family, not
        # a claim that the generated parser implements semantic diagnostics.
        pipeline=reference(source,c["kind"],base) if syntax=="ACCEPT" else ("E200" if c["kind"]=="flow" else "E003")
        if pipeline != ref or ref!=c["expect"]:
            raise AssertionError(f"{c['file']}: generated pipeline={pipeline}, reference={ref}, expected={c['expect']}")
        rows.append({"file":c["file"],"syntax":syntax,"pipeline":pipeline,"reference":ref,"expected":c["expect"]})
    for filename,start in [("nets/Inventory.coloured.weave","n1_file"),("nets/Lease.weave","n0_file"),("valid/lease_roundtrip.weave","flow_file")]:
        p.parse(layout((ROOT/"examples"/filename).read_text()),start=start)
    out=ROOT/"validation";out.mkdir(exist_ok=True)
    (out/"generated-weave.lark").write_text(grammar)
    report={"productions":count,"cases":rows,"agreement":len(rows),
            "scope":"Independent generated syntax front end plus shared reference semantic checks; not independent semantic equivalence."}
    (out/"grammar-report.json").write_text(json.dumps(report,indent=2)+"\n")
    print(f"PASS: {count} EBNF productions; {len(rows)}/{len(rows)} corpus pipeline agreements; N1 and lease syntax parsed")
    return 0

if __name__=="__main__": raise SystemExit(main())

