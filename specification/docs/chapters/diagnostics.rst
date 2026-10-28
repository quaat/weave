Diagnostics and rejection behaviour
=========================================

.. index:: diagnostic, error code, source location

A rejected source is not executable. Reference diagnostics carry a code,
message, and, when available, a source line. They are fail-fast; the first error
reported need not be the only error. Exact wording and ordering are not stable
language semantics.

.. list-table::
   :header-rows: 1
   :widths: 15 45 40

   * - Code
     - Meaning
     - Typical correction
   * - E001
     - Tab, invalid indentation, skipped level, unexpected block
     - Use four spaces and a valid block header
   * - E002
     - Invalid type, parameter, brackets, or comma list
     - Use nominal types and identifier indices
   * - E003
     - Duplicate/invalid net declaration or unexpected nested content
     - Check declaration grammar and uniqueness
   * - E100
     - Invalid ownership/API/runtime contract
     - Make signatures, issuers, cancellations, and arcs agree
   * - E101
     - Unauthorized resource/runtime consumption or activation read
     - Use only declared consumers; do not bypass sealing
   * - E110
     - Invalid/non-affine invariant
     - Restrict names and integer arithmetic appropriately
   * - E111
     - Initial aggregate invariant mismatch
     - Correct initialization or the intended equality
   * - E112
     - Transition changes an aggregate invariant
     - Correct the transition or revisit the contract explicitly
   * - E200
     - Invalid flow declaration or unsupported statement
     - Use only F0 syntax
   * - E201
     - Wrong call argument count
     - Supply all required arguments, including permits
   * - E202
     - Discarded non-Unit result or resource payload
     - Bind and handle the obligation
   * - E203
     - Use after move or double consumption
     - Transfer each live linear binding once
   * - E204
     - Live linear obligations at normal/propagated return
     - Consume, hand off, or return them on every path
   * - E205
     - Attempt to construct a sealed resource
     - Obtain it from its authorized issuer API
   * - E206
     - Unknown/private operation
     - Use an exported API or same-file helper
   * - E207
     - Unknown argument or return binding
     - Pass existing in-scope names
   * - E208
     - Wrong nominal type, arity, or unresolved call identity
     - Match the operation signature
   * - E209
     - Conflicting identity substitution
     - Use the permit belonging to the requested identity
   * - E210
     - Statement after return
     - Remove unreachable source
   * - E211
     - Binding/payload shadows an existing name
     - Choose a new binding name
   * - E212
     - Operation called without await
     - Use the supported awaited call form
   * - E213
     - Invalid or nonterminal match
     - Match a live enum at the end of the block
   * - E214
     - Missing or extra match cases
     - Cover exactly the declared case set
   * - E215
     - Path lacks explicit termination
     - End with return or exhaustive terminal match
   * - E216
     - Invalid flow signature/index binding
     - Bind result indices and use supported types
   * - E217
     - Return type mismatch
     - Return exactly the declared type
   * - E218
     - Recursive helper cycle
     - Use an acyclic F0 call graph
   * - E219
     - Constructor outside declared result enum
     - Use a case of that result
   * - E300
     - Missing/invalid legacy ordering model
     - Supply the required check declarations
   * - E320
     - Legacy safety counterexample
     - Inspect the trace and repair the protocol
   * - E321
     - Legacy token/state bound exhausted
     - Report NOT ESTABLISHED; review the model and limits
   * - E400
     - Invalid coloured syntax, sorts, or model
     - Preserve colour arity and required declarations
   * - E411
     - Invalid family/aggregate initialization or expression
     - Use valid per-colour or aggregate accounting
   * - E412
     - Nonzero symbolic colour residual
     - Repair per-identity token accounting
   * - E420
     - Coloured safety/correlation/admission violation
     - Inspect the identity-specific counterexample
   * - E421
     - Disabled or ambiguous coloured firing
     - Check marking and firing-mode selection
   * - E422
     - Coloured bound/budget exhausted
     - Report NOT ESTABLISHED, not successful verification

The original CLI sometimes reports a flow error using its net-source argument
as the filename. Some net-projection errors have projected rather than original
line numbers. The documentation validator labels inputs itself; it does not
change the upstream checker. Preserve the full message and selected source when
filing a diagnostic-location issue.

Host I/O errors, invalid CLI usage, and R0 ValueError/AssertionError failures are
not all mapped into E-codes. They must not be described as source-language
exceptions or silently converted into confirmed foreign rejection.

Rule cross-reference
----------------------------

The following maps diagnostic families to stable requirements. It is a navigation
aid, not a new diagnostic precedence rule. The normative corpus gives the required
first diagnostic for its particular inputs in :doc:`conformance`.

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Diagnostic
     - Principal rule
   * - E001–E003
     - :ref:`SYN-01 <SYN-01>`, :ref:`SYN-02 <SYN-02>`, :ref:`LEX-REQ-1 <LEX-REQ-1>`
   * - E100–E101
     - :ref:`SYN-09 <SYN-09>`, :ref:`N0-SEAL-1 <N0-SEAL-1>`
   * - E110–E112
     - :ref:`SYN-10 <SYN-10>`; accounting definitions in :doc:`verification`
   * - E200, E212
     - :ref:`SYN-14 <SYN-14>`, :ref:`F0-BIND-1 <F0-BIND-1>`
   * - E201, E205–E209
     - :ref:`F0-CALL-1 <F0-CALL-1>`, :ref:`F0-CALL-2 <F0-CALL-2>`, :ref:`F0-CALL-3 <F0-CALL-3>`
   * - E202–E204
     - :ref:`F0-UNITCALL-1 <F0-UNITCALL-1>`, :ref:`F0-CALL-2 <F0-CALL-2>`, :ref:`F0-RETURN-1 <F0-RETURN-1>`
   * - E210, E215, E217
     - :ref:`F0-RETURN-1 <F0-RETURN-1>`, :ref:`F0-TAGRETURN-1 <F0-TAGRETURN-1>`, :ref:`SYN-13 <SYN-13>`
   * - E211
     - :ref:`F0-BIND-1 <F0-BIND-1>`, :ref:`F0-MATCH-1 <F0-MATCH-1>`
   * - E213–E214
     - :ref:`F0-MATCH-1 <F0-MATCH-1>`
   * - E216, E218
     - :ref:`F0-SIGNATURE-1 <F0-SIGNATURE-1>`
   * - E219
     - :ref:`F0-TAGRETURN-1 <F0-TAGRETURN-1>`
   * - E300, E320–E321
     - :ref:`N0-ORDER-1 <N0-ORDER-1>`; :doc:`counterexamples`
   * - E400, E411–E412, E420–E422
     - N1 rules in :doc:`net-semantics` and :doc:`verification`;
       :ref:`PROTO-IDENTITY-1 <PROTO-IDENTITY-1>` limits transfer of conclusions

E421 reports the current analyser's disabled/ambiguous firing. It is not a D0
language-level failure outcome: :ref:`D0-AWAIT-1 <D0-AWAIT-1>` instead requires waiting.

