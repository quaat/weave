.. SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
.. SPDX-License-Identifier: MIT

Core semantic decisions
=============================

.. index:: core semantic decision, integer semantics, pure fault, identity value,
   deadline, cancellation ownership, verification fragment, durable state

This chapter records seven decisions on the core semantics of Weave. The
maintainer took them on 29 October 2026 on quaat/weave#5 (`decision comment
<https://github.com/quaat/weave/issues/5#issuecomment-6498004593>`_), adopting
options 1A (with D3, L1 and E1), 2B, 3A, 4A, 5A, 6A and 7A of the decision record
``docs/decisions/0005-core-semantics.md``. That record holds the full analysis:
the current behaviour with line-level citations, every option with its
trade-offs and its effect on the Rust implementation, and the probes run for it.
Each section below summarises one area. Its **Decision** quotes the maintainer's
decision comment and then describes the adopted option as the record states it.

Scope and status
----------------------

These decisions bind the specification and implementation work of the later
milestones. The downstream issues named in each section turn them into
normative rules and implement them.

They do not change the executable fragment of draft 0.2. F0, N0, N1 and R0, the
targets D0 and N2, every rule, every diagnostic code and every result label keep
their meaning, and this chapter adds no rule ID. Normative rules arrive with the
downstream issues. Until then, a conformance claim cannot rest on this chapter,
and no checker, analyser or runtime implements these decisions.

Classification under :doc:`stability`:

* This chapter changes no accepted program, diagnostic code, dynamic outcome or
  guarantee, and no meaning of a rule ID, diagnostic code, profile or result
  label. It is therefore not a semantic change and needs no migration note
  (:ref:`chapters/stability:Migration notes`). While MAJOR is 0, changes merged
  between published drafts accumulate under the current language identifier,
  ``0.2-draft``; the change history in :doc:`provenance` summarises them when the
  next draft is cut.
* The colour-scope note after :ref:`D0-COLOR-2 <D0-COLOR-2>` in
  :doc:`execution-contract` states the scope that D0's colour rules already have:
  one tenant/order pair per operation. It changes no accepted program,
  diagnostic code or guarantee. Supporting arbitrary declared identity sorts needs
  a documented amendment with a migration note, not a reinterpretation of D0
  (:ref:`chapters/stability:Profile meanings are preserved`).
* The work that specifies these decisions follows the same policy. New
  capability, such as pure syntax, generalised identity or durable execution,
  arrives as a versioned extension or a new profile with its own rule IDs, never
  by changing F0, N0, N1 or R0. A change to an existing profile is a semantic
  change and needs a maintainer decision, a migration note and a new language
  revision.

The table summarises the adopted options and their downstream work.

