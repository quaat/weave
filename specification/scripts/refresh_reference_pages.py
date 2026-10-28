#!/usr/bin/env python3
"""Regenerate conformance and rule-index pages from stable IDs; --check detects drift."""
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
    for c in m["cases"]:
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
    conf+="""
Execution scenarios and supplemental evidence
------------------------------------------------

The three manifest scenarios are normative for the legacy scripted simulator's
selected outcomes and asserted markings. They do not confer D0 or R0 conformance.
The validator additionally checks all eight accepted flows and their lowerings
against N1's API projection.

The lease example requires structural/accounting and F0 acceptance, and E300
when ordering is requested without a check block. The E420 walkthrough uses a
separate coloured-read mutation. These are supplemental regression evidence,
outside the original 25-case baseline.

N2 and D0 have identified normative target rules but no implemented conformance
suite in this delivery. No existing test-pass claim establishes them.

Generated grammar comparison
-----------------------------

The generated parser pipeline agrees on all 25 required outcomes. Its syntax
parser and layout pass are independent; its semantic stage is the reference
checker. This is not independent confirmation of the semantic implementation.
See ``validation/grammar-report.json`` for both stages separately.
"""
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
            "rules.json":json.dumps(rules,indent=2)+"\n"}

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--check",action="store_true");args=ap.parse_args()
    for path,text in generate().items():
        p=ROOT/path
        if args.check:
            if not p.exists() or p.read_text()!=text:raise SystemExit("Generated reference drift: "+path)
        else:p.write_text(text,encoding="utf-8")
    print("PASS: conformance table and rule catalogue"+(" current" if args.check else " generated"))
if __name__=="__main__":main()

