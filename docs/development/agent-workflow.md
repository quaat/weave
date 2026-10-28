# Agent workflow: operator guide

This is the operator's guide to the Weave development workflow: how to set it up, start
and resume a run, what each step does, how failures are recovered, and what the workflow
cannot do. Policy details live in the linked documents; `CLAUDE.md` holds the
non-negotiables.

## Components

| Component | Location | Responsibility |
| --- | --- | --- |
| Orchestrator skill | `.claude/skills/weave-project/SKILL.md` | Discover, reconcile, schedule, claim, administer, report |
| Task skill | `.claude/skills/weave-task/SKILL.md` | Drive one claimed issue through implementation, verification and documentation |
| Review skill | `.claude/skills/weave-review/SKILL.md` | Build the review packet, run Codex, validate, record findings |
| Documentation skill | `.claude/skills/weave-docs/SKILL.md` | Documentation impact, map application, drift audit |
| Subagents | `.claude/agents/` | Implementer, verifier, documentation editor, local reviewer, safety reviewer, investigator |
| Hooks | `.claude/settings.json`, `.claude/hooks/weave_hook.py` | Guards and lifecycle evidence (not a security boundary) |
| Controller | `tools/weave_workflow/` | GitHub adapter, scheduler, events, gates, review, audit, recovery, CLI |
| Policy | `tools/weave_workflow/policy.json` | Versioned project contract: IDs to discover, milestones, exceptions, labels, budgets |
| Schemas | `tools/weave_workflow/schemas/` | Event, review-result and task-packet schemas (version 1) |
| Documentation map | `tools/weave_workflow/docmap.json`, `docs/development/documentation-map.md` | Which document describes which artefact, and how claims are verified |

The controller is standard-library Python 3.11+. It validates its own schemas with a
strict, fail-closed subset validator (`tools/weave_workflow/schema.py`), so there is
nothing to install beyond the tools below.

## Setup

1. Tools: Claude Code, `gh`, Codex CLI, Git, Python 3.11+. Versions observed at bootstrap
   are recorded in `docs/development/capabilities.md`; re-check with
   `python3 -m tools.weave_workflow capabilities`.
2. GitHub scopes: the coordinator's token needs `repo` and `project` (board reads and
   writes); pushing workflow files additionally needs `workflow` or SSH. Grant the project
   scope interactively: `gh auth refresh -s project`. Never paste tokens into issues.
3. Codex: `codex login` (or a configured provider). The reviewer runs with
   `--sandbox read-only --ephemeral`, no MCP servers, and GitHub and SSH credentials
   removed from its environment.
4. Verify read-only: `python3 -m tools.weave_workflow discover` must report the four Status
   options **Todo**, **In Progress**, **In Review**, **Done** with their live IDs.
5. Rehearse: `python3 -m tools.weave_workflow report` produces the dry-run report.

Local state (ledger, outbox, checkpoints, coordinator lock, review artefacts) lives in
`$(git rev-parse --git-common-dir)/weave-workflow/`, shared by all worktrees and never
committed. Task worktrees are created under `.worktrees/` (ignored by Git).

## Starting and resuming a run

Start explicitly, in the main conversation:

```text
/weave-project start a development run for the next eligible task
```

The skill runs `python3 -m tools.weave_workflow run start`, reconciles, selects one task,
and continues autonomously within the run's scope and budget. To resume after an
interruption, invoke `/weave-project resume`; it reconciles first and resumes existing work
before claiming anything new. `python3 -m tools.weave_workflow run status` shows the active
run, the last checkpoint and undelivered messages. `run stop --reason "..."` stops cleanly;
stopping is not Done.

## State machine

```
            claim gate                  in-review gate                 done gate
  Todo ───────────────▶ In Progress ─────────────────▶ In Review ─────────────────▶ Done
   ▲                      │   ▲                          │
   │ RELEASED             │   └──────────────────────────┘
   └──────────────────────┘     changes requested, failed evidence,
                                new edits or changed requirements
```

Blocked work stays in its truthful column with `agent:blocked` or `agent:needs-human`;
there is no fifth column. Approved work awaiting a maintainer merge stays In Review with
`agent:ready-to-merge`. Gate details: [transitions.md](transitions.md).

## Roadmap baseline

Revalidated against live records by `python3 -m tools.weave_workflow plan` on every run.

