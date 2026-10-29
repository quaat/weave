Status and conformance
============================

Scope
-----------

This document specifies the restricted, executable Weave language represented by
the 28 October 2026 version-3 prototype. It is intended for implementers, protocol
authors, application authors, and reviewers of verification results.

The source contains two closely related net languages and one common flow
language, plus a protocol-specific durable driver. Their guarantees must not be
conflated. These profile names are introduced by this draft:

.. list-table::
   :header-rows: 1
   :widths: 10 50 40

   * - Profile
     - Coverage
     - Reference
   * - F0
     - Indexed nominal types, linear flows, terminal matches, propagation
     - ``checker.py`` with a validated net API environment
   * - N0
     - Uncoloured places, sealed ownership, affine invariants, one-order checks
     - ``checker.py``
   * - N1
     - N0 structure extended with two-sort colours, families, finite exploration
     - ``coloured.py`` and ``checker.py``
   * - R0
     - Concrete two-order process-crash model over the Inventory N1 protocol
     - ``durable.py``; not a general F0 interpreter

Supporting N1 does not imply supporting R0. Accepting an F0 program does not
establish that every operation is enabled or that a real service completes it.

Profile matrix
--------------------

The matrix records, for each profile of this draft, where it is specified, what
implements it in the pinned snapshot ``reference/prototype/``, what tests it, and
a command that produces its evidence. Run each command from ``specification/``
with Python 3.11 or newer; it needs no third-party package. The last column
gives the exit status and the result lines at this revision. D0 and N2 are targets: they
have no implementation, so no command establishes them.

.. list-table::
   :header-rows: 1
   :widths: 7 19 18 24 32

   * - Profile
     - Specified
     - Implemented
     - Tested
     - Evidence command and expected result
   * - F0
     - :doc:`static-semantics`, :doc:`flow-semantics`, :doc:`types`,
       :doc:`grammar`; rules ``F0-*``, ``TYPE-REQ-1``
     - Yes: ``checker.py`` (``check_flow``, ``lower_flow_source``) against a
       validated N0 or N1 API environment
     - Conformance cases C001--C018; ``test_checker.py``,
       ``test_composition.py``, ``test_rejection_and_propagation.py``;
       ``tests/test_rule_cases.py``
     - ``python3 reference/prototype/checker.py check
       examples/nets/Inventory.weave examples/valid/checkout_propagating.weave``:
       exit 0, three ``CHECKED`` lines (``checkout_propagating``,
       ``place_order``, ``pay_with``).
       ``python3 scripts/validate.py``: exit 0, ``PASS: 25 source expectations;
       3 scripted scenarios``
   * - N0
     - :doc:`declarations`, :doc:`net-semantics` (uncoloured markings),
       :doc:`verification` (one-order model); rules ``N0-*``, ``NET-*``
     - Yes: ``checker.py`` (``parse_net``, ``prove``, ``explore_order``)
     - Conformance cases C019--C025; ``test_checker.py``,
       ``test_composition.py``, ``test_rejection_and_propagation.py``;
       ``tests/test_rule_cases.py``
     - ``python3 reference/prototype/checker.py analyze
       examples/nets/Inventory.weave``: exit 0; ``PROVED stock_conservation``,
       ``PROVED registration_balance``, three structural ``CHECKED`` lines and
       nine ``CHECKED WITHIN BOUNDS`` property lines
   * - N1
     - :doc:`net-semantics` (coloured markings), :doc:`verification`
       (coloured model)
     - Yes: ``coloured.py`` with the shared ``checker.py`` structure
       (MODEL-01 in :doc:`limitations`)
     - ``test_coloured.py``; ``scripts/validate.py`` checks the eight accepted
       flows against the N1 API projection and the E420 walkthrough. The
       conformance corpus has no N1 case.
     - ``python3 reference/prototype/coloured.py analyze
       examples/nets/Inventory.coloured.weave``: exit 0; two ``PROVED aggregate``
       and three ``PROVED per-colour`` lines, ``CHECKED WITHIN BOUNDS orders=2,
       states=841, edges=3712``
   * - R0
     - :doc:`runtime`
     - Inventory protocol only: ``durable.py``; not a general F0 interpreter
     - ``test_durable.py``
     - ``python3 reference/prototype/durable.py``: exit 0, six ``PASSED``
       process-crash scenario lines
   * - D0 (target)
     - :doc:`execution-contract`; rules ``D0-*``
     - No
     - No conformance suite; the ``D0-*`` rules are pending in
       :doc:`rule-coverage`
     - None. A D0 conformance claim is NOT ESTABLISHED (missing model).
   * - N2 (target)
     - :doc:`evidence-design`; ``grammar/weave-n2-delta.ebnf``; rules ``N2-*``
     - No
     - No conformance suite; the ``N2-*`` rules are pending in
       :doc:`rule-coverage`
     - None. An N2 conformance claim is NOT ESTABLISHED (missing model).

