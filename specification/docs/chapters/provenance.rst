Sources, provenance, and change history
=============================================

Source hierarchy
----------------------

The specification is grounded in these project artifacts, inspected on
28 October 2026:

.. list-table::
   :header-rows: 1
   :widths: 25 45 30

   * - Artifact
     - Role
     - Treatment
   * - weave-inventory-proof.zip, version 3
     - Current parser, checker, coloured analyser, durable model, tests, nets
     - Primary implementation baseline
   * - weave-agent-kit.zip
     - Older version-2 teaching guide, examples, manifest, runner conventions
     - Teaching examples rechecked against version 3
   * - claude-code-weave-merge-sort.md
     - Proposed pure-function and fork/join implementation task
     - Proposal only; no implementation claim
   * - claude-code-tiny-shop.md
     - Application brief for the restricted effectful language
     - Context; no additional accepted syntax

The agent kit's statement that no durable runtime exists describes its older
bundled snapshot. Version 3 adds a narrow process-crash model. Conversely,
version 3 does not implement the later merge-sort brief's pure functions or
scheduler. This document reconciles those boundaries explicitly.

The exact original archive checksums and byte-level hashes of included reference
files are recorded in ``PROVENANCE.json``. Included reference files retain their
original bytes. Python caches are excluded from the delivered snapshot.

Traceability
------------------

.. list-table::
   :header-rows: 1

   * - Specification area
     - Primary source anchors under reference/prototype
   * - Lines, indentation, types
     - ``checker.py: tree, split_commas, type_of, parameters``
   * - Net grammar and ownership
     - ``checker.py: parse_net, validate``
   * - Aggregate arithmetic
     - ``checker.py: linear_expression, prove``
   * - F0 signatures and moves
     - ``checker.py: check_flow, apply_call, check_body``
   * - Question-mark transformation
     - ``checker.py: lower_questions, lower_flow_source``
   * - N0 ordering
     - ``checker.py: explore_order``
   * - N1 parsing and families
     - ``coloured.py: parse_coloured, prove_colours``
   * - Coloured firing and search
     - ``coloured.py: Unfolding, explore_colours``
   * - Scripted F0 execution
     - ``simulate.py: simulate``
   * - Crash model
     - ``durable.py: Provider, Runtime, run_crash_cases``
   * - Negative language and protocol cases
     - ``tests/test_checker.py``, ``test_composition.py``,
       ``test_rejection_and_propagation.py``, ``test_coloured.py``
   * - Recovery acceptance
     - ``tests/test_durable.py``

Function names are stable reading anchors for this snapshot, not a published
Python API. This package's scripts import them solely for reproducibility.

Distribution status
-------------------------

The specification, the reference prototype snapshot and the teaching kit are
released under the MIT License, Copyright (c) 2026 Thomas F. Hagelien. The
license text is in ``LICENSE`` at the root of the
`project repository <https://github.com/quaat/weave>`_.

Change history
--------------------

0.1-draft — 28 October 2026
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Initial specification package: consolidated grammar; lexical and static rules;
flow and net semantics; effects and recovery; exact proof/bounded-check scope;
diagnostics; implementation-discrepancy register; proposals separated from
supported syntax; Sphinx sources, checked examples, provenance, and build evidence.


Draft 0.2 — 28 October 2026
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Responds to the specification review: D-01/D-02 decisions, D0 identity and waiting
contract, N2 declared-evidence direction, explicit N0/N1 protocol differences,
F0 inference rules and stable IDs, centralized syntax constraints, generated
grammar audit, normative conformance appendix, checked inline documentation,
rationale/history/security, lease tutorial, SVG figures, trace walkthroughs,
R0 acceptance table, footer hash and build hygiene. The original prototype is
unchanged. The four earlier design drafts remain unavailable; their chronology
is not invented.
