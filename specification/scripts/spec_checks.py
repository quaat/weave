"""Shared example checks for the Sphinx directive and documentation tests."""
from pathlib import Path
import json
import sys
import textwrap

ROOT=Path(__file__).resolve().parents[1]
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT/"reference/prototype"))
from checker import CheckError, check_flow, parse_net, prove, tree
from coloured import parse_coloured, prove_colours

def replace_declarations(fragment, template):
    """Replace the displayed declarations in a complete net, then check that net."""
    import re
    raw=template.splitlines()
    original=tree(template)[0].children
    snippets=tree(fragment)
    replacements=[]
    def key(text):
        m=re.match(r"(\w+)\s+([A-Za-z_]\w*)",text)
        if not m: raise ValueError("Fragment needs complete net declarations")
        return m.groups()
    fragment_lines=fragment.splitlines()
    for i,node in enumerate(snippets):
        matches=[(j,n) for j,n in enumerate(original) if key(n.text)==key(node.text)]
        if len(matches)!=1: raise ValueError(f"Fragment context cannot resolve {node.text!r}")
        j,old=matches[0]
        end=original[j+1].line-1 if j+1<len(original) else len(raw)
        fend=snippets[i+1].line-1 if i+1<len(snippets) else len(fragment_lines)
        new=textwrap.indent("\n".join(fragment_lines[node.line-1:fend]),"    ").splitlines()
        replacements.append((old.line-1,end,new))
    for start,end,new in sorted(replacements,reverse=True):
        raw[start:end]=new
    return "\n".join(raw)+"\n"

DIAGNOSTIC_MAP=json.loads((ROOT/"diagnostics.json").read_text(encoding="utf-8"))["codes"]

def as_diagnostic(error,file,source,stage):
    """A CheckError as a weave-diagnostic-v1 document, with the rules from diagnostics.json."""
    entry=DIAGNOSTIC_MAP.get(error.code)
    if entry is None: raise KeyError(f"Diagnostic code {error.code} is not in diagnostics.json")
    return error.diagnostic(file,source,stage,entry["rule"],entry["secondary_rules"],entry["category"])

def _shift(diagnostic,displayed,lines,columns):
    """Map spans of a wrapped body back to the displayed snippet; generated lines map to the whole snippet."""
    rows=displayed.splitlines() or [""]
    whole={"start":{"line":1,"column":1},"end":{"line":len(rows),"column":len(rows[-1])+1}}
    for span in [diagnostic["span"]]+[r["span"] for r in diagnostic["related"]]:
        start,end=span["start"],span["end"]
        if start["line"]<=lines or end["line"]-lines>len(rows):
            span.update(whole);continue
        for point in (start,end):
            point["line"]-=lines;point["column"]=max(1,point["column"]-columns)
    return diagnostic

def check_example_diagnostic(source,profile="F0/N0",context="file",net_path=None,label="example.weave"):
    """Return (result, diagnostic): ACCEPT or the code, and a weave-diagnostic-v1 document for a rejection.

    Spans refer to ``label``. Profile ``P0`` checks a pure file with the P0
    reference evaluator; ``context`` and ``net_path`` do not apply to it. For a net fragment they refer to the completed net
    (the template with the fragment substituted), named by its path."""
    if profile=="P0":
        # P0 pure files are checked by the P0 reference evaluator (docs/chapters/pure.rst).
        import p0_reference
        try:
            p0_reference.check(source)
            return "ACCEPT",None
        except p0_reference.Diagnostic as e:
            return e.code,e.document(label)
    path=Path(net_path) if net_path else ROOT/"examples/nets"/("Inventory.coloured.weave" if "N1" in profile else "Inventory.weave")
    template=path.read_text(encoding="utf-8")
    displayed,shift=source,None
    file=label
    stage="net" if context=="net-fragment" or profile in {"N0","N1"} else "flow"
    try:
        if context=="net-fragment":
            source=replace_declarations(textwrap.dedent(source),template)
            file=f"{path.relative_to(ROOT) if path.is_relative_to(ROOT) else path} (with {label})"
        if context=="result-body":
            source="flow sample(result: ChargeOutcome[t, o]) -> CheckoutOutcome[t, o]:\n"+textwrap.indent(source,"    ")
            shift=(1,4)
        elif context=="await-body":
            source=("flow sample(tenant: TenantId, order: OrderId, amount: Money, escrow: Escrow[tenant, order]) -> ChargeOutcome[tenant, order]:\n"+
                    textwrap.indent(source.rstrip()+"\nreturn Ok(paid)\n","    "))
            shift=(1,4)
        if stage=="net":
            if "N1" in profile: prove_colours(parse_coloured(source))
            else: prove(parse_net(source))
        else:
            net=parse_coloured(template).base if "N1" in profile else parse_net(template)
            check_flow(net,source)
        return "ACCEPT",None
    except CheckError as e:
        diagnostic=as_diagnostic(e,file,source,stage)
        if shift: diagnostic=_shift(diagnostic,displayed,*shift)
        return e.code,diagnostic

def check_example(source,profile="F0/N0",context="file",net_path=None):
    return check_example_diagnostic(source,profile,context,net_path)[0]

