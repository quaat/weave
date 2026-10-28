A smaller protocol: a single-slot lease
=============================================

This example separates reusable resource accounting from the payment-specific
ordering DSL. It is runnable through the existing parser, invariant checker,
and F0 type checker. It makes no grant/revocation evidence claim.

The net
-------------

.. weave-check:: ../../examples/nets/Lease.weave
   :expect: ACCEPT
   :profile: N0
   :caption: N0 structural and accounting subset; no ordering check block

The one free token is the slot. acquire consumes it and produces a sealed
LeaseToken; release and cancellation put it back. Exactly one transition issues
the token type, and the declared API/cancellation routes are its only consumers.
The invariant proves free + leased = 1 for every finite firing sequence.

The net parameter is syntactically required by N0 but unused in this invariant.
Initial capacity is the literal one. The example is not a multi-client identity
proof because its net marking is uncoloured.

A checked client
----------------------

.. weave-check:: ../../examples/valid/lease_roundtrip.weave
   :expect: ACCEPT
   :profile: F0/N0
   :net: ../../examples/nets/Lease.weave

The handle cannot be copied or silently dropped. A second acquisition while
leased is marked is disabled at the net level. Under the D0 waiting decision,
a corresponding runtime call waits; this example does not implement that
scheduler. F0 type checking alone does not reject a flow that waits forever.

The existing boundary becomes visible
-------------------------------------------

The current ordering analyser cannot describe granted/revoked witnesses. Giving
them payment names would be a semantic disguise, not a general solution.
The net intentionally omits a check block; accounting succeeds, while calling
the legacy ordering explorer reports E300 (model absent).

The N2 design adds declared grant/revocation classes, as shown in
:doc:`evidence-design`. That extension is not needed to show token conservation,
but is needed to state domain-appropriate evidence ordering. This example thus
demonstrates both the reusable core and MODEL-04's real limitation.

Reproduce
---------------

``scripts/validate.py`` checks the net, its invariant and the client, and checks
that the absent ordering model reports E300. The generated grammar audit also
parses both files. No payment provider or Inventory net is used for these checks.

