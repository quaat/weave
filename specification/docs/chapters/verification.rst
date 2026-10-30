Verification semantics and evidence
=========================================

.. index:: P-invariant, invariant family, bounded exploration, proof certificate

Result vocabulary
-----------------------

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - Label
     - Established claim
   * - PROVED
     - Exact integer invariant obligations discharged for the parsed transition
       system and stated initialization
   * - CHECKED WITHIN BOUNDS
     - Complete finite exploration at explicit colours, stock, token bounds,
       state budget, and guard abstraction
   * - CHECKED flow
     - F0 type, identity, move, return, and exhaustiveness checks passed
   * - CHECKED pure
     - P0 type, effect, path, and recursion-shape checks passed
   * - SCRIPTED / passed scenario
     - A selected concrete execution or injected crash case satisfied assertions
   * - VIOLATED
     - A modeled counterexample was found
   * - NOT ESTABLISHED
     - Missing model, budget/bound exhaustion, or a guarantee outside the tool

Result labels in tool output
----------------------------------

The seven labels above are the only labels a tool or an evidence document attaches
to a claim, written exactly as in the table. CHECKED pure was added with the P0
profile (:doc:`pure`, quaat/weave#10); the other six predate it. It is a compatible
addition: no existing result changes label, and no label changes meaning.
CHECKED pure applies only to P0 files and says nothing about termination,
faults or budgets; a P0 run's outcome is runtime status, and a run compared with
an asserted expectation is a passed scenario. The labels are used as follows.

* **One label per claim.** A label attaches to an individual claim: one stated
  result about one subject, such as the invariants of one net, one bounded
  exploration, the flows of one source file, one scenario run or one
  counterexample. A label never summarises a command, a test run or a report as
  a whole.
* **Runtime status is not evidence.** The status of a run (``waiting``,
  ``timed out`` or ``completed``) and the status of a tool or test step (for
  example pass or fail) are separate fields. They never take the place of a
  label, and a successful step establishes nothing beyond the claims it labels.
* **Unknown is an application outcome.** :term:`Unknown` is an unresolved
  foreign outcome of the application (:doc:`flow-semantics`). It is never equated with
  NOT ESTABLISHED, which is an evidence result about a claim: a scripted run
  whose outcome is ``Unknown`` can be a passed scenario, and a claim can be
  NOT ESTABLISHED whatever the application outcome.
* **Prototype console lines are raw tool output.** The version-3 prototype
  prints its own words, such as ``PASSED``, ``RECHECKED``, bare ``CHECKED``
  lines and ``NOT PROVED`` in a diagnostic message. These lines stay unchanged
  in the pinned snapshots and are not claims. The agent kit's runner and the
  evidence envelopes state the corresponding claims with the labels above.
* **Diagnostics are not claims.** A diagnostic reports a code. Where a check's
  result is decided by its diagnostic, the claim takes the label the code
  implies: E320 and E420 report a counterexample (VIOLATED), and E321 and E422
  report NOT ESTABLISHED (:doc:`diagnostics`).

Changing which label a result receives (including labelling a result that had
no label), or what a label means, is a semantic change
(:ref:`chapters/stability:Migration notes`); changing only the layout of a
tool's output is an interface change of that tool. The agent kit's
``tests/test_result_labels.py`` and the specification's
``tests/test_result_labels.py`` lint tool output and evidence envelopes against
these rules.

Aggregate invariants
--------------------------

For incidence matrix :math:`C_{p,t}=O_t(p)-I_t(p)`, an aggregate invariant has
place coefficient vector :math:`w` and target :math:`a\,s+b`, where :math:`s`
is the stock parameter. The checker requires:

.. math::

   w^\mathsf{T}M_0(s)=a\,s+b
   \qquad\text{and}\qquad
   w^\mathsf{T}C=0.

The first equality is checked by comparing exact integer coefficients of stock
and the constant term. The second checks every transition column. Induction on
the number of firings then preserves the equality for every finite firing
sequence and every nonnegative initial stock under the net model.

The accepted expressions use integer constants, names, unary minus, addition,
subtraction, parentheses, and multiplication with at least one constant affine
operand. Products of two variable-bearing expressions are rejected. Arithmetic
is exact. The left side names only places and has a nonzero place vector; the
right side names only the stock parameter. Constants may occur on either side.

Read arcs and guards do not affect the incidence matrix. Consequently, an
invariant is not a reachability proof, a correlation proof, or evidence that
payment guards are truthful.

In N1, a bare indexed-place name in an aggregate expression denotes its total
over colours. The erased projection has valid initial aggregate coefficients
only when every initially nonzero indexed place has zero weight. The checker
rejects the unsupported cardinality-dependent case; use a family invariant.

Invariant families
------------------------

A family quantifies over a tenant/order pair:

.. weave-check::
   :expect: ACCEPT
   :profile: N1
   :context: net-fragment

   invariant registration_balance[t, o]:
       registrations[t, o] - escrow[t, o] - inflight[t, o] - paid[t, o] - unpaid[t, o] - uncertain[t, o] - recovery_queue[t, o] - manual[t, o] == 0

All left-side place references use exactly the declared binder and refer to
indexed places. The right side is a constant. Initial values for involved
indexed places must be constants per colour.

.. _N1-FAMILY-1:

**N1-FAMILY-1.** A family invariant MUST quantify over two distinct indices. Its
left side MUST consist of indexed places written with exactly that binder, with
no unindexed term; its right side MUST be a constant; the initial value of each
place it names MUST be a constant per colour, and the per-colour initial marking
MUST satisfy the equality. An aggregate invariant that gives nonzero weight to
an initially nonzero indexed place depends on the number of colours and is
rejected as well. Each violation is reported with E411.

For each transition, the checker groups weighted take/put coefficients by their
symbolic inscription tuple and requires every residual group to be zero.
This proves preservation for all valuations in this restricted variable-only
inscription fragment, independent of the finite exploration domain. It is a
sufficient algebraic check; richer colour expressions are not implemented.

.. _N1-FAMILY-2:

**N1-FAMILY-2.** For every transition, each group of weighted take and put
coefficients with the same symbolic inscription tuple MUST sum to zero. A
nonzero group means the family is not proved for every colour; the checker
reports E412 and names the transition and its residual.

An example mutation consumes ``paid[t, o]`` with
``registrations[t, other]``. Its total counts can balance while per-colour
registration accounting fails. Read-only identity mistakes may preserve all
families and require the separate token-correlation check.

Safety properties
-----------------------

Let ``present(p, c)`` mean a positive token count. Evidence and dispatch flags are
persistent history bits, initially false.

.. list-table::
   :header-rows: 1

   * - Source form
     - Safety condition
   * - ``marked p requires paid_evidence``
     - Presence of p implies a paid witness for that identity
   * - ``marked p requires rejected_evidence``
     - Presence implies a final-rejection witness
   * - ``marked p requires marked q``
     - Presence of p implies presence of q for the same identity
   * - ``after paid_evidence forbid p``
     - Once paid is witnessed, p must remain unmarked
   * - ``after dispatch marked p requires rejected_evidence``
     - After dispatch, presence of p requires final rejection
   * - ``tokens match firing`` (N1)
     - Every indexed arc in an enabled mode belongs to its firing colour

A guard classified ``establishes_paid`` or ``establishes_rejected`` adds the
corresponding witness when its transition fires. Other guards are abstract
nondeterministic enablers. Witnesses never reset; the explorer does not assume
paid and rejected witnesses are mutually exclusive. Provider consistency is an
explicit external assumption.

One-order model: N0
-------------------------

N0 fixes stock to one, allows at most one admission, and applies the declared
bound to every place. The default state budget is 10,000. The second admission
is excluded by this model's construction; N0 does not prove arbitrary admission
uniqueness.

.. _N0-ORDER-1:

**N0-ORDER-1.** A complete N0 search checks the stated witness predicates in
the initial and every reached state; a violating trace MUST report E320.
Bound/budget exhaustion reports E321 rather than a successful check.

The supplied legacy net has 20 states and 43 edges and reaches all 21 transitions.
These numbers characterize that exact net and algorithm, not the language.

Coloured model: N1
------------------------

The default finite colour set is one tenant with ``orders N`` distinct orders.
Stock defaults to N. The supplied protocol uses N=2. Each indexed cell is bounded
by ``place_bound``. Each shared cell is bounded by the maximum of initial stock
and that cell's initial count. The default state budget is 100,000.

Unlike N0, N1 reports a violation if a second reservation for an admitted identity
is enabled. The supplied identities token disables it structurally.
Correlation is checked for all enabled modes, including read and output arcs.

.. _N1-ORDER-1:

**N1-ORDER-1.** A complete N1 search checks, in the initial and every reached
state, each property for every colour, the ``tokens match firing`` correlation
of every enabled mode, and that no second admission of an admitted identity is
enabled. A violation MUST report E420 with its trace. Exceeding a cell bound or
the state budget reports E422 rather than a successful check.

The supplied N1 net explores 841 states and 3,712 edges, reaches all 24
transitions, and unfolds to 32 cells and 48 firing modes. It does not establish
an arbitrary-order cutoff theorem. Custom two-tenant cases occur in regression
tests; the default run still has one tenant.

Property premise counters and transition coverage help detect vacuous checks.
A property whose premise never occurs may hold vacuously; reachability coverage
does not establish fairness or eventual completion.

Proof artifacts and trusted components
--------------------------------------------

Legacy accounting evidence is source-bound and contains the place/transition
order, initial affine vectors, incidence matrix, weights, and residuals.
``verify_certificate.py`` rechecks that arithmetic against the source. It shares
the parser and expression reader; it is not an independent proof assistant.

Coloured evidence contains aggregate results, family coefficients, symbolic
residuals, inscriptions, and a finite unfolding. It is generated by the same
checker and has no independent formal verifier in this snapshot.

The Python implementation, expression reader, source-to-model translation, and
execution runtime remain trusted components. No soundness, progress, termination,
or compiler-refinement theorem has been machine-checked here.

