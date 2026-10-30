Conformance appendix
========================

This appendix and ``examples/manifest.json`` are normative for the listed
profiles. They define a minimum compatibility corpus, not the entire language.
Illustrative commentary remains informative.

.. _CONF-CASE-1:

**CONF-CASE-1.** A checker claiming this corpus MUST accept each ACCEPT case and
reject each negative case with its required diagnostic code. Full wording and
error ordering outside these exact inputs are not standardized. A checker may
add diagnostics, but must preserve the primary required code for these cases.

Files are relative to ``examples/``. F0/N0 uses ``nets/Inventory.weave``.
For ``net_append``, append the fragment inside that net before checking.
Net cases run structure, accounting and then ordering; flow cases check F0.
These stage requirements prevent an accounting-only pass from masking E320.

.. list-table::
   :header-rows: 1
   :widths: 8 35 12 12 33

   * - ID
     - File / kind
     - Profile
     - Required result
     - Rules
   * - C001
     - ``valid/return_hold.weave`` (flow)
     - F0/N0
     - ACCEPT
     - :ref:`F0-BIND-1 <F0-BIND-1>`
   * - C002
     - ``valid/arm_hold.weave`` (flow)
     - F0/N0
     - ACCEPT
     - :ref:`F0-BIND-1 <F0-BIND-1>`
   * - C003
     - ``valid/finish_paid.weave`` (flow)
     - F0/N0
     - ACCEPT
     - :ref:`F0-BIND-1 <F0-BIND-1>`
   * - C004
     - ``valid/settle.weave`` (flow)
     - F0/N0
     - ACCEPT
     - :ref:`F0-BIND-1 <F0-BIND-1>`
   * - C005
     - ``valid/propagate_bound.weave`` (flow)
     - F0/N0
     - ACCEPT
     - :ref:`F0-TRY-1 <F0-TRY-1>`, :ref:`F0-TRY-2 <F0-TRY-2>`, :ref:`F0-TRY-3 <F0-TRY-3>`
   * - C006
     - ``valid/checkout.weave`` (flow)
     - F0/N0
     - ACCEPT
     - :ref:`F0-BIND-1 <F0-BIND-1>`
   * - C007
     - ``valid/checkout_composed.weave`` (flow)
     - F0/N0
     - ACCEPT
     - :ref:`F0-BIND-1 <F0-BIND-1>`
   * - C008
     - ``valid/checkout_propagating.weave`` (flow)
     - F0/N0
     - ACCEPT
     - :ref:`F0-TRY-1 <F0-TRY-1>`, :ref:`F0-TRY-2 <F0-TRY-2>`, :ref:`F0-TRY-3 <F0-TRY-3>`
   * - C009
     - ``invalid/direct_charge.weave`` (flow)
     - F0/N0
     - E201
     - :ref:`F0-CALL-1 <F0-CALL-1>`
   * - C010
     - ``invalid/drop_hold.weave`` (flow)
     - F0/N0
     - E204
     - :ref:`F0-RETURN-1 <F0-RETURN-1>`
   * - C011
     - ``invalid/forge_escrow.weave`` (flow)
     - F0/N0
     - E205
     - :ref:`F0-CALL-1 <F0-CALL-1>`
   * - C012
     - ``invalid/wrong_order.weave`` (flow)
     - F0/N0
     - E209
     - :ref:`F0-CALL-2 <F0-CALL-2>`
   * - C013
     - ``invalid/reuse_hold.weave`` (flow)
     - F0/N0
     - E203
     - :ref:`F0-CALL-2 <F0-CALL-2>`
   * - C014
     - ``invalid/missing_unknown.weave`` (flow)
     - F0/N0
     - E214
     - :ref:`F0-MATCH-1 <F0-MATCH-1>`
   * - C015
     - ``invalid/paid_release.weave`` (flow)
     - F0/N0
     - E208
     - :ref:`F0-CALL-2 <F0-CALL-2>`
   * - C016
     - ``invalid/early_return_leak.weave`` (flow)
     - F0/N0
     - E204
     - :ref:`F0-TRY-3 <F0-TRY-3>`, :ref:`F0-RETURN-1 <F0-RETURN-1>`
   * - C017
     - ``invalid/recursion.weave`` (flow)
     - F0/N0
     - E218
     - :ref:`F0-SIGNATURE-1 <F0-SIGNATURE-1>`
   * - C018
     - ``invalid/unsupported_if.weave`` (flow)
     - F0/N0
     - E200
     - :ref:`SYN-14 <SYN-14>`
   * - C019
     - ``mutations/skim.weave`` (net_append)
     - N0
     - E101
     - :ref:`N0-SEAL-1 <N0-SEAL-1>`
   * - C020
     - ``mutations/lose_paid.weave`` (net_append)
     - N0
     - E101
     - :ref:`N0-SEAL-1 <N0-SEAL-1>`
   * - C021
     - ``mutations/bogus_sell.weave`` (net_append)
     - N0
     - E101
     - :ref:`N0-SEAL-1 <N0-SEAL-1>`
   * - C022
     - ``mutations/quick_recover.weave`` (net_append)
     - N0
     - E101
     - :ref:`N0-SEAL-1 <N0-SEAL-1>`
   * - C023
     - ``mutations/leak.weave`` (net_append)
     - N0
     - E101
     - :ref:`N0-SEAL-1 <N0-SEAL-1>`
   * - C024
     - ``mutations/manual_leak.weave`` (net_append)
     - N0
     - E101
     - :ref:`N0-SEAL-1 <N0-SEAL-1>`
   * - C025
     - ``nets/unsafe_paid_release.weave`` (net)
     - N0
     - E320
     - :ref:`N0-ORDER-1 <N0-ORDER-1>`
   * - C026
     - ``valid/commented_blocks.weave`` (flow)
     - F0/N0
     - ACCEPT
     - :ref:`LEX-REQ-1 <LEX-REQ-1>`
   * - C027
     - ``invalid/skipped_level.weave`` (flow)
     - F0/N0
     - E001
     - :ref:`LEX-REQ-1 <LEX-REQ-1>`

Execution scenarios and supplemental evidence
------------------------------------------------

The three manifest scenarios are normative for the legacy scripted simulator's
selected outcomes and asserted markings. They do not confer D0 or R0 conformance.
The validator additionally checks all 9 accepted flows and their lowerings
against N1's API projection.

The lease example requires structural/accounting and F0 acceptance, and E300
when ordering is requested without a check block. The E420 walkthrough uses a
separate coloured-read mutation. These are supplemental regression evidence,
outside the original 25-case baseline.

N2 and D0 have identified normative target rules but no implemented conformance
suite in this delivery. No existing test-pass claim establishes them.

Generated grammar comparison
-----------------------------

The generated parser pipeline agrees on all 27 required outcomes. Its syntax
parser and layout pass are independent; its semantic stage is the reference
checker. This is not independent confirmation of the semantic implementation.
See ``validation/grammar-report.json`` for both stages separately.
