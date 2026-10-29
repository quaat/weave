# SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
# SPDX-License-Identifier: MIT
"""Wrap existing evidence files in weave-evidence-envelope-v1 envelopes.

Each wrapper reads one existing file, refuses a ``format`` it does not
implement, and emits one envelope per claim the file records. The claim label
is taken from the file's own result field where it has one, or from the fixed
rule documented on the wrapper and in evidence/README.md. Parts of a file that
record no claim under one of the six result labels are listed as not wrapped,
with the reason. The originals are only read, never written.

Hashes: ``wrapped.sha256`` is the hash of the file's bytes; ``sources`` and
``dependencies`` hash the files present under ``root`` when the envelope is
made. The wrapper does not re-run the producer. Where the original records its
own ``source_sha256``, the wrapper checks it against the source file and
refuses on a mismatch.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from . import __version__
from .documents import ENVELOPE, TRACE, canonical_bytes, parse, sha256_bytes, sha256_file
from .traces import ConversionError, from_counterexample, from_durable, from_simulation, require

LABEL_SCRIPTED = "SCRIPTED / passed scenario"

# Profiles each prototype tool supports: every module named in the "Reference"
# column of the profile table in specification/docs/chapters/status.rst
# (F0: checker.py; N0: checker.py; N1: coloured.py and checker.py; R0:
# durable.py). Tools not named there support no profile. A test compares this
# mapping with the table.
SUPPORTED_PROFILES = {
    "checker.py": ["F0", "N0", "N1"],
    "coloured.py": ["N1"],
    "durable.py": ["R0"],
}
PROTOTYPE_ARCHIVE = "weave-inventory-proof.zip"


@dataclass
class Wrapped:
    """The result of wrapping one file."""

    path: str
    envelopes: list[dict] = field(default_factory=list)
    traces: list[dict] = field(default_factory=list)
    not_wrapped: list[tuple[str, str]] = field(default_factory=list)


class Context:
    def __init__(self, root: Path):
        self.root = Path(root)
        provenance = json.loads((self.root / "specification/PROVENANCE.json").read_text(encoding="utf-8"))
        self.revision = provenance["document"]
        self.pinned = provenance["reference_files"]
        archive = [s for s in provenance["sources"] if s["filename"] == PROTOTYPE_ARCHIVE]
        self.prototype_version = archive[0]["version"] if len(archive) == 1 else None

    def file(self, rel: str) -> dict:
        path = self.root / rel
        require(path.is_file(), f"{rel}: file not found")
        return {"path": rel, "sha256": sha256_file(path)}

    def profiles(self, names) -> list[dict]:
        return [{"name": n, "revision": self.revision} for n in names]

    def prototype_tool(self, rel: str) -> dict:
        """A prototype module: version 3 only if its bytes match the pinned snapshot hash."""
        name = rel.rsplit("/", 1)[-1]
        pinned = self.pinned.get(f"reference/prototype/{name}")
        same = pinned is not None and sha256_file(self.root / rel) == pinned
        return {"name": rel, "version": self.prototype_version if same else None,
                "supported_profiles": SUPPORTED_PROFILES.get(name, [])}

    def tools(self, prototype: list[str], extra: list[dict] = ()) -> list[dict]:
        own = {"name": "evidence/weave_evidence", "version": __version__, "supported_profiles": []}
        return [self.prototype_tool(rel) for rel in prototype] + list(extra) + [own]


def load_original(root: Path, rel: str) -> tuple[object, dict]:
    path = Path(root) / rel
    data = path.read_bytes()
    try:
        document = parse(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as error:
        raise ConversionError(f"{rel}: not one strict JSON document: {error}") from error
    return document, {"path": rel, "sha256": sha256_bytes(data)}


def expect_format(document, rel: str, expected: str) -> None:
    require(isinstance(document, dict), f"{rel}: expected a JSON object")
    found = document.get("format", "(no format field)")
    require(found == expected, f"{rel}: refused: unrecognised format identifier {found!r}; this wrapper reads {expected!r}")


def expect_source(document: dict, rel: str, source: dict) -> None:
    require(document.get("source_sha256") == source["sha256"],
            f"{rel}: source_sha256 does not match {source['path']}; the file was not produced from this source")


def envelope(*, claim, label, profiles, wrapped, wrapped_format, sources, dependencies, tools,
             bounds=None, assumptions=(), scope=None, completeness=None, trace=None, runtime_status=None) -> dict:
    return {
        "format": ENVELOPE,
        "claim": claim,
        "claim_label": label,
        "runtime_status": runtime_status,
        "profiles": profiles,
        "bounds": bounds,
        "assumptions": list(assumptions),
        "scope": scope,
        "completeness": completeness,
        "wrapped": {"path": wrapped["path"], "sha256": wrapped["sha256"], "format": wrapped_format},
        "sources": sources,
        "dependencies": dependencies,
        "tools": tools,
        "trace": None if trace is None else {"format": TRACE, "sha256": sha256_bytes(canonical_bytes(trace))},
    }


def claim(name, pointer, statement=None, detail=None) -> dict:
    return {"name": name, "pointer": pointer, "statement": statement, "detail": detail or {}}


def status_label(entry: dict, where: str, allowed: tuple[str, ...]) -> str:
    """Take the label from the original's ``status`` field; refuse any other value."""
    status = entry.get("status")
    require(status in allowed, f"{where}: status {status!r} is not one this wrapper reads ({', '.join(allowed)})")
    return status


