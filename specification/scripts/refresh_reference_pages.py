#!/usr/bin/env python3
"""Regenerate conformance, rule-index and diagnostic-map pages from stable IDs; --check detects drift."""
from pathlib import Path
import argparse
import json
import re
ROOT=Path(__file__).resolve().parents[1]

def generate():
    m=json.loads((ROOT/"examples/manifest.json").read_text())
    rules={}
    for p in sorted((ROOT/"docs/chapters").glob("*.rst")):
        if p.stem in {"rule-catalogue","conformance"}:continue
        s=p.read_text()
        for match in re.finditer(r"^\.\. _([A-Z][A-Z0-9-]*-\d+):\s*$",s,re.M):
            id=match[1]
            if id in rules:raise ValueError("Duplicate rule ID: "+id)
            rules[id]={"chapter":p.stem,"line":s[:match.start()].count("\n")+1}
    pure=json.loads((ROOT/"examples/pure/manifest.json").read_text())
    if pure.get("format")!="weave-p0-conformance-v1":raise ValueError("Unsupported P0 manifest format")
    modules=json.loads((ROOT/"examples/modules/manifest.json").read_text())
    if modules.get("format")!="weave-modules-conformance-v1":raise ValueError("Unsupported modules manifest format")
    for c in m["cases"]+pure["cases"]+modules["cases"]:
        for rule in c["rules"]:
            if rule not in rules:raise ValueError(f"Unknown rule {rule} in {c['file']}")
    conf="""Conformance appendix
========================

This appendix and ``examples/manifest.json`` are normative for the listed
profiles. They define a minimum compatibility corpus, not the entire language.
Illustrative commentary remains informative.

.. _CONF-CASE-1:

**CONF-CASE-1.** A checker claiming this corpus MUST accept each ACCEPT case and
reject each negative case with its required diagnostic code. Full wording and
error ordering outside these exact inputs are not standardized. A checker may
add diagnostics, but must preserve the primary required code for these cases.

Files are relative to ``examples/``. F0/N0 uses ``nets/Inventory.weave``.
For ``net_append``, append the fragment inside that net before checking.
Net cases run structure, accounting and then ordering; flow cases check F0.
These stage requirements prevent an accounting-only pass from masking E320.

.. list-table::
   :header-rows: 1
   :widths: 8 35 12 12 33

   * - ID
     - File / kind
     - Profile
     - Required result
     - Rules
"""
    for c in m["cases"]:
        refs=", ".join(f":ref:`{x} <{x}>`" for x in c["rules"])
        conf+=f"   * - {c['id']}\n     - ``{c['file']}`` ({c['kind']})\n     - {c['profile']}\n     - {c['expect']}\n     - {refs}\n"
    counts={"accepted_flows":sum(c["kind"]=="flow" and c["expect"]=="ACCEPT" for c in m["cases"]),
            "cases":len(m["cases"])}
    conf+="""
Execution scenarios and supplemental evidence
------------------------------------------------

The three manifest scenarios are normative for the legacy scripted simulator's
selected outcomes and asserted markings. They do not confer D0 or R0 conformance.
The validator additionally checks all {accepted_flows} accepted flows and their lowerings
against N1's API projection.

The lease example requires structural/accounting and F0 acceptance, and E300
when ordering is requested without a check block. The E420 walkthrough uses a
separate coloured-read mutation. These are supplemental regression evidence,
outside the original 25-case baseline.

N2 and D0 have identified normative target rules but no implemented conformance
suite in this delivery. No existing test-pass claim establishes them.

P0 pure files
-------------------

The P0 cases are in ``examples/pure/manifest.json`` (format
``weave-p0-conformance-v1``), apart from ``manifest.json``, whose
``weave-conformance-v1`` readers do not implement their kinds
(:doc:`pure`). A *check* case requires ACCEPT or the code of the first
diagnostic. A *run* case checks the file and calls the entry function with
the given JSON arguments and budgets (others at the tool defaults); it requires
VALUE with the given value, or the code of the fault, exhaustion or invalid
request, and, where a usage is listed, exactly that fuel used, largest depth
and largest integer size. CONF-CASE-1 applies to these cases for P0.
``scripts/p0_differential.py`` checks them with the P0 reference evaluator
and compares the Rust ``weave`` command with it; ``tests/test_p0.py`` and the
Rust tests check them too. The conformance applications, sequential merge sort
and the routing function (:ref:`chapters/tooling:Conformance applications`),
are informative regression evidence beside these cases, not corpus cases; they
do not cover the concurrent fork/join merge sort (quaat/weave#42, M6).

.. list-table::
   :header-rows: 1
   :widths: 8 40 18 34

   * - ID
     - File / entry and arguments
     - Required result
     - Rules
""".format(**counts)
    for c in pure["cases"]:
        refs=", ".join(f":ref:`{x} <{x}>`" for x in c["rules"])
        if c["kind"]=="check":
            what=f"``{c['file']}`` (check)"
            result=c["expect"]
        else:
            args=json.dumps(c["args"],separators=(", ",": "))
            if len(args)>60:args=args[:57]+"..."
            what=f"``{c['file']}``: ``{c['entry']}({args[1:-1]})``"
            if c.get("budgets"):
                what+=" with "+", ".join(f"{k} {v}" for k,v in c["budgets"].items())
            result=c["expect"]
            if c["expect"]=="VALUE":
                value=json.dumps(c["value"],separators=(",",":"))
                if len(value)>40:value=value[:37]+"..."
                result=f"VALUE ``{value}``"
            if c.get("usage"):
                u=c["usage"]
                result+=f"; usage fuel {u['fuel']}, depth {u['depth']}, bits {u['int_bits']}"
        conf+=f"   * - {c['id']}\n     - {what}\n     - {result}\n     - {refs}\n"
    conf+="""

modules-1 corpus
---------------------

The modules-1 cases are in ``examples/modules/manifest.json`` (format
``weave-modules-conformance-v1``), apart from the F0/N0 and P0 manifests, whose
formats are unchanged (:ref:`chapters/names:P0 modules (modules-1)`). A *check*
case checks the program whose entry file is given, with the project root given
(else the entry's directory); it requires ACCEPT or the code of the first
diagnostic, whose primary span is in the given file at the given line and, for an
import cycle, whose related spans are the listed imports. A *run* case also calls
the entry function with the given arguments under the default budgets and requires
VALUE with the value, or the code of the fault or invalid request at the given
file and line. A *flow* case checks an F0 flow whose ``use net`` header is resolved
from the given root (``.`` is ``examples/``), with ``--net`` where a net is given;
it requires ACCEPT or the code at the given line and column, and, where a net form
is given, the same result and location as the flow with a comment in place of its
header checked against that net. CONF-CASE-1 applies to these cases for modules-1.
``scripts/modules_conformance.py`` runs the check and run cases through the Rust
``weave`` command (recording them as not established when no binary is available,
never as agreement) and the flow cases through its own header resolution and the
reference checker; ``crates/weave-cli/tests/modules.rs`` runs the check and run
cases too, and ``agent-kit/tests/test_use_net.py`` covers the kit runner's header.

.. list-table::
   :header-rows: 1
   :widths: 8 40 18 34

   * - ID
     - Case
     - Required result
     - Rules
"""
    for c in modules["cases"]:
        refs=", ".join(f":ref:`{x} <{x}>`" for x in c["rules"])
        root=f" with root ``{c['root']}``" if c.get("root") and c["kind"]!="flow" else ""
        if c["kind"]=="check":
            what=f"``{c['entry']}`` (check{root})"
        elif c["kind"]=="run":
            args=json.dumps(c["args"],separators=(", ",": "))
            what=f"``{c['entry']}``: ``{c['function']}({args[1:-1]})``{root}"
        else:
            net=f", ``--net {c['net']}``" if c.get("net") else ""
            what=f"``{c['file']}`` (flow{net})"
        result=c["expect"]
        if c["expect"]=="VALUE":result=f"VALUE ``{json.dumps(c['value'])}``"
        if c.get("file") and c["kind"]!="flow":result+=f" in ``{c['file']}`` line {c['line']}"
        elif c.get("line"):result+=f" at line {c['line']}, column {c['column']}"
        if c.get("related"):result+=f"; {len(c['related'])} related import(s)"
        if c.get("same_as_net"):result+="; as the ``--net`` form"
        conf+=f"   * - {c['id']}\n     - {what}\n     - {result}\n     - {refs}\n"
    conf+="""

Generated grammar comparison
-----------------------------

The generated parser pipeline agrees on all {cases} required outcomes. Its syntax
parser and layout pass are independent; its semantic stage is the reference
checker. This is not independent confirmation of the semantic implementation.
See ``validation/grammar-report.json`` for both stages separately.
""".format(**counts)
    index="""Normative rule catalogue
==========================

Rule IDs are explicit source labels and do not depend on chapter numbering.
The grammar's production names identify syntax rules; this catalogue indexes
prose and inference-rule obligations. Explanatory text does not add hidden
conformance requirements. Editorial portability restrictions are identified
separately from implementation-enforced rules.

The machine-readable index is ``rules.json``. To regenerate this appendix and
the conformance table, run ``python scripts/refresh_reference_pages.py``.
``--check`` fails if generated pages or rule links drift.

.. list-table::
   :header-rows: 1
   :widths: 40 60

   * - Rule
     - Chapter
"""
    rules["CONF-CASE-1"]={"chapter":"conformance","line":9}
    for id,data in sorted(rules.items()):
        index+=f"   * - :ref:`{id} <{id}>`\n     - :doc:`{data['chapter']}`\n"
    return {"docs/chapters/conformance.rst":conf,"docs/chapters/rule-catalogue.rst":index,
            "rules.json":json.dumps(rules,indent=2)+"\n",
            "docs/chapters/diagnostics.rst":diagnostics_page(rules)}

