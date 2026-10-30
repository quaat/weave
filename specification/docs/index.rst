Weave language specification
==================================

**Draft 0.2 — 28 October 2026**

Weave describes stateful protocols as functional Petri nets and composes their
operations through nominally typed, linear flows. This specification defines the
documented executable fragment, its verification contracts, and its current
implementation boundaries.

.. important::

   This is a specification draft grounded in prototype version 3, not a claim
   that a general-purpose Weave compiler or distributed runtime is complete.
   Read :doc:`chapters/status` before interpreting a conformance or proof claim.

For language users, start with :doc:`chapters/overview` and
:doc:`chapters/examples`. For implementers, read the lexical and grammar chapters
followed by static and dynamic semantics. For reviewers, use
:doc:`chapters/verification`, :doc:`chapters/limitations`, and
:doc:`chapters/provenance`.

.. toctree::
   :maxdepth: 2
   :numbered:
   :caption: Specification

   chapters/status
   chapters/rationale
   chapters/overview
   chapters/lexical
   chapters/grammar
   chapters/names
   chapters/types
   chapters/declarations
   chapters/static-semantics
   chapters/flow-semantics
   chapters/pure
   chapters/execution-contract
   chapters/net-semantics
   chapters/effects
   chapters/verification
   chapters/runtime
   chapters/diagnostics
   chapters/security
   chapters/evidence-design

.. toctree::
   :maxdepth: 2
   :caption: Reference and maintenance

   chapters/protocol-diff
   chapters/examples
   chapters/lease-tutorial
   chapters/counterexamples
   chapters/stability
   chapters/baseline
   chapters/conformance
   chapters/rule-catalogue
   chapters/rule-coverage
   chapters/limitations
   chapters/core-decisions
   chapters/proposals
   chapters/tooling
   chapters/provenance
   chapters/design-history
   chapters/glossary

.. only:: not singlehtml

   * :ref:`genindex`
   * :ref:`search`

.. only:: singlehtml

   Use your browser's Find command to search this single-page edition. The
   published site's default is the `multi-page edition with full-text search
   <https://quaat.github.io/weave/>`_; PDF editions are attached to the
   project's `releases <https://github.com/quaat/weave/releases>`_.

