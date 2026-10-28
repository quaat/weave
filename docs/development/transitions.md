# State transitions and definition of done

Gates are pure functions in `tools/weave_workflow/transitions.py` over authenticated events,
maintainer decisions, the issue's current requirements digest, the candidate head and
integration evidence. Evaluate a gate without writing anything:

```bash
python3 -m tools.weave_workflow transition 6 "In Review" --worktree .worktrees/agent-6-machine-readable-diagnostics
```

| From → To | Required evidence |
| --- | --- |
| Todo → In Progress | Eligible milestone and task; dependency gate passes; validated packet including documentation impact; exclusive claim (coordinator lock); CLAIMED, DOCS_IMPACT and PLAN published; isolated worktree assigned; requirements unchanged since PLAN |
| In Progress → In Review | Committed candidate in a clean worktree; IMPLEMENTATION_READY for that head mapping every PLAN criterion to evidence; VERIFICATION_RESULT PASS for the head; change-scope DOCS_AUDIT_RESULT PASS for the head (cited by IMPLEMENTATION_READY); local and safety LOCAL_REVIEW_RESULT PASS for the head; REVIEW_REQUESTED for the head |
| In Review → In Progress | A valid review requested changes (REVIEW_RESULT + CHANGES_REQUESTED), acceptance or documentation evidence failed for the head, the head moved since the review request, or requirements changed |
| In Review → Done | REVIEW_RESULT PASS answering the latest REVIEW_REQUESTED for the exact candidate, same base and current requirements, not superseded; review budget not exceeded; every blocking finding disposed; checks and documentation audit PASS for the head; maintainer decision or action recorded where the policy requires one; integration evidence: PR merged, PR head equals the reviewed head, checks passed, merge commit contained in `main`, integrated tree equals the reviewed tree, required human reviews satisfied |
| In Progress → Todo | RELEASED published, preserving partial work and the claim release |

A failing documentation audit at the In Review gate adds `agent:docs-stale` and blocks the
transition.

## Rules

- **Done means accepted, integrated and documented.** AI-reviewed work awaiting a human
  merge stays In Review with `agent:ready-to-merge`. Approval grants no merge authority.
- A decision-only issue needs the designated maintainer's recorded decision and every
  criterion; no PR is fabricated for it.
- A runtime task is not complete because a prototype demonstration passes.
- Merge authority stays with the maintainer (`merge.delegated_to_coordinator: false`).
  Authorised merges use an expected-head guard; if the branch changes, gates are recomputed.
  Matching only the final merge commit to the reviewed head is insufficient: the Done gate
  also requires the integrated tree to equal the reviewed tree.
- Blocked work stays in its truthful column with `agent:blocked` or `agent:needs-human`. A
  review outage stays In Review with a blocker and no approval. A timeout or invalid response
  is not a verdict.
- Manual card moves or issue closure never satisfy gates. `reconcile` reports unexpected
  manual changes; a legitimate maintainer decision is never overwritten blindly. Falsely
  completed work is reopened only through an auditable corrective transition; a later
  regression normally gets a linked new issue.

## Guarded execution

`transition N <status> --apply` publishes TRANSITION_INTENT with a unique operation id,
compares the observed board status with the expected one, writes the Status through the
resolved project, item, field and option IDs, reads it back, then publishes STATE_CHANGED
and swaps labels. Each phase is recorded in the operation ledger; `reconcile --apply`
completes or abandons partial operations after a restart.

GitHub's built-in project automations (for example "item closed → Done") would compete with
these gates. Inspect them in the project settings; the workflow cannot read them through the
API. Disable any rule that moves cards to Done or In Review automatically, or record it as a
known discrepancy (maintainer action).
