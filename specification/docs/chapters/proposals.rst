Proposed extensions — nonnormative
========================================

.. warning::

   Nothing in this chapter is accepted syntax of the pinned prototype.
   The merge-sort document is an implementation brief, not evidence that the
   extension exists. These proposals are excluded from the F0/N0/N1 grammar.

Pure computation
----------------------

.. note::

   **Adopted by P0.** quaat/weave#10 adopted this proposal, with the maintainer's
   decisions recorded there, as the P0 profile (:doc:`pure`): typed pure
   functions over integers, Booleans, ``List[T]`` and records, with arithmetic,
   Euclidean ``div`` and ``mod``, comparisons, ``and``/``or``/``not``, terminal
   if/else, direct self-recursion and reported fuel, depth and integer-size
   budgets. P0 keeps the core list primitives (``length``, ``is_empty``,
   ``head``, ``tail``, ``cons``); ``split_half``, ``first``, ``second`` and the
   built-in pair were not adopted, because a split is written in Weave over a
   record. Fork/join remains a proposal (below). The text of this section is
   kept as the proposal's history.

The separate merge-sort brief proposes typed pure functions with immutable
integers, Booleans, integer lists, and a pair of integer lists. It requests
integer literals, comparison, local bindings, terminal if/else, direct
self-recursion, and a small primitive set.

.. list-table::
   :header-rows: 1

   * - Proposed primitive
     - Intended role
   * - length / is_empty
     - Inspect list size or emptiness
   * - head / tail
     - Inspect a nonempty list, with specified empty-list failure
   * - cons
     - Prepend without repeatedly copying suffixes
   * - split_half
     - Stable contiguous split with lengths differing by at most one
   * - first / second
     - Project a pair of lists

A future pure function must not receive, capture, forge, duplicate, or drop
linear resources, call an effectful flow, or invoke a foreign API. Signatures
should be registered before bodies; unused bodies still require checking.
The brief excludes mutual recursion and higher-order functions.

Integer range/overflow, primitive error types, pair naming, expression precedence,
resource exhaustion, and a complete static/dynamic semantics require explicit
adoption. A fuel or depth limit is not a termination proof.

The maintainer has since decided integer semantics, empty-list failure, pure
fault propagation and evaluation order for future work; see :doc:`core-decisions`.
Those decisions do not make this proposal accepted syntax.

Scoped fork/join
----------------------

.. note::

   **Not adopted, not implemented.** P0 has no fork/join. The sequential merge
   sort ``examples/pure/valid/merge_sort.weave`` is a P0 conformance
   application (:ref:`chapters/tooling:Conformance applications`), not this
   proposal: the concurrent merge-sort brief, with scoped child activations and
   correlated joins, is quaat/weave#42 in milestone M6 and is not complete.

The brief requests two independent pure calls whose results join before the
parent continues. Children require distinct activation identities and a shared
parent/fork correlation identity. Joining must consume the matching result pair
once, in branch order, and resume the parent once.

A bounded cooperative scheduler is sufficient for the brief. Waiting parents
must not monopolize workers needed by children. Failure and exhaustion require
explicit outcomes, cleanup of pending work, and no manufactured partial results.
Sequential and concurrent modes must evaluate the same source consistently.
CPU parallelism must not be claimed from cooperative scheduling alone.

Acceptance evidence must come from actual scheduler events and tests: both
siblings can progress, either can complete first, joins match identities, and
completion leaves no orphan tasks. Inventory accounting does not prove a future
task scheduler correct.

Modules and packages
--------------------------

.. note::

   **Local P0 modules adopted as modules-1.** quaat/weave#12 adopted local P0
   modules, with the maintainer's decisions recorded there, as the versioned
   extension modules-1 (:ref:`chapters/names:P0 modules (modules-1)`): selective
   imports of exported functions and records from one project root, and the
   ``use net`` header that selects one net for a flow file. Its scope was amended
   from importing protocols across projects. What remains proposed, and is not
   accepted syntax: locked cross-project imports, package identity and lockfiles
   (quaat/weave#13); reusable protocol packages (quaat/weave#19); composition of
   several nets or protocols (quaat/weave#91); and qualified calls, wildcard
   imports, re-exports and opaque types, which modules-1 deliberately leaves out.

Future effect providers and durable services
--------------------------------------------------

Earlier design notes also propose statically selected effect providers, durable
admission binding to code revisions, recovery-role upgrades, generation-aware
leases, bounded inboxes, escalation budgets, and transport reply lifetimes.
These preserve capabilities and uncertainty rather than erasing them.

Only the narrow R0 behaviours documented in :doc:`runtime` are implemented.
The broader proposal still needs syntax, types, scheduling rules, persistence
contracts, migration rules, and evidence. No executable examples of it are
included in the acceptance corpus.

Promotion process
-----------------------

P0 followed this process for pure computation (:doc:`pure`), and modules-1 for
local modules (:doc:`names`). To promote a
proposal, adopt its complete grammar and semantics, implement the
parser/checker/evaluator, add positive and negative cases, test runtime failure
paths, preserve existing conformance cases, update provenance, and revise the
profile matrix. A plausible source example alone is insufficient.

