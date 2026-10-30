Flow evaluation and propagation
=====================================

.. index:: evaluation order, await, propagation, lowering

Evaluation model
----------------------

A flow invocation receives scalar values and ownership of its linear arguments.
Statements execute in source order. Calls take already-bound arguments, so no
argument-expression evaluation order is needed. A helper evaluates its body
and returns one value. Bindings are immutable; a moved handle is unavailable.

A local API request corresponds to its declared net transition. On an enabled,
successful firing, input handles are consumed and the returned handle represents
the produced activation token. Unit signifies no returned activation obligation.

A foreign request dispatches into runtime-owned pending state. Its eventual
result has one of the declared outcome tags and transfers the corresponding
resource payload to the continuation. The language requires ``await`` on
operations; it does not specify a general asynchronous task object, worker
allocation, or transport scheduler.

The reference synchronous interpreter chooses an outcome immediately from the
scenario and executes dispatch then the outcome transition. It does not wait for
a real service. Disabled transitions cause a host failure in this reference simulator. That is
a documented nonconformance to D0-AWAIT-1, whose normative target is waiting
without changing the marking or returning a failure outcome. See
:doc:`execution-contract` for identity binding, interleaving, and deadlock.

Matching and returning
----------------------------

A match inspects exactly one selected tag and evaluates only that branch.
The payload binding is branch-local. Returning a handle or enum transfers
ownership to the immediate caller; it does not implicitly fire a net transition.
Constructing an enum return wraps an existing payload without minting a new
protocol resource.

The language has no general throw/catch facility. Operational failures in a
reference tool are host diagnostics, not an additional source-level enum case.
Unknown is an explicit protocol result, not a caught host exception.

Exact lowering of question mark
-------------------------------------

Given the source fragment:

.. weave-check::
   :expect: ACCEPT
   :profile: F0/N0
   :context: result-body

   let paid = result?
   await Inventory.sell(paid)
   return Ok()

the continuation is moved into Ok:

.. weave-check::
   :expect: ACCEPT
   :profile: F0/N0
   :context: result-body

   match result:
       Ok(paid):
           await Inventory.sell(paid)
           return Ok()
       Err(_try_1):
           return Err(_try_1)
       Unknown(_try_2):
           return Unknown(_try_2)

These fragments require the surrounding enum-typed flow contract.
Generated names above are illustrative; the implementation chooses fresh
``_try_N`` identifiers absent from the source's collected words.

For:

.. weave-check::
   :expect: ACCEPT
   :profile: F0/N0
   :context: await-body

   let paid = (await Payments.charge(tenant, order, amount, escrow))?

lowering first introduces a fresh binding for the awaited outcome, then performs
the same match. Multiple propagations nest continuations in successive Ok
branches. Only the continuation reachable after success executes.

Lowering inserts no cancellation, release, recovery handoff, payload conversion,
additional foreign call, or net firing beyond the explicit source call.
Err and Unknown return immediately with their existing payloads.

Source locations
----------------------

Internal generated nodes retain the source line of ``?``. Version 3 marks
generated residual returns, allowing E204 to identify the original propagation
and the other outstanding handles. Rendering a lowered source file produces
ordinary source with its own line numbers and no separate source map.
Comments and original formatting are not retained.

The source and its lowering are both statically checked by this documentation's
validator. This is regression evidence for the selected examples, not a proved
semantics-preservation theorem for every program.

What is not specified
---------------------------

F0 has no loops, ordinary if/else, recursion, parallel blocks, effect handlers,
timeouts, retry statements, arithmetic, or user-defined pure function evaluation.
No evaluation rules should be inferred from familiar syntax in other languages.
Pure computation is the separate P0 profile (:doc:`pure`), in its own file kind;
F0 flows do not call P0 functions in this revision.

