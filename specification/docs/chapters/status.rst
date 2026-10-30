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
   * - P0
     - Pure files: typed pure functions over integers, Booleans, lists and
       records, terminal conditionals, direct recursion, run budgets
     - Rust ``crates/weave-check`` and ``crates/weave-eval`` (command
       ``weave``); Python ``scripts/p0_reference.py``; not the snapshot
   * - modules-1 (extension of P0)
     - P0 programs of several module files: selective imports and exports from
       one project root; the ``use net`` header that selects a flow's net
     - Rust ``crates/weave-check`` (command ``weave``) for P0 modules; the agent
       kit's runner over ``checker.py`` for ``use net``; not the snapshot

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
     - Conformance cases C001--C018, C026 and C027; ``test_checker.py``,
       ``test_composition.py``, ``test_rejection_and_propagation.py``;
       ``tests/test_rule_cases.py``
     - ``python3 reference/prototype/checker.py check
       examples/nets/Inventory.weave examples/valid/checkout_propagating.weave``:
       exit 0, three ``CHECKED`` lines (``checkout_propagating``,
       ``place_order``, ``pay_with``).
       ``python3 scripts/validate.py``: exit 0, ``PASS: 27 source expectations;
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
     - ``test_coloured.py``; ``scripts/validate.py`` checks the nine accepted
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
   * - P0
     - :doc:`pure`, :doc:`grammar`; rules ``P0-*``
     - Yes, outside the snapshot: Rust ``crates/weave-check``,
       ``crates/weave-eval`` and the ``weave`` command (``crates/weave-cli``);
       the Python reference evaluator ``scripts/p0_reference.py``
     - Conformance cases C101--C178 (``examples/pure/manifest.json``);
       ``tests/test_p0.py``; ``cargo test --all`` (``crates/weave-check``,
       ``crates/weave-eval``, ``crates/weave-cli``);
       ``scripts/p0_differential.py``; the conformance applications
       ``scripts/p0_applications.py`` (merge sort and routing,
       :ref:`chapters/tooling:Conformance applications`)
     - From the repository root, ``cargo run -q -p weave-cli -- check
       specification/examples/pure/valid/merge_sort.weave``: exit 0, one line
       ``CHECKED pure ...: split, merge, merge_sort, split_items, merge_items,
       sort_items``. ``python3 scripts/p0_differential.py`` (needs Lark) with
       ``cargo`` on ``PATH``: exit 0, ``PASS: P0 reference meets 78 corpus
       expectations; ...`` and ``PASS: Rust weave agrees with the P0
       reference on 743 inputs``. ``python3 scripts/p0_applications.py``
       (needs Lark) with ``cargo`` on ``PATH``: exit 0, ``PASS: P0 reference
       equals the oracles: ...`` and ``PASS: weave run equals the oracles and
       the P0 reference on 2729 runs``
   * - modules-1 (extension of P0)
     - :doc:`names` ("P0 modules (modules-1)", "Net selection"); :doc:`grammar`;
       rules ``MOD-*``
     - Yes, outside the snapshot: P0 modules by ``crates/weave-check`` and the
       ``weave`` command (``--root``); ``use net`` by the agent kit's runner,
       which hands the unchanged prototype checker the flow with the header
       blanked. The Python P0 reference implements P0 only
     - Conformance cases M101--M306 (``examples/modules/manifest.json``);
       ``tests/test_modules.py``; ``cargo test --all``
       (``crates/weave-check/tests/modules.rs``,
       ``crates/weave-eval/tests/modules.rs``,
       ``crates/weave-cli/tests/modules.rs``);
       ``agent-kit/tests/test_use_net.py``
     - ``python3 scripts/modules_conformance.py`` (needs Lark) with ``cargo`` on
       ``PATH``: exit 0, ``PASS: 6 use net flow cases with the reference
       checker, ...`` and ``PASS: weave agrees with 37 modules-1 check and run
       cases (codes, files, lines, related imports)``; without ``cargo`` or
       ``WEAVE_BIN`` the second line is ``SKIP: modules-1 P0 cases not
       established: ...``
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

F0, N0, N1 and R0 are implemented only by the reference snapshot. The Rust
crate ``crates/weave-syntax`` (quaat/weave#9) parses F0, N0, N1 and P0 source
with the EBNF of :doc:`grammar` and reports syntax diagnostics. For F0, N0 and
N1 it checks syntax only: it implements no static rule, analysis or runtime of
those profiles and establishes no conformance claim for them beyond syntax
acceptance. P0 (quaat/weave#10) is implemented outside the snapshot, by the
Rust crates ``crates/weave-check`` and ``crates/weave-eval`` and,
independently, by the Python reference evaluator; a P0 conformance claim names
the implementation and the budgets used. Its
acceptance is compared with the generated parser on the corpus
(:ref:`chapters/grammar:Generated-parser agreement`); run ``cargo test --all``
from the repository root. The modules-1 extension (quaat/weave#12) is
implemented by the same Rust crates for P0 programs of several files, and by the
agent kit's runner for the ``use net`` header of flow files; flows are still
checked only by the reference checker.

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
diagnostic codes are compatibility anchors, not a complete portable ABI. The
reference diagnostics also carry source spans and a principal rule, and can be
written as ``weave-diagnostic-v1`` documents (:doc:`diagnostics`); spans and the
rule mapping locate and explain a rejection, they do not change which programs
a profile accepts.

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

**D-03:** :doc:`pure` defines P0, pure computation in a separate file kind
(quaat/weave#10). It is implemented by the Rust crates and the Python reference
evaluator, not by the snapshot. Flows do not call P0 functions in this
revision.

**D-04:** :doc:`names` defines modules-1, a versioned extension of P0
(quaat/weave#12): local P0 modules with selective imports and exports resolved
from one project root, and the ``use net`` header that selects one net for a
flow file. Its rules are ``MOD-*``, its codes E600 to E619, and its corpus has
its own manifest. It changes no meaning of F0, N0, N1 or P0 and no existing
manifest. Cross-project imports (quaat/weave#13), protocol packages
(quaat/weave#19) and composition of nets (quaat/weave#91) are not part of it.

A new implementation can claim F0 static conformance without a D0 runtime. It
must name that limitation. Neither a future N2 implementation nor a D0 scheduler
is included in this documentation revision.

:doc:`core-decisions` records the maintainer's decisions on integers, pure
faults, identity values, deadlines, cancellation ownership, the M4 verification
fragment and the M5 durable state (quaat/weave#5). They bind later milestones;
they add no rule ID, profile or conformance target to this revision.
