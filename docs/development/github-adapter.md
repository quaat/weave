# GitHub adapter and recovery

`tools/weave_workflow/github.py` wraps `gh api` (REST and GraphQL) and `gh project` behind a
small typed adapter (`GhCli`) with an in-memory twin (`FakeGitHub`) for tests and offline
rehearsals (`--fixture snapshot.json`; produce one with `discover --save`).

## Reads

All issues, comments, labels, milestones, native blocked-by and sub-issue relationships,
project items and the Status field, and pull requests with check results are paginated
(`gh api --paginate --slurp`) and compared with their reported totals. A short or truncated
listing raises an error. Read-only discovery:

```bash
python3 -m tools.weave_workflow capabilities
python3 -m tools.weave_workflow discover
python3 -m tools.weave_workflow plan
python3 -m tools.weave_workflow report
```

Repository access and project scope are checked without displaying credentials. A
repository Actions token cannot administer a user-owned project, so board automation runs
from the coordinator's own `gh` session with the `project` scope.

## Writes

- Status updates resolve the project ID, **project item ID**, Status field ID and option ID
  from live data (`gh project item-edit --id … --field-id … --single-select-option-id …`).
  An issue number is never used as an item ID, and IDs are never guessed.
- The observed status is compared with the expected one before mutating and read back
  afterwards. Errors are reported, never turned into invented transitions.
- Comments, labels and Status changes are not atomic. Each transition is
  intent → guarded write → verified completion, with a unique operation id in the local
  operation ledger; `reconcile --apply` completes or abandons partial operations.
- Messages go through the write-ahead outbox and are deduplicated by event id, including
  after ambiguous timeouts (the comment is looked up before any retry). Rate limits back off
  exponentially and then pause delivery.
- Bodies are JSON in temporary UTF-8 files passed with `--input`; nothing is interpolated
  into a shell.

## Coordinator exclusivity

One active coordinator, enforced on a single host by an OS advisory lock
(`coordinator.lock` in the state directory). Run ownership and claims are recorded as
CLAIMED events with an expiry. Labels and comments are not locks. There is no multi-host
fencing, so multi-host exclusivity is not claimed: concurrent startup is rejected, and a
takeover must be explicit and reconciled. An expired claim does not prove the old worker
stopped; it is checkpointed and fenced (its worktree preserved, its branch not reused) before
the work is taken over.

## Restart

`python3 -m tools.weave_workflow reconcile` reports, without writing: board status versus the
last recorded transition, published claims, agent worktrees, PR heads versus reviewed heads,
rejected or spoofed envelopes, undelivered messages and partial operations. With `--apply` it
replays the outbox in order and recovers partial operations. Existing work is resumed before
new work is claimed. A human's checkout is never reset, uncommitted changes are never
discarded, nothing is force-pushed, and completion is never inferred from a stale cache.

## Actor identity

At bootstrap the coordinator uses the maintainer's own account (`quaat`), so GitHub's actor
field cannot tell coordinator events from maintainer comments. Coordinator events are
authenticated through the ledger, and maintainer decisions must use the `/weave-decision`
form (see [communication-protocol.md](communication-protocol.md)). A dedicated bot account
or GitHub App with only `issues`, `pull_requests` and project permissions is recommended;
provision it manually and never post credentials in issues.
