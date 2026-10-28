Dynamic execution contract: D0
====================================

**Status: normative design decision in draft 0.2; not implemented by the general
prototype runtime.** F0 is a static-language profile. D0 specifies how an F0
activation is to execute against N1. The existing synchronous simulator and
R0 driver remain reference models with their separately stated limits.

Decision D-02 selects waiting semantics for a disabled await. It does not add a
hidden failure enum. A second implementation claiming D0 must implement these
rules; passing the current F0 checker alone does not claim D0 conformance.

.. _D0-AWAIT-1:

D0-AWAIT-1 — Start and waiting
------------------------------------

At an await, the activation captures the checked arguments and continuation in
a pending invocation. Linear inputs move out of accessible local bindings into
that invocation's exclusive ownership. If its selected transition lacks tokens
or its guards are false, the invocation MUST wait. Waiting changes neither the
marking nor an external operation ledger and does not produce Unit, Err, or
Unknown. A disabled local reserve is not a foreign failure.

An implementation can report a wait to tooling or suspend its worker. Waiting
MUST NOT reserve shared domain tokens speculatively or occupy a worker required
for other runnable activations. Its own linear handles remain exclusive.

.. _D0-AWAIT-2:

D0-AWAIT-2 — Atomic firing and completion
-----------------------------------------------

Enabledness and firing MUST be checked and committed atomically against the
current marking. After a local firing, the result handle denotes its actual
output token and is delivered once to the continuation. Losing a race for a
shared token leaves the request waiting; it cannot use a stale enabledness test.

Foreign dispatch consumes the permit into the declared pending place, then waits
for a separately enabled and correlated outcome firing. Only a dispatched
operation can yield its foreign outcome. Completion delivers its single tagged
payload once. No duplicate receipt may create a second payload.

.. _D0-COLOR-1:

D0-COLOR-1 — Runtime identities
-------------------------------------

Let rho map scalar identity symbols to concrete identity values. A live handle
of type R[t,o] MUST refer to a token whose colour is (rho(t),rho(o)) and whose
place is R's declared place. A handle's colour is immutable; it cannot be
reinterpreted by changing a type annotation. Forged or mismatched handles are
runtime contract violations, not alternative colours to try.

For a call, instantiate formal identity names with actual scalar identity
arguments and actual handle colours, consistently with F0-CALL-2.
A local API with a resource input derives its ordered colour from that input;
a scalar-only issuer derives it from its indexed resource result. A foreign
API derives it from its permit and keyed scalar arguments. All available
sources of the colour MUST agree.

.. _D0-COLOR-2:

D0-COLOR-2 — Mode selection
---------------------------------

Substitute the resulting pair into the transition's primary tenant/order binder.
Every indexed input/read/output MUST refer to that same pair. Select that exact
mode, not a mode found by searching for any available matching resource type.
A cross-order enabled mode is an invalid operation contract, not a fallback.

For an operation with several indexed resource inputs, their colours must agree
under this single-colour profile. A signature that determines no unique colour
from its indexed inputs or result is outside D0; an implementation MUST reject
that binding at load time. It must not guess based on parameter spellings.
This is stricter than the current erased API validator, recorded as MODEL-06.

.. _D0-ADMIT-1:

D0-ADMIT-1 — Repeated identity
------------------------------------

A type index is an equality constraint, not a freshness proof. In Inventory N1,
reserve consumes identities[t,o]. Its absence prevents another reservation for
that identity. The separate R0 job record makes duplicate admission resume a
prior job and rejects a conflicting payload.

A general D0 invocation with no identity token waits like any disabled call.
A resume/reject policy requires an explicit admission layer; it cannot silently
manufacture another token. The static type system guarantees neither that an
identity is fresh nor that a repeated call will complete.

.. _D0-SCHEDULE-1:

D0-SCHEDULE-1 — Interleaving
----------------------------------

Pure local binding, matching, and returning do not modify the net and are
unobservable to other activations through the net. Await requests, firings, and
completions are the net-visible interleaving points. Other activations and runtime
transitions may fire while an await waits. A foreign await has separate dispatch
and completion points.

The ownership guarantee across those points is exclusive authority to each live
handle, not exclusive access to every domain/runtime place needed by the call.
No worker/thread count, fairness policy, or wall-clock completion bound is implied.

.. _D0-CANCEL-1:

D0-CANCEL-1 — Cancellation while waiting
----------------------------------------------

Cancellation is an explicit runtime action, not normal return. Before dispatch,
the invocation still owns its resource inputs; cancellation transfers them via
their declared routes exactly once. After dispatch, cancellation acts on the
runtime pending state. A fenced activation MUST NOT subsequently consume its
former handles or accept a second completion. Durable execution needs persisted
ownership/generation records; D0 alone makes no storage durability claim.

.. _D0-DEADLOCK-1:

D0-DEADLOCK-1 — Stalled executions
----------------------------------------

If all activations wait and no modeled transition or admissible external event
can enable progress, the execution is flow-level deadlock. Waiting may also be
indefinite without a global deadlock, for example under starvation or absent
external evidence. The toolchain MUST NOT present a static check or P-invariant
as excluding either phenomenon. No current checker proves D0 deadlock freedom
or liveness.

Prototype discrepancy
---------------------------

The legacy simulator raises on a disabled transition; it therefore does not
implement D0-AWAIT-1. R0 executes protocol-specific operation groups in SQLite
transactions and supplies no general F0 waiting scheduler. These are explicit
conformance gaps, not evidence that waiting has already been implemented.

