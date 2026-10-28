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
