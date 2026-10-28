Design rationale
======================

This chapter explains the choices rather than introducing additional normative
rules. The arguments are a rationale for this draft, not invented quotations
from unavailable historical drafts.

Why obligations are linear
--------------------------------

An exception records that control flow did not finish normally. It does not say
who still owns reserved stock, whether a payment happened, or who must reconcile
an unresolved operation. A linear handle makes those obligations part of the
call/return contract. A branch cannot return while quietly leaving one behind.

A cancellation route complements that discipline for abnormal execution.
It does not excuse a normal drop. Treating obligations as garbage would make
correctness depend on collection timing, destructor execution on a crashed
machine, and a live stack that may no longer exist. Explicit transfer to durable
owners gives recovery a protocol state to act upon.

This is not an argument that exceptions are never useful. It is an argument that
exceptions alone cannot encode the selected resource-accounting contract.

Why three outcomes
------------------------

A lost response after a provider commits is observationally different from a
confirmed rejection. A two-outcome interface forces the caller either to lie
about failure or to hide unresolved work outside its type. Unknown carries that
state explicitly, with a linear recovery obligation.

Distinguishing Paid, Unpaid, and Uncertain prevents a caller from using the same
cleanup on incompatible evidence. Unknown must not become Err merely because a
deadline expired or an unqualified lookup returned NotFound.

Why nets describe resources
---------------------------------

Nets make atomic resource transfers, shared-state prerequisites, registrations,
and cancellation paths visible. Their incidence matrix supports a narrow,
auditable conservation argument. Coloured inscriptions preserve identity that
aggregate arithmetic loses.

Encoding every ordinary list operation or pure recursive call as a business
resource net would complicate that model without automatically proving the
algorithm correct. The separate pure-computation brief therefore uses immutable
data/functions and scoped task semantics. Its scheduler needs its own contracts;
Inventory's certificate cannot certify merge sort or fork/join.

Why closed nominal outcomes
---------------------------------

A closed enum names the obligations a caller must handle and gives exhaustive
matching a fixed target. Implicit structural unions and widening can obscure
which residual payload must be preserved. An explicit mapping can be designed
later without making today's permit disappear through inference.

Why waiting, rather than an implicit failure
--------------------------------------------------

An empty shared place is a temporary enabling condition in a Petri net. Making
it a generic failure would require a specified result type and recovery contract.
D0 chooses waiting so a call either fires under its stated conditions or remains
pending with ownership intact. The cost is explicit: deadlock and starvation
become possible, and static linearity does not rule them out.

Why evidence and correlation become declarations
------------------------------------------------------

The current payment-specific DSL is a prototype limitation, not proof that
evidence is inherently about payments. A lease needs grant/revocation evidence;
another protocol may require approval/withdrawal. Declared names expose the
trust assumptions without adding a new compiler terminal for every business
domain. Likewise, correlation is an adapter contract selected by name, not a
universally valid client-key/provider-reference recipe.

Why multiple evidence labels
----------------------------------

Accounting proofs, bounded searches, successful type checks, and concrete crash
tests answer different questions. Keeping their labels separate prevents a
strong result in one abstraction from silently supporting a claim in another.
This also makes missing work visible: a perfect conservation proof can coexist
with unsafe authorization, a wrong-order read, or a permanently waiting flow.

