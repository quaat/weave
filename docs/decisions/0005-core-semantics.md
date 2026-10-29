<!--
SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
SPDX-License-Identifier: MIT
-->

# 0005: Core semantics: integers, pure errors, identity naming, deadlines, cancellation, verification fragment

- **Issue:** [quaat/weave#5](https://github.com/quaat/weave/issues/5), milestone M0
- **Status:** Proposed (awaiting maintainer decision)
- **Prepared against:** base revision `0d3185ffdc2084800f4e84bd5d3c74b14b8998dc`, 29 October 2026
- **Decision owner:** the maintainer. This record sets out options and recommendations. It
  does not decide anything.

This is phase 1 of #5: preparing the decisions. For each of the seven decision areas it gives
the current specification and prototype behaviour, the question, the options with their
trade-offs, a recommendation and the downstream issues. Every recommendation is labelled
**Recommendation (not a decision)**. Phase 2 starts after the maintainer records the decisions
on #5. It writes the decided record (AC-1), adds the D0 note prepared
[below](#prepared-d0-note-ac-3) (AC-3) and references the decisions from the downstream
issues (AC-2). This change leaves the specification, the rules, the checkers and the
prototypes untouched.

## Conventions

- **Citations.** `path` (lines a–b) refers to the base revision. The prototype working copy
  and both pinned snapshots are byte-identical at base: R1 under [Commands run](#commands-run)
  prints no differences. A citation of `inventory-proof/` therefore also holds for
  `agent-kit/.agents/skills/weave/assets/prototype/` and `specification/reference/prototype/`.
  The kit's pure-function extension, `agent-kit/.agents/skills/weave/scripts/weave_pure/`, is
  not part of the snapshots.
- **Probes.** P1–P9 and C1–C2 are commands run for this record with Python 3.13.5 and GNU
  sed. Their outputs and exit codes are under [Commands run](#commands-run). They write only to
  `$TMPDIR`. Where these probes print result labels such as `PROVED`, the labels are quoted
  tool output; this record makes no evidence claim of its own.
- **Downstream issues.** The texts of #15, #17, #22, #24 and #27 are not quoted anywhere in
  the repository. This record therefore uses only their numbers, as the #5 issue text relays
  them in the task packet, and does not describe their scope.
- **Rust.** `docs/development/implementation-language.md` (lines 27–33) puts semantics in the
  specification: Rust machine integers, ownership, panics and error handling must not silently
  become Weave semantics. Each option names what it requires of the Rust implementation.

## 1. Integer semantics

### (a) Current behaviour

Specification:
- F0 flows have no arithmetic (`specification/docs/chapters/flow-semantics.rst`, lines
  111–113). Arithmetic exists only inside invariant equalities
  (`specification/docs/chapters/limitations.rst`, lines 83–84).
- Opaque scalars have no representation, range or arithmetic
  (`specification/docs/chapters/types.rst`, lines 30–34). `Nat` denotes a nonnegative
  initial-count parameter with no arithmetic (lines 36–38).
- Invariant arithmetic is exact over integer constants, names, `+`, `-`, unary minus and
  scalar multiplication (`specification/docs/chapters/verification.rst`, lines 43–52).
- The pure-computation proposal lists "integer range/overflow, primitive error types" among
  the points that need explicit adoption (`specification/docs/chapters/proposals.rst`,
  lines 39–41). It asks for `head`/`tail` "with specified empty-list failure" (line 26)
  without specifying that failure.
- LEX-04 records that "Python invariant AST admits some extra numeric spellings". Its
  treatment is "Editorial decimal-only integer tokens" (`limitations.rst`, lines 26–28).

Prototypes:
- **Invariant numerals come from Python's parser.** `linear_expression` parses invariants
  with Python's `ast` and accepts any `int` constant (`inventory-proof/checker.py`, lines
  502–534). C1: an invariant ending in `== 0x0` is accepted, and the checker prints
  `PROVED registration_balance`.
- **Initial counts come from `\w+` and `int()`.** Place initial counts are matched by `\w+`
  (`checker.py`, line 213) and converted with `int()` (line 541). Both accept non-ASCII
  digits. C2: with `place sold = ٠` (ARABIC-INDIC DIGIT ZERO) the checker accepts the net and
  prints `PROVED` for both invariants.
- **Pure `Int` is an unbounded Python `int`.** Literals match `-?\d+` (`agent-kit/.agents/skills/weave/scripts/weave_pure/syntax.py`,
  lines 107–108) and are converted with `int()` (line 210). Entry arguments are accepted when
  they are a JSON integer of any size (`agent-kit/.agents/skills/weave/scripts/weave_pure/values.py`, lines 79–90).
  - P1 returns a 39-digit literal unchanged.
  - P3 accepts a 26-digit list element.
  - P4 rejects `1e3` with E424.
  - P2: the literal `٣٤` (Arabic-Indic digits) evaluates to `34`.
- **Comparison is the only operator.** `<=` is the only operator in the pure extension
  (`agent-kit/docs/weave.md`, lines 331–333; `agent-kit/.agents/skills/weave/scripts/weave_pure/runtime.py`, lines 253–255).
- **Python division and `max([])` are not reachable from Weave programs at base.** No
  division, remainder, `max` or `min` is exposed to Weave source. R2 lists every `//`, `max(`,
  `min(` and `divmod` in the prototypes:
  - the only division over program data is `xs.length // 2` in `split_half`
    (`agent-kit/.agents/skills/weave/scripts/weave_pure/values.py`, line 58), on a nonnegative length, where floor and truncation
    agree;
  - the other hits are internal: indentation, statistics and limits.
- **They would leak if added naively.** In Python, `-7 // 2` is `-4`, `-7 % 2` is `1` and
  `max([])` raises `ValueError` (P8, P9). The Rust Reference states that Rust integer division
  "rounds towards zero" and that the remainder takes the sign of the dividend. Integer
  operators "will panic when they overflow when compiled in debug mode", and compiler flags
  control this ([Rust Reference, operator expressions](https://doc.rust-lang.org/reference/expressions/operator-expr.html),
  fetched for this record). The two hosts therefore disagree on negative division and overflow.
- **Empty lists.** `head` and `tail` of an empty list raise E420 (`agent-kit/.agents/skills/weave/scripts/weave_pure/values.py`,
  lines 50–53; `agent-kit/docs/weave.md`, lines 264–265). `length` and `is_empty` are total.
- **Evaluation budgets exist only as implementation defaults.** `fuel`, `max_depth` and
  `max_tasks` are runner defaults (`agent-kit/.agents/skills/weave/scripts/weave_pure/runtime.py`, lines 22–28) that raise E421–E423.
  No integer-size budget exists.

### (b) Question

What integer type does Weave have, what happens at the limits of size and evaluation, and how
are division, remainder, literals and empty-list primitives defined, independently of Python
and Rust?

### (c) Options

| Option | Content | Trade-offs | Effect on Rust |
| --- | --- | --- | --- |
| **1A** Exact integers with declared budgets | `Int` denotes mathematical integers. A declared **size budget** (maximum magnitude, for example in bits) and **evaluation budgets** (steps, depth, live activations) are part of the run configuration and are reported. Exceeding a budget is a defined *budget-exhaustion* outcome, never wrap-around or a host error. | One integer model for programs and the analyser, whose invariant arithmetic is already exact. Results do not depend on the host as long as they stay within budget. Costs a big-integer representation and budget accounting per operation. | Needs an arbitrary-precision integer type, from a crate under the dependency policy or written in-house, with checked size accounting. Machine `i64` may serve only as an optimisation that is never observable. |
| **1B** Fixed-width signed integers (for example 64-bit), overflow is a fault | `Int` is a 64-bit two's-complement value; overflow, including `MIN / -1`, is a defined pure fault. | Simple and fast; a familiar model. Introduces a second integer model beside the exact invariant arithmetic, and the analyser must reason about overflow. The width becomes part of the language. | Use `checked_*` operations throughout; the build-mode-dependent overflow behaviour of plain operators must never be reached. |
| **1C** Unbounded without budgets (status quo) | Whatever the host integer does. | No work now. Inherits Python's unbounded `int` and its parsing of numerals (C1, C2, P1–P3). Resource exhaustion is undefined, and a Rust port has to copy Python behaviour. | Matching Python means copying Python's semantics, against `docs/development/implementation-language.md`. |

Division and remainder are a sub-question. No option adds them now; the question is what they
mean once they exist.

| Option | Quotient rounding | Remainder | Note |
| --- | --- | --- | --- |
| **D1** Floor | towards −∞ | sign of the divisor | Python's `//` and `%` (P8) |
| **D2** Truncate | towards 0 | sign of the dividend | Rust's `/` and `%` (Rust Reference, above) |
| **D3** Euclidean | so that `0 <= r < abs(d)` | always nonnegative | Rust `i64::div_euclid` and `rem_euclid` ([std docs](https://doc.rust-lang.org/std/primitive.i64.html#method.div_euclid)); Python needs an explicit implementation |

In every option, division or remainder by zero is a defined pure fault, never a host exception
or panic. D3 is the only option that matches the native operator of neither host, so both
implementations have to choose it explicitly and differential tests catch drift.

Literals have two options. **L1**: ASCII decimal digits only, with an optional leading `-`
where the grammar allows it; this makes LEX-04's editorial rule normative and rejects C1's
`0x0`, C2's `٠` and P2's `٣٤`. **L2**: keep the editorial status quo.

Empty-list primitives have three options:
- **E1** (status quo): partial primitives (`head`, `tail` and any future aggregate such as a
  list `max`) fail with a defined pure fault on an empty list. There is no default value.
- **E2**: total primitives returning a closed enum. Pure code has no enums (its types are
  `Int`, `Bool`, `IntList` and `IntListPair`: `agent-kit/docs/weave.md`, line 255), and F0 has no
  optional value (`types.rst`, line 106) and no enums with scalar payloads (lines 73–76), so
  E2 needs new types.
- **E3**: static non-emptiness checking, which needs refinement types.

### (d) Recommendation (not a decision)

**1A with D3, L1 and E1.** Weave integers are exact. Size and evaluation budgets are explicit
parameters of a run. Exceeding a budget is a reported budget-exhaustion outcome, separate from
pure faults (area 2). Division is Euclidean, and division by zero is a pure fault. Literals are
ASCII decimal. Partial list primitives fault on empty input.

### (e) Downstream

Rust interpreter and conformance fixtures; the verification fragment (area 6, #27). #15 may
take integer and pure-error semantics, but only by elimination from the issues named in the
packet; see [Open question](#open-question).

## 2. Pure error propagation and evaluation order

### (a) Current behaviour

Specification:
- F0 has no exception object (`types.rst`, line 106). There is no implicit error union, retry
  or `map_error` (`specification/docs/chapters/effects.rst`, lines 92–95).
- For pure computation, "Failure and exhaustion require explicit outcomes, cleanup of pending
  work, and no manufactured partial results. Sequential and concurrent modes must evaluate the
  same source consistently" (`proposals.rst`, lines 51–55). Primitive error types still need
  adoption (lines 39–41).

Prototype (`agent-kit/.agents/skills/weave/scripts/weave_pure/`):
- **Faults are one exception class.** Primitive failures and budget exhaustion are both
  raised as a `RuntimeFault` exception (`agent-kit/.agents/skills/weave/scripts/weave_pure/values.py`, lines 45–53;
  `agent-kit/.agents/skills/weave/scripts/weave_pure/runtime.py`, lines 220–223). Only the code tells them apart: E420 for a
  primitive failure, E421–E423 for budgets.
- **No catching in pure code.** The statements are `let`, `return`, terminal `if`/`else`
  and `fork` (`agent-kit/docs/weave.md`, line 256); none handles a fault. A failing child fails its parent, cancels the sibling
  subtree and propagates to the root (`agent-kit/.agents/skills/weave/scripts/weave_pure/runtime.py`, lines 354–382;
  `agent-kit/docs/weave.md`, lines 297–299).
- **Faults are reported, not returned.** The runner reports a runtime fault with exit code 2
  (`agent-kit/.agents/skills/weave/scripts/weave_pure/cli.py`, lines 60–62).
- **Order is left to right.** Call arguments are compiled left to right
  (`agent-kit/.agents/skills/weave/scripts/weave_pure/runtime.py`, line 65), and fork arguments are evaluated left branch first, then
  right (lines 88–91). P5: `cons(head(a), tail(b))` with both lists empty reports `head()`.
- **The fault reported from a fork depends on the schedule.** With both branches failing:
  - P6 (`--schedule fifo`) reports the left branch's `head()` at line 2;
  - P7 (`--schedule lifo`) reports the right branch's `tail()` at line 4;
  - sequential mode reports `head()`.
- **Pure functions are not callable from flows** (`agent-kit/docs/weave.md`, lines 331–333),
  so no pure fault reaches a flow today.

### (b) Question

How do primitive failures surface and propagate? Is evaluation order part of the semantics?
Is the outcome of a program with forks independent of the schedule? How does a pure fault
reach a flow once pure calls are allowed there?

### (c) Options

| Option | Content | Trade-offs | Effect on Rust |
| --- | --- | --- | --- |
| **2A** Abort, schedule-dependent fault (status quo) | A fault aborts the whole pure evaluation. Which fault is reported when several branches fail is unspecified. | Earliest cancellation of siblings. But outcomes differ between runs (P6, P7) and between sequential and concurrent mode, against `proposals.rst` line 54, and replay (area 7) cannot reproduce them. | Any scheduler is acceptable; tests must accept a set of outcomes. |
| **2B** Abort with a sequential-equivalent outcome | A closed set of pure faults (primitive failure, division by zero and others), with budget exhaustion as a separate outcome class. Arguments and operands evaluate left to right. Every mode and schedule must produce the outcome of left-to-right sequential evaluation: the value, or the first fault in that order. Budget exhaustion may occur instead and is reported as exhaustion. | Deterministic and replayable, and matches `proposals.rst` line 54. A right-branch fault cannot be reported until the left branch finishes or faults, so early cancellation applies only when the left branch faults. | The interpreter returns `Result<Value, PureFault>` with a closed fault enum. Weave faults never use `panic`/unwind; a host panic is an implementation failure, not a Weave outcome. |
| **2C** Faults as values | Primitives return explicit result enums that pure code must match. | Fully explicit, but needs new pure types (see E2 in area 1) and makes ordinary recursive code verbose. | Same as 2B, plus enum types in the pure fragment. |

### (d) Recommendation (not a decision)

**2B.** Pure faults abort evaluation and form a closed, specified set. Evaluation order is
left to right. The outcome of a fork is the sequential-equivalent outcome; budget exhaustion
is a separate outcome. When pure calls become available in flows, a pure fault must reach the
flow as an explicit outcome that the flow handles. It must never discard live linear handles
or turn into Err or Unknown of a foreign operation.

### (e) Downstream

Rust interpreter; durable replay (area 7); the verification fragment (#27). Possibly #15 (see
[Open question](#open-question)).

## 3. Identity naming

### (a) Current behaviour

Specification:
- Opaque scalar types such as `TenantId` and `OrderId` are accepted nominally, with "no scalar
  declaration, representation, range, serialization, or arithmetic" (`types.rst`, lines
  17–18 and 30–34).
- Identity arguments are compared by symbolic binding: distinct parameters are not assumed
  equal, and indices establish neither freshness nor uniqueness (`types.rst`, lines 115–120;
  `specification/docs/chapters/names.rst`, lines 57–65).
- TYPE-01 leaves validation, equality, serialization and ABI to a future profile, and TYPE-02
  keeps identity tokens and admission rules separate (`limitations.rst`, lines 36–41).
- D0-COLOR-1 lets rho map identity symbols to "concrete identity values" without defining
  those values (`specification/docs/chapters/execution-contract.rst`, lines 44–60).

Prototypes:
- Colours are Python string pairs, by default `('tenant', 'order1')` and so on
  (`inventory-proof/coloured.py`, lines 187–189; `inventory-proof/durable.py`, line 25).
- R0 forms operation keys by JSON-encoding the operation name with the colour strings
  (`durable.py`, lines 37–38). Identity values are therefore ordinary strings at run time.

### (b) Question

What is a runtime identity value? Is it a category distinct from ordinary strings and
integers? How is it created, compared, serialized and kept apart from other identity sorts?

### (c) Options

| Option | Content | Trade-offs | Effect on Rust |
| --- | --- | --- | --- |
| **3A** Nominal identity values | Each identity type (`TenantId`, `OrderId`, …) is its own opaque sort. Values enter only at declared boundaries (admission, adapters) through validation, and leave only through a declared canonical serialization. The only operation is equality within one sort: no ordering, arithmetic, concatenation or conversion to a string or integer. | Prevents mixing sorts and mixing identities with ordinary data. Gives TYPE-01 a definite target. Needs a serialization contract per sort. | A newtype per sort with no `From<String>` and no `Deref`. Serialization is explicit, and `Hash`/`Eq` stay within one sort. |
| **3B** Sort-tagged strings | An identity is a (sort, string) pair. Equality compares both, and string operations stay available. | Cheap to implement and close to R0. String operations can still make or take apart identities, and the separation from ordinary strings depends on discipline. | A struct holding a tag and a `String`. |
| **3C** Plain strings or integers (status quo) | Identity values are host strings or integers. | No work. Sort confusion and collisions with ordinary values are not excluded by construction. | Rust's `String` semantics become the identity semantics by default. |

### (d) Recommendation (not a decision)

**3A.** Identity values form a nominal category of their own, with equality within a sort as
the only operation and explicit validation and serialization at boundaries.

### (e) Downstream

#17 (identity naming input). It also shapes the D0 colour note ([below](#prepared-d0-note-ac-3))
and the operation keys of the durable inventory (area 7).

## 4. Deadline observation (`within`)

### (a) Current behaviour

Specification:
- `within` and durations are unsupported (`limitations.rst`, lines 78–81; `flow-semantics.rst`,
  lines 111–113). It is "not established as permanently rejected": "A timeout cannot establish
  that an external mutation failed" (`specification/docs/chapters/design-history.rst`, lines
  44–48).
- A timeout or a missing reply is not final rejection (`effects.rst`, lines 35–37). Unknown
  must not become Err because a deadline expired
  (`specification/docs/chapters/rationale.rst`, lines 34–35).
- A lease is "distinct from a hard execution deadline"
  (`specification/docs/chapters/glossary.rst`, lines 84–87).
- D0 implies no wall-clock completion bound (`execution-contract.rst`, line 106), and N1 does
  not specify wall-clock timing (`specification/docs/chapters/net-semantics.rst`, lines 93–96).

Design notes:
- Heartbeats extend a lease, never a hard deadline, and lease loss "means loss of commit
  authority, not proof that physical work stopped" (`inventory-proof/DESIGN_NOTES.md`, lines
  120–126).
- "The timeout is never treated as evidence that a payment failed" (line 141).
- A reply deadline closes only the transport obligation (lines 143–147).

Prototypes:
- There is no time at all. The net grammar has no timed transitions (`limitations.rst`, lines
  83–84).
- R0's recovery budget counts attempts (`durable.py`, lines 164–165 and 292–294). The
  specification says the analyser proves no elapsed-time policy
  (`specification/docs/chapters/runtime.rst`, lines 84–86).

### (b) Question

What does `within d` mean for an await: what does expiry produce, and what happens to the
awaited operation and to the obligations it holds?

### (c) Options

| Option | Content | Trade-offs | Effect on Rust |
| --- | --- | --- | --- |
| **4A** Observation deadline | `within d` bounds only how long the activation waits to observe an outcome. Before dispatch, expiry withdraws the waiting invocation, and its linear inputs return to the activation unchanged; waiting has changed no marking (D0-AWAIT-1, `execution-contract.rst`, lines 15–27). After dispatch, expiry yields a distinct "not observed by deadline" result that carries the still-pending obligation. It is never Err, and the operation's later outcome is still correlated and recorded. | Matches the specification text and the design notes cited above. Needs durable timers and a typed result for late outcomes. | Needs a monotonic clock that tests can inject and timers persisted with the obligation. The timer must not cancel host work as a side effect. |
| **4B** Hard deadline with cancellation | Expiry triggers D0-CANCEL-1 cancellation of the invocation. After dispatch, the runtime pending state keeps the obligation. | Reuses cancellation. But expiry stops being observable as its own outcome, and the activation loses any chance to act on a late result. | Same timer requirements, combined with cancellation (area 5). |
| **4C** No `within` in the language | Deadlines are adapter or runtime configuration only. | Keeps the language small. Deadlines become invisible to typing and to the analyser. | Configuration only. |

### (d) Recommendation (not a decision)

**4A.** `within` is an observation deadline. Expiry is a distinct outcome, and a timeout never
implies that the external action failed or that the obligation ended.

### (e) Downstream

#22 (deadline input). Area 7 needs durable timers.

## 5. Cancellation ownership

### (a) Current behaviour

Specification:
- Every resource declaration names a cancellation route (`types.rst`, lines 56–58).
- D0-CANCEL-1 covers cancellation while waiting (`execution-contract.rst`, lines 108–118):
  - before dispatch, the invocation's resource inputs move via their declared routes exactly
    once;
  - after dispatch, cancellation acts on the runtime pending state;
  - a fenced activation must not consume its former handles or accept a second completion.
- Cancellation routes transfer outputs to non-activation owners. Normal return never cancels
  (`effects.rst`, lines 46–49). For an in-flight payment, cancellation preserves the recovery
  obligation, and paid evidence commits the sale (lines 51–53).

Design notes:
- Cancellation transfers the handle to its abort route "once, after fencing the activation".
  A crash runs no destructor; a durable owner record lets another worker continue
  (`DESIGN_NOTES.md`, lines 27–32).
- While a foreign call is suspended, ownership belongs to the runtime pending state (lines
  34–36).

Prototypes:
- R0's `cancel` advances the job generation and fires the cancellation transition of the
  first live protocol place (`durable.py`, lines 274–283). Stale generations are rejected
  (lines 192–193; `runtime.rst`, lines 55–57).
- The pure scheduler marks a cancelled sibling subtree `CANCELLED`; there are no obligations
  to transfer (`agent-kit/.agents/skills/weave/scripts/weave_pure/runtime.py`, lines 370–382).

### (b) Question

After an activation is cancelled, who owns each outstanding obligation, and until when? The
obligations are live handles not yet dispatched, operations in flight, outcomes received but
not consumed, and child activations.

### (c) Options

| Option | Content | Trade-offs | Effect on Rust |
| --- | --- | --- | --- |
| **5A** Declared-route transfer to non-activation owners | Cancellation first fences the activation (generation). It then cancels child activations, innermost first. Each live handle then moves exactly once along its resource's declared cancellation route to a runtime or domain owner. In-flight operations stay with the runtime pending state, and their outcomes go to the declared recovery owner. | Generalises D0-CANCEL-1 and R0. Each obligation has exactly one owner at every point, and the owner is visible in the net, which the analyser can use. Every resource needs a route that is complete for each state. | Ownership is data in persisted records, never Rust `Drop`. A dropped Rust value must not cancel or discharge anything. |
| **5B** Return to the canceller | Outstanding obligations become the cancelling (parent) activation's responsibility, and it must handle them. | Flexible, and obligations stay in program logic. Requires the canceller to be live and typed for every obligation; this fails when the canceller is itself cancelled or has crashed. | Needs typed hand-back channels and fencing of the canceller. |
| **5C** Single recovery role | Every outstanding obligation goes to one declared recovery role per protocol, with an operator work item. | Simple, with one place to look. Loses the state-sensitive routes that `effects.rst` (line 53) requires, since "a single generic 'undo' action is insufficient". | A single queue. |

### (d) Recommendation (not a decision)

**5A.** Cancellation fences, cancels children, then moves each live obligation exactly once
along its declared route to a non-activation owner. In-flight obligations stay
runtime-owned until a correlated outcome or recovery resolves them.

### (e) Downstream

#24 (cancellation ownership input). Area 7 needs ownership and generation records, and area 6
may check the reachability of routes.

## 6. Verification fragment for M4

### (a) Current behaviour

Specification:
- The result vocabulary is PROVED, CHECKED WITHIN BOUNDS, CHECKED flow, SCRIPTED / passed
  scenario, VIOLATED and NOT ESTABLISHED, each with a defined scope (`verification.rst`, lines
  13–28).
- What is covered today:
  - exact aggregate P-invariants (lines 43–52);
  - invariant families over a tenant/order pair with variable-only inscriptions (lines 63–84);
  - N0 one-order bounded exploration (lines 121–133);
  - N1 exploration with one tenant and N orders; the supplied protocol uses N = 2 (lines
    141–153);
  - the safety-property forms (lines 97–113), with guards as abstract enablers (lines
    115–119).
- No soundness, progress, termination or refinement theorem is machine-checked (lines
  171–173). Liveness and deadlock freedom are not established (`limitations.rst`, lines
  90–94; `execution-contract.rst`, lines 122–132).
- The pure extension has no net or certificate (`agent-kit/docs/weave.md`, lines 320–323).

Prototypes:
- The coloured checker accepts only two distinct tenant/order indices per indexed place and
  per transition binder (`inventory-proof/coloured.py`, lines 52–53 and 57–58).

### (b) Question

Which finite fragment will the M4 analyser cover? This means the nets and inscriptions, the
colour domains, the property forms, whether flows, pure functions and time are included, and
which result labels it may emit for each part.

### (c) Options

| Option | Content | Trade-offs | Effect on Rust |
| --- | --- | --- | --- |
| **6A** Current N1 fragment, made explicit | Aggregate and family invariants (exact, all colours); bounded exploration with explicit colours, stock, bounds and budget; the existing safety forms; F0 flow checks. Pure functions, time, deadlines, liveness and arbitrary declared sorts are excluded and reported NOT ESTABLISHED. | Smallest scope, and every part already has a defined label. Leaves cancellation and deadline behaviour unanalysed. | A Rust analyser can be checked differentially against the Python reference over exactly this fragment. |
| **6B** 6A plus cancellation and deadline paths within bounds | Also explores the declared cancellation routes and the deadline outcomes (areas 4–5) as transitions in the bounded model. | Covers the new semantics where errors are most likely. Depends on #22 and #24 being decided and specified first. | More model generation; same labels. |
| **6C** 6B plus pure functions and liveness | Bounded analysis of pure integer code under the size budget, plus liveness under declared fairness assumptions. | Largest. Liveness needs fairness assumptions that the specification does not yet state (`net-semantics.rst`, lines 93–96). | Substantial new analyser work. |

### (d) Recommendation (not a decision)

**6A for M4.** The 6B additions are listed as explicit exclusions, to be revisited once #22
and #24 are specified. The fragment is limited to the two-sort tenant/order colours of N1, as
the [D0 note](#prepared-d0-note-ac-3) states.

### (e) Downstream

#27 (verification fragment input).

## 7. Durable state inventory for M5

### (a) Current behaviour

Specification:
- D0 "alone makes no storage durability claim", and durable execution "needs persisted
  ownership/generation records" (`execution-contract.rst`, lines 117–118).
- R0 stores marking, jobs, operations, results and events in one SQLite database
  (`runtime.rst`, lines 25–28). Admission commits before acknowledgement (lines 30–34).
- R0 does not execute arbitrary F0 continuations (`runtime.rst`, lines 17–20; RUN-01,
  `limitations.rst`, lines 60–61).
- Durable admission binding to code revisions, generation-aware leases and similar features
  are proposals (`proposals.rst`, lines 65–73).

The R0 schema is in `durable.py`, lines 93–98, with the provider table at line 45. The
continuation representation is a separate decision task, #35
(`docs/development/scheduling.md`, line 78).

| State item | Purpose | R0 at base | Gap |
| --- | --- | --- | --- |
| Admission records | Deduplicate and resume admissions; acknowledge after commit | `jobs` key, payload, `source_ack` (`durable.py`, lines 95 and 171–185) | Per-admission code or route revision; only one global net digest exists (lines 100–108) |
| Continuations | Resume a waiting invocation: captured arguments, moved handles, continuation (D0-AWAIT-1) | None | Entire item; representation is #35 |
| Markings | Token counts per cell | `marking` (line 94) | None for N1 cells |
| Timers | Deadlines (area 4), leases, elapsed recovery budgets | None; attempt counters only (lines 96, 164–165, 292–294) | Entire item |
| Operation ledger | Key, request digest, state, attempts, correlation | `operations` (line 96); request digest only on the provider side (line 45) | Domain-side request digest and provider-reference aliases (`effects.rst`, lines 68–72) |
| Result ledger | Each completion delivered once | `results` (line 97); `completed` and `worker_ack` in `jobs` (line 95) | Generalisation beyond the Inventory result |
| Fencing generations | Reject stale activations and workers | `jobs.generation` (lines 95, 192–193, 274–277) | Generations for activations, recovery roles and leases, not only jobs |
| Ownership records | Current owner of each live obligation (area 5) | Implicit in the owner kind each place declares (`inventory-proof/checker.py`, line 213) | Explicit owner per obligation |
| Event history | Audit and replay | `events` (line 98) | Replay contract, if 7B is chosen |

### (b) Question

What is the complete set of state the M5 runtime must persist, and which items must commit
together atomically?

### (c) Options

| Option | Content | Trade-offs | Effect on Rust |
| --- | --- | --- | --- |
| **7A** Full inventory, persisted directly | Every row above is persisted, with commit groups specified: admission with its record; firing with marking, ledger and result; cancellation with generation, ownership and routes; timer arming with its obligation. | Explicit and auditable, and recovery reads state instead of recomputing it. More schema to migrate. | Storage layer with an explicit schema; host data structures never serialized as the format. |
| **7B** Event-sourced | Persist events and ledgers; markings, continuations and timers are derived by replay. | Smaller core schema. Replay requires deterministic pure evaluation (2B) and a stable continuation format. Recovery time grows with history. | Deterministic replay engine; the same version and migration questions arise for events. |
| **7C** Host-state snapshots | Serialize interpreter or task state as host objects. | Quick. Ties the durable format to Python or Rust internals, against `docs/development/implementation-language.md`, and pre-empts #35. | The format would depend on Rust internals. |

### (d) Recommendation (not a decision)

**7A.** All nine items are in the inventory, with the commit groups specified. The
continuation representation is left to #35.

### (e) Downstream

M5 (epic #59, `docs/development/orchestration-requirements.md`, line 83) and #35.

## Decisions for the maintainer

One line per area. Each names the recommended option; none is decided.

- [ ] 1. Integer semantics: recommended **1A** (exact integers with declared size and
  evaluation budgets), with **D3** Euclidean division (division by zero is a pure fault),
  **L1** ASCII decimal literals and **E1** partial list primitives that fault on empty input.
- [ ] 2. Pure error propagation: recommended **2B** (closed fault set, left-to-right order,
  sequential-equivalent fork outcome, budget exhaustion as a separate outcome).
- [ ] 3. Identity naming: recommended **3A** (nominal identity values, equality within a sort
  only, explicit boundary validation and serialization).
- [ ] 4. Deadline observation: recommended **4A** (`within` bounds observation only; expiry
  is a distinct outcome; a timeout never implies failure).
- [ ] 5. Cancellation ownership: recommended **5A** (fence, cancel children, move each
  obligation exactly once along its declared route to a non-activation owner).
- [ ] 6. Verification fragment: recommended **6A** (current N1 fragment made explicit;
  everything else reported NOT ESTABLISHED; 6B revisited after #22 and #24).
- [ ] 7. Durable state inventory: recommended **7A** (all nine items persisted with specified
  commit groups; continuation representation left to #35).

## Prepared D0 note (AC-3)

Phase 2 inserts this note into `specification/docs/chapters/execution-contract.rst` after line
76, the end of D0-COLOR-2 and before the `D0-ADMIT-1` anchor. The insertion shifts the line
numbers of later rules, so phase 2 regenerates `specification/rules.json` and the rule
catalogue with `cd specification && python3 scripts/refresh_reference_pages.py`. The wording
rests on `net-semantics.rst`, lines 62–63 (two positional sorts), and
`specification/docs/chapters/declarations.rst`, line 101 (two distinct firing variables per
transition).

```rst
.. note::

   **Scope of the colour rules.** D0-COLOR-1 and D0-COLOR-2 currently assume that a
   colour is exactly one tenant/order pair: the two positional N1 sorts in
   :doc:`net-semantics`. Every transition binds one such pair, and every indexed
   handle, input, read and output of an operation refers to that pair. D0 does not
   define resources indexed by other or additional declared sorts, by a different
   arity, or by more than one pair per operation. Supporting arbitrary declared
   sorts requires a documented amendment to these rules, to N1 and to the
   verification fragment.
```

## Open question

#15 is named among the downstream issues, but neither the repository nor the material given
to the preparer says which decision area it consumes. By elimination it could take areas 1–2,
but this record does not assume so. The orchestrator or the maintainer should confirm before
phase 2 adds the references for AC-2.

## Acceptance criteria status

| Criterion | Status after this change |
| --- | --- |
| AC-1 Decisions documented with rationale and rejected alternatives | Options, trade-offs and recommendations prepared. The decided record, with the options not chosen recorded as rejected alternatives, follows in phase 2 |
| AC-2 Decisions referenced from downstream issues | Phase 2; the downstream issue of each area is listed above |
| AC-3 D0 colour note in the specification | Wording prepared above; phase 2 edits the specification |

## Commands run

Run from the repository root unless a directory is shown. `$TMPDIR` was `/tmp/claude-1000`.

| ID | Command | Result (exit code) |
| --- | --- | --- |
| R1 | `diff -rq -x __pycache__ inventory-proof agent-kit/.agents/skills/weave/assets/prototype; diff -rq -x __pycache__ inventory-proof specification/reference/prototype` | no output (0, 0). Without `-x __pycache__` the ignored bytecode caches differ, because they embed their own paths |
| R2 | `grep -rnE '//\|\bmax\(\|\bmin\(\|divmod' inventory-proof/*.py agent-kit/.agents/skills/weave/scripts/weave_pure/*.py` | 9 hits: `coloured.py:325`, `check.py:141,146,156`, `runtime.py:132,164,174`, `syntax.py:124`, `values.py:58` (0) |
| P1 | in `agent-kit/`: `printf 'fn big() -> Int:\n    return 123456789012345678901234567890123456789\n' > "$TMPDIR/big.weave"; python3 scripts/weave.py run-pure "$TMPDIR/big.weave" --entry big` | `RESULT 123456789012345678901234567890123456789` (0) |
| P2 | in `agent-kit/`: `printf 'fn digits() -> Int:\n    return \xd9\xa3\xd9\xa4\n' > "$TMPDIR/digits.weave"; python3 scripts/weave.py run-pure "$TMPDIR/digits.weave" --entry digits` | `RESULT 34` (0) |
| P3 | in `agent-kit/`: `printf 'fn echo(xs: IntList) -> IntList:\n    return xs\n' > "$TMPDIR/echo.weave"; python3 scripts/weave.py run-pure "$TMPDIR/echo.weave" --entry echo --args '[[99999999999999999999999999]]'` | `RESULT [99999999999999999999999999]` (0) |
| P4 | as P3 with `--args '[[1e3]]'` | `E424 [runtime] argument xs: expected a JSON list of integers, got [1000.0].` (2) |
| P5 | in `agent-kit/`: `printf 'fn both(a: IntList, b: IntList) -> IntList:\n    return cons(head(a), tail(b))\n' > "$TMPDIR/both.weave"; python3 scripts/weave.py run-pure "$TMPDIR/both.weave" --entry both --args '[[], []]'` | `both.weave:2: E420 head() of an empty list.` (2) |
| P6 | in `agent-kit/`: `printf 'fn hd(xs: IntList) -> Int:\n    return head(xs)\nfn tl(xs: IntList) -> IntList:\n    return tail(xs)\nfn race(a: IntList, b: IntList) -> IntList:\n    fork:\n        let x = hd(a)\n        let y = tl(b)\n    return cons(x, y)\n' > "$TMPDIR/race.weave"; python3 scripts/weave.py run-pure "$TMPDIR/race.weave" --entry race --args '[[], []]' --schedule fifo` | `race.weave:2: E420 head() of an empty list.` (2) |
| P7 | as P6 with `--schedule lifo`; then with `--mode sequential` | `race.weave:4: E420 tail() of an empty list.` (2); sequential: `race.weave:2: E420 head() of an empty list.` (2) |
| P8 | `python3 -c "print(-7 // 2, -7 % 2, 7 // -2)"` | `-4 1 -4` (0) |
| P9 | `python3 -c "max([])"` | `ValueError: max() iterable argument is empty` (1) |
| C1 | in `inventory-proof/`: `sed 's/manual == 0$/manual == 0x0/' Inventory.weave > "$TMPDIR/hex.weave"; python3 checker.py prove "$TMPDIR/hex.weave"` | prints `PROVED registration_balance` for the invariant ending `== 0x0` (0) |
| C2 | in `inventory-proof/`: `sed 's/place sold = 0 owner/place sold = \xd9\xa0 owner/' Inventory.weave > "$TMPDIR/digit.weave"; python3 checker.py prove "$TMPDIR/digit.weave"` | prints `PROVED stock_conservation` and `PROVED registration_balance` (0) |

The Rust Reference passages quoted in area 1 and the `i64::div_euclid` documentation were
fetched from `doc.rust-lang.org` on 29 October 2026. No Rust toolchain was run for this
record.
