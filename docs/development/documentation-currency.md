# Documentation currency

Documentation is a deliverable of every change, not a follow-up. This repository's documents
make verifiable claims (test counts, state counts, diagnostic codes, snapshot hashes, command
names, profile boundaries), and the specification already re-checks its displayed examples
at build time. The workflow extends that discipline to the whole repository.

The machine-readable map is `tools/weave_workflow/docmap.json`; the human-readable
[documentation map](documentation-map.md) is partly generated from it.

## Rules

1. **Impact is computed at claim time.** Before delegating, the orchestrator derives the
   impact list from the task's allowed paths and the map, publishes it as DOCS_IMPACT, and
   includes it in the packet. The implementer may extend the list with justification and may
   not shorten it without orchestrator approval (a `not-applicable` entry with a
   justification).
2. **Claims are verified, not transcribed.** Counts, diagnostic codes, command names, file
   paths, profile boundaries and version or snapshot identifiers must be generated from, or
   checked against, tool output in the same change. Where a figure cannot be verified, the
   document says so instead of stating it.
3. **Drift audit.** `python3 -m tools.weave_workflow docs-audit` runs offline and checks:
   paths mentioned in managed documents exist (or are marked as planned or external targets);
   `weave.py`, `make` and workflow commands name real subcommands and targets; declared counts
   match the artefacts; diagnostic codes exist in a checker or `specification/rules.json`;
   synced copies are identical and provenance hashes match; generated documents match their
   generators. With `--base` it also checks the impact list, the changelog requirement, new or
   removed documents, moved boundary statements and new uses of protected vocabulary. It runs
   in `ci.yml` and at the In Progress → In Review gate as DOCS_AUDIT_RESULT. A failing audit
   labels the issue `agent:docs-stale` and blocks the transition. The audit, `docs-map` and
   the claim-time impact list read the map from the audited tree
   (`tools/weave_workflow/docmap.json` in that worktree or checkout), so a candidate that
   changes the map is audited against its own map. The running module's map is used only
   when neither the audited tree nor the base revision has one; a change that deletes the
   map is audited with the base map and reported as an error. In change scope (`--base`) the base revision's map is a
   floor: the audit applies the union of both maps' requirements (impact rules, required
   documents, managed-document globs, generated documents, protected labels, provenance
   manifests and synced copies; a claim id from the base map is checked with both
   definitions), only the exemptions both maps grant (vocabulary and historical-record
   exemptions, ignored path segments, diagnostic-code sources, path bases), and the base
   map's command sources; `docmap_version` may rise but not fall. Every removal or narrowing, and any change to another top-level
   key of the base map, is an error: it must be justified and approved by the maintainer.
   Keys only the candidate adds are allowed. The generated
   section of `documentation-map.md` is checked against the candidate's own map.
   Known limitation: the tooling records no approval that clears a docmap-floor error, so a
   legitimate narrowing keeps the change-scope audit, and with it the In Review gate,
   failing until the maintainer decides how to land it. Known limitation: CI (`ci.yml`) runs
   `docs-audit` without `--base`, so the floor and the other change-scope checks apply only
   where the audit is run with a base, such as the DOCS_AUDIT_RESULT for the In Review gate.
4. **Boundary statements move with the boundary.** When something documented as
   unimplemented, deferred or not established becomes implemented, every document that stated
   the limitation changes in the same change, including the specification's status profile
   table and limitations register, plus a design-history entry. The reverse applies when a
   capability is removed or narrowed. A gap is never described as closed before its tests and
   conformance metadata exist. The audit flags a removed boundary statement without
   `status.rst`, `limitations.rst` and `design-history.rst` updates.
5. **Evidence vocabulary is protected.** PROVED, CHECKED WITHIN BOUNDS, CHECKED flow,
   CHECKED pure, SCRIPTED, VIOLATED and NOT ESTABLISHED keep the specification's meaning. The audit flags
   new uses outside the specification and prototype for review.
6. **Generated documents are regenerated, not edited.** The rule catalogue, conformance
   appendix, prototype outputs and report, lowered sources, certificates and the generated
   part of the documentation map come from their scripts; a mismatch with the generator is a
   finding.
7. **Documentation-only changes follow the full workflow** (claim, review, transition) with a
   lighter review packet; they still need the drift audit and may not alter normative meaning
   without the corresponding semantic task.
8. **Periodic audit.** At the start of every run and at every milestone exit gate, the whole
   repository is audited, and a single `agent:managed` documentation-audit issue lists residual
   drift. Milestone exit requires that issue to be empty for the milestone's scope.
9. **Reviewers check documentation.** The local reviewer verifies the impact list was applied;
   the independent reviewer receives the list and the audit result and assesses the `DOC-n`
   criteria like any other.
10. **The specification is the source of truth for semantics.** When implementation and
    specification disagree, the change records a discrepancy in the specification's register
    and names the resolving task; documentation never papers over the disagreement.

## Marking targets

A path that does not exist yet, or that names something outside the repository, is marked in
the document so the audit skips it:

```markdown
<!-- docs-audit: planned crates/weave-check/ -- created by the Rust checker task -->
<!-- docs-audit: external preview/specimen.pdf -- path inside the original design bundle -->
```

Historical records (dated validation reports, the design history, the original
requirements) are listed in the map and are not claim-checked.
