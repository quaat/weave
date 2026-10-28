"""Execute every displayed implemented Weave example while building Sphinx."""
import json
from pathlib import Path
import re
import sys
import textwrap
from docutils import nodes
from docutils.parsers.rst import directives
from sphinx.errors import ExtensionError
from sphinx.util.docutils import SphinxDirective

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"scripts"))
from spec_checks import check_example

class WeaveCheck(SphinxDirective):
    optional_arguments=1
    final_argument_whitespace=True
    has_content=True
    option_spec={
        "expect":directives.unchanged_required,
        "profile":directives.unchanged_required,
        "context":directives.unchanged,
        "net":directives.path,
        "caption":directives.unchanged,
        "linenos":directives.flag,
        "start-at":directives.unchanged,
        "end-at":directives.unchanged,
    }
    def run(self):
        if "expect" not in self.options or "profile" not in self.options:
            raise self.error("weave-check requires :expect: and :profile:")
        current=Path(self.state.document.current_source).parent
        if self.arguments:
            path=(current/self.arguments[0]).resolve()
            self.env.note_dependency(str(path))
            source=path.read_text(encoding="utf-8")
            label=str(path.relative_to(ROOT))
        else:
            source="\n".join(self.content)+"\n";label=f"{self.env.docname}:{self.lineno}"
        net=(current/self.options["net"]).resolve() if "net" in self.options else None
        actual=check_example(source,self.options["profile"],self.options.get("context","file"),net)
        expected=self.options["expect"]
        if actual!=expected:
            raise self.error(f"Weave example {label}: expected {expected}; got {actual}")
        display=source
        if "start-at" in self.options:
            lines=display.splitlines()
            start=next((i for i,l in enumerate(lines) if self.options["start-at"] in l),None)
            if start is None: raise self.error("start-at text absent")
            display="\n".join(lines[start:])
        if "end-at" in self.options:
            lines=display.splitlines()
            end=next((i for i,l in enumerate(lines) if self.options["end-at"] in l),None)
            if end is None: raise self.error("end-at text absent")
            display="\n".join(lines[:end+1])
        display=textwrap.dedent(display).rstrip()+"\n"
        code=nodes.literal_block(display,display)
        code["language"]="weave";code["linenos"]="linenos" in self.options
        code.source=self.state.document.current_source;code.line=self.lineno
        container=nodes.container(classes=["weave-checked-example"])
        if "caption" in self.options:
            container+=nodes.paragraph(text=self.options["caption"],classes=["rubric"])
        container+=code
        container+=nodes.paragraph(text=f"Checked: {self.options['profile']} · {expected}",classes=["weave-check-status"])
        if not hasattr(self.env,"weave_checks"):self.env.weave_checks={}
        self.env.weave_checks[f"{self.env.docname}:{self.lineno}"]={
            "doc":self.env.docname,"source":label,"profile":self.options["profile"],
            "context":self.options.get("context","file"),"expected":expected,"actual":actual}
        return [container]

def audit_source(app,docname,source):
    if re.search(r"^\.\. code-block:: weave\s*$|^\.\. literalinclude:: .*\.weave\s*$",source[0],re.M):
        raise ExtensionError(f"{docname}: implemented Weave examples require weave-check")
def purge(app,env,docname):
    if hasattr(env,"weave_checks"):
        env.weave_checks={k:v for k,v in env.weave_checks.items() if v["doc"]!=docname}
def recheck(app,env,added,changed,removed):
    # Checker code and complete fragment templates can change independently of
    # an RST file. Re-read on every build so cached doctrees cannot hide drift.
    return sorted(env.found_docs-set(removed))
def finish(app,error):
    if error is None:
        values=list(getattr(app.env,"weave_checks",{}).values())
        (Path(app.outdir)/"weave-check-report.json").write_text(json.dumps(values,indent=2)+"\n")
def setup(app):
    app.add_directive("weave-check",WeaveCheck)
    app.connect("source-read",audit_source)
    app.connect("env-purge-doc",purge)
    app.connect("env-get-outdated",recheck)
    app.connect("build-finished",finish)
    return {"version":"0.2","parallel_read_safe":False,"parallel_write_safe":True}