# ------------------------------------------------------------------ inventory-proof


def wrap_place_invariant(ctx: Context, rel: str = "inventory-proof/proof.json") -> Wrapped:
    """proof.json (weave-place-invariant-v1): one PROVED claim per invariant, label from ``status``."""
    doc, wrapped = load_original(ctx.root, rel)
    expect_format(doc, rel, "weave-place-invariant-v1")
    source = ctx.file("inventory-proof/Inventory.weave")
    expect_source(doc, rel, source)
    deps = [ctx.file("inventory-proof/checker.py"), ctx.file("inventory-proof/demo.py")]
    tools = ctx.tools(["inventory-proof/checker.py", "inventory-proof/demo.py"])
    out = Wrapped(rel)
    for i, inv in enumerate(doc["invariants"]):
        out.envelopes.append(envelope(
            claim=claim(inv["name"], f"/invariants/{i}", inv["expression"]),
            label=status_label(inv, f"{rel}/invariants/{i}", ("PROVED",)),
            profiles=ctx.profiles(["N0"]), wrapped=wrapped, wrapped_format=doc["format"],
            sources=[source], dependencies=deps, tools=tools, scope=doc["scope"]))
    return out


def wrap_one_order(ctx: Context, rel: str = "inventory-proof/ordering.json") -> Wrapped:
    """ordering.json (weave-one-order-check-v2): one claim per property, label from ``status``."""
    doc, wrapped = load_original(ctx.root, rel)
    expect_format(doc, rel, "weave-one-order-check-v2")
    source = ctx.file("inventory-proof/Inventory.weave")
    expect_source(doc, rel, source)
    deps = [ctx.file("inventory-proof/checker.py"), ctx.file("inventory-proof/demo.py")]
    tools = ctx.tools(["inventory-proof/checker.py", "inventory-proof/demo.py"])
    bounds = {k: doc[k] for k in ("stock", "orders", "admission", "admission_limit", "dispatch", "place_bound", "max_states")}
    completeness = {"complete": doc["complete"], "states": doc["states"], "edges": doc["edges"],
                    "unreached_transitions": doc["unreached_transitions"]}
    out = Wrapped(rel)
    for i, prop in enumerate(doc["properties"]):
        out.envelopes.append(envelope(
            claim=claim(prop["name"], f"/properties/{i}", detail={"model": doc["model"], "premise_states": prop["premise_states"]}),
            label=status_label(prop, f"{rel}/properties/{i}", ("CHECKED WITHIN BOUNDS",)),
            profiles=ctx.profiles(["N0"]), wrapped=wrapped, wrapped_format=doc["format"],
            sources=[source], dependencies=deps, tools=tools, bounds=bounds,
            assumptions=doc["assumptions"], completeness=completeness))
    return out


def wrap_colour_invariant(ctx: Context, rel: str = "inventory-proof/colour-proof.json") -> Wrapped:
    """colour-proof.json (weave-colour-invariant-v1): one claim per aggregate and family entry, label from ``status``."""
    doc, wrapped = load_original(ctx.root, rel)
    expect_format(doc, rel, "weave-colour-invariant-v1")
    source = ctx.file("inventory-proof/Inventory.coloured.weave")
    expect_source(doc, rel, source)
    modules = ["inventory-proof/coloured.py", "inventory-proof/checker.py", "inventory-proof/demo.py"]
    deps, tools = [ctx.file(m) for m in modules], ctx.tools(modules)
    out = Wrapped(rel)
    for group in ("aggregate", "families"):
        for i, inv in enumerate(doc[group]):
            out.envelopes.append(envelope(
                claim=claim(inv["name"], f"/{group}/{i}", inv["expression"], {"group": group}),
                label=status_label(inv, f"{rel}/{group}/{i}", ("PROVED",)),
                profiles=ctx.profiles(["N1"]), wrapped=wrapped, wrapped_format=doc["format"],
                sources=[source], dependencies=deps, tools=tools, scope=doc["scope"]))
    return out


