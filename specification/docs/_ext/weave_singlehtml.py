"""Keep the pinned Sphinx 8.2 single-page output navigable."""
from docutils import nodes
from sphinx import addnodes
import re

def configure(app):
    # Alabaster's default single-page sidebar is not navigable; Furo's is.
    if app.builder.name=="singlehtml" and app.config.html_theme=="alabaster":
        app.config.html_sidebars={"**":["about.html","navigation.html"]}

def repair_anchors(app,tree,docname):
    if app.builder.name!="singlehtml":return
    # Single-page output has no general index; remove its per-document anchors.
    for entry in list(tree.findall(addnodes.index)):
        entry.parent.remove(entry)
    for element in tree.findall(nodes.Element):
        element["ids"]=[id for id in element.get("ids",[]) if not re.fullmatch(r"index-\d+",id)]
    ids={id for element in tree.findall(nodes.Element) for id in element.get("ids",[])}
    for ref in tree.findall(nodes.reference):
        uri=ref.get("refuri","")
        # Only document-local double fragments are affected. Do not rewrite
        # external URLs or a fragment whose destination has not been assembled.
        if uri.startswith("#document-") and uri.count("#")==2:
            anchor=uri.rsplit("#",1)[1]
            if anchor in ids:ref["refuri"]="#"+anchor

def setup(app):
    app.connect("builder-inited",configure)
    app.connect("doctree-resolved",repair_anchors)
    return {"version":"0.2","parallel_read_safe":True,"parallel_write_safe":True}

