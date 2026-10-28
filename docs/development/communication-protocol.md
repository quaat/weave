# Issue-based communication protocol

Every inter-agent instruction, handoff, question, answer, finding, disposition and result is
recorded in the task's issue: user-facing rationale and evidence, not private reasoning or
raw transcripts. Raw tool logs stay in the run directory; the issue carries enough commands
and results to audit each conclusion.

## Comment format

```text
[weave-agent] REVIEW_RESULT — codex-reviewer → orchestrator
<!-- weave-agent:event:v1 -->
```

followed by a fenced JSON envelope and a concise body. The envelope schema is
`tools/weave_workflow/schemas/event.v1.schema.json` (strict: unknown fields are rejected;
each kind has required fields). Build events with
`python3 -m tools.weave_workflow new-event --kind ... --fields '{...}'`.

| Kind | Required fields beyond the common envelope |
| --- | --- |
| CLAIMED | `claim_expires_at`, `coordinator_host`, `work_type` |
| PLAN | `requirements_digest`, `criteria` (id, text digest, verification) |
| DELEGATED | `delegate`, `packet_digest`, `base_sha`, `worktree` |
| QUESTION / ANSWER | `question` / `answer` |
| PROGRESS, RESUMED | — |
| IMPLEMENTATION_READY | `head_sha`, `docs_updated`, `docs_audit_event_id`, `criteria_map` |
| VERIFICATION_RESULT | `head_sha`, `result`, `checks` (argv, cwd, exit code) |
| DOCS_IMPACT | `docs_impact` (path, reason, status) |
| DOCS_AUDIT_RESULT | `head_sha`, `result`, `error_count`, `scope` |
| LOCAL_REVIEW_RESULT | `head_sha`, `verdict`, `review_kind` (local or safety) |
| REVIEW_REQUESTED | `head_sha`, `base_sha`, `requirements_digest`, `review_round` |
| REVIEW_RESULT | as requested plus `verdict`, `review_digest`, `review_request_id`, `reviewer_provenance` |
| FINDING_DISPOSITION | `finding_id`, `disposition`, `evidence` |
| CHANGES_REQUESTED | `finding_ids` |
| BLOCKED | `reason`, `blocker` |
| TRANSITION_INTENT / STATE_CHANGED | `operation_id`, `from_status`, `to_status` |
| READY_TO_MERGE | `head_sha` |
| COMPLETED | `head_sha`, `merge_sha` |
| RELEASED | `reason` |
| DECISION_RECORDED | `decision` |
| GATE_EVALUATED | `gate`, `result` |

These are this project's protocol, not GitHub events. `event_id` deduplicates,
`correlation_id` groups a conversation and `causation_id` records what triggered an event.
History is append-only; errors are corrected with superseding events. One editable summary
comment may index status and evidence, but it is not the audit history.

## Delivery

- The orchestrator is the **sole GitHub writer**. Workers return messages to a local outbox;
  the orchestrator validates them (`event validate FILE`) and publishes them with explicit
  attribution (`event publish FILE --apply`). A relayed Codex report is labelled as relayed
  and is never presented as a GitHub approval.
- Publication is write-ahead (`tools/weave_workflow/publisher.py`): queue, post, record the
  delivery (comment id and envelope digest) in the ledger. Delivery is strictly in sequence
  and pauses at the first failure, so causally dependent messages are never reordered.
- A delegation is published before dependent work starts; a result is published before the
  next handoff. Fan-out and fan-in keep each message and sender. Cross-issue decisions are
  linked and recorded on every affected issue.
- Bodies are passed as JSON in a temporary UTF-8 file with argument arrays, never through a
  shell. Secrets, tokens and e-mail addresses are redacted before publication, and the
  envelope records that a redaction occurred.
- If GitHub is unavailable, messages stay queued, a checkpoint is written, and dispatches and
  transitions pause. Delivery is never claimed before it happens.

## Reserved kinds

Gates rely on some kinds, so only the command that produces their evidence may publish them.
The origin is recorded in the ledger delivery, and an envelope of a reserved kind delivered
from any other origin is not trusted.

| Kind | Published only by |
| --- | --- |
| CLAIMED, DOCS_IMPACT, PLAN | `claim --apply` |
| VERIFICATION_RESULT | `verify --apply` (runs the recorded packet's checks plus the diff-derived checks itself) |
| DOCS_AUDIT_RESULT | `docs-audit --publish N --apply` (runs the audit itself against the claim's base, worktree and impact list) |
| REVIEW_REQUESTED, REVIEW_RESULT, READY_TO_MERGE | `review --apply` (runs and validates Codex itself) |
| TRANSITION_INTENT, STATE_CHANGED, COMPLETED | `transition --apply` |
| GATE_EVALUATED | `milestone-gate --apply` |
| DECISION_RECORDED | never the coordinator; decisions are maintainer comments |

Everything else goes through the relay (`event publish`), which also checks that the sender
role may send the kind (for example only the implementer sends IMPLEMENTATION_READY).

## Authentication

An envelope is trusted only if its comment was posted by a login in
`actors.coordinator_logins`, has not been edited, and matches a ledger delivery record with
the same comment id and envelope digest. Text claiming a sender is never enough. Spoofed,
stale, edited or unrecognised envelopes are ignored and listed by `reconcile`.

Maintainer decisions are unedited comments by a login in `actors.maintainer_logins`, absent
from the ledger, whose first line starts with `/weave-decision`. The coordinator refuses to
publish any body containing that prefix. No shell fragment from any comment is ever executed.

## Labels

Existing labels are preserved. The workflow adds `agent:managed`, `agent:blocked`,
`agent:needs-human`, `agent:review-requested`, `agent:changes-requested`,
`agent:ready-to-merge` and `agent:docs-stale`. Labels are signals, not locks or verdicts;
stale mutually exclusive labels are removed after transitions. An `@codex` mention is not an
execution mechanism; the coordinator launches the reviewer. Humans are mentioned only when
authorised.
