#!/usr/bin/env python3
"""Render exact-source SVG diagrams with standard-library SVG generation."""
from pathlib import Path
from html import escape
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"reference/prototype"))
from checker import parse_net

def canvas(w,h,title,desc):
    return [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img"><title>{escape(title)}</title><desc>{escape(desc)}</desc>',
    '<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 Z" fill="#385b72"/></marker></defs>',
    '<style>text{font-family:DejaVu Sans,Arial,sans-serif;fill:#17364c}.small{font-size:14px}.label{font-size:16px}.title{font-size:26px;font-weight:700}.edge{fill:none;stroke:#385b72;stroke-width:2;marker-end:url(#arrow)}.read{stroke:#167c9a;stroke-dasharray:5 4}.cancel{stroke-dasharray:5 4}</style>',
    f'<rect width="{w}" height="{h}" fill="#fff"/>']
def text(svg,x,y,s,size=16,anchor="middle"):
    svg.append(f'<text x="{x}" y="{y}" font-size="{size}" text-anchor="{anchor}">{escape(s)}</text>')
def box(svg,x,y,w,h,s,fill="#e7f2f0"):
    svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="{fill}" stroke="#45677a"/>')
    text(svg,x+w/2,y+h/2+6,s)
def line(svg,x1,y1,x2,y2,label="",klass=""):
    svg.append(f'<path class="edge {klass}" d="M{x1},{y1} L{x2},{y2}"/>')
    if label:text(svg,(x1+x2)/2,(y1+y2)/2-8,label,14)
def save(name,svg):
    out=ROOT/"docs/_static/diagrams";out.mkdir(parents=True,exist_ok=True)
    (out/name).write_text("\n".join(svg)+"\n</svg>\n")

def net_panels():
    net=parse_net((ROOT/"examples/nets/Inventory.weave").read_text())
    s=canvas(1480,1860,"Inventory N0 — all 21 transitions",
             "Each panel is an exact transition star. Repeated place labels denote the same place across panels. Solid incoming arcs consume, dashed incoming arcs read, outgoing arcs produce.")
    text(s,740,40,"Inventory N0 · complete transition panels",28)
    text(s,740,70,"Repeated place labels denote the same place. Dashed input = read. All arc multiplicities shown.",16)
    colours={"domain":"#e4edf6","activation":"#e5f4ee","runtime":"#fff0d6","adapter":"#f1e7f7"}
    for i,t in enumerate(net.transitions.values()):
        ox=20+(i%3)*490;oy=95+(i//3)*245
        s.append(f'<rect x="{ox}" y="{oy}" width="470" height="230" rx="10" fill="#f8fafc" stroke="#d6e1e8"/>')
        text(s,ox+15,oy+25,f"{i+1:02d}",14,"start")
        box(s,ox+160,oy+90,150,45,t.name,"#d8e7ed")
        inputs=[(p,n,"take") for p,n in t.take.items()]+[(p,n,"read") for p,n in t.read.items()]
        outputs=list(t.put.items())
        for side,items in [("left",inputs),("right",outputs)]:
            for j,item in enumerate(items):
                p,n=item[:2];x=ox+(72 if side=="left" else 397)
                y=oy+112+(j-(len(items)-1)/2)*60
                s.append(f'<ellipse cx="{x}" cy="{y}" rx="65" ry="23" fill="{colours[net.places[p].owner]}" stroke="#45677a"/>')
                text(s,x,y+5,p,12)
                if side=="left":line(s,x+65,y,ox+160,oy+112,str(n),"read" if item[2]=="read" else "")
                else:line(s,ox+310,oy+112,x-65,y,str(n))
        if t.guards:
            text(s,ox+235,oy+190,"guard:",13)
            text(s,ox+235,oy+211,", ".join(t.guards),12)
    text(s,740,1830,"Blue: domain · green: activation · amber: runtime · violet: adapter. Source: Inventory.weave (N0).",16)
    save("inventory-n0.svg",s)

def handles():
    s=canvas(1040,710,"Inventory handle state machine","Normal handle transfers and settlement. Runtime pending state is not an activation handle. Recovery may resolve later.")
    text(s,520,35,"Inventory · handles and obligations",27)
    box(s,420,65,200,48,"Hold[t,o]")
    box(s,420,175,200,48,"Escrow[t,o]")
    line(s,520,113,520,175,"arm + registration")
    box(s,395,285,250,48,"inflight (runtime)","#fff0d6")
    line(s,520,223,520,285,"foreign dispatch")
    for x,label,outcome in [(90,"Paid[t,o]","Ok"),(420,"Unpaid[t,o]","Err"),(750,"Uncertain[t,o]","Unknown")]:
        box(s,x,410,200,48,label)
        line(s,520,333,x+100,410,outcome)
    box(s,90,555,200,55,"sold","#e4edf6")
    box(s,420,555,200,55,"stock returned","#e4edf6")
    box(s,750,555,200,55,"recovery queue","#fff0d6")
    line(s,190,458,190,555,"sell")
    line(s,520,458,520,555,"release")
    line(s,850,458,850,555,"handoff")
    text(s,520,660,"No handle copy or normal drop. Cancellation uses declared state-specific routes.",17)
    text(s,520,690,"Recovery retains registration until authoritative resolution. N1 also records identity-specific release.",15)
    save("handle-states.svg",s)

def unknown():
    s=canvas(1340,1040,"R0 Unknown and late successful resolution",
             "Sequence for cancellation after a lost successful reply. The initial Unknown result returns a worker credit; late paid evidence updates the same result identity.")
    text(s,670,35,"R0 · lost reply, cancellation, Unknown, late evidence",26)
    actors=[(115,"Activation"),(395,"Domain transaction"),(675,"Provider"),(955,"Recovery worker"),(1220,"Result record")]
    for x,label in actors:
        box(s,x-105,70,210,45,label,"#d8e7ed")
        s.append(f'<path d="M{x},115 L{x},970" stroke="#a8bac5" stroke-dasharray="5 5"/>')
    events=[
      (115,395,170,"1  start: reserve, arm, dispatch"),
      (395,675,260,"2  send; provider commits Paid"),
      (675,395,340,"3  reply lost; ledger still pending"),
      (115,395,430,"4  cancel: fence activation; recovery_queue"),
      (395,1220,520,"5  finish Unknown + completion + credit (one domain transaction)"),
      (955,675,615,"6  lookup same operation key"),
      (675,955,690,"7  authenticated Paid receipt (scripted provider)"),
      (955,395,770,"8  receive: record Paid; recover_paid"),
      (395,1220,860,"9  update existing result to Ok; no second credit/completion"),
    ]
    for a,b,y,label in events:
        line(s,a,y,b,y,"","cancel" if y==340 else "")
        text(s,(a+b)/2,y-12,label,14)
    text(s,670,1000,"The other order retains its own recovery_queue and registration. Diagram is R0-specific, not a D0 scheduler.",16)
    save("r0-unknown.svg",s)

if __name__=="__main__":
    net_panels();handles();unknown()
    print("Rendered 3 static SVG diagrams; no Graphviz dependency")

