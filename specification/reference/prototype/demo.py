#!/usr/bin/env python3
"""Run the demonstration and regenerate its actual output and proof certificate."""
from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

from checker import CheckError, check_flow, explore_order, lower_flow_source, ordering_text, parse_net, proof_text, prove
from simulate import simulate, simulation_text
from coloured import parse_coloured, prove_colours, explore_colours
from durable import run_crash_cases
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
    coloured_source = (ROOT / 'Inventory.coloured.weave').read_text()
    coloured_net = parse_coloured(coloured_source)
    colour_proof = prove_colours(coloured_net)
    colour_check = explore_colours(coloured_net)
    colour_output = ['COLOURED PROTOCOL: Inventory.coloured.weave']
    for item in colour_proof['aggregate']:
        colour_output.append('PROVED aggregate ' + item['name'])
    for item in colour_proof['families']:
        colour_output.append('PROVED per-colour family ' + item['name'])
    colour_output += [f"CHECKED WITHIN BOUNDS orders=2, stock=2, states={colour_check['states']}, edges={colour_check['edges']}",
                      'CHECKED token identity on every enabled firing; unique admission per tenant/order']
    for name in check_flow(coloured_net.base, propagating):
        colour_output.append(f'CHECKED {name} against the coloured protocol API')
    wrong_colour = coloured_source.replace('transition sell[t, o]:\n        take 1 paid[t, o]\n        take 1 registrations[t, o]',
                                           'transition sell[t, o]:\n        take 1 paid[t, o]\n        take 1 registrations[t, other]')
    if wrong_colour == coloured_source: raise AssertionError('Cross-order mutation did not apply')
    mutated = parse_coloured(wrong_colour)
    for analyze, code in ((prove_colours, 'E412'), (explore_colours, 'E420')):
        try: analyze(mutated)
        except CheckError as error:
            if error.code != code: raise
            colour_output += ['', 'EXPECTED CROSS-ORDER REJECTION', error.render('cross-order-sell.weave')]
        else: raise AssertionError('Cross-order registration theft accepted')
    with tempfile.TemporaryDirectory() as directory:
        durable_cases = run_crash_cases(directory)
    colour_output += ['', 'DURABLE CRASH CASES (two orders; separate domain/provider SQLite databases)']
    for case in durable_cases:
        colour_output.append(f"PASSED {case['scenario']}: process exit={case['crash']['exit_code']} at {case['crash']['checkpoint']}")
        colour_output.append('  ' + json.dumps(case['marking'], sort_keys=True))
    colour_output += ['NOT ESTABLISHED orders>2 ordering exploration, a cutoff theorem, real-provider truthfulness/authentication, power-loss durability, distributed consensus, or compiler-to-runtime refinement.']
    output = colour_output + ['', 'LEGACY UNCOLOURED REGRESSIONS (orders=1 only)'] + output
    transcript = "\n".join(output) + "\n"
    (ROOT / 'colour-proof.json').write_text(json.dumps(colour_proof,indent=2)+'\n')
    (ROOT / 'colour-check.json').write_text(json.dumps(colour_check,indent=2)+'\n')
    (ROOT / 'durable-scenarios.json').write_text(json.dumps(durable_cases,indent=2)+'\n')
    (ROOT / "proof.json").write_text(json.dumps(certificate, indent=2) + "\n")
    (ROOT / "ordering.json").write_text(json.dumps(ordering, indent=2) + "\n")
    (ROOT / "scenarios.json").write_text(json.dumps(scenarios, indent=2) + "\n")
    (ROOT / "LOWERED_PROPAGATION.weave").write_text(lowered)
    (ROOT / "ACTUAL_OUTPUT.txt").write_text(transcript)
    report = f'''# Inventory: coloured checking and durable crash scenarios

This report is regenerated by `python3 demo.py`. The current protocol source is
`Inventory.coloured.weave`. `Inventory.weave` is retained as an explicitly
uncoloured regression fixture; its two-order limitation is stated in its output.

## Actual output

```text
{transcript.rstrip()}
```

## Source-level `?` diagnostics

The lowering records the origin of each generated propagation return. A live
handle on that path now produces `E204` at the original `?` line, explaining that
`Err`/`Unknown` may propagate while the named handle is still held and suggesting
consumption before `?` or explicit outcome handling. It does not describe a normal
return the programmer never wrote. The tests include an expression on line 4 and
verify both the rendered location and message. The lowered file remains available
for inspection; errors in that explicitly expanded file naturally use its lines.

## Current coloured net

```text
{coloured_source.rstrip()}
```

`available` is a shared one-SKU stock pool. Reservations, registrations, pending
requests, recovery, results, and identity permissions carry `[tenant, order]`.
A transition has a firing colour, and each arc has an explicit inscription.
Colour variables are sorted by their tenant/order position. Erasing an indexed
arc or mixing the sorts is rejected, rather than interpreted as a wildcard.

`reserve` consumes the order's single `identities[t,o]` token, stock, and a pool
credit. It cannot fire twice for the same identity. Release records `released[t,o]`
while returning the stock to the shared pool. The identity is not recycled.
The flow type indices themselves still do not prove freshness or resolve aliases:
uniqueness is enforced by this protocol token and the durable admission key.
A repeated raw reserve is disabled; duplicate inbound delivery resumes the same
job. This is not a claim that the type checker statically rejects every duplicate
reservation expression or proves such a caller deadlock-free.

## Accounting with colour

`colour-proof.json` records two aggregate proofs (stock and pool credits), three
invariant families (registration balance, identity conservation, job accounting),
the source inscriptions, and the actual two-colour incidence matrix with 32 rows
and 48 transition modes.

Each family has the form `sum(w[p] * M[p,c]) = k` for an arbitrary colour `c`.
For each transition binding, the prover groups input/output contributions by their
symbolic colour tuple. Every coefficient must cancel, and the per-colour initial
marking must satisfy the equality. This is a sufficient P-invariant argument for
**all colours and bindings in this restricted inscription language**. It does not
use the two-order exploration to infer an unbounded theorem.

The cross-order mutation changes `sell` to consume `paid[t,o]` and
`registrations[t,other]`. The aggregate count still balances, but the family has
uncancelled terms for `(t,o)` and `(t,other)` and fails with `E412`. Exploration
also finds the enabled firing, naming both orders and the stolen registration.
A cross-order read preserves arithmetic and is separately caught by the firing
identity property. Tests also exercise two tenants with the same order label.

## Ordering at two orders

The finite exploration exhausts **{colour_check['states']} states and
{colour_check['edges']} edges**, using two tenant/order pairs, two stock units,
one SKU, and one unit per order. Indexed places are bounded to one token per
colour; shared stock and credits have capacity two. The state budget is
{colour_check['max_states']}; no depth cutoff or silent successor pruning is used.
All 24 transitions are reached. The identity token, rather than an artificial
scheduler exclusion, enforces one reservation per order.

Payment and rejection witnesses and dispatch history are tracked separately for
each colour. Correlation checks compare every indexed input, read, and output
against the firing's colour. Safety properties refer to the corresponding
order's `released`, `sold`, pending, and registration states. No registration for
order B can satisfy order A's requirement in this model.

These ordering results are **CHECKED WITHIN BOUNDS**. There is no cutoff theorem
for arbitrary order counts; `orders>2` ordering exploration is explicitly
**NOT ESTABLISHED**. Arbitrary colour expressions, dynamic colour creation, more
SKUs, quantities, and cross-order business transactions are outside the fragment.

## Durable simulator

`durable.py` uses the same parsed inscriptions and enabledness rules through
`Unfolding.fire`; it does not maintain hand-written inventory deltas. The domain
and scripted payment provider use separate SQLite databases with WAL and
`synchronous=FULL`. Each domain transaction commits the marking and associated
ledger/journal changes together. The provider commits independently under a
stable operation key and request digest.

Every acceptance scenario terminates a child with `os._exit(91)` at its named
checkpoint and then opens fresh connections. No shutdown handler is needed to
save the state. A second order remains unresolved throughout each scenario, with
its own recovery registration, so resolving the first order must preserve it.
`durable-scenarios.json` contains actual exit checkpoints, event histories,
marking snapshots, operation records, result rows, and provider attempts/charges.

| Case | Required observation, asserted by the harness |
| --- | --- |
| Admission committed before source acknowledgment | Redelivery finds one admitted job for that identity |
| Result committed before worker acknowledgment | Result, job completion, and returned credit are all present; retry creates no second result or credit |
| Provider committed success but response was lost | Reopened domain retains the registration; provider status resolves the original operation |
| Cancellation after payment evidence but before sale | Paid cancellation commits the sale and closes its registration |
| Late receipt after cancellation | Stale generation cannot resume; the operation ledger accepts correlated evidence and recovery resolves the order |
| Inconclusive status | Repeated status checks never release stock; the two-attempt model budget escalates to manual with registration retained |

The adapter actually fires `adapter_dequeue`. Both request places are empty at
the end of all six cases. `finish_sold`, `finish_released`, and `finish_unknown`
return the pool credit and create the result token. The database transaction
also writes the result row and marks the job completed. A previously `Unknown`
result may be updated to a resolved status under the same identity; this is a
status update, not a second completion token or credit.

Additional tests kill a process before admission, start, receipt, and result
commits; verify rollback; kill it between dequeue and provider dispatch; resend
a lost response with the same key; reject swapped receipts; reject contradictory
final evidence; and resolve a previously escalated operation after late success.
A source digest prevents silently reopening stored state under different code.
There is no implementation of schema migration here.

This is a **single-machine process-crash model**, not a production runtime or a
verified storage engine. SQLite/OS commit semantics and the scripted provider's
key/evidence contract are assumptions. Power loss, disk corruption, real network
faults, authentication, Byzantine evidence, distributed consensus, and an
exhaustive exploration of crash schedules are not established. The durable driver
executes the protocol operations; it is not a compiler-refinement proof for every
possible flow. Recovery uses current runtime authority; late evidence does not
restore an old worker generation.

## Flow and lowering

The existing helper-based `?` example is checked against the coloured API:

```text
{propagating.rstrip()}
```

`LOWERED_PROPAGATION.weave` contains the generated exhaustive matches. `Err` and
`Unknown` move their payloads into the enclosing result, with exact payload types
and identity indices. Other live handles must be accounted for on early exits.
The earlier synchronous `simulate.py` remains a distinct reference-execution
regression, not the crash simulator.

## Reproduction and evidence boundaries

Run `python3 demo.py` and `python3 -m unittest discover -s tests -v`.
Use `python3 coloured.py analyze Inventory.coloured.weave` for the current net,
`python3 coloured.py check Inventory.coloured.weave examples/checkout_propagating.weave`
for combined checking, and `python3 durable.py` for the six crash cases alone.
`python3 durable.py --directory ./crash-run` keeps the SQLite files for inspection;
use a new directory because existing evidence is preserved.

The coloured certificate is an auditable arithmetic witness generated by this
checker, not a proof-assistant certificate or independently verified compiler.
The original certificate verifier continues to recheck only the legacy uncoloured
arithmetic. The main contribution remains source integration and the composition
of distinct checks. General language features and the broader ergonomics claim
remain outside this implementation.
'''
    (ROOT / "REPORT.md").write_text(report)
    print(transcript, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
