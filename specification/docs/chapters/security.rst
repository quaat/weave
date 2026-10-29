Security considerations
=============================

This chapter consolidates the trust boundary. It does not claim a hardened
production runtime, cryptographic protocol, or security audit.

.. _SEC-CAP-1:

SEC-CAP-1 — Authority containment
---------------------------------------

A deployment claiming capability enforcement MUST prevent application code from
obtaining provider credentials or equivalent unrestricted network authority
outside the enforcing adapter. Static sealing only constrains checked Weave;
arbitrary Python with the same credentials can bypass it.

.. _SEC-EVIDENCE-1:

SEC-EVIDENCE-1 — Authentication and correlation
-----------------------------------------------------

Provider evidence MUST be authenticated, scoped to the correct account/tenant,
and correlated to one admitted operation before it authorizes a state change.
A successful lookup by an untrusted reference is not sufficient. Conflicting
resolver results must not select whichever order is convenient.

The current analyser assumes guard truthfulness and correlation. R0 checks
scripted receipt identity but does not implement webhook signature verification,
key rotation, anti-replay authentication, or production account isolation.

.. _SEC-REPLAY-1:

SEC-REPLAY-1 — Stable operation identity
----------------------------------------------

Retries and duplicate deliveries MUST preserve the original operation key and
request digest. A conflicting payload under the same key is rejected. Provider
retention horizons must be part of the adapter contract; generating a new key
because a response was lost can duplicate an external mutation.

A provider-generated alias can be absent on Unknown. A missing reference or
NotFound result MUST NOT be treated as final rejection without an authoritative
contract ruling out a late effect.

.. _SEC-FENCE-1:

SEC-FENCE-1 — Stale workers
---------------------------------

A worker that has lost its generation MUST NOT commit a transition using its
old authority. Late authentic evidence can still update the operation ledger;
that does not reactivate the stale worker. Cancellation and completion require
exactly-once ownership transfer in the runtime model.

.. _SEC-MODEL-1:

SEC-MODEL-1 — Trusted specifications and artifacts
--------------------------------------------------------

Net declarations, guard classifications, adapters, parser/model translation, and
the Python checker are trusted components. A report MUST identify their versions
and assumptions. Weakening a property or consumer list changes the claim.
A source-bound certificate is not a signature attesting who approved the source.

Build-time weave-check executes only the bundled checker over source text; it
does not evaluate Weave as Python or contact providers. Nevertheless Sphinx
configuration/extensions are executable Python: build documentation only from
trusted packages. Huge hostile inputs can exhaust checker resources; this
delivery is not a sandbox or a denial-of-service-hardened service.


.. _source-to-model-trust-boundary:

Source-to-model trust boundary
------------------------------------

Every result in :doc:`status` concerns a *model*: the places, transitions, arcs,
guards, signatures and flow trees that the reference implementation builds from
source text. This section states what is trusted between the source text and that
model. It elaborates :ref:`SEC-MODEL-1 <SEC-MODEL-1>`, which lists
"parser/model translation" among the trusted components, and adds no rule.

**Trusted, not independently checked.** The following hold only if the pinned
reference code in ``reference/prototype/`` is correct.

* *One parser for every result.* ``checker.py`` builds a line tree (``tree``) and
  matches each line with regular expressions (``parse_net``). ``coloured.py``
  reuses ``tree`` for N1 and renders an erased N0 text that ``parse_net`` then
  validates (MODEL-01 in :doc:`limitations`). Accounting proofs, ordering
  exploration, flow checking, the scripted simulator and the R0 model all read
  models built by this code, so a parsing defect would affect them together.
  ``verify_certificate.py`` rechecks certificate arithmetic with the same parser
  and is not an independent check of translation (:doc:`verification`).
* *Translation of declarations.* Nothing compares the parsed model with the source
  by a second route. In particular, the binding of N1 inscriptions to colours, the
  erased API projection used to check flows against N1, and the correspondence
  between symbolic F0 indices and concrete firing modes (MODEL-06) are trusted.
* *Lowering of* ``?``. ``check_flow`` rewrites every propagation with the rules of
  :ref:`F0-TRY-1 <F0-TRY-1>` and :ref:`F0-TRY-2 <F0-TRY-2>` before it checks a
  flow, so the checker judges the lowered tree, not the surface form. That the
  rewrite matches those rules is trusted. ``scripts/validate.py`` checks the
  rendered lowering of each accepted corpus flow again; this is regression
  evidence for those examples, not a semantics-preservation proof
  (:doc:`flow-semantics`).
* *Source positions.* Diagnostic lines come from the line tree; rendered
  lowerings have no source map, and some coloured diagnostics use erased-source
  positions (DIAG-01 in :doc:`limitations`).

**Checked at the boundary.** These properties are tested rather than assumed;
:doc:`rule-coverage` lists the tests.

* Unrecognised or unsupported syntax is rejected rather than ignored
  (:ref:`CONF-REQ-1 <CONF-REQ-1>`), including nested content under a line that
  takes no block.
* The structural rules ``SYN-01`` to ``SYN-14`` of :doc:`grammar`, for the inputs
  the tests exercise.
* The generated parser of ``scripts/grammar_audit.py`` agrees with the reference
  checker on the 25 corpus outcomes. Its syntax stage is independent; its
  semantic stage is the reference checker (:doc:`grammar`).
* ``scripts/validate.py`` fails unless every file of the snapshot matches the
  SHA-256 recorded in ``PROVENANCE.json``, so results are produced by the pinned
  parser and not a modified copy.

**Outside the boundary.** Editorial portability rules are not enforced
(:doc:`status`); guard truthfulness, provider correlation and adapters are
trusted as stated above in this chapter; documentation fragments shown with
``weave-check`` are spliced into a complete reference net before they are
checked (``scripts/spec_checks.py``).

**Tracking.** quaat/weave#4 links this boundary to quaat/weave#15 for parser and
lowering work. No independent parser or translation check exists at this
revision, so every accounting, exploration, flow-check and scenario result in
this specification depends on the reference parser.
