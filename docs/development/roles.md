# Roles, delegation and isolation

| Role | Definition | Allowed | Prohibited |
| --- | --- | --- | --- |
| Main orchestrator | Main conversation with the `weave-project` skill | Select and claim tasks; all GitHub writes; board, label and assignment administration; branch and PR coordination; review dispatch; gate evaluation; documentation audit | Waive unmet criteria, invent evidence, self-approve |
| Implementer | `.claude/agents/weave-implementer.md` | Implement the assigned scope in its worktree; add meaningful tests; update the documents in the packet's documentation impact; return evidence | Pick another task, change board state, write to GitHub, merge |
| Verifier and tool investigator | `.claude/agents/weave-verifier.md`, `.claude/agents/weave-investigator.md` | Run approved checks, inspect dependencies and tooling, capture reproducible results | Reclassify failures as passes, broaden permissions |
| Documentation editor | `.claude/agents/weave-docs-editor.md` | Apply the documentation map; regenerate derived documents; run the drift audit | Alter normative semantics, provenance or expected-rejection fixtures |
| Local reviewer | `.claude/agents/weave-local-reviewer.md` | Inspect diff, acceptance coverage and documentation impact; return findings | Approve its own implementation as the independent review |
| Safety reviewer | `.claude/agents/weave-safety-reviewer.md` | Examine trust boundaries, irreversible operations, dependency, workflow and policy changes | Approve rights, legal or other maintainer-only exceptions |
| Independent Codex reviewer | Fresh `codex exec` session launched by `review --apply` | Inspect the pinned change and requirements read-only; return a structured report | Edit, administer GitHub, merge, accept its own fixes |

## Task packet

Every worker receives a packet validated against
`tools/weave_workflow/schemas/task-packet.v1.schema.json`: issue URL, milestone, run and
attempt, dependency evidence, acceptance criteria with stable IDs (`AC-n`) and text digests,
the **documentation impact list**, allowed paths, non-goals, base revision, branch and
worktree, checks, reporting contract and escalation conditions. `claim N` prints it as a dry
run and stores it in the run directory on `--apply`.

All questions and findings return through the orchestrator. Workers spawn no workers unless
the orchestrator has published a `DELEGATED` event for that delegation.

## Isolation

- Each task gets its own worktree and `agent/<issue>-<slug>` branch. Parallel writers never
  edit the same files or shared generated artefacts.
- The orchestrator owns integration. Any integration change invalidates earlier evidence
  for the old head.
- Subagent definitions restrict tools: reviewers and investigators cannot edit files.
- The `PreToolUse` hook prefixes every worker shell command with an environment that removes
  `GH_TOKEN`, `GITHUB_TOKEN`, `SSH_AUTH_SOCK` and points `GH_CONFIG_DIR` at an empty
  location, and it refuses `gh`, `codex`, `claude`, `git push`, remote and worktree changes,
  and history rewrites in worker shells. Worker edits to protected paths (snapshots,
  provenance, policy, CI and agent configuration) are refused.

These controls narrow what a worker can do, but they are not an OS-level boundary:
subagents share the coordinator's process, user account and keyring. A shell regex cannot
stop every indirect network write. Stronger isolation needs a separate OS user or container
without credentials; see [capabilities.md](capabilities.md).