def wrap_colour_exploration(ctx: Context, rel: str = "inventory-proof/colour-check.json") -> Wrapped:
    """colour-check.json (weave-colour-exploration-v1). Its properties carry no status field.

    Rule: ``coloured.explore_colours`` returns this document only after every
    listed property held in every explored state, and raises E420 (VIOLATED) or
    E422 (NOT ESTABLISHED) otherwise. Each listed property is therefore labelled
    CHECKED WITHIN BOUNDS when ``complete`` is true, and NOT ESTABLISHED otherwise.
    """
    doc, wrapped = load_original(ctx.root, rel)
    expect_format(doc, rel, "weave-colour-exploration-v1")
    source = ctx.file("inventory-proof/Inventory.coloured.weave")
    expect_source(doc, rel, source)
    modules = ["inventory-proof/coloured.py", "inventory-proof/checker.py", "inventory-proof/demo.py"]
    deps, tools = [ctx.file(m) for m in modules], ctx.tools(modules)
    require(isinstance(doc["complete"], bool), f"{rel}: complete must be a boolean")
    label = "CHECKED WITHIN BOUNDS" if doc["complete"] else "NOT ESTABLISHED"
    bounds = {k: doc[k] for k in ("orders", "colours", "stock", "max_states", "token_bound_per_colour")}
    completeness = {"complete": doc["complete"], "states": doc["states"], "edges": doc["edges"],
                    "unreached_transitions": doc["unreached_transitions"]}
    out = Wrapped(rel)
    for i, name in enumerate(doc["properties"]):
        detail = {"premise_states": doc["premise_states"][name]} if name in doc["premise_states"] else {}
        out.envelopes.append(envelope(
            claim=claim(name, f"/properties/{i}", detail=detail), label=label,
            profiles=ctx.profiles(["N1"]), wrapped=wrapped, wrapped_format=doc["format"],
            sources=[source], dependencies=deps, tools=tools, bounds=bounds,
            scope=doc["scope"], completeness=completeness))
    return out


def wrap_simulations(ctx: Context, rel: str = "inventory-proof/scenarios.json") -> Wrapped:
    """scenarios.json (no format field; a JSON array). Its runs carry no status field.

    Rule: ``demo.py`` writes this file only after ``simulate.simulate`` returned for
    each scripted reply; ``simulate`` raises if the flow fails its checks or fires a
    disabled transition. Each run is labelled SCRIPTED / passed scenario. The run's
    ``outcome`` (Ok, Err or Unknown) is the scripted application outcome and is kept
    in the trace, never as a result label.
    """
    doc, wrapped = load_original(ctx.root, rel)
    require(isinstance(doc, list), f"{rel}: refused: expected the unversioned JSON array written by demo.py")
    sources = [ctx.file("inventory-proof/Inventory.weave"), ctx.file("inventory-proof/examples/checkout_propagating.weave")]
    modules = ["inventory-proof/simulate.py", "inventory-proof/checker.py", "inventory-proof/demo.py"]
    deps, tools = [ctx.file(m) for m in modules], ctx.tools(modules)
    out = Wrapped(rel)
    for i, run in enumerate(doc):
        trace = from_simulation(run, f"{rel}/{i}")
        out.traces.append(trace)
        out.envelopes.append(envelope(
            claim=claim(f"{run['entry']}[{run['outcome']}]", f"/{i}",
                        detail={"scripted_outcome": run["outcome"], "return_type": run["return_type"]}),
            label=LABEL_SCRIPTED, profiles=ctx.profiles(["F0", "N0"]), wrapped=wrapped, wrapped_format=None,
            sources=sources, dependencies=deps, tools=tools, trace=trace))
    return out


