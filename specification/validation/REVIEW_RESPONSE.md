# Draft 0.2 review response

This revision changes the specification and documentation tooling. The vendored
version-3 prototype remains byte-for-byte unchanged. New D0 and N2 requirements
are explicit targets; they are not advertised as implemented features.

## Substantive findings

| Finding | Disposition | Where to review |
|---|---|---|
| 1. Payment-specific check grammar | MODEL-04 registered. D-01 adopts declared evidence classes and correlation strategies in N2. The legacy grammar stays reproducible; the N2 delta and migration mapping are explicit. | `docs/chapters/evidence-design.rst`, `grammar/weave-n2-delta.ebnf` |
| 2. Disabled calls | D-02 chooses waiting, with no marking change or fabricated failure outcome. Flow deadlock and indefinite waits are named. The fail-fast simulator does not implement D0. | `execution-contract.rst`, MODEL-05 |
| 3. Symbolic identities to colours | D0-COLOR-1/2 bind scalars and immutable handle colours to an exact firing mode. Ambiguous bindings are rejected. Admission tokens, rather than symbolic typing, govern repetition. | `execution-contract.rst`, MODEL-06 |
| 4. N0 versus N1 | Side-by-side structural and property diff, separate claim scopes, and an explicit N0-only label on observed executions. | `protocol-diff.rst`, `examples.rst` |
| 5. Interleaving | Net-visible await requests, atomic firings, and completions; local computation is invisible to the net. Exclusivity is scoped to owned handles. | D0-SCHEDULE-1 |
| 6. Formal static semantics | Call, bind, unit call, ordinary/tagged return, match and propagation rules over Sigma/Gamma/Delta; explicit lowering freshness. Stable labels, rule index, corpus and diagnostic cross-references. | `static-semantics.rst`, `rules.json` |
| 7. Grammar over-generation | Fourteen co-located syntax/static constraints. A parser generated from the EBNF agrees with the original pipeline on all 25 cases; shared semantic checking is disclosed. | `grammar.rst`, `scripts/grammar_audit.py` |
| 8. Conformance corpus | Promoted manifest and generated normative appendix with file, stage/profile, diagnostic and rule IDs. | `conformance.rst`, `examples/manifest.json` |

Chapter paths in the table are relative to `docs/chapters/` unless a full project
path is shown. D0 and N2 have normative target rules but no implementation or
passing conformance claim.

## Documentation and tooling

| Request | Delivery / limit |
|---|---|
| Rationale | Dedicated chapter covering linearity, three outcomes, resource nets, closed enums, waiting, and evidence declarations. |
| Four-draft design history | Evidence-based history and rejected/deferred feature table. The four original drafts were not recovered; exact chronology and motivations for Task, within, retry, effect rows and dataflow remain explicitly unverified. |
| Smaller protocol | Single-slot Lease net plus checked client. Structural/accounting and F0 checks pass. The payment-specific legacy ordering analyser returns E300; no invented lease evidence support is claimed. |
| Figures | Three shipped, pre-rendered SVGs: complete N0 transition panels, handle states, and the R0 Unknown path. Regeneration needs only Python; PNG renders were visually inspected. |
| Counterexamples | Actual E320/E420 diagnostics, precise transition-by-transition annotation, and a separate cross-order-read mutation. |
| R0 acceptance | Six crash-injection cases with persisted-state assertions and the other order's retained resources. |
| Spec-as-test | Local `weave-check` directive validates complete included files and actual inline fragments in explicit contexts; nine tooling tests cover important negative cases. Every build rechecks source, including incremental builds. |
| Security | Dedicated trust-boundary chapter on capabilities, adapters, authenticity, replay, fencing and model integrity. |
| Glossary | Admission, generation, lease, pending place, cancellation route, firing mode, unfolding, profile, witness and invariant distinctions. |
| Build hygiene | `make validate` includes grammar, rule drift, documentation and reference tests, strict HTML, and external linkcheck; `validate-offline` omits external links. Snapshot SHA-256 in every HTML footer; prefixed autosection labels supplement stable rule IDs. |

## Evidence and remaining boundaries

See `BUILD_REPORT.md` and the adjacent machine-readable reports for actual
results. Generated parsing is independent syntax checking followed by shared
reference semantics, not an independent implementation of the type system.
Passing the corpus does not prove language equivalence or soundness.

N2 remains a core language-design delta, with production adapter contracts still
to specify. D0 has no general scheduler or runtime refinement proof. Historical
draft reconstruction remains incomplete where source artifacts were unavailable.

