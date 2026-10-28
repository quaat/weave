#!/usr/bin/env python3
"""Run the demonstration and regenerate its actual output and proof certificate."""
from __future__ import annotations

import json
import re
from pathlib import Path

from checker import CheckError, check_flow, explore_order, lower_flow_source, ordering_text, parse_net, proof_text, prove
from simulate import simulate, simulation_text
from verify_certificate import verify

ROOT = Path(__file__).resolve().parent


def main() -> int:
    source = (ROOT / "Inventory.weave").read_text()
    net = parse_net(source)
    certificate = prove(net)
    ordering = explore_order(net)
    output = [proof_text(net, certificate), "", ordering_text(ordering), ""]
    good = (ROOT / "examples/checkout.weave").read_text()
    composed = (ROOT / "examples/checkout_composed.weave").read_text()
    propagating = (ROOT / "examples/checkout_propagating.weave").read_text()
    lowered = lower_flow_source(propagating)
    check_flow(net, lowered)
    for program in (good, composed, propagating):
        for name in check_flow(net, program):
            output.append(f"CHECKED {name}: nominal types, indexed permits, exhaustive outcomes, linear calls/returns, no drops")
    expected = {"direct_charge": "E201", "drop_hold": "E204", "forge_escrow": "E205", "wrong_order": "E209"}
    for name, code in expected.items():
        file = ROOT / f"examples/{name}.weave"
        try:
            check_flow(net, file.read_text())
        except CheckError as error:
            if error.code != code:
                raise
            output.extend(["", "EXPECTED REJECTION", error.render(f"examples/{file.name}")])
        else:
            raise AssertionError(f"Invalid example was accepted: {file.name}")
    for name in ("skim", "lose_paid", "bogus_sell", "quick_recover", "leak", "manual_leak"):
        broken = source + "\n" + (ROOT / f"mutations/{name}.weave").read_text()
        expected_code = "E101"
        try:
            mutated_net = parse_net(broken)
            prove(mutated_net)
            output += ["", f"MUTATION {name}: both aggregate invariants still hold"]
            explore_order(mutated_net)
        except CheckError as error:
            if error.code != expected_code:
                raise
            output += ["", f"EXPECTED REJECTION ({name})", error.render(f"mutated-{name}.weave")]
        else:
            raise AssertionError(f"Protocol violation accepted: {name}")
    for name, place, property_name in (
        ("quick_recover", "recovery_queue", "sold_requires_paid"),
        ("leak", "inflight", "dispatched_release_requires_rejection"),
        ("manual_leak", "recovery_queue", "dispatched_release_requires_rejection"),
    ):
        broken = source + "\n" + (ROOT / f"mutations/{name}.weave").read_text()
        for runtime_place in (place, "registrations"):
            broken = re.sub(rf"(    runtime_state {runtime_place} consumers [^\n]+)", rf"\g<1>, {name}", broken)
        mutated_net = parse_net(broken)
        prove(mutated_net)
        try:
            explore_order(mutated_net)
        except CheckError as error:
            if error.code != "E320" or property_name not in error.message:
                raise
            output += ["", f"EXPECTED ORDERING FAILURE ({name} explicitly authorized; both invariants hold)", error.render(f"authorized-{name}.weave")]
        else:
            raise AssertionError(f"Authorized protocol violation accepted: {name}")
    # An authorized consumer can itself be wrong: sealing alone cannot detect it.
    broken = source.replace("transition cancel_paid:\n        take 1 paid\n        take 1 registrations\n        put 1 sold",
                            "transition cancel_paid:\n        take 1 paid\n        take 1 registrations\n        put 1 available")
    if broken == source:
        raise AssertionError("Cancellation mutation did not apply")
    mutated_net = parse_net(broken)
    prove(mutated_net)
    try:
        explore_order(mutated_net)
    except CheckError as error:
        if error.code != "E320" or "dispatched_release_requires_rejection" not in error.message:
            raise
        output += ["", "EXPECTED ORDERING FAILURE (authorized cancel releases paid stock)", error.render("mutated-cancel.weave")]
    else:
        raise AssertionError("Paid release accepted")
    broken_flow = composed.replace("    await settle(result)", "    let stolen = await Inventory.arm(hold)\n    await settle(result)")
    try:
        check_flow(net, broken_flow)
    except CheckError as error:
        if error.code != "E203":
            raise
        output += ["", "EXPECTED CALL-BOUNDARY FAILURE (caller reuses transferred hold)", error.render("mutated-checkout_composed.weave")]
    else:
        raise AssertionError("Transferred hold was reusable")
    early_drop = """flow abandon(result: ChargeOutcome[t, o], extra: Paid[u, v]) -> ChargeOutcome[t, o]:
    let paid = result?
    await Inventory.sell(extra)
    return Ok(paid)
"""
    try:
        check_flow(net, early_drop)
    except CheckError as error:
        if error.code != "E204" or error.line != 2:
            raise
        output += ["", "EXPECTED PROPAGATION FAILURE (another handle is live at ?)", error.render("early-drop.weave")]
    else:
        raise AssertionError("Early return silently dropped another handle")
    # Change the model itself: release manufactures one additional unit of stock.
    broken = source.replace("transition release:\n        take 1 unpaid\n        take 1 registrations\n        put 1 available",
                            "transition release:\n        take 1 unpaid\n        take 1 registrations\n        put 2 available")
    if broken == source:
        raise AssertionError("Mutation did not apply")
    try:
        prove(parse_net(broken))
    except CheckError as error:
        if error.code != "E112":
            raise
        output.extend(["", "EXPECTED INVARIANT FAILURE (mutated release)", error.render("mutated-Inventory.weave")])
    else:
        raise AssertionError("Stock-creating mutation was accepted")
    scenarios = [simulate(net, propagating, "checkout_propagating", tag) for tag in ("Ok", "Err", "Unknown")]
    unknown = scenarios[2]
    returns = [e for e in unknown["events"] if e["kind"] == "RETURN" and e["tag"] == "Unknown"]
    assert [e["name"] for e in returns] == ["pay_with", "place_order"]
    assert all(e["marking"]["uncertain"] == e["marking"]["registrations"] == 1 for e in returns)
    assert unknown["marking"]["recovery_queue"] == unknown["marking"]["registrations"] == 1
    for scenario in scenarios:
        output += ["", simulation_text(scenario)]
    output += ["", f"RECHECKED {verify(source, certificate)} source-bound invariant certificates"]
    transcript = "\n".join(output) + "\n"
    (ROOT / "proof.json").write_text(json.dumps(certificate, indent=2) + "\n")
    (ROOT / "ordering.json").write_text(json.dumps(ordering, indent=2) + "\n")
    (ROOT / "scenarios.json").write_text(json.dumps(scenarios, indent=2) + "\n")
    (ROOT / "LOWERED_PROPAGATION.weave").write_text(lowered)
    (ROOT / "ACTUAL_OUTPUT.txt").write_text(transcript)
    report = f'''# Inventory: runtime sealing, rejection evidence, and `?`

Generated by `python3 demo.py`. All diagnostic and scenario output below is
computed from the included sources. The previous one-witness model admitted
release after dispatch without rejection; this revision checks that missing rule.

| Result | Meaning |
| --- | --- |
| `PROVED` | Standard P-invariant accounting equalities for arbitrary stock |
| `CHECKED WITHIN BOUNDS` | Safety in a declared one-order guard abstraction |
| `CHECKED` | Structural resource sealing and nominal linear typing |
| `SCRIPTED` | Concrete in-memory execution of one supplied foreign outcome |

The P-invariant method is textbook. The contribution here is source integration
and composition with ownership and ordering checks. The reference executor is
not a durable runtime or an independent refinement proof.

## Actual analyzer, type-checker, and reference-execution output

```text
{transcript.rstrip()}
```

## Executable net source

```text
{source.rstrip()}
```

## Propagating `Unknown` across helper boundaries

```text
{propagating.rstrip()}
```

`?` unwraps `Ok` on the continuing path. On `Err` and `Unknown`, it returns the
same tagged linear payload through the enclosing flow's declared result enum.
No cancellation, release, recovery handoff, or implicit destructor is inserted.
All other live handles must be discharged on each early-return path too.

The source enum must have exactly `Ok`, `Err`, and `Unknown` (the generated match
is exhaustive). The destination must declare compatible `Err` and `Unknown`
payloads, including identical identity indices. `CheckoutOutcome` changes only
`Ok` to `Unit`, allowing a successful sale to consume `Paid` before returning.
This is checked compatibility between declared nominal cases, not an inferred
open union or an error conversion. Enums now support `Unit` payloads; foreign
outcomes still must carry protocol-state resources in all three cases.

`return Ok(paid)` wraps an existing handle; it cannot mint one. `return Ok()` is
allowed only for a declared `Unit` payload. Return constructors and every residual
path use the same linear move and scope-exit checks as ordinary returns.

## Actual lowering (also type-checked)

```text
{lowered.rstrip()}
```

Fresh internal bindings avoid source names, and generated nodes retain the `?`
line for diagnostics. The same lowered tree is passed to the flow checker and
the reference executor. `LOWERED_PROPAGATION.weave` is a separately checkable
rendering. The original direct and helper-based examples remain checked too.

In the scripted `Unknown` run, `charge_unknown` creates `Uncertain` while leaving
one registration. `pay_with` returns `Unknown` and then `place_order` does the
same. Neither early return fires a net transition: both snapshots still contain
`uncertain=1, registrations=1`. The outer handler fires `handoff`, producing
`recovery_queue=1, registrations=1`. The `Ok` and `Err` scenarios instead exercise
sale and confirmed rejection/release. These are concrete executions of this
restricted interpreter, not a proof of arbitrary distributed executions.

## Sealed consumers and ordering are independent checks

Every runtime-owned place now requires an explicit consumer list, including
`registrations`. Missing lists are rejected. Each listed transition must exist
and consume exactly one token from that place. Foreign outcomes and cancellation
routes retain their existing signature/arc validation. All activation-owned
places remain sealed through their exported API and cancellation declarations.

The six supplied theft/sale transitions are rejected structurally with `E101`.
The demo then explicitly authorizes `quick_recover`, `leak`, and `manual_leak` in
all affected consumer lists. Both aggregate invariants still hold, but exploration
reports an unpaid sale or release without rejection, with a firing trace.
A mutation to the authorized `cancel_paid` body fails that same release rule.
Changing the trusted module's consumer list therefore does not waive ordering.

## Exact bounded semantics

The model fixes stock to one and permits `reserve` at most once. All 12 places,
all 21 transitions, and read arcs participate. It exhausts {ordering['states']}
states and {ordering['edges']} edges; all transitions and all property premises
are reached. The per-place bound is {ordering['place_bound']} tokens and the
search budget is {ordering['max_states']} states. Exceeding either is
`NOT ESTABLISHED`, never silent pruning. There is no depth cutoff.

Four monotone flags record admission, dispatch, paid evidence, and final rejection
evidence. The observed dispatch must be the foreign signature's dispatch
transition. `establishes_paid` and `establishes_rejected` guards set their witness
only on the transition where they occur. Other guards enable nondeterministically;
false guard outcomes stutter. Witnesses are independent: neither resets the other.
A test supplies both witnesses and verifies that paid stock still cannot return
to `available`. There is no hidden mutual-exclusion pruning.

The central new source property is:

```text
property dispatched_release_requires_rejection: after dispatch marked available requires rejected_evidence
```

Pre-dispatch cancellation can release without rejection. After dispatch, releases
from inflight, recovery, manual handling, or a corrupted paid cancellation require
rejection evidence. Separate paid-history and typed-state properties remain;
presence of registration is also checked in uncertain, recovery, and manual states.

Independent provider messages, contradictory late replies, and receipt correlation
are not modeled. Guard truthfulness, consistency, and order identity are assumed
and explicitly listed in `NOT ESTABLISHED`. This is an isolated order model, not
a cutoff theorem for arbitrarily many orders or a colored-token runtime.

`fast_escalate` is rejected when undeclared, but authorizing it or removing the
budget guard from `escalate` does not violate these safety properties. Quantitative
retry/time budgets are **not checked** and are explicitly listed as unestablished.

## Accounting and remaining boundary

The checker derives `C = Post - Pre`, verifies the symbolic initial marking and
`wᵀ C = 0`, and reports only these accounting equalities as `PROVED`.
`registration_balance` remains an aggregate count, not a per-order correlation
proof. `verify_certificate.py` rechecks arithmetic but shares the parser and
expression reader; `ordering.json` is an exploration summary, not an independent
proof certificate.

Still absent from the flow fragment: general expressions, `within`, `retry`,
ordinary conditionals, loops, `parallel`, recursion, higher-order flows, and
statements after an explicit terminal match. The new `?` can sequence continuations
by lowering them inside its success branch. All helpers are checked, including
unused helpers. The broader language ergonomics claim remains untested.

Persistence, physical worker failure, asynchronous cancellation, provider contracts,
liveness, upgrades, and source-to-durable-runtime refinement are not established.
The reference executor is synchronous, uses one scripted foreign completion, and
sends no network requests. It does not simulate a provider delivery queue; the
`charge_requests` token can remain in the projection after a supplied completion.

See `README.md` for commands and `DESIGN_NOTES.md` for separate proposed mechanisms.
'''
    (ROOT / "REPORT.md").write_text(report)
    print(transcript, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
