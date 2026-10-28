# Scheduling and milestone dependencies

Implemented by `tools/weave_workflow/scheduler.py`; run `python3 -m tools.weave_workflow plan`
(read-only) to see the graph, gates, candidates and the next task with reasons.

## Inputs

The scheduler reads **all pages** of issues, milestones, comments, native blocked-by and
sub-issue relationships, project items and fields, and pull requests with their checks.
Every connection is paginated and checked against its reported total; an incomplete listing
is an error, never a partial schedule. It never schedules from a first page or the visible
board.

Milestones are matched by stable identity: the `M<number>` prefix of the title, compared
numerically (`M2` precedes `M10`). The GitHub milestone API number is not that identity.

## Dependency graph

| Relationship | Source | Effect |
| --- | --- | --- |
| Blocking | Native GitHub blocked-by; a `## Depends on` section in the issue body; explicit entries in `tools/weave_workflow/policy.json` | Prerequisite must be completed (closed as completed and Done) |
| Membership | Epic "Work items" checklists; native sub-issues | Aggregate gate only; never a prerequisite |
| Contextual | Any other `#N` mention | Reported for review; never blocking |

Each blocking edge carries its provenance. The graph reports cycles, edges to unknown
issues, edges to epics, and contradictory dependencies (a task blocked by work in a later
milestone). Prose dependencies on epics (`Depends on: M1 and M2`) are compared with the
policy baseline and disagreements are reported.

## Selection rules

1. Select from the lowest numerically ordered unfinished milestone. Its predecessors must
   have **passed their exit gates**, not merely closed their milestone objects.
2. Within it, only tasks whose blocking prerequisites are complete. Order by documented
   sequence (the epic's work-item order), then project rank when the board exposes it, then
   issue number.
3. Eligible tasks have actionable acceptance criteria, a milestone, board status Todo, no
   `agent:blocked` or `agent:needs-human` label, no cycle, and no contradictory dependency.
4. Roadmap and epic tracking issues (`epic` label) are aggregate gates, not tasks. Deferred
   issues (`deferred` label, currently #49–#53) are excluded unless explicitly activated.
5. One active implementation issue by default
   (`concurrency.max_active_implementation_issues` in the policy). An active claim must be
   resumed before new work is claimed. Subagents may run in parallel inside an issue only on
   independent files.
6. A blocked task does not block independent tasks in the same milestone. If nothing is
   eligible the run records the blockers and stops; it never jumps ahead.
7. Early-start exceptions are narrow and inactive by default
   (`early_start_exceptions_active`): adapter design for #18 during M0 (#56), and the
   arithmetic verifier #28 and editor work #30 before M4 (#58). They waive no dependency,
   integration or exit gate. Unclear scope needs a maintainer decision.

## Special cases

- **#14** (formatter) is owned by M1 and required by the M4 exit gate. It is scheduled once,
  in M1.
- **#48** has no milestone at bootstrap; it is reported as unscheduled, not assigned.
- **Decision tasks** (#2 licence, #5 core semantics, #35 continuation representation):
  agents research and prepare proposals; Done requires the designated maintainer's recorded
  decision. Decisions are never fabricated.
- **Maintainer actions** (#4 baseline tag, #26 and #34 usability work with real
  participants): agents prepare; the maintainer performs and records the action.

## Milestone exit gates

A milestone passes when every constituent task is completed and Done, cross-milestone
requirements are met, the epic is closed as completed, and the orchestrator has recorded a
passing `GATE_EVALUATED` event (`gate: milestone-exit:<Mx>`) on the epic citing the exit
criteria, any required maintainer evidence, and a documentation audit with no residual
drift for the milestone's scope. Closed-as-not-planned is not success. An epic cannot
depend on its own closure; aggregate checklists are updated with evidence and the epic is
closed only when its gate passes.
