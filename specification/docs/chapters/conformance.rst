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

P0 pure files
-------------------

The P0 cases are in ``examples/pure/manifest.json`` (format
``weave-p0-conformance-v1``), apart from ``manifest.json``, whose
``weave-conformance-v1`` readers do not implement their kinds
(:doc:`pure`). A *check* case requires ACCEPT or the code of the first
diagnostic. A *run* case checks the file and calls the entry function with
the given JSON arguments and budgets (others at the tool defaults); it requires
VALUE with the given value, or the code of the fault, exhaustion or invalid
request, and, where a usage is listed, exactly that fuel used, largest depth
and largest integer size. CONF-CASE-1 applies to these cases for P0.
``scripts/validate.py`` checks them with the P0 reference evaluator and
``scripts/p0_differential.py`` compares the Rust ``weave`` command with it.

.. list-table::
   :header-rows: 1
   :widths: 8 40 18 34

   * - ID
     - File / entry and arguments
     - Required result
     - Rules
   * - C101
     - ``pure/valid/arithmetic.weave`` (check)
     - ACCEPT
     - :ref:`P0-FILE-1 <P0-FILE-1>`, :ref:`P0-TYPE-2 <P0-TYPE-2>`, :ref:`P0-PATH-1 <P0-PATH-1>`, :ref:`P0-REC-1 <P0-REC-1>`
   * - C102
     - ``pure/valid/records.weave`` (check)
     - ACCEPT
     - :ref:`P0-DECL-2 <P0-DECL-2>`, :ref:`P0-RECORD-1 <P0-RECORD-1>`, :ref:`P0-RECORD-2 <P0-RECORD-2>`, :ref:`P0-NAME-2 <P0-NAME-2>`
   * - C103
     - ``pure/valid/lists.weave`` (check)
     - ACCEPT
     - :ref:`P0-TYPE-1 <P0-TYPE-1>`, :ref:`P0-TYPE-3 <P0-TYPE-3>`, :ref:`P0-CALL-1 <P0-CALL-1>`
   * - C104
     - ``pure/valid/merge_sort.weave`` (check)
     - ACCEPT
     - :ref:`P0-DECL-3 <P0-DECL-3>`, :ref:`P0-DECL-4 <P0-DECL-4>`, :ref:`P0-REC-1 <P0-REC-1>`
   * - C105
     - ``pure/valid/routing.weave`` (check)
     - ACCEPT
     - :ref:`P0-DECL-1 <P0-DECL-1>`, :ref:`P0-NAME-1 <P0-NAME-1>`, :ref:`P0-EFFECT-1 <P0-EFFECT-1>`
   * - C106
     - ``pure/valid/short_circuit.weave`` (check)
     - ACCEPT
     - :ref:`P0-TYPE-2 <P0-TYPE-2>`
   * - C107
     - ``pure/valid/budgets.weave`` (check)
     - ACCEPT
     - :ref:`P0-REC-1 <P0-REC-1>`
   * - C108
     - ``pure/valid/contextual_words.weave`` (check)
     - ACCEPT
     - :ref:`P0-FILE-1 <P0-FILE-1>`, :ref:`P0-DECL-1 <P0-DECL-1>`, :ref:`P0-NAME-2 <P0-NAME-2>`
   * - C109
     - ``pure/invalid/chained_comparison.weave`` (check)
     - E500
     - :ref:`P0-FILE-1 <P0-FILE-1>`
   * - C110
     - ``pure/invalid/flow_in_pure_file.weave`` (check)
     - E500
     - :ref:`P0-FILE-1 <P0-FILE-1>`
   * - C111
     - ``pure/invalid/builtin_name.weave`` (check)
     - E501
     - :ref:`P0-DECL-1 <P0-DECL-1>`
   * - C112
     - ``pure/invalid/duplicate_field.weave`` (check)
     - E502
     - :ref:`P0-DECL-2 <P0-DECL-2>`
   * - C113
     - ``pure/invalid/recursive_record.weave`` (check)
     - E503
     - :ref:`P0-DECL-3 <P0-DECL-3>`
   * - C114
     - ``pure/invalid/handle_parameter.weave`` (check)
     - E504
     - :ref:`P0-TYPE-1 <P0-TYPE-1>`
   * - C115
     - ``pure/invalid/unknown_name.weave`` (check)
     - E505
     - :ref:`P0-NAME-1 <P0-NAME-1>`
   * - C116
     - ``pure/invalid/shadowing.weave`` (check)
     - E506
     - :ref:`P0-NAME-2 <P0-NAME-2>`
   * - C117
     - ``pure/invalid/wrong_arity.weave`` (check)
     - E507
     - :ref:`P0-CALL-1 <P0-CALL-1>`
   * - C118
     - ``pure/invalid/missing_field.weave`` (check)
     - E508
     - :ref:`P0-RECORD-1 <P0-RECORD-1>`
   * - C119
     - ``pure/invalid/wrong_field.weave`` (check)
     - E509
     - :ref:`P0-RECORD-2 <P0-RECORD-2>`
   * - C120
     - ``pure/invalid/type_mismatch.weave`` (check)
     - E510
     - :ref:`P0-TYPE-2 <P0-TYPE-2>`
   * - C121
     - ``pure/invalid/untyped_empty_list.weave`` (check)
     - E511
     - :ref:`P0-TYPE-3 <P0-TYPE-3>`
   * - C122
     - ``pure/invalid/effect_call.weave`` (check)
     - E512
     - :ref:`P0-EFFECT-1 <P0-EFFECT-1>`
   * - C123
     - ``pure/invalid/await_in_fn.weave`` (check)
     - E513
     - :ref:`P0-EFFECT-2 <P0-EFFECT-2>`
   * - C124
     - ``pure/invalid/fork.weave`` (check)
     - E514
     - :ref:`P0-FORK-1 <P0-FORK-1>`
   * - C125
     - ``pure/invalid/non_terminal_if.weave`` (check)
     - E515
     - :ref:`P0-PATH-1 <P0-PATH-1>`
   * - C126
     - ``pure/invalid/mutual_recursion.weave`` (check)
     - E516
     - :ref:`P0-REC-1 <P0-REC-1>`
   * - C127
     - ``pure/invalid/unused_body_checked.weave`` (check)
     - E510
     - :ref:`P0-DECL-4 <P0-DECL-4>`, :ref:`P0-TYPE-2 <P0-TYPE-2>`
   * - C128
     - ``pure/valid/arithmetic.weave``: ``polynomial(5)``
     - VALUE ``58``
     - :ref:`P0-ARITH-1 <P0-ARITH-1>`, :ref:`P0-RUN-2 <P0-RUN-2>`, :ref:`P0-EVAL-1 <P0-EVAL-1>`
   * - C129
     - ``pure/valid/arithmetic.weave``: ``polynomial(-3)``
     - VALUE ``26``
     - :ref:`P0-ARITH-1 <P0-ARITH-1>`, :ref:`P0-RUN-2 <P0-RUN-2>`
   * - C130
     - ``pure/valid/arithmetic.weave``: ``precedence(2, 5, 3)``
     - VALUE ``11``
     - :ref:`P0-ARITH-1 <P0-ARITH-1>`, :ref:`P0-RUN-2 <P0-RUN-2>`
   * - C131
     - ``pure/valid/arithmetic.weave``: ``quotient(-7, 2)``
     - VALUE ``-4``
     - :ref:`P0-ARITH-2 <P0-ARITH-2>`
   * - C132
     - ``pure/valid/arithmetic.weave``: ``remainder(-7, 2)``
     - VALUE ``1``
     - :ref:`P0-ARITH-2 <P0-ARITH-2>`
   * - C133
     - ``pure/valid/arithmetic.weave``: ``quotient(7, -2)``
     - VALUE ``-3``
     - :ref:`P0-ARITH-2 <P0-ARITH-2>`
   * - C134
     - ``pure/valid/arithmetic.weave``: ``remainder(7, -2)``
     - VALUE ``1``
     - :ref:`P0-ARITH-2 <P0-ARITH-2>`
   * - C135
     - ``pure/valid/arithmetic.weave``: ``quotient(-7, -2)``
     - VALUE ``4``
     - :ref:`P0-ARITH-2 <P0-ARITH-2>`
   * - C136
     - ``pure/valid/arithmetic.weave``: ``remainder(-7, -2)``
     - VALUE ``1``
     - :ref:`P0-ARITH-2 <P0-ARITH-2>`
   * - C137
     - ``pure/valid/arithmetic.weave``: ``quotient(1, 0)``
     - E520
     - :ref:`P0-ARITH-2 <P0-ARITH-2>`, :ref:`P0-FAULT-1 <P0-FAULT-1>`
   * - C138
     - ``pure/valid/arithmetic.weave``: ``remainder(0, 0)``
     - E520
     - :ref:`P0-ARITH-2 <P0-ARITH-2>`, :ref:`P0-FAULT-1 <P0-FAULT-1>`
   * - C139
     - ``pure/valid/arithmetic.weave``: ``reconstructs(-123456789012345678901234567890, 97)``
     - VALUE ``true``
     - :ref:`P0-ARITH-1 <P0-ARITH-1>`, :ref:`P0-ARITH-2 <P0-ARITH-2>`, :ref:`P0-RUN-1 <P0-RUN-1>`
   * - C140
     - ``pure/valid/arithmetic.weave``: ``compare(1, 2)``
     - VALUE ``-1``
     - :ref:`P0-ARITH-1 <P0-ARITH-1>`, :ref:`P0-RUN-2 <P0-RUN-2>`
   * - C141
     - ``pure/valid/arithmetic.weave``: ``ordered(1, 2)``
     - VALUE ``true``
     - :ref:`P0-ARITH-1 <P0-ARITH-1>`, :ref:`P0-RUN-2 <P0-RUN-2>`
   * - C142
     - ``pure/valid/arithmetic.weave``: ``power(2, 100)``
     - VALUE ``1267650600228229401496703205376``
     - :ref:`P0-ARITH-1 <P0-ARITH-1>`, :ref:`P0-VALUE-1 <P0-VALUE-1>`, :ref:`P0-RUN-2 <P0-RUN-2>`
   * - C143
     - ``pure/valid/arithmetic.weave``: ``power(2, 100)`` with int_bits 64
     - E532; usage fuel 101, depth 101, bits 64
     - :ref:`P0-BUDGET-4 <P0-BUDGET-4>`, :ref:`P0-BUDGET-1 <P0-BUDGET-1>`
   * - C144
     - ``pure/valid/records.weave``: ``point(1, 2)``
     - VALUE ``{"x":1,"y":2}``
     - :ref:`P0-VALUE-1 <P0-VALUE-1>`, :ref:`P0-RUN-2 <P0-RUN-2>`
   * - C145
     - ``pure/valid/records.weave``: ``length_squared({"start": {"x": 0, "y": 0}, "finish": {"x": 3, "y": 4}})``
     - VALUE ``25``
     - :ref:`P0-RUN-1 <P0-RUN-1>`, :ref:`P0-EVAL-1 <P0-EVAL-1>`
   * - C146
     - ``pure/valid/records.weave``: ``diagonal(2)``
     - VALUE ``{"start":{"x":0,"y":0},"finish":{"x":...``
     - :ref:`P0-EVAL-3 <P0-EVAL-3>`
   * - C147
     - ``pure/valid/records.weave``: ``mirror({"finish": {"y": 4, "x": 3}, "start": {"x": 0, "y": 0}})``
     - VALUE ``{"start":{"x":3,"y":4},"finish":{"x":...``
     - :ref:`P0-VALUE-1 <P0-VALUE-1>`
   * - C148
     - ``pure/valid/lists.weave``: ``empty_ints()``
     - VALUE ``[]``
     - :ref:`P0-LIST-1 <P0-LIST-1>`
   * - C149
     - ``pure/valid/lists.weave``: ``literal()``
     - VALUE ``[1,5,-4]``
     - :ref:`P0-LIST-1 <P0-LIST-1>`, :ref:`P0-EVAL-1 <P0-EVAL-1>`
   * - C150
     - ``pure/valid/lists.weave``: ``nested()``
     - VALUE ``[[],[1],[2,3]]``
     - :ref:`P0-LIST-1 <P0-LIST-1>`
   * - C151
     - ``pure/valid/lists.weave``: ``first([7, 8])``
     - VALUE ``7``
     - :ref:`P0-LIST-1 <P0-LIST-1>`
   * - C152
     - ``pure/valid/lists.weave``: ``first([])``
     - E521
     - :ref:`P0-LIST-1 <P0-LIST-1>`, :ref:`P0-FAULT-1 <P0-FAULT-1>`
   * - C153
     - ``pure/valid/lists.weave``: ``rest([])``
     - E521
     - :ref:`P0-LIST-1 <P0-LIST-1>`, :ref:`P0-FAULT-1 <P0-FAULT-1>`
   * - C154
     - ``pure/valid/lists.weave``: ``flags([{"tag": 1, "flag": true}, {"tag": 2, "flag": false}])``
     - VALUE ``[true,false]``
     - :ref:`P0-LIST-1 <P0-LIST-1>`, :ref:`P0-RUN-1 <P0-RUN-1>`
   * - C155
     - ``pure/valid/lists.weave``: ``reverse([1, 2, 3], [])``
     - VALUE ``[3,2,1]``
     - :ref:`P0-LIST-1 <P0-LIST-1>`
   * - C156
     - ``pure/valid/lists.weave``: ``sum([1, 2, 3, 4])``
     - VALUE ``10``
     - :ref:`P0-LIST-1 <P0-LIST-1>`
   * - C157
     - ``pure/valid/merge_sort.weave``: ``merge_sort([5, -2, 5, 0, -2])``
     - VALUE ``[-2,-2,0,5,5]``
     - :ref:`P0-EVAL-3 <P0-EVAL-3>`, :ref:`P0-RUN-2 <P0-RUN-2>`
   * - C158
     - ``pure/valid/merge_sort.weave``: ``merge_sort([])``
     - VALUE ``[]``
     - :ref:`P0-EVAL-3 <P0-EVAL-3>`
   * - C159
     - ``pure/valid/merge_sort.weave``: ``sort_items([{"key": 2, "id": 1}, {"key": 1, "id": 2}, {"key": 2, "i..)``
     - VALUE ``[{"key":1,"id":2},{"key":1,"id":4},{"...``
     - :ref:`P0-EVAL-3 <P0-EVAL-3>`, :ref:`P0-VALUE-1 <P0-VALUE-1>`
   * - C160
     - ``pure/valid/routing.weave``: ``route([{"dest": 1, "cost": 5, "hops": 2}, {"dest": 2, "cost": ..)``
     - VALUE ``{"accepted":true,"dest":0,"cost":3}``
     - :ref:`P0-EVAL-2 <P0-EVAL-2>`, :ref:`P0-RUN-2 <P0-RUN-2>`
   * - C161
     - ``pure/valid/routing.weave``: ``route([], 10)``
     - VALUE ``{"accepted":false,"dest":0,"cost":0}``
     - :ref:`P0-RUN-1 <P0-RUN-1>`
   * - C162
     - ``pure/valid/routing.weave``: ``route([{"dest": 1, "cost": 50, "hops": 2}], 10)``
     - VALUE ``{"accepted":false,"dest":0,"cost":0}``
     - :ref:`P0-EVAL-2 <P0-EVAL-2>`
   * - C163
     - ``pure/valid/short_circuit.weave``: ``safe_ratio_above(0, 1)``
     - VALUE ``false``
     - :ref:`P0-EVAL-2 <P0-EVAL-2>`
   * - C164
     - ``pure/valid/short_circuit.weave``: ``safe_ratio_above(3, 30)``
     - VALUE ``true``
     - :ref:`P0-EVAL-2 <P0-EVAL-2>`
   * - C165
     - ``pure/valid/short_circuit.weave``: ``zero_or_divides(0)``
     - VALUE ``true``
     - :ref:`P0-EVAL-2 <P0-EVAL-2>`
   * - C166
     - ``pure/valid/short_circuit.weave``: ``zero_or_divides(7)``
     - VALUE ``false``
     - :ref:`P0-EVAL-2 <P0-EVAL-2>`, :ref:`P0-ARITH-2 <P0-ARITH-2>`
   * - C167
     - ``pure/valid/short_circuit.weave``: ``guarded_head([])``
     - VALUE ``true``
     - :ref:`P0-EVAL-2 <P0-EVAL-2>`, :ref:`P0-LIST-1 <P0-LIST-1>`
   * - C168
     - ``pure/valid/short_circuit.weave``: ``skips_calls(true, 1000)``
     - VALUE ``true``; usage fuel 1, depth 1, bits 10
     - :ref:`P0-EVAL-2 <P0-EVAL-2>`, :ref:`P0-BUDGET-2 <P0-BUDGET-2>`
   * - C169
     - ``pure/valid/short_circuit.weave``: ``skips_calls(false, 3)``
     - VALUE ``true``; usage fuel 5, depth 5, bits 2
     - :ref:`P0-EVAL-2 <P0-EVAL-2>`, :ref:`P0-BUDGET-2 <P0-BUDGET-2>`, :ref:`P0-BUDGET-3 <P0-BUDGET-3>`
   * - C170
     - ``pure/valid/budgets.weave``: ``spin(0)`` with fuel 1000
     - E530; usage fuel 1000, depth 1000, bits 10
     - :ref:`P0-BUDGET-2 <P0-BUDGET-2>`, :ref:`P0-BUDGET-1 <P0-BUDGET-1>`
   * - C171
     - ``pure/valid/budgets.weave``: ``depth(100)`` with depth 50
     - E531; usage fuel 51, depth 50, bits 7
     - :ref:`P0-BUDGET-3 <P0-BUDGET-3>`, :ref:`P0-EVAL-3 <P0-EVAL-3>`
   * - C172
     - ``pure/valid/budgets.weave``: ``depth(100000)`` with depth 200000
     - VALUE ``100000``; usage fuel 100001, depth 100001, bits 17
     - :ref:`P0-BUDGET-3 <P0-BUDGET-3>`
   * - C173
     - ``pure/valid/budgets.weave``: ``doubling(100, 1)`` with int_bits 32
     - E532; usage fuel 32, depth 32, bits 32
     - :ref:`P0-BUDGET-4 <P0-BUDGET-4>`
   * - C174
     - ``pure/valid/budgets.weave``: ``factorial(30)``
     - VALUE ``265252859812191058636308480000000``
     - :ref:`P0-ARITH-1 <P0-ARITH-1>`
   * - C175
     - ``pure/valid/budgets.weave``: ``identity(300)`` with int_bits 8
     - E532; usage fuel 0, depth 0, bits 0
     - :ref:`P0-BUDGET-4 <P0-BUDGET-4>`, :ref:`P0-RUN-1 <P0-RUN-1>`
   * - C176
     - ``pure/valid/budgets.weave``: ``identity("300")``
     - E540
     - :ref:`P0-RUN-1 <P0-RUN-1>`
   * - C177
     - ``pure/valid/budgets.weave``: ``missing()``
     - E540
     - :ref:`P0-RUN-1 <P0-RUN-1>`
   * - C178
     - ``pure/valid/budgets.weave``: ``identity(1.5)``
     - E540
     - :ref:`P0-RUN-1 <P0-RUN-1>`


Generated grammar comparison
-----------------------------

The generated parser pipeline agrees on all 27 required outcomes. Its syntax
parser and layout pass are independent; its semantic stage is the reference
checker. This is not independent confirmation of the semantic implementation.
See ``validation/grammar-report.json`` for both stages separately.
