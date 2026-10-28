"""Shared example checks for the Sphinx directive and documentation tests."""
from pathlib import Path
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

def check_example(source,profile="F0/N0",context="file",net_path=None):
    path=Path(net_path) if net_path else ROOT/"examples/nets"/("Inventory.coloured.weave" if "N1" in profile else "Inventory.weave")
    template=path.read_text(encoding="utf-8")
    try:
        if context=="net-fragment": source=replace_declarations(textwrap.dedent(source),template)
        if context=="result-body":
            source="flow sample(result: ChargeOutcome[t, o]) -> CheckoutOutcome[t, o]:\n"+textwrap.indent(source,"    ")
        elif context=="await-body":
            source=("flow sample(tenant: TenantId, order: OrderId, amount: Money, escrow: Escrow[tenant, order]) -> ChargeOutcome[tenant, order]:\n"+
                    textwrap.indent(source.rstrip()+"\nreturn Ok(paid)\n","    "))
        if context=="net-fragment" or profile in {"N0","N1"}:
            if "N1" in profile: prove_colours(parse_coloured(source))
            else: prove(parse_net(source))
        else:
            net=parse_coloured(template).base if "N1" in profile else parse_net(template)
            check_flow(net,source)
        return "ACCEPT"
    except CheckError as e:
        return e.code

