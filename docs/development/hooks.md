# Hooks and deterministic enforcement

Hooks are lightweight adapters to the tested controller (`tools/weave_workflow/hooks.py`,
entry point `.claude/hooks/weave_hook.py`, registered in `.claude/settings.json`). They make
no network calls, run no builds and launch no Codex sessions. Event names and output fields
were checked against the installed Claude Code (see [capabilities.md](capabilities.md)).

| Hook | Behaviour |
| --- | --- |
| `SessionStart` | When a run is active or messages are queued: adds the run, last checkpoint and outbox state as context and asks for reconciliation first. Silent otherwise |
| `PreToolUse` | Guards (below) |
| `PostToolUse` / `PostToolUseFailure` | During a run: records tool outcome evidence in the ledger; after an edit to a managed document, queues a documentation-audit check |
| `SubagentStart` / `SubagentStop` | During a run: associates the worker's agent id and type with the run |
| `Stop` | During a run: writes a recoverable checkpoint; blocks at most twice per session when protocol messages are undelivered. Respects `stop_hook_active`, so it cannot recurse |
| `PreCompact` | Checkpoints the active task, outstanding messages and next action |
| `SessionEnd` | Best-effort checkpoint and a recorded claim-release intent (the claim itself is released only by a RELEASED event) |

## Guards (`PreToolUse`)

| Who | Command or tool | Decision |
| --- | --- | --- |
| Everyone | `git push` with `--force`, `-f` or `--force-with-lease` | deny |
| Main conversation | `gh pr merge`; `git reset --hard`; `git clean -f…`; release or tag publication | ask |
| Main conversation during a run | Direct `gh` board, issue, label or mutating API calls | ask (use the CLI so gates and the ledger apply) |
| Worker subagents (`policy.json` → `worker_agent_types`) | `gh`, `codex`, `claude`, `git push`, remote changes, worktree changes, history rewrites, direct GitHub API hosts | deny |
| Worker subagents | Any other shell command | allowed, rewritten to run with GitHub and SSH credentials removed |
| Worker subagents | Edits to `protected_paths`, or outside the delegation's `allowed_paths` | deny |

If the guard itself fails for a worker, it fails closed (exit 2). For the main conversation a
hook error is reported and does not block.

## Limits

The transition controller enforces every gate even when hooks are absent, disabled or
failing; hooks are neither a security boundary nor a scheduler. A regular expression cannot
prevent arbitrary `curl`, Python, Git or indirect API writes; credential removal narrows
that, and OS users, containers and credential isolation are the real boundary. Policy, hook
and CI changes require independent review and cannot be self-approved.

Whether `PreToolUse` payloads from subagents carry `agent_type` is recorded in
[capabilities.md](capabilities.md). The evidence hooks log the payload's key names (not
values) so the contract can be re-verified after Claude Code upgrades.
