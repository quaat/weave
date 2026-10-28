Design history and rejected or deferred alternatives
==========================================================

Evidence status
---------------------

The review refers to four earlier design drafts. They were not recovered from
the available project files or context retrieval for this revision. Their
titles, dates, ordering, and per-draft changes cannot be reconstructed reliably.
This appendix deliberately does not invent a four-draft chronology.

The available evidence consists of the version-3 DESIGN_NOTES.md, version-2
agent-kit boundary, the later merge-sort brief, the delivered 0.1 specification,
and the user's current review. The table distinguishes recorded decisions from
current exclusions and new rationale.

.. list-table::
   :header-rows: 1
   :widths: 16 25 34 25

   * - Construct
     - Established status
     - Reason supported by available material
     - Evidence / missing history
   * - Open unions
     - Explicitly withdrawn from initial design
     - Closed nominal enums; no implicit widening; explicit mapping for a future
       general language
     - DESIGN_NOTES.md, Closed error types
   * - General resumable handlers
     - Excluded from proposed version-one providers
     - Statically selected typed providers retain capabilities and uncertainty
     - DESIGN_NOTES.md, Non-foreign effects
   * - Effect rows
     - Not implemented; historical removal unverified
     - This draft keeps explicit signatures; it does not infer that all future
       effect abstraction was rejected
     - Current boundary; four-draft rationale unavailable
   * - Task
     - No implemented first-class Task type
     - Merge-sort brief asks for scoped child activations and correlated joins,
       not proof of a general task API
     - Review names earlier construct; no retrieved removal decision
   * - within
     - Unsupported; not established as permanently rejected
     - A timeout cannot establish that an external mutation failed; deadline,
       lease, and obligation lifetime require separate contracts
     - Boundary + DESIGN_NOTES timing discussion; original syntax decision absent
   * - retry
     - Unsupported source construct; R0 has a concrete recovery policy
     - Stable keys, retention horizons, evidence, and budgets must survive retries
     - DESIGN_NOTES + R0; no recovered general syntax history
   * - dataflow
     - Unsupported; historical design status unverified
     - No rationale attributed to absent drafts
     - User review only
   * - Recursive effectful flows
     - Rejected by the implemented fragment (E218)
     - The pure merge-sort extension is deliberately separate; it does not need
       recursive resource-bearing flows
     - Checker and merge-sort brief
   * - Pure functions / fork-join
     - Proposed extension, unimplemented
     - Immutable computation separated from effects; scoped joins with explicit
       identity and bounded resources
     - Merge-sort brief, not a completed implementation

The explanation of why obligations are not garbage and why waiting is selected
is this draft's :doc:`rationale`. It must not be misread as a quotation from a
missing historical source.

Known evolution
---------------------

* Agent-kit snapshot: restricted N0/F0, 107 prototype tests, no durable runtime.
* Prototype version 3: N1 colour accounting/correlation and R0 process-crash
  cases; 143 tests in the delivered snapshot.
* Specification 0.1: implementation profiles, EBNF, result vocabulary and limits.
* Specification 0.2: D-01 declared evidence/correlation direction; D-02 waiting
  execution contract; explicit N0/N1 difference; formal rules and conformance.

To complete the four-draft appendix, the original texts are still needed.
When available, record each draft's identity/hash and cite concrete changes.
Absence from an implementation is not, by itself, evidence of a rejected design.