DIAGNOSTICS="docs/chapters/diagnostics.rst"
CATEGORIES={"specification","kit-extension","tool"}
KIT_RULE=re.compile(r"KIT-PURE-[A-Z]+-\d+")

def check_diagnostic_map(codes,rules):
    """Each code has one principal rule (none for 'tool') and known secondary rules."""
    for code,entry in codes.items():
        cat=entry.get("category")
        if cat not in CATEGORIES:raise ValueError(f"{code}: unknown category {cat!r}")
        principal,secondary=entry.get("rule"),entry.get("secondary_rules")
        if not isinstance(secondary,list) or len(set(secondary))!=len(secondary):
            raise ValueError(f"{code}: secondary_rules must be a list without repeats")
        if cat=="tool":
            if principal is not None or secondary:raise ValueError(f"{code}: a tool code has no rule")
            continue
        if not isinstance(principal,str):raise ValueError(f"{code}: needs exactly one principal rule")
        if principal in secondary:raise ValueError(f"{code}: principal rule repeated as secondary")
        for rule in [principal,*secondary]:
            known=rule in rules if cat=="specification" else bool(KIT_RULE.fullmatch(rule))
            if not known:raise ValueError(f"Unknown rule {rule} for diagnostic {code}")
        if not entry.get("meaning") or not entry.get("correction"):
            raise ValueError(f"{code}: meaning and correction are required")