def wrap_durable(ctx: Context, rel: str = "inventory-proof/durable-scenarios.json") -> Wrapped:
    """durable-scenarios.json (no format field; a JSON array): label from ``status``, PASSED only.

    ``status: PASSED`` is the prototype's record that the crash case satisfied its
    assertions; it maps to SCRIPTED / passed scenario. Any other status is refused.
    The prototype records no runtime status, so ``runtime_status`` is null.
    """
    doc, wrapped = load_original(ctx.root, rel)
    require(isinstance(doc, list), f"{rel}: refused: expected the unversioned JSON array written by demo.py")
    sources = [ctx.file("inventory-proof/Inventory.coloured.weave")]
    modules = ["inventory-proof/durable.py", "inventory-proof/coloured.py", "inventory-proof/checker.py", "inventory-proof/demo.py"]
    deps, tools = [ctx.file(m) for m in modules], ctx.tools(modules)
    out = Wrapped(rel)
    for i, case in enumerate(doc):
        trace = from_durable(case, f"{rel}/{i}")
        status_label(case, f"{rel}/{i}", ("PASSED",))
        out.traces.append(trace)
        out.envelopes.append(envelope(
            claim=claim(case["scenario"], f"/{i}", detail={"crash": case["crash"]}),
            label=LABEL_SCRIPTED, profiles=ctx.profiles(["R0"]), wrapped=wrapped, wrapped_format=None,
            sources=sources, dependencies=deps, tools=tools, trace=trace))
    return out


# ------------------------------------------------------------------ specification


SPEC_MODULES = ["specification/reference/prototype/checker.py", "specification/reference/prototype/coloured.py",
                "specification/reference/prototype/simulate.py"]


def wrap_spec_validation(ctx: Context, rel: str = "specification/validation/report.json") -> Wrapped:
    """report.json (weave-specification-validation-v1), written by specification/scripts/validate.py.

    Wrapped: accepted flow cases (CHECKED flow; validate.py checked the flow and its
    lowering against the N0 net and the N1 net's API), the counterexamples
    (VIOLATED, with the trace read from validation/counterexample-<code>.txt) and
    the scripted scenarios (SCRIPTED / passed scenario; validate.py compares each
    final marking with the manifest). Not wrapped: expected-rejection cases, which
    record a diagnostic code rather than a claim under one of the six labels, and
    summary fields that restate counts without a per-claim result.
    """
    doc, wrapped = load_original(ctx.root, rel)
    expect_format(doc, rel, "weave-specification-validation-v1")
    examples = "specification/examples"
    manifest = json.loads((ctx.root / examples / "manifest.json").read_text(encoding="utf-8"))
    expect_format(manifest, f"{examples}/manifest.json", "weave-conformance-v1")
    deps = [ctx.file("specification/scripts/validate.py"), ctx.file(f"{examples}/manifest.json")] + [ctx.file(m) for m in SPEC_MODULES]
    tools = ctx.tools(SPEC_MODULES, [{"name": "specification/scripts/validate.py", "version": None, "supported_profiles": []},
                                     {"name": "python", "version": doc["python"], "supported_profiles": []}])
    nets = [ctx.file(f"{examples}/nets/Inventory.weave"), ctx.file(f"{examples}/nets/Inventory.coloured.weave")]
    by_file = {c["file"]: c for c in manifest["cases"]}
    accepted = set(doc["accepted_flows_checked_original_and_lowered_against_n0_and_n1"])
    out = Wrapped(rel)
    common = dict(wrapped=wrapped, wrapped_format=doc["format"], dependencies=deps, tools=tools, scope=doc["scope"])
    for i, case in enumerate(doc["cases"]):
        pointer = f"/cases/{i}"
        entry = by_file.get(case["file"])
        require(entry is not None, f"{rel}{pointer}: {case['file']} is not in the manifest")
        if case["expected"] == case["actual"] == "ACCEPT" and entry["kind"] == "flow" and case["file"] in accepted:
            out.envelopes.append(envelope(
                claim=claim(case["file"], pointer, entry.get("lesson"), {"case": entry["id"], "rules": entry["rules"]}),
                label="CHECKED flow", profiles=ctx.profiles(entry["profile"].split("/")),
                sources=[ctx.file(f"{examples}/{case['file']}")] + nets, **common))
        else:
            reason = (f"{entry['kind']} case, expected {case['expected']}, actual {case['actual']}: a diagnostic "
                      "regression outcome, not a claim under one of the six labels")
            if case["actual"] in doc["counterexamples"]:
                reason += f"; the VIOLATED claim is wrapped from /counterexamples/{doc['counterexamples'].index(case['actual'])}"
            out.not_wrapped.append((pointer, reason))
    for i, code in enumerate(doc["counterexamples"]):
        text_rel = f"specification/validation/counterexample-{code}.txt"
        text = (ctx.root / text_rel).read_text(encoding="utf-8")
        trace = from_counterexample(text, text_rel)
        net_rel = "specification/" + trace["context"]["location"].rsplit(":", 1)[0]
        require(trace["context"]["diagnostic"] == code, f"{text_rel}: diagnostic is not {code}")
        out.traces.append(trace)
        rest = {k: v for k, v in common.items() if k != "dependencies"}
        out.envelopes.append(envelope(
            claim=claim(trace["subject"], f"/counterexamples/{i}", f"VIOLATED {trace['subject']} {trace['context']['model']}",
                        {"diagnostic": code, "counterexample": text_rel}),
            label="VIOLATED", profiles=ctx.profiles(["N0"] if code == "E320" else ["N1"]),
            sources=[ctx.file(net_rel)], dependencies=deps + [ctx.file(text_rel)], trace=trace, **rest))
    scenarios = manifest["scenarios"]
    require(len(scenarios) == len(doc["scenarios"]), f"{rel}: scenarios do not match the manifest")
    for i, (run, entry) in enumerate(zip(doc["scenarios"], scenarios)):
        require(run["outcome"] == entry["outcome"], f"{rel}/scenarios/{i}: outcome does not match the manifest")
        out.envelopes.append(envelope(
            claim=claim(f"{entry['entry']}[{run['outcome']}]", f"/scenarios/{i}",
                        detail={"scripted_outcome": run["outcome"], "expected_marking": entry["marking"]}),
            label=LABEL_SCRIPTED, profiles=ctx.profiles(["F0", "N0"]),
            sources=[ctx.file(f"{examples}/{entry['file']}"), nets[0]], **common))
    for key in ("reference_integrity", "lease", "n0", "n1"):
        out.not_wrapped.append((f"/{key}", "summary field without a per-claim result label"))
    return out


