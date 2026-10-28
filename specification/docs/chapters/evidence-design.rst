Declared evidence and correlation: N2 design
==================================================

**Status: normative direction and core rules adopted for this draft; N2 is not
implemented and is not a complete production adapter specification.**
N0/N1 remain reproducible legacy profiles with payment-specific check terminals.
The complete implementation grammar remains unchanged by this decision.

Decision D-01 replaces those fixed evidence and correlation words with declared
names in the next net profile. This resolves MODEL-04 as a language design
decision while leaving its implementation work open.

.. _N2-EVIDENCE-1:

N2-EVIDENCE-1 — Declarations
----------------------------------

A net MUST declare each evidence class once. A class name is a nominal,
net-scoped symbol; it carries no hard-coded payment meaning. For example, the
following is **N2 target syntax, rejected by the version-3 checker**:

.. code-block:: text

   evidence granted, revoked
   correlation request_key, lease_receipt

A class is a persistent historical witness scoped to one operation identity.
Evidence sets start empty. Witnesses are monotonic: revoked does not erase
granted. Reusing a logical lease after revocation requires a new operation
identity or a separately specified generation, not resetting history in place.

.. _N2-EVIDENCE-2:

N2-EVIDENCE-2 — Establishment and properties
--------------------------------------------------

A classified guard MUST reference a declared class. A firing with that guard adds
the class to the firing identity's witness set. Other guards can remain
nondeterministic. Generic property forms are:

.. code-block:: text

   guard authoritative_grant establishes granted
   guard authoritative_revocation establishes revoked
   property active_needs_grant: marked active requires evidence granted
   property revoked_is_not_active: after evidence revoked forbid active
   property late_release: after dispatch marked released requires evidence revoked

Here granted/revoked are identifiers, not grammar terminals. The same syntax
expresses paid/rejected. The property semantics is set membership in the
per-identity witness set. Multiple witnesses can coexist; no mutual exclusion
or truthfulness follows from their spelling.

.. _N2-CORRELATION-1:

N2-CORRELATION-1 — Declared strategy names
------------------------------------------------

A foreign operation MUST select one or more declared correlation strategy names:

.. code-block:: text

   correlate request_key or lease_receipt

Each selected name binds to a trusted adapter resolver contract at deployment.
A resolver maps authenticated, account-scoped evidence to exactly one admitted
operation identity, or reports unresolved. Missing resolver implementations are
load-time configuration errors; they do not turn dispatch into an unkeyed call.

If several resolvers succeed, they MUST agree. Contradictory mappings are rejected
and recorded as a correlation fault; no outcome token is issued under a guessed
identity. Unresolved correlation is retained for reconciliation. It cannot mint
a normal payload for an arbitrary caller. General authentication and wire-schema
details remain adapter contracts, not net grammar.

Grammar delta
-------------------

The following is a delta to the N1 grammar, not a complete implemented parser.

.. literalinclude:: ../../grammar/weave-n2-delta.ebnf
   :language: text

.. _N2-MIGRATE-1:

N2-MIGRATE-1 — Legacy interpretation
------------------------------------------

A mechanical migration of the legacy evidence DSL declares paid and rejected,
maps establishes_paid to establishes paid, maps establishes_rejected similarly,
and replaces paid_evidence/rejected_evidence with evidence paid/evidence rejected.
The legacy correlation phrase declares the strategy names client_key and
provider_reference before using them.

This mapping preserves the intended witness-set abstraction, not verified
adapter behavior. All source hashes and proof artifacts MUST be regenerated
after migration. No N2 parser or migration implementation is supplied here.