.. list-table::
   :header-rows: 1
   :widths: 22 18 60

   * - Area
     - Adopted
     - Downstream
   * - 1. Integer semantics
     - 1A, D3, L1, E1
     - Rust interpreter and conformance fixtures; verification fragment
       (quaat/weave#27)
   * - 2. Pure error propagation
     - 2B
     - Rust interpreter; durable replay (area 7); verification fragment
       (quaat/weave#27)
   * - 3. Identity naming
     - 3A
     - quaat/weave#17; the D0 colour note; operation keys in the durable
       inventory (area 7)
   * - 4. Deadline observation
     - 4A
     - quaat/weave#22; durable timers (area 7)
   * - 5. Cancellation ownership
     - 5A
     - quaat/weave#24; ownership and generation records (area 7); route
       reachability (area 6)
   * - 6. Verification fragment for M4
     - 6A
     - quaat/weave#27
   * - 7. Durable state inventory for M5
     - 7A
     - M5 (epic quaat/weave#59); quaat/weave#35

Area 1: Integer semantics
-------------------------------

**Status.** Decided, 29 October 2026, by the maintainer on quaat/weave#5: option
1A with D3, L1 and E1.

**Context.** F0 flows have no arithmetic (:doc:`flow-semantics`). Integers occur
only in invariant equalities, whose arithmetic is exact
(:ref:`chapters/verification:Aggregate invariants`), and as initial counts. Opaque scalars have no representation, range or arithmetic
(:doc:`types`). The pure-computation proposal leaves integer range and overflow,
primitive error types and resource exhaustion to explicit adoption
(:doc:`proposals`), and LEX-04 makes decimal-only integer tokens an editorial
rule only (:doc:`limitations`). In the prototypes, invariant numerals and
initial counts come from Python's parser and ``int()``
(``inventory-proof/checker.py``, lines 213, 502--534 and 541), which accept
spellings such as ``0x0`` and non-ASCII digits. The agent kit's pure ``fn``
extension uses Python's unbounded ``int``
(``agent-kit/.agents/skills/weave/scripts/weave_pure/syntax.py``, lines
107--108; ``values.py``, lines 79--90), has comparison as its only operator,
faults on ``head`` and ``tail`` of an empty list (``values.py``, lines 50--53) and
has evaluation limits only as runner defaults (``runtime.py``, lines 22--28).
Python and Rust disagree on the rounding of negative division and on overflow;
record 0005, area 1, gives the probes and references.

**Decision.** The maintainer's decision: "Weave integers are exact. Size and
evaluation budgets are explicit parameters of a run. Exceeding a budget is a
reported budget-exhaustion outcome, separate from pure faults. Division is
Euclidean, and division by zero is a pure fault. Literals are ASCII decimal.
Partial list primitives fault on empty input."

As the record describes the adopted options:

* **1A, exact integers with declared budgets.** ``Int`` denotes the mathematical
  integers. A declared size budget (a maximum magnitude, for example in bits) and
  evaluation budgets (steps, depth, live activations) are part of the run
  configuration and are reported. Exceeding a budget is a defined
  budget-exhaustion outcome, never wrap-around or a host error.
* **D3, Euclidean division.** The quotient is rounded so that the remainder ``r``
  satisfies ``0 <= r < abs(d)``; the remainder is always nonnegative. Division or
  remainder by zero is a defined pure fault, never a host exception or panic. No
  division operator is added now; D3 fixes what division means once it exists.
* **L1, ASCII decimal literals.** Literals use ASCII decimal digits only, with an
  optional leading ``-`` where the grammar allows it. This makes LEX-04's
  editorial rule normative.
* **E1, partial primitives fault.** Partial primitives (``head``, ``tail`` and any
  future aggregate such as a list maximum) fail with a defined pure fault on an
  empty list. There is no default value.

**Rationale.** 1A gives programs and the analyser one integer model, and the
analyser's invariant arithmetic is already exact. Results do not depend on the
host as long as they stay within budget. The cost is a big-integer
representation and budget accounting for each operation. D3 matches the native
operator of neither Python nor Rust, so both implementations have to choose it
explicitly and differential tests catch drift. L1 rejects the host-parser
spellings that the prototypes accept today. E1 is the current behaviour and needs
no new types.

**Rejected alternatives.**

* **1B, fixed-width signed integers with overflow as a fault:** introduces a
  second integer model beside the exact invariant arithmetic; the analyser must
  reason about overflow, and the width becomes part of the language.
* **1C, unbounded without budgets (status quo):** inherits Python's unbounded
  ``int`` and its parsing of numerals; resource exhaustion stays undefined, and a
  Rust port would have to copy Python behaviour, against
  ``docs/development/implementation-language.md``.
* **D1, floor division:** Python's native ``//`` and ``%``. **D2, truncating
  division:** Rust's native ``/`` and ``%``. Each matches one host's native
  operator; D3 was preferred because it matches neither.
* **L2, keep the editorial status quo:** leaves LEX-04 editorial, under which the
  prototypes accept ``0x0`` and non-ASCII digits (record 0005, probes C1, C2 and
  P2).
* **E2, total primitives returning a closed enum:** pure code has no enums, and
  F0 has no optional value and no enums with scalar payloads, so E2 needs new
  types. **E3, static non-emptiness checking:** needs refinement types.

**Consequences and downstream.** The Rust interpreter needs an arbitrary-precision
integer type with checked size accounting; a machine ``i64`` may serve only as an
optimisation that is never observable. Both implementations implement D3
explicitly. Conformance fixtures and the verification fragment (area 6,
quaat/weave#27) depend on this area.

Area 2: Pure error propagation and evaluation order
---------------------------------------------------------

**Status.** Decided, 29 October 2026, by the maintainer on quaat/weave#5: option
2B.

**Context.** F0 has no exception object (:doc:`types`) and no implicit error
union, retry or error mapping (:doc:`effects`). The fork/join proposal requires
explicit outcomes for failure and exhaustion and consistent evaluation of the
same source in sequential and concurrent modes (:doc:`proposals`). The agent
kit's pure runner raises primitive failures and budget exhaustion as one fault
exception, told apart only by code
(``agent-kit/.agents/skills/weave/scripts/weave_pure/values.py``, lines 45--53;
``runtime.py``, lines 220--223). Pure code cannot catch a fault; a failing child
fails its parent and cancels the sibling subtree (``runtime.py``, lines
354--382). Arguments evaluate left to right (``runtime.py``, lines 65 and
88--91), but when both branches of a fork fail, the reported fault depends on
the schedule (record 0005, probes P6 and P7). Pure functions are not callable
from flows (``agent-kit/docs/weave.md``, lines 331--333).

**Decision.** The maintainer's decision: "Pure faults abort evaluation and form a
closed, specified set. Evaluation order is left to right. The outcome of a fork
is the sequential-equivalent outcome; budget exhaustion is a separate outcome.
When pure calls become available in flows, a pure fault reaches the flow as an
explicit outcome that the flow handles; it never discards live linear handles or
turns into Err or Unknown of a foreign operation."

As the record describes the adopted option: **2B, abort with a
sequential-equivalent outcome.** Pure faults (primitive failure, division by zero
and others) form a closed set; budget exhaustion is a separate outcome class.
Arguments and operands evaluate left to right. Every mode and schedule must
produce the outcome of left-to-right sequential evaluation: the value, or the
first fault in that order. Budget exhaustion may occur instead and is reported
as exhaustion.

**Rationale.** 2B is deterministic and replayable, and it meets the proposal's
requirement that sequential and concurrent modes evaluate the same source
consistently. The cost: a fault in a right branch cannot be reported until the
left branch finishes or faults, so early cancellation applies only when the left
branch faults.

**Rejected alternatives.**

* **2A, abort with a schedule-dependent fault (status quo):** outcomes differ
  between runs and between sequential and concurrent mode, against the proposal's
  consistency requirement, and replay (area 7) cannot reproduce them.
* **2C, faults as values:** needs new pure types (see E2 in area 1) and makes
  ordinary recursive code verbose.

**Consequences and downstream.** The Rust interpreter returns a result over a
closed fault enumeration. Weave faults never use a Rust panic or unwinding; a
host panic is an implementation failure, not a Weave outcome. Durable replay
(area 7) and the verification fragment (quaat/weave#27) depend on this area.

Area 3: Identity naming
-----------------------------

**Status.** Decided, 29 October 2026, by the maintainer on quaat/weave#5: option
3A.

**Context.** Opaque scalar types such as ``TenantId`` and ``OrderId`` are
accepted nominally, with no scalar declaration, representation, range,
serialization or arithmetic (:doc:`types`). Identity arguments are compared by
symbolic binding, and indices establish neither freshness nor uniqueness
(:doc:`types`, :doc:`names`). TYPE-01 leaves validation, equality, serialization
and ABI to a future profile, and TYPE-02 keeps identity tokens and admission
rules separate (:doc:`limitations`). :ref:`D0-COLOR-1 <D0-COLOR-1>` maps identity
symbols to concrete identity values without defining those values. In the
prototypes, colours are Python string pairs (``inventory-proof/coloured.py``,
lines 187--189; ``inventory-proof/durable.py``, line 25), and R0 forms operation
keys by JSON-encoding the operation name with the colour strings
(``durable.py``, lines 37--38).

**Decision.** The maintainer's decision: "Identity values form a nominal category
of their own. The only operation is equality within a sort, with explicit
validation and serialization at boundaries."

As the record describes the adopted option: **3A, nominal identity values.** Each
identity type (``TenantId``, ``OrderId`` and so on) is its own opaque sort.
Values enter only at declared boundaries (admission, adapters) through
validation, and leave only through a declared canonical serialization. The only
operation is equality within one sort: no ordering, arithmetic, concatenation or
conversion to a string or integer.

**Rationale.** 3A prevents mixing sorts and mixing identities with ordinary data,
and gives TYPE-01 a definite target. The cost is a serialization contract for
each sort.

**Rejected alternatives.**

* **3B, sort-tagged strings:** string operations can still make or take apart
  identities, and the separation from ordinary strings depends on discipline.
* **3C, plain strings or integers (status quo):** sort confusion and collisions
  with ordinary values are not excluded by construction, and Rust's ``String``
  semantics would become the identity semantics by default.

**Consequences and downstream.** In Rust, each sort is a newtype with no
conversion from a string and no dereference to one; serialization is explicit,
and hashing and equality stay within one sort. Downstream: quaat/weave#17
(identity naming input). The area also shapes the D0 colour note in
:doc:`execution-contract` and the operation keys of the durable inventory
(area 7).

Area 4: Deadline observation (``within``)
-----------------------------------------------

**Status.** Decided, 29 October 2026, by the maintainer on quaat/weave#5: option
4A.

**Context.** ``within`` and durations are unsupported (:doc:`limitations`,
:doc:`flow-semantics`), and ``within`` is not established as permanently
rejected (:doc:`design-history`). A timeout or a missing reply is not final
rejection (:doc:`effects`), and Unknown must not become Err because a deadline
expired (:doc:`rationale`). A lease is distinct from a hard execution deadline
(:doc:`glossary`). D0 implies no wall-clock completion bound
(:ref:`D0-SCHEDULE-1 <D0-SCHEDULE-1>`). The design notes treat lease loss as loss
of commit authority, never treat a timeout as evidence that a payment failed,
and let a reply deadline close only the transport obligation
(``inventory-proof/DESIGN_NOTES.md``, lines 120--126 and 141--147). The
prototypes have no time; R0's recovery budget counts attempts (:doc:`runtime`).

**Decision.** The maintainer's decision: "``within`` is an observation deadline.
Expiry is a distinct outcome, and a timeout never implies that the external
action failed or that the obligation ended."

As the record describes the adopted option: **4A, observation deadline.**
``within d`` bounds only how long the activation waits to observe an outcome.
Before dispatch, expiry withdraws the waiting invocation, and its linear inputs
return to the activation unchanged; waiting has changed no marking
(:ref:`D0-AWAIT-1 <D0-AWAIT-1>`). After dispatch, expiry yields a distinct "not
observed by deadline" result that carries the still-pending obligation. It is
never Err, and the operation's later outcome is still correlated and recorded.

**Rationale.** 4A matches the specification text and the design notes cited
above. The cost is durable timers and a typed result for late outcomes.

**Rejected alternatives.**

* **4B, hard deadline with cancellation:** expiry stops being observable as an
  outcome of its own, and the activation loses any chance to act on a late
  result.
* **4C, no** ``within`` **in the language:** deadlines become invisible to typing
  and to the analyser.

**Consequences and downstream.** The Rust implementation needs a monotonic clock
that tests can inject and timers persisted with the obligation; a timer must not
cancel host work as a side effect. Downstream: quaat/weave#22 (deadline input).
The durable state inventory (area 7) includes durable timers.

Area 5: Cancellation ownership
------------------------------------

**Status.** Decided, 29 October 2026, by the maintainer on quaat/weave#5: option
5A.

**Context.** Every resource declaration names a cancellation route
(:doc:`types`). :ref:`D0-CANCEL-1 <D0-CANCEL-1>` covers cancellation while
waiting: before dispatch, the invocation's resource inputs move along their
declared routes exactly once; after dispatch, cancellation acts on the runtime
pending state; a fenced activation must not consume its former handles or accept
a second completion. Cancellation routes transfer outputs to non-activation
owners, normal return never cancels, and recovery is state-sensitive
(:doc:`effects`). The design notes transfer a handle to its abort route once,
after fencing the activation, and give ownership of a suspended foreign call to
the runtime pending state (``inventory-proof/DESIGN_NOTES.md``, lines 27--36).
R0's ``cancel`` advances the job generation and fires the cancellation
transition of the first live protocol place (``inventory-proof/durable.py``,
lines 274--283); stale generations are rejected (:doc:`runtime`).

**Decision.** The maintainer's decision: "Cancellation fences the activation,
cancels children, then moves each live obligation exactly once along its
declared route to a non-activation owner. In-flight obligations stay
runtime-owned until a correlated outcome or recovery resolves them."

As the record describes the adopted option: **5A, declared-route transfer to
non-activation owners.** Cancellation first fences the activation (generation).
It then cancels child activations, innermost first. Each live handle then moves
exactly once along its resource's declared cancellation route to a runtime or
domain owner. In-flight operations stay with the runtime pending state, and their
outcomes go to the declared recovery owner.

**Rationale.** 5A generalises :ref:`D0-CANCEL-1 <D0-CANCEL-1>` and R0. Each
obligation has exactly one owner at every point, and the owner is visible in the
net, which the analyser can use. The cost: every resource needs a route that is
complete for each state.

**Rejected alternatives.**

* **5B, return to the canceller:** requires the canceller to be live and typed
  for every obligation, which fails when the canceller is itself cancelled or has
  crashed.
* **5C, single recovery role:** loses the state-sensitive routes that
  :doc:`effects` requires, since a single generic "undo" action is insufficient.

**Consequences and downstream.** Ownership is data in persisted records, never
Rust ``Drop``; a dropped Rust value must not cancel or discharge anything.
Downstream: quaat/weave#24 (cancellation ownership input). The durable state
inventory (area 7) needs ownership and generation records, and the verification
fragment (area 6) may check the reachability of routes.

Area 6: Verification fragment for M4
------------------------------------------

**Status.** Decided, 29 October 2026, by the maintainer on quaat/weave#5: option
6A.

**Context.** The result vocabulary and the scope of each label are defined in
:ref:`chapters/verification:Result vocabulary`. Today's coverage is exact
aggregate P-invariants, invariant families over a tenant/order pair with
variable-only inscriptions, N0 one-order bounded exploration, N1 exploration
with one tenant and N orders (the supplied protocol uses N = 2) and the
safety-property forms, with guards as abstract enablers (:doc:`verification`).
No soundness, progress, termination or refinement theorem is machine-checked,
and liveness and deadlock freedom are not established (:doc:`verification`,
:doc:`limitations`, :ref:`D0-DEADLOCK-1 <D0-DEADLOCK-1>`). The agent kit's pure
extension has no net or certificate (``agent-kit/docs/weave.md``, lines
320--323). The coloured checker accepts only two distinct tenant/order indices
per indexed place and per transition binder (``inventory-proof/coloured.py``,
lines 52--53 and 57--58).

**Decision.** The maintainer's decision: "6A for M4: the current N1 fragment,
made explicit, limited to the two-sort tenant/order colours of N1. The 6B
additions are explicit exclusions, to be revisited once #22 and #24 are
specified. Everything outside the fragment is reported NOT ESTABLISHED."

As the record describes the adopted option: **6A, the current N1 fragment made
explicit.** Aggregate and family invariants (exact, all colours); bounded
exploration with explicit colours, stock, bounds and budget; the existing safety
forms; F0 flow checks. Pure functions, time, deadlines, liveness and arbitrary
declared sorts are excluded and reported NOT ESTABLISHED. The colour-scope note
after :ref:`D0-COLOR-2 <D0-COLOR-2>` in :doc:`execution-contract` states the
two-sort limit for D0.

**Rationale.** 6A has the smallest scope, and every part already has a defined
result label. A Rust analyser can be checked differentially against the Python
reference over exactly this fragment. The cost: cancellation and deadline
behaviour stay unanalysed.

**Rejected alternatives.**

* **6B, 6A plus cancellation and deadline paths within bounds:** depends on
  quaat/weave#22 and quaat/weave#24 being decided and specified first. Its
  additions are explicit exclusions of the M4 fragment, to be revisited once
  those issues are specified.
* **6C, 6B plus pure functions and liveness:** the largest scope; liveness needs
  fairness assumptions that the specification does not yet state
  (:doc:`net-semantics`).

**Consequences and downstream.** Downstream: quaat/weave#27 (verification
fragment input). Integer semantics (area 1) and pure error propagation (area 2)
feed into it.

Area 7: Durable state inventory for M5
--------------------------------------------

**Status.** Decided, 29 October 2026, by the maintainer on quaat/weave#5: option
7A.

**Context.** D0 alone makes no storage durability claim, and durable execution
needs persisted ownership and generation records
(:ref:`D0-CANCEL-1 <D0-CANCEL-1>`). R0 stores marking, jobs, operations, results
and events in one SQLite database and commits admission before acknowledgement
(:doc:`runtime`), but it does not execute arbitrary F0 continuations (RUN-01 in
:doc:`limitations`). Durable admission binding to code revisions and
generation-aware leases are proposals (:doc:`proposals`). The R0 schema is in
``inventory-proof/durable.py``. The continuation representation is a separate
decision task, quaat/weave#35.

**Decision.** The maintainer's decision: "All nine items are in the inventory,
with the commit groups specified. The continuation representation is left to
#35."

As the record describes the adopted option: **7A, full inventory, persisted
directly.** The nine items are admission records, continuations, markings,
timers, the operation ledger, the result ledger, fencing generations, ownership
records and the event history; record 0005, area 7, gives the purpose of each
and its gap against R0. The commit groups are: admission with its record; firing
with marking, ledger and result; cancellation with generation, ownership and
routes; timer arming with its obligation.

**Rationale.** 7A is explicit and auditable, and recovery reads state instead of
recomputing it. The cost is more schema to migrate.

**Rejected alternatives.**

* **7B, event-sourced:** replay requires deterministic pure evaluation (2B) and a
  stable continuation format, and recovery time grows with history.
* **7C, host-state snapshots:** ties the durable format to Python or Rust
  internals, against ``docs/development/implementation-language.md``, and
  pre-empts quaat/weave#35.

**Consequences and downstream.** The Rust storage layer has an explicit schema;
host data structures are never serialized as the format. Under :doc:`stability`,
the store carries a ``weave-store-v<N>`` identifier, first assigned in M5.
Downstream: M5 (epic quaat/weave#59) and quaat/weave#35.
