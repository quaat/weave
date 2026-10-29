---
name: weave-review
description: Independent review of a Weave task candidate. Builds the review packet, launches a fresh read-only Codex session, validates the structured result against the exact request, publishes it, and records findings and dispositions. Use after verification, documentation audit and local and safety reviews have passed for the candidate head.
---

# Independent review

Policy: `docs/development/review.md`. The reviewer is not you and not a Claude subagent: it
is a fresh `codex exec` session with no GitHub credentials, no MCP servers and a read-only
sandbox.

1. Confirm the worktree is clean and committed. The head you review is the candidate; any
   later edit invalidates the review.
2. Dry run and read the packet:
   `python3 -m tools.weave_workflow review <N> --worktree <path>`.
   Check that it contains the criteria, documentation criteria, verification results with
   exit codes, the documentation audit result, and the local-review findings with
   dispositions. Do not add text that tells the reviewer to agree.
3. Run it: `python3 -m tools.weave_workflow review <N> --worktree <path> --apply`, adding
   `--ci-link URL` and `--limitation "..."` where relevant. This publishes REVIEW_REQUESTED,
   runs Codex, validates the result (schema, identity, head, base, requirements, consistency)
   and publishes REVIEW_RESULT with CLI, version and session provenance.
4. A rejected result (timeout, crash, silence, prose, invalid JSON, stale identity) is
   published as BLOCKED with blocker `review-outage`. It is not a verdict; the issue stays
   where it is, without approval. Retry once the cause is fixed.
5. On REQUEST_CHANGES: publish CHANGES_REQUESTED with the finding IDs, move the issue back
   with `transition <N> "In Progress" --apply`, and delegate fixes. Each finding gets a
   FINDING_DISPOSITION: `fixed` with evidence; `rejected` with evidence, which needs the
   reviewer's concurrence in the next round; or `accepted_by_maintainer`, which needs a
   recorded maintainer decision. Never dismiss a finding to obtain PASS.
6. After fixes, rerun the affected checks and the documentation audit, then request a fresh
   review of the new head. Reuse finding IDs; say whether the review is full or a justified
   delta.
7. On PASS, `review --apply` has already mirrored the result to the PR (when it exists) as a
   relayed comment, never a GitHub approval, published READY_TO_MERGE and set
   `agent:ready-to-merge`. If the PR is opened later, link the issue's REVIEW_RESULT from its
   description. The issue stays In Review until the maintainer merges.
8. Budget: three standard review rounds per attempt, plus up to two extra rounds only when
   the remaining findings are narrow (wording, documentation, small fixes); record on the
   issue why each extra round is used. Otherwise, or when findings remain after the fifth
   round, preserve the work, return genuine rework to In Progress, add `agent:needs-human`
   and summarise the disagreement for the maintainer.