| Milestone | Epic | Required predecessor milestones |
| --- | --- | --- |
| M0 | #54 | Start; access and rights decisions |
| M1 | #55 | M0 |
| M2 | #56 | M1 |
| M3 | #57 | M1 and M2 |
| M4 | #58 | M3 |
| M5 | #59 | M3 and M4 |
| M6 | #60 | M5 for durable variants; numeric ordering otherwise |

## A task, step by step

| Step | Command or skill | Evidence produced |
| --- | --- | --- |
| Discover and reconcile | `discover`, `reconcile` | Snapshot, reconciliation report |
| Select | `plan` | Deterministic next task with reasons for every exclusion |
| Claim | `claim N` (dry run), `claim N --apply` | CLAIMED, DOCS_IMPACT, PLAN; worktree `agent/N-slug`; Todo → In Progress |
| Delegate | `/weave-task`, subagent with the packet | DELEGATED (published before work starts) |
| Implement | `weave-implementer` | IMPLEMENTATION_READY in the local outbox |
| Verify | `verify N --apply` (the `weave-verifier` subagent may investigate failures) | VERIFICATION_RESULT for the claimed worktree's head: the recorded packet's checks plus those derived from the diff, with argv, directory and exit code |
| Documentation | `/weave-docs`, `docs-audit --publish N --apply` | DOCS_AUDIT_RESULT for the candidate head, audited against the claim's base, worktree and DOCS_IMPACT list |
| Local and safety review | `weave-local-reviewer`, `weave-safety-reviewer` | LOCAL_REVIEW_RESULT (local, safety) |
| Independent review | `/weave-review`, `review N --worktree PATH --apply` | REVIEW_REQUESTED, REVIEW_RESULT with Codex provenance (mirrored to the PR); READY_TO_MERGE on PASS |
| Transition | `transition N "In Review" --apply` | TRANSITION_INTENT, STATE_CHANGED |
| Integrate | maintainer merge, then `transition N Done --worktree PATH --apply` | integration evidence derived from the PR and Git; STATE_CHANGED; COMPLETED |
| Milestone exit | `milestone-gate Mx --evidence FILE --apply` | GATE_EVALUATED on the epic (PASS only if the mechanical checks hold) |

Workers never write to GitHub. They return structured messages to the orchestrator, which
validates them (`event validate FILE`) and publishes them with attribution
(`event publish FILE --apply`). Event kinds that gates rely on (claims, plans, verification
and audit results, review requests and results, transitions, gate evaluations) cannot be
relayed this way: only the command that produces their evidence publishes them.

## Failure recovery

| Situation | Behaviour |
| --- | --- |
| GitHub unavailable or rate limited | Messages stay in the write-ahead outbox; dispatches and transitions pause; `reconcile --apply` replays in order |
| Ambiguous timeout on a comment | The comment is looked up by event id before any retry; never posted twice |
| Status write half-done | The operation ledger records intent; `reconcile --apply` completes it if the board shows the target, or abandons it and re-evaluates the gate |
| Codex timeout, crash, silence, prose or invalid JSON | Not a verdict; BLOCKED (review outage); the task stays In Review without approval |
| Stale review (head, base or requirements moved) | Result rejected; a fresh review of the current candidate is required |
| Review budget exhausted (3 rounds) | Work preserved, returned to In Progress, `agent:needs-human`, disagreement summarised |
| Manual card move or edited comment | Reported as a discrepancy by `reconcile`; never overwritten blindly |
| Restart | Reconcile board, events, claims, worktrees, PR heads, outbox and audit state; resume before claiming |
| Second coordinator | The OS lock rejects concurrent startup; a claim re-runs selection after acquiring the lock; a takeover must be explicit and reconciled |

## Limitations

- The coordinator currently posts as the maintainer's GitHub account. Events are
  authenticated by the local ledger, and maintainer decisions are recognised only in the
  `/weave-decision` form and only when absent from the ledger. A dedicated bot account
  would make actor identity meaningful.
- Subagents run in the coordinator's process. Hooks remove GitHub and SSH credentials
  from worker shells and refuse GitHub commands, but this is not an OS-level boundary.
- Exclusivity is single-host (an advisory file lock); there is no multi-host fencing.
- `main` has no branch protection at bootstrap, so GitHub does not enforce required checks
  or human reviews; the Done gate checks them itself, and protection is a maintainer action.
- The installed `autonomous-development` plugin is not present; the review gate uses the
  built-in `codex exec` adapter (see [capabilities.md](capabilities.md)).
