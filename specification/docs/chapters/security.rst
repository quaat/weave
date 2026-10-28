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

