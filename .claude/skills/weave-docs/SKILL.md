---
name: weave-docs
description: Documentation currency for Weave changes. Computes the documentation impact of a change from the documentation map, applies it, regenerates generated documents, and runs the offline drift audit (repository or change scope). Use at claim time, before the In Review gate, at milestone exit, and whenever documents or the map change.
---

# Documentation impact and drift audit

Policy: `docs/development/documentation-currency.md`. Map:
`docs/development/documentation-map.md` (generated part from
`tools/weave_workflow/docmap.json`).

## At claim time

The `claim` command computes the impact list from the allowed paths and publishes it as
DOCS_IMPACT. Review it: add documents the map misses (with a reason) and never shorten it
without a recorded justification (`status: not-applicable`, `justification: ...`).

## Before the In Review gate

1. Apply every entry of the impact list. Use the `weave-docs-editor` subagent for larger
   edits; it may not change normative semantics, provenance or expected-rejection fixtures.
2. Regenerate, never hand-edit, generated documents:
   - `cd inventory-proof && python3 demo.py` (REPORT.md, ACTUAL_OUTPUT.txt and other outputs)
   - `cd specification && python3 scripts/refresh_reference_pages.py` (rule catalogue,
     conformance appendix)
   - `cd agent-kit && python3 scripts/sync_skill_reference.py` (skill copy of `agent-kit/docs/weave.md`)
   - `python3 -m tools.weave_workflow docs-map --write` (after editing `docmap.json`)
3. Update claims from tool output in the same change (test counts, state and edge counts,
   diagnostic codes, commands, hashes). If a figure cannot be verified, say so in the
   document instead of stating it.
4. If a boundary moved (something became implemented, or was narrowed), update the
   specification's `status.rst`, `limitations.rst` and `design-history.rst` and every document
   that stated the old boundary.
5. Run and publish the change-scope audit of the committed candidate, with the impact list
   from the packet:
   `python3 -m tools.weave_workflow docs-audit --repo <worktree> --base <base-sha> --impact <packet.json> --publish <N> --apply`.
   It publishes DOCS_AUDIT_RESULT (scope `change`, the head SHA, result, error count). On FAIL
   the In Review gate stays closed and the transition adds `agent:docs-stale`.
6. Warnings about protected vocabulary need a reviewer to confirm that the new use carries
   the specification's meaning.

## Periodic and milestone audits

Run `python3 -m tools.weave_workflow docs-audit` (repository scope) at the start of every
run and at milestone exit. Keep one `agent:managed` documentation-audit issue listing
residual drift. A milestone cannot exit while that issue lists drift in its scope.

## When documents are added or removed

Update `tools/weave_workflow/docmap.json` (managed, historical or generated lists, impact
rules, claims) and regenerate the map. Mark not-yet-existing or external paths in the
document with `<!-- docs-audit: planned ... -->` or `<!-- docs-audit: external ... -->`.
