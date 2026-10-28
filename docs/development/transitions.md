# State transitions and definition of done

Gates are pure functions in `tools/weave_workflow/transitions.py` over authenticated events,
maintainer decisions, the issue's current requirements digest, the candidate head and
integration evidence. Evaluate a gate without writing anything:

```bash
python3 -m tools.weave_workflow transition 6 "In Review" --worktree .worktrees/agent-6-machine-readable-diagnostics
```

| From → To | Required evidence |
| --- | --- |
| Todo → In Progress | Eligible milestone and task; dependency gate passes; fewer than `concurrency.max_active_implementation_issues` active implementation issues (claimed and not yet In Review), no held claim on the issue, and allowed paths disjoint from every active implementation issue's, all checked by `claim` under the coordinator lock ([scheduling.md](scheduling.md)); validated packet including documentation impact; exclusive claim (coordinator lock); CLAIMED, DOCS_IMPACT and PLAN published; isolated worktree assigned; requirements unchanged since PLAN |
| In Progress → In Review | Committed candidate in a clean worktree; IMPLEMENTATION_READY for that head mapping every PLAN criterion to evidence; VERIFICATION_RESULT PASS for the head; change-scope DOCS_AUDIT_RESULT PASS for the head (cited by IMPLEMENTATION_READY); local and safety LOCAL_REVIEW_RESULT PASS for the head; REVIEW_REQUESTED for the head |
| In Review → In Progress | A valid review requested changes (REVIEW_RESULT + CHANGES_REQUESTED), acceptance or documentation evidence failed for the head, the head moved since the review request, or requirements changed |
| In Review → Done | REVIEW_RESULT PASS answering the latest REVIEW_REQUESTED for the exact candidate, same base and current requirements, not superseded; review budget not exceeded (`review.max_rounds_per_attempt` counts the REVIEW_REQUESTED events of the current attempt, the highest attempt among the issue's events; rounds of a released attempt do not count); every blocking finding disposed; checks and documentation audit PASS for the head; maintainer decision or action recorded where the policy requires one; integration evidence derived by `tools/weave_workflow/integration.py` from the fetched PR and local Git (never supplied by the caller): a PR from the claim's recorded branch that closes the issue, merged into the integration branch (`policy.json` → `integration`), PR head equals the reviewed head, the complete check list of the PR head contains every required check (the policy's CI jobs plus any checks required by branch protection; unreadable protection fails the gate) and none failed, merge commit contained in `origin/main`, integrated tree equals the candidate merged into the first parent, and required human reviews satisfied (an approving review decision under branch protection; otherwise a merge by a maintainer login) |
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
  manual changes as conflicts; a legitimate maintainer decision is never overwritten
  blindly. The one recognised exception is the automation move described under
  [Guarded execution](#guarded-execution), which is still gated. Falsely
  completed work is reopened only through an auditable corrective transition; a later
  regression normally gets a linked new issue.

Run `git fetch` for `origin/main` before evaluating the Done gate so containment can be
checked; the integration branch comes from the policy and cannot be chosen on the command line. `transition N Done --worktree PATH` prints the derived integration evidence with the
gate result.

## Guarded execution

`transition N <status> --apply` publishes TRANSITION_INTENT with a unique operation id,
compares the observed board status with the expected one, writes the Status through the
resolved project, item, field and option IDs, reads it back, then publishes STATE_CHANGED
and swaps labels. Each phase is recorded in the operation ledger; `reconcile --apply`
completes or abandons partial operations after a restart.

GitHub's built-in project automation "item closed → Done" moves the card when the merged PR
closes the issue, before `transition N Done` runs. That case is recognised only when all of
these hold: the board shows Done, the last recorded STATE_CHANGED is to In Review, the issue
is closed as completed, and the derived integration evidence shows a merged PR from the
claim's recorded branch that closes the issue. `transition N Done` then evaluates the
In Review → Done gate with every condition above unchanged. On PASS, `--apply` publishes
TRANSITION_INTENT, reads the Status back as Done without writing it, and publishes
STATE_CHANGED (In Review → Done) and COMPLETED. `reconcile` reports the case as a note
("board moved to Done by project automation after merged PR #N"), not as a conflict.

Any other unrecorded status, including Done without such a merged PR, stays a conflict and
the Done gate refuses it. The workflow cannot read the automations through the API: inspect
them in the project settings and disable any other rule that moves cards to Done or
In Review, or record it as a known discrepancy (maintainer action).
