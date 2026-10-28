# Decisions beyond the executable fragment

These notes preserve the broader language/runtime proposal. Some narrow pieces
are now executable; `README.md` and the generated `REPORT.md` are authoritative
about that boundary. The current implementation includes tenant/order colours,
two-order exploration, and a SQLite process-crash model. It is not the full
distributed runtime described below.

## Protocol authority and resource obligations

There is no unrestricted `Payments.charge` in an application's ordinary API.
Its declared capability parameter is `Escrow[tenant, order]`. Only the selected,
trusted inventory module can mint this sealed nominal type, and its issuer
transition also creates a recovery registration. The executable validator now
seals consumption too: activation resources can move only through matching
exported API transitions or their declared cancellation routes. The foreign-dispatch contract
consumes the permit. An application cannot use its ordinary network capability
to bypass this if the real runtime only delegates access to the payment provider
through that adapter; arbitrary unrestricted FFI would invalidate this claim.

The legacy scalar registration invariant proves only aggregate accounting.
The coloured source now checks a family indexed by tenant/order and the bounded
explorer checks arc identities. The durable model correlates operation keys and
receipts to those indices. Richer registration payloads (schemas, recovery-role
versions, and general budgets) and their production refinement remain future work.

The linear handle records an abort route in its type declaration. Normal scope
exit requires an explicit move or discharge. Cancellation transfers the handle
to its abort route under the domain sequencer, once, after fencing the activation.
It does not silently drop it and does not depend on user-written `finally` code.
A machine crash does not execute a destructor on the failed machine: the durable
owner record lets another runtime worker perform the transition.

While a foreign call is suspended, ownership belongs to the runtime pending state,
not to a vanished stack frame. After paid evidence arrives, cleanup remains armed
until the sale commits. The source models this explicitly.

## Per-event code binding and upgrades

A long-lived inbox supervisor owns an admission route, not a forever-pinned job
closure. At admission, one transaction records the route revision, resolved job
code identity, handler bundle, input schema, and input event. New admissions can
therefore use new code while previously admitted events keep their original plan.
Worker retries reuse that recorded plan; they never resolve the route again.

A graceful drain first stops admission. Queue adapters pause consumption (or leave
deliveries unacknowledged with bounded prefetch); HTTP ingress refuses new work
with an explicit overload/draining response. Accepted jobs finish or transfer to
another owner. A drain deadline moves still-active obligations to recovery; it
does not delete them. The worker-pool activation can then end. Outstanding recovery
obligations may outlive the application deployment that admitted them.

An armed recovery record contains both a stable recovery role and the exact current
implementation revision. It does not automatically follow the newest callback.
A controlled recovery upgrade:

1. Stops new recovery claims for the selected role and establishes a checkpoint.
2. Verifies that the replacement accepts the same protocol-state schema and
   capabilities, and can perform only the protocol's exported transitions.
3. Atomically rebinds selected records and advances their recovery generation.
4. Records the upgrade as an event and rejects commits from older generations.

Changing payload schemas or the net itself needs an explicit migration with
resource accounting and invariant preservation checked before committing it.
Changing only recovery procedure code can reuse the existing state schema and
net. It still requires replay compatibility or a checkpoint, not arbitrary
continuation reinterpretation. External operations retain their original keys
across either kind of upgrade. A stale worker's authenticated payment evidence is
still eligible for the operation ledger, although it cannot advance an old flow.

## Closed error types

Open unions and implicit widening are withdrawn from the initial design.
Errors and outcomes use declared nominal enums. `ChargeOutcome[t, o]` is a real
example in the executable source, with exactly `Ok`, `Err`, and `Unknown` cases
and distinct resource-state payloads.

For the eventual general language, `?` propagates an exactly matching error type
or uses an explicit mapping selected by the programmer. For example, a library
would declare `FetchProblem` with named cases and call `map_error` when converting
an adapter error. There is no inferred structural `E1 | E2` subtype relation.
The revised prototype implements `?` by lowering it to an exhaustive match.
The `Err` and `Unknown` payload types and identity indices must match the enclosing
declared enum's cases exactly. The success payload may differ (`CheckoutOutcome`
uses `Unit` after selling). It inserts no cleanup, cancellation, or payload
conversion. `REPORT.md` contains the executable example and reference traces.