def splice(text,name,body):
    begin,end=f".. BEGIN GENERATED: {name}\n",f".. END GENERATED: {name}\n"
    if text.count(begin)!=1 or text.count(end)!=1:raise ValueError(f"{DIAGNOSTICS}: markers for {name} missing")
    head,rest=text.split(begin);_,tail=rest.split(end)
    return head+begin+"\n"+body+"\n"+end+tail

def diagnostics_page(rules):
    codes=json.loads((ROOT/"diagnostics.json").read_text())["codes"]
    check_diagnostic_map(codes,rules)
    ref=lambda r:f":ref:`{r} <{r}>`" if r in rules else f"``{r}``"
    spec=[(c,e) for c,e in codes.items() if e["category"]=="specification"]
    other=[(c,e) for c,e in codes.items() if e["category"]!="specification"]
    table=lambda widths,head:(".. list-table::\n   :header-rows: 1\n   :widths: "+widths+"\n\n"
                              +"".join(("   * - " if i==0 else "     - ")+h+"\n" for i,h in enumerate(head)))
    row=lambda cells:"".join(("   * - " if i==0 else "     - ")+c+"\n" for i,c in enumerate(cells))
    meaning=table("15 45 40",["Code","Meaning","Typical correction"])
    meaning+="".join(row([c,e["meaning"],e["correction"]]) for c,e in spec)
    cross=table("12 28 60",["Code","Principal rule","Secondary rules"])
    cross+="".join(row([c,ref(e["rule"]),", ".join(map(ref,e["secondary_rules"])) or "none"]) for c,e in spec)
    outside=table("14 16 26 44",["Code","Category","Rule","Meaning"])
    outside+="".join(row([f"``{c}``",e["category"],ref(e["rule"]) if e["rule"] else "none (not a rule)",e["meaning"]]) for c,e in other)
    text=(ROOT/DIAGNOSTICS).read_text()
    for name,body in (("diagnostic-codes",meaning),("rule-cross-reference",cross),("codes-outside-the-fragment",outside)):
        text=splice(text,name,body)
    return text

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--check",action="store_true");args=ap.parse_args()
    for path,text in generate().items():
        p=ROOT/path
        if args.check:
            if not p.exists() or p.read_text()!=text:raise SystemExit("Generated reference drift: "+path)
        else:p.write_text(text,encoding="utf-8")
    print("PASS: conformance table and rule catalogue"+(" current" if args.check else " generated"))
if __name__=="__main__":main()