WRAPPERS = {
    "inventory-proof/proof.json": wrap_place_invariant,
    "inventory-proof/ordering.json": wrap_one_order,
    "inventory-proof/colour-proof.json": wrap_colour_invariant,
    "inventory-proof/colour-check.json": wrap_colour_exploration,
    "inventory-proof/scenarios.json": wrap_simulations,
    "inventory-proof/durable-scenarios.json": wrap_durable,
    "specification/validation/report.json": wrap_spec_validation,
}


def wrap(root: Path, rel: str) -> Wrapped:
    if rel not in WRAPPERS:
        raise ConversionError(f"{rel}: no wrapper; wrappable files: {', '.join(WRAPPERS)}")
    return WRAPPERS[rel](Context(root), rel)


def rederive(envelope: dict, root: Path, cache: dict | None = None) -> list[str]:
    """Re-derive ``envelope`` from its wrapped file with the same wrapper and compare every field.

    Returns one error per top-level field that differs (claim, claim_label, scope,
    bounds, completeness, assumptions, profiles, hashes, tools, trace, ...), or the
    reason the claim cannot be re-derived. An empty list means the envelope is
    exactly what the wrapper produces from the files under ``root`` now.
    """
    rel = envelope["wrapped"]["path"]
    pointer = envelope["claim"]["pointer"]
    if rel not in WRAPPERS:
        return [f"no wrapper for {rel}; the claim cannot be re-derived"]
    cache = {} if cache is None else cache
    if rel not in cache:
        try:
            cache[rel] = wrap(root, rel)
        except (ConversionError, OSError, ValueError, KeyError, IndexError, TypeError) as error:
            cache[rel] = f"{type(error).__name__}: {error}"
    result = cache[rel]
    if isinstance(result, str):
        return [f"re-derivation from {rel} refused: {result}"]
    derived = [e for e in result.envelopes if e["claim"]["pointer"] == pointer]
    if len(derived) != 1:
        return [f"{rel} has no claim at {pointer!r}"]
    same = lambda a, b: json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    return [f"{key}: differs from the envelope re-derived from {rel}{pointer}"
            for key in sorted(set(envelope) | set(derived[0])) if not same(envelope.get(key), derived[0].get(key))]


def wrap_all(root: Path) -> list[Wrapped]:
    ctx = Context(root)
    return [fn(ctx, rel) for rel, fn in WRAPPERS.items()]
