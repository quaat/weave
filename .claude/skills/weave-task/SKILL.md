---
name: weave-task
description: Execute one claimed Weave roadmap issue through bounded implementation, verification, documentation update and local review, up to the In Review gate. Use only after the weave-project skill has claimed the issue (CLAIMED and PLAN published, worktree created).
---

# Execute one claimed issue

Inputs: the issue number, the task packet path (printed by `claim --apply`; also in
`run status`), and the worktree. Policy: `docs/development/roles.md`,
`docs/development/review.md`, `docs/development/documentation-currency.md`.

The orchestrator (you, in the main conversation) is the only GitHub writer. Subagents return
structured messages; you validate them with
`python3 -m tools.weave_workflow event validate <file>` and publish them with
`python3 -m tools.weave_workflow event publish <file> --apply`. Publish a delegation before
the dependent work starts and a result before the next handoff.

## Steps

1. **Plan the verification.** For each criterion `AC-n` in the packet, write the
   verification you will accept (test, check, inspection). For Rust work, confirm the ADR
   from `docs/development/implementation-language.md` exists or make producing it the task.
2. **Delegate implementation.** Publish DELEGATED (delegate `implementer`, packet digest,
   base SHA, worktree). Launch the `weave-implementer` subagent with the full packet and the
   verification plan. Independent sub-parts may go to parallel implementers only with
   disjoint files.
3. **Handle questions.** Publish each QUESTION and your ANSWER. Escalate to the maintainer
   (`agent:needs-human`, BLOCKED) for decisions on rights, semantics or architecture.
4. **Verify.** Launch `weave-verifier` on the committed candidate head with the packet's
   checks. Publish VERIFICATION_RESULT with argv, working directory and exit code of every
   check. A failure goes back to the implementer; never reclassify it.
5. **Documentation.** Use the `weave-docs` skill: apply the impact list, regenerate generated
   documents, then run the change-scope audit for the candidate head and publish
   DOCS_AUDIT_RESULT. On failure add `agent:docs-stale` and return to step 2.
6. **Implementation ready.** Publish IMPLEMENTATION_READY with `head_sha`, `docs_updated`,
   `docs_audit_event_id` and a `criteria_map` entry for every criterion (location, check,
   evidence, documentation location).
7. **Local and safety review.** Launch `weave-local-reviewer` and `weave-safety-reviewer` on
   the same head. Publish both LOCAL_REVIEW_RESULT events. Findings go back to step 2; every
   fix moves the head, so steps 4–7 repeat for the new head.
8. **Independent review.** Use the `weave-review` skill.
9. **Transition.** Dry run first:
   `python3 -m tools.weave_workflow transition <N> "In Review" --worktree <path>`, then
   `--apply`. If the gate refuses, fix the reported gap; never work around it.
10. **Checkpoint** the next action and return control to `weave-project`.

## Stop conditions

Escalate instead of continuing when: a check, guarantee, evidence label or provenance record
would have to be weakened; criteria conflict with the specification; work is needed outside
the allowed paths; or the review budget is exhausted. Publish BLOCKED with the reason and
leave the issue in its truthful column.