Test files in the "Tested" column are in ``reference/prototype/tests/`` unless
another directory is named. ``python3 scripts/test_reference.py`` runs all five
prototype test files (exit 0, ``Ran 143 tests``). :doc:`rule-coverage` maps each
rule ID to its cases and tests or to a pending-implementation entry.
:doc:`baseline` lists the public claims with their profile and command, and the
procedure that reproduces the whole baseline from a fresh clone. What the
checkers trust about parsing and lowering is stated in
:ref:`source-to-model-trust-boundary`.

Authority and normative language
--------------------------------------

**MUST**, **MUST NOT**, **SHOULD**, and **MAY** express requirements within this
draft. MUST is mandatory, SHOULD permits a documented reason for deviation, and
MAY marks an option. They do not imply prior project approval of new features.

The grammar and identified normative rules define a documented, portable subset;
other prose explains those requirements. Rule IDs are indexed in
:doc:`rule-catalogue` and used by :doc:`conformance`.
Requirements marked **Editorial portability rule** avoid accidental parser
behaviour; they are not claimed to be enforced by the existing checker.
:doc:`limitations` collects them. The example explanation is informative, but the required cases and diagnostics
in :doc:`conformance` are normative. R0 describes the
actual model without adding language syntax. :doc:`proposals` is wholly
nonnormative and unsupported.

For an implementation audit, pinned source and tests are evidence of observed
behaviour. A difference between that implementation and this draft is a
discrepancy to report. Once a draft is adopted as a language standard, normative
prose should take precedence over implementation accidents.

Conformance
-----------------

.. _CONF-REQ-1:

**CONF-REQ-1.** A conformance claim MUST name the document revision and supported profiles,
parser deviations, analysis bounds, and runtime assumptions. Unsupported
constructs MUST be rejected rather than silently ignored or executed as
host-language text.

.. _CONF-REQ-2:

**CONF-REQ-2.** An F0 checker MUST enforce nominal equality, identity consistency, move-only
obligations, exhaustive terminal matches, and complete returns. A net validator
MUST check ownership contracts before attributing guarantees to client code.
An analyser MUST distinguish invariant proof, bounded checking, and execution.
Search exhaustion MUST NOT be reported as a successful exhaustive check.

Diagnostic wording and internal structures are not standardized. Reference
diagnostic codes are compatibility anchors, not a complete portable ABI.

Versioning
----------------

.. _CONF-REQ-3:

**CONF-REQ-3.** ``0.2-draft`` versions this document, not the compiler. There is no
language-version pragma, package manifest, import system, stable bytecode format,
or binary ABI. Programs and evidence SHOULD include the selected net, source and
tool revision, and analysis settings.

Adding an enum case breaks exhaustive callers. Changing issuers, cancellation
routes, identity indices, or inscriptions can invalidate old checks and stored
state. An unchanged operation name does not establish compatibility.


New draft decisions and conformance targets
-------------------------------------------------

**D-01:** :doc:`evidence-design` adopts declared evidence classes and correlation
strategies for N2. N0/N1 remain payment-specific legacy check languages; N2 is
unimplemented. The Inventory state machine is an instance, but its original
evidence/check DSL is not domain-neutral.

**D-02:** :doc:`execution-contract` defines D0: disabled await waits, no marking
change or implicit failure; runtime identity selects one exact firing colour.
D0 is a normative implementation target, not a claim about the existing simulator.
The profile table above lists implemented reference scopes only.

A new implementation can claim F0 static conformance without a D0 runtime. It
must name that limitation. Neither a future N2 implementation nor a D0 scheduler
is included in this documentation revision.
