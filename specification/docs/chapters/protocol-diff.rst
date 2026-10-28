Inventory N0 and Inventory N1 are different protocols
===========================================================

The files share an API shape and several business-state names. N1 is not merely
a colour annotation of N0: it adds admission, release history, worker credits,
and completion accounting. Claims attach to exact source hashes, not the word
Inventory.

.. list-table::
   :header-rows: 1
   :widths: 22 38 40

   * - Aspect
     - Inventory.weave (N0)
     - Inventory.coloured.weave (N1)
   * - Token identity
     - One count per place; identity erased in net state
     - Tenant/order cells plus shared stock/credits
   * - Places / transitions
     - 12 places; 21 transitions
     - 17 place declarations; 24 transitions; two-colour unfolding 32/48
   * - Reserve
     - Take available; put held
     - Also take identities[t,o] and pool_free; put pool_busy[t,o]
   * - Admission uniqueness
     - At-most-once admission imposed by the exploration abstraction
     - Single-use identities token; repeated enabled admission is a violation
   * - Release history
     - Return stock to available; no identity-specific history cell
     - Return stock and put released[t,o]
   * - Release-like routes
     - release, recover_rejected, manual_rejected, cancel_held,
       cancel_escrow, cancel_unpaid return available
     - Each also produces released[t,o]
   * - Ordering predicates
     - Released-stock conditions refer to shared available
     - Per-order release conditions refer to released[t,o]
   * - Worker pool
     - Absent
     - pool_free + pool_busy = 2
   * - Completion
     - No results place
     - finish_sold, finish_released, finish_unknown produce results and return credit
   * - Accounting
     - Aggregate stock and registration invariants
     - Aggregate stock/credits; registration, identity, and job families
   * - Exploration
     - One order, stock one: 20 states / 43 edges
     - Two orders, stock two: 841 states / 3,712 edges
   * - Execution model
     - In-memory F0 simulator with scripted outcome
     - R0 protocol driver; not a general F0 interpreter
   * - Adapter queue in executions
     - May retain charge_requests
     - R0 acceptance scenarios dequeue and assert neither order retains a request

A prohibition on available after paid evidence is meaningful only in N0's
one-item abstraction. Another order can legitimately release stock in N1.
The indexed released place is what lets N1 state that the paid order itself
must not be released.

Claim-to-source map
-------------------------

.. list-table::
   :header-rows: 1

   * - Material
     - Applies to
   * - Legacy execution table in Examples
     - N0 simulator only
   * - N0 net diagram and E320 walkthrough
     - Exact legacy N0 protocol (or its explicitly named mutation)
   * - Colour families, correlation, E420 walkthrough
     - N1 protocol and named mutations
   * - R0 acceptance table and Unknown sequence
     - Durable driver over N1
   * - F0 static rules
     - Shared flow interface; no protocol equivalence claim
   * - D0 dynamic execution contract
     - New normative runtime target; not established by either driver

.. _PROTO-IDENTITY-1:

PROTO-IDENTITY-1 — Evidence reuse
---------------------------------------

A tool or report MUST name which net and execution model its results concern.
Passing the same F0 source against both API projections MUST NOT be reported as
proving that the two nets are equivalent. Source/protocol changes require new
accounting, exploration, and runtime evidence.


.. figure:: ../_static/diagrams/inventory-n0.*
   :name: fig-inventory-n0
   :alt: All 21 N0 transitions with take, read and put arcs; repeated place labels are aliases.
   :width: 100%

   Complete N0 net as transition panels. Repeated place names denote the same
   place, not independent copies. Counts and guards are generated from the net.