## Key source and correlation

The source says `keyed by tenant, order`. The adapter contract defines a stable
operation-kind namespace plus a canonical encoding of those fields. A different
implementation hash is not a different operation key. Repeating the same key
with different request contents is rejected against the recorded request digest;
it does not create a new key. A deliberate second business operation requires a
new business operation identity.

The provider receives that client key as its idempotency/correlation field. The
ledger records it before dispatch. An adapter outcome always identifies the local
operation and client key; a provider-generated reference is optional until it has
actually been observed. A lost first response can make that reference unknowable.
It would be incorrect to require an adapter to invent one on `Unknown`.

Automatic late correlation therefore requires at least one provider facility:

- Webhook/reply echo of the client key; or
- An authenticated lookup by client key that supplies the provider reference.

Later provider references are recorded as aliases of the original operation.
Webhooks authenticate the provider, validate tenant/account scope, and correlate
through those keys/aliases. A provider lacking both facilities cannot support
automatic correlation; its unresolved cases remain in manual reconciliation.

`NotFound` is not final rejection unless the provider contract also establishes
that an earlier request can no longer take effect. Retrying stops at the declared
deduplication horizon. Neither correlation nor the provider guarantee is proved
by this prototype's place invariant.

## Heartbeats, capacity, escalation, and reply lifetimes

Workers use a runtime API `checkpoint(progress)` to renew an execution lease and
persist resumable progress. Pure computation workers can have a supervisor renew
leases while the process is healthy; long external adapters must report their
own progress. The renewal carries operation/activation identity and generation.
Stale renewals are rejected. Lease length is distinct from a hard execution
deadline: heartbeats extend the lease, never the hard deadline. Loss of a lease
means loss of commit authority, not proof that physical work stopped.

An inbox capacity declaration includes an overflow policy. For queues the default
is bounded prefetch plus paused consumption; a delivery already received when
admission fails remains unacknowledged or is negatively acknowledged for delayed
redelivery. Immediate requeue loops are avoided. HTTP ingress returns 429 or 503
with an explicit retry policy; it never returns an acceptance receipt for an
uncommitted event. A webhook adapter uses the sender's documented redelivery
contract. Durable admission and acknowledgment remain separate actions.

Recovery policy declares both a maximum automatic-attempt count and an elapsed
time budget, for example 20 attempts or 24 hours, whichever comes first. Exhaustion
fires the source's `escalate` transition into `manual`; stock and recovery
registration remain present. The operator view receives a durable work item, not
an unbounded restart loop. Fixing code or supplying authoritative evidence can
resume the case. The timeout is never treated as evidence that a payment failed.

A synchronous HTTP reply obligation is scoped to one connection/request generation.
`ReplySent`, `PeerDisconnected`, or `ReplyDeadline` closes that transport obligation
exactly once. A closed socket cannot consume a second reply. The accepted business
operation has a separate lifetime and remains queryable by its operation reference.
Disconnecting does not turn uncertain business work into confirmed failure.

## Non-foreign effects

Non-foreign interfaces such as `effect Source` remain in the proposed language.
They express abstract request operations implemented by statically selected,
typed providers. A provider may invoke other such interfaces or foreign adapters.
Its inferred requirements must retain the underlying capabilities, effect class,
and uncertainty behavior. It cannot erase the payment permit or reinterpret an
unknown mutation as a confirmed failure. These providers are deliberately not
general resumable algebraic handlers in version one. This small parser does not
implement provider declarations; the decision is recorded here rather than
quietly removing the abstraction.

## Acceptance before claiming a real implementation

The prototype demonstrates a source-declared Petri invariant and a protocol gate
enforced by a small type checker. It now also implements coloured invariant
families, two-order ordering analysis, and concrete process-crash tests over a
file-backed coloured marking. The source-to-runtime refinement argument,
arbitrary-order ordering, production persistence guarantees, capability-enforcing
adapters, heartbeat behavior, and safe upgrades are still missing.
Guard truthfulness and authentication remain assumptions. The durable model
enforces one concrete retry-count budget; the analyser does not prove general
time/retry policies. None of these results is a proof of an entire distributed
payment system.
