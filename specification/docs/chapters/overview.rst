Language overview
=======================

.. index:: flow, Petri net, capability, linear resource

Design
------------

A net declares protocol states and transitions. A flow composes operations
exported by the net and its foreign declarations. Linear handles expose selected
states to application code. A handle is both an obligation and permission to
request a state change.

**Accounting**, **identity**, and **evidence** have distinct roles. Accounting
tracks token counts. Identity distinguishes tenants and orders. Evidence
justifies transitions such as committing a paid sale. Each needs its own checks.

A typical order reserves inventory, obtaining ``Hold[tenant, order]``; arms
recovery and receives ``Escrow[tenant, order]``; dispatches a payment using that
permit; and receives ``Paid``, ``Unpaid``, or ``Uncertain`` inside a closed outcome.
It then sells, releases, or transfers to recovery. These state/type names belong to the Inventory instance. However, N0/N1
check syntax itself embeds payment evidence terminology; MODEL-04 records this
limitation and :doc:`evidence-design` gives its adopted generalization.

A complete helper
-----------------------

.. weave-check:: ../../examples/valid/arm_hold.weave
   :expect: ACCEPT
   :profile: F0/N0
   :caption: Checked against the supplied Inventory API

The call consumes ``hold``. Its binding remains in scope for diagnostics but is
unavailable for reuse. Returning ``escrow`` transfers the replacement obligation
to the caller. Normal return does not implicitly release resources.

Functional and concurrent meaning
---------------------------------------

Bindings are single-assignment. State changes occur through declared operations
and net firings. Flows do not provide general pure functions, arithmetic,
lists, or higher-order programming; typed pure functions with arithmetic, lists
and records are the separate P0 profile (:doc:`pure`), in its own file kind.

A net may enable multiple transitions simultaneously. Reference analysis uses
interleaved atomic firings, expressing potential concurrency without providing a
parallel-flow construct or promising a thread scheduler. The synchronous flow
simulator and durable protocol driver have different execution scopes.

Reading a result
----------------------

``CHECKED flow`` means static obligations were satisfied; ``CHECKED pure`` means
the same for a P0 pure file, not that a run terminates. ``PROVED`` means a
specified accounting equality is inductive over net firings. ``CHECKED WITHIN
BOUNDS`` means the stated finite model was exhaustively explored. A passed
scenario is concrete execution evidence. These do not individually establish
provider honesty, production durability, general liveness, or correct compilation
of all source programs.


.. figure:: ../_static/diagrams/handle-states.*
   :name: fig-handle-states
   :alt: Hold becomes Escrow, then runtime pending state and one of Paid, Unpaid or Uncertain.
   :width: 100%

   Normal handle path. The complete net, including all cancellation routes, is
   in :doc:`protocol-diff`; this figure summarizes the interface states.
