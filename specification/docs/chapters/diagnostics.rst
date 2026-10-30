Diagnostics and rejection behaviour
=========================================

.. index:: diagnostic, error code, source location

A rejected source is not executable. Reference diagnostics carry a code, a
message, a source line and a source span (see `Source spans`_). They are
fail-fast; the first error reported need not be the only error. Exact wording
and ordering are not stable language semantics.

The tables in this chapter are generated from ``diagnostics.json``, the
machine-readable code-to-rule map, by ``scripts/refresh_reference_pages.py``;
``--check`` fails if they drift. A duplicated case tag in a match is reported
as E003 (duplicate declaration), not E214.

.. BEGIN GENERATED: diagnostic-codes

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
     - Duplicate/invalid net declaration, unexpected nested content, or a duplicated match case tag
     - Check declaration grammar and uniqueness; name each match case once
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
     - Missing or undeclared match cases (a case tag written twice reports E003)
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
   * - E500
     - Invalid P0 pure-file syntax: a lexical fault, input the pure-file grammar does not derive, a word other than await before a qualified name, or nesting beyond the parser's limit
     - Use only P0 syntax (fn and record declarations)
   * - E501
     - Duplicate top-level name, or a function or record named like a built-in name
     - Give each function and record a distinct, non-built-in name
   * - E502
     - Duplicate field name in a record declaration
     - Name each field once
   * - E503
     - Recursive record type: a record reaches itself through its field types
     - Remove the cycle; P0 has no recursive records
   * - E504
     - Type outside P0: a handle or other indexed nominal type, an unknown type name, or a malformed List type
     - Use Int, Bool, List[T] or a record declared in the file
   * - E505
     - Unknown name, or a function, record or primitive name used as a value
     - Refer to a parameter, an earlier let binding, true or false
   * - E506
     - Shadowing: a parameter or let binding reuses a name already in scope, a top-level name or a built-in name
     - Choose a fresh name
   * - E507
     - Unknown call target, wrong argument count, or wrong argument form (named and positional arguments)
     - Call a declared function, primitive or record with its arguments
   * - E508
     - Record construction does not name every field exactly once
     - Name every declared field once, and no other
   * - E509
     - Field access on a value that is not a record, or of a field the record does not declare
     - Access a declared field of a record-typed binding
   * - E510
     - Type mismatch in an operand, argument, condition, list element or returned value
     - Make the expression's type match the expected type
   * - E511
     - Empty list literal without an expected list type
     - Use [] where a List type is expected, such as a return or an argument
   * - E512
     - Qualified call in pure code: a net, foreign or flow operation
     - Perform effects in a flow; pure code calls only functions, primitives and records
   * - E513
     - await in pure code
     - Pure code does not wait; move the operation to a flow
   * - E514
     - fork block in pure code
     - P0 is sequential; call the functions one after the other
   * - E515
     - A block does not end in return or a terminal if/else, an if has no else, or a statement follows a return or if
     - End every block with return or with if/else whose blocks both end
   * - E516
     - Mutual recursion: a call cycle through two or more functions
     - Only direct self-recursion is allowed
   * - E520
     - Division or remainder by zero at run time (pure fault)
     - Test the divisor before calling div or mod
   * - E521
     - head or tail of an empty list at run time (pure fault)
     - Test is_empty before head or tail
   * - E530
     - Fuel budget exhausted: too many user-function calls
     - Raise the fuel budget, or check termination; fuel is not a termination proof
   * - E531
     - Depth budget exhausted: too many active function calls
     - Raise the depth budget or reduce recursion depth
   * - E532
     - Integer size budget exhausted: an integer needs more bits than the budget
     - Raise the integer size budget or keep values smaller
   * - E540
     - Invalid run request: unknown entry function, or arguments that do not match its parameters
     - Name a declared function and pass one JSON value of the right type per parameter
   * - E600
     - Invalid modules-1 header syntax: a malformed import declaration, or one after the first declaration, in a module file; or a malformed use net header in a flow file
     - Write imports as 'from a.b import x, y as z', one per line before the first declaration, and the header as 'use net a.b' before the first flow
   * - E601
     - No module file: a module path names no file <root>/a/b.weave under the project root
     - Create the module file, or correct the path; paths resolve from the project root, never from the working directory
   * - E602
     - A module path differs in case from the directory or file names on disk
     - Spell each segment exactly as the directory or file is named
   * - E603
     - A module path leaves the project root once symbolic links are resolved
     - Keep every module, and every directory on its path, inside the project root
   * - E604
     - Import cycle: this import closes a cycle of imports (including a module importing itself); cross-module recursion and record cycles always need one
     - Move the shared declarations into a module that both import
   * - E605
     - No project root: an import in a file read without a project root, or an entry file outside the project root given with --root
     - Give the project root with --root, or check a file inside it
   * - E606
     - An imported name is not a function or record declared in the named module
     - Import a declaration the module declares; imports are selective and there are no wildcards
   * - E607
     - An imported declaration is not marked export in its module
     - Mark the declaration export in its module, or do not import it
   * - E608
     - An import name collides with a built-in name, another import or a declaration of the importing module
     - Rename the import with 'as'; imports never shadow and are never shadowed
   * - E609
     - An exported declaration names, in its signature or field types, a record that is not exported
     - Export the record too, or do not export the declaration
   * - E610
     - A flow's use net header and the --net argument select different nets
     - Drop --net, or make it name the header's net file

.. END GENERATED: diagnostic-codes

The original CLI sometimes reports a flow error using its net-source argument
as the filename. Errors that the erased N0 view of a coloured net reports are
given the coloured source line they came from. The documentation validator
labels inputs itself; it does not change the upstream checker. Preserve the
full message and selected source when filing a diagnostic-location issue.

Host I/O errors, invalid CLI usage, and R0 ValueError/AssertionError failures are
not all mapped into E-codes. They must not be described as source-language
exceptions or silently converted into confirmed foreign rejection.

Source spans
------------------

The reference checker locates each diagnostic against the source text it
checked. The *primary span* is the statement the diagnostic is reported at:
lines and columns are 1-based, and the end column is one past the statement's
last character, without indentation or trailing comment. A diagnostic about a
whole source, such as an empty flow file, has line 0 and a span covering the
whole source. Diagnostics about a net as a whole, such as a net without
invariants, are placed on the net header.

Ownership diagnostics also carry *related spans*, each with a role:

* E204: always ``binding``, the identifier of every linear handle still held,
  where it was bound (a flow parameter, a ``let`` or a match payload); and only
  when the return was generated by ``?``, ``propagation``, the ``?`` itself. An
  E204 at an ordinary ``return`` has no ``propagation`` span;
* E203: always ``binding``, where the reused handle was bound, and always
  ``moved``, where it was consumed. When one call passes the same handle twice,
  ``moved`` is the handle's first argument occurrence in that call.

* E604 (modules-1, :ref:`MOD-CYCLE-1 <MOD-CYCLE-1>`): always ``import``, one
  span for every import of the cycle, each in the file that contains it.

``diagnostics.json`` records these roles for each code (``related_roles``),
marking each as ``always`` or naming its condition.

In a P0 program of several modules (modules-1, :doc:`names`), every span names
the file it is in: a primary or related span may be in an imported module, and a
P0 error or run-time fault inside an imported module keeps its P0 code and is
located there. The modules-1 codes E600 to E619 are for failures specific to
modules (E600 to E610 are used).

The machine-readable form of a diagnostic is the evidence format
``weave-diagnostic-v1`` (``evidence/schemas/diagnostic.v1.schema.json`` in the
repository; :doc:`stability`). It records the code, the category, the principal
rule and secondary rules from ``diagnostics.json``, the severity, the checking
stage, the message, the primary span with its file, the related spans and a
``details`` object. The agent kit's ``--json`` output and the ``weave-check``
directive of this document use it. Spans locate a diagnostic; like wording, they
are not language semantics, and the rule mapping is a navigation aid.

Rule cross-reference
----------------------------

Each code has exactly one principal rule, the requirement its rejection most
directly enforces, and may name secondary rules that some of its messages also
enforce. The map is a navigation aid, not a new diagnostic precedence rule. The
normative corpus gives the required first diagnostic for its particular inputs
in :doc:`conformance`. E210 and E215 map to :ref:`SYN-12 <SYN-12>`, which
states that every path terminates and nothing follows a return; E217 maps to
:ref:`SYN-10 <SYN-10>`, which governs what a return means. E110 to E112 map to
:ref:`SYN-13 <SYN-13>`; the
accounting itself, including preservation by every transition (E112), is
defined in :doc:`verification`, "Aggregate invariants", which has no rule ID of
its own.

.. BEGIN GENERATED: rule-cross-reference

.. list-table::
   :header-rows: 1
   :widths: 12 28 60

   * - Code
     - Principal rule
     - Secondary rules
   * - E001
     - :ref:`LEX-REQ-1 <LEX-REQ-1>`
     - none
   * - E002
     - :ref:`SYN-07 <SYN-07>`
     - :ref:`SYN-04 <SYN-04>`, :ref:`CONF-REQ-1 <CONF-REQ-1>`
   * - E003
     - :ref:`SYN-04 <SYN-04>`
     - :ref:`SYN-01 <SYN-01>`, :ref:`SYN-09 <SYN-09>`, :ref:`SYN-11 <SYN-11>`, :ref:`F0-MATCH-1 <F0-MATCH-1>`, :ref:`CONF-REQ-1 <CONF-REQ-1>`
   * - E100
     - :ref:`SYN-08 <SYN-08>`
     - :ref:`N0-DECL-1 <N0-DECL-1>`, :ref:`N0-DECL-2 <N0-DECL-2>`, :ref:`N0-DECL-3 <N0-DECL-3>`, :ref:`N0-DECL-4 <N0-DECL-4>`, :ref:`N0-DECL-5 <N0-DECL-5>`, :ref:`SYN-04 <SYN-04>`, :ref:`SYN-06 <SYN-06>`, :ref:`SYN-07 <SYN-07>`, :ref:`SYN-09 <SYN-09>`, :ref:`SYN-11 <SYN-11>`
   * - E101
     - :ref:`N0-SEAL-1 <N0-SEAL-1>`
     - :ref:`N0-DECL-3 <N0-DECL-3>`
   * - E110
     - :ref:`SYN-13 <SYN-13>`
     - none
   * - E111
     - :ref:`SYN-13 <SYN-13>`
     - none
   * - E112
     - :ref:`SYN-13 <SYN-13>`
     - :ref:`CONF-REQ-2 <CONF-REQ-2>`
   * - E200
     - :ref:`CONF-REQ-1 <CONF-REQ-1>`
     - :ref:`SYN-01 <SYN-01>`, :ref:`SYN-04 <SYN-04>`, :ref:`SYN-14 <SYN-14>`
   * - E201
     - :ref:`F0-CALL-1 <F0-CALL-1>`
     - none
   * - E202
     - :ref:`F0-UNITCALL-1 <F0-UNITCALL-1>`
     - :ref:`F0-MATCH-1 <F0-MATCH-1>`
   * - E203
     - :ref:`F0-CALL-2 <F0-CALL-2>`
     - :ref:`TYPE-REQ-1 <TYPE-REQ-1>`, :ref:`F0-RETURN-1 <F0-RETURN-1>`, :ref:`F0-MATCH-1 <F0-MATCH-1>`
   * - E204
     - :ref:`F0-RETURN-1 <F0-RETURN-1>`
     - :ref:`F0-TRY-3 <F0-TRY-3>`, :ref:`F0-MATCH-1 <F0-MATCH-1>`
   * - E205
     - :ref:`F0-CALL-1 <F0-CALL-1>`
     - :ref:`TYPE-REQ-1 <TYPE-REQ-1>`, :ref:`SYN-14 <SYN-14>`
   * - E206
     - :ref:`F0-CALL-1 <F0-CALL-1>`
     - none
   * - E207
     - :ref:`F0-CALL-1 <F0-CALL-1>`
     - :ref:`SYN-10 <SYN-10>`, :ref:`SYN-14 <SYN-14>`
   * - E208
     - :ref:`F0-CALL-2 <F0-CALL-2>`
     - :ref:`F0-CALL-1 <F0-CALL-1>`, :ref:`F0-SIGNATURE-1 <F0-SIGNATURE-1>`
   * - E209
     - :ref:`F0-CALL-2 <F0-CALL-2>`
     - none
   * - E210
     - :ref:`SYN-12 <SYN-12>`
     - :ref:`F0-RETURN-1 <F0-RETURN-1>`
   * - E211
     - :ref:`F0-BIND-1 <F0-BIND-1>`
     - :ref:`SYN-12 <SYN-12>`, :ref:`F0-MATCH-1 <F0-MATCH-1>`
   * - E212
     - :ref:`SYN-14 <SYN-14>`
     - :ref:`F0-BIND-1 <F0-BIND-1>`
   * - E213
     - :ref:`F0-MATCH-1 <F0-MATCH-1>`
     - :ref:`SYN-12 <SYN-12>`
   * - E214
     - :ref:`F0-MATCH-1 <F0-MATCH-1>`
     - :ref:`SYN-11 <SYN-11>`
   * - E215
     - :ref:`SYN-12 <SYN-12>`
     - :ref:`F0-MATCH-1 <F0-MATCH-1>`, :ref:`F0-RETURN-1 <F0-RETURN-1>`
   * - E216
     - :ref:`F0-SIGNATURE-1 <F0-SIGNATURE-1>`
     - :ref:`SYN-06 <SYN-06>`, :ref:`SYN-07 <SYN-07>`
   * - E217
     - :ref:`SYN-10 <SYN-10>`
     - :ref:`F0-RETURN-1 <F0-RETURN-1>`, :ref:`F0-TAGRETURN-1 <F0-TAGRETURN-1>`, :ref:`F0-TRY-3 <F0-TRY-3>`
   * - E218
     - :ref:`F0-SIGNATURE-1 <F0-SIGNATURE-1>`
     - :ref:`SYN-12 <SYN-12>`
   * - E219
     - :ref:`F0-TAGRETURN-1 <F0-TAGRETURN-1>`
     - :ref:`SYN-10 <SYN-10>`
   * - E300
     - :ref:`SYN-03 <SYN-03>`
     - :ref:`SYN-02 <SYN-02>`, :ref:`N0-ORDER-1 <N0-ORDER-1>`
   * - E320
     - :ref:`N0-ORDER-1 <N0-ORDER-1>`
     - none
   * - E321
     - :ref:`N0-ORDER-1 <N0-ORDER-1>`
     - :ref:`NET-REQ-1 <NET-REQ-1>`
   * - E400
     - :ref:`N1-COLOUR-1 <N1-COLOUR-1>`
     - :ref:`SYN-01 <SYN-01>`, :ref:`SYN-02 <SYN-02>`, :ref:`SYN-03 <SYN-03>`, :ref:`SYN-04 <SYN-04>`, :ref:`SYN-05 <SYN-05>`
   * - E411
     - :ref:`N1-FAMILY-1 <N1-FAMILY-1>`
     - :ref:`SYN-13 <SYN-13>`
   * - E412
     - :ref:`N1-FAMILY-2 <N1-FAMILY-2>`
     - none
   * - E420
     - :ref:`N1-ORDER-1 <N1-ORDER-1>`
     - :ref:`D0-COLOR-2 <D0-COLOR-2>`
   * - E421
     - :ref:`N1-FIRE-1 <N1-FIRE-1>`
     - :ref:`NET-FIRE-1 <NET-FIRE-1>`
   * - E422
     - :ref:`N1-ORDER-1 <N1-ORDER-1>`
     - :ref:`NET-REQ-1 <NET-REQ-1>`
   * - E500
     - :ref:`P0-FILE-1 <P0-FILE-1>`
     - :ref:`SYN-01 <SYN-01>`
   * - E501
     - :ref:`P0-DECL-1 <P0-DECL-1>`
     - none
   * - E502
     - :ref:`P0-DECL-2 <P0-DECL-2>`
     - none
   * - E503
     - :ref:`P0-DECL-3 <P0-DECL-3>`
     - none
   * - E504
     - :ref:`P0-TYPE-1 <P0-TYPE-1>`
     - :ref:`TYPE-REQ-1 <TYPE-REQ-1>`
   * - E505
     - :ref:`P0-NAME-1 <P0-NAME-1>`
     - none
   * - E506
     - :ref:`P0-NAME-2 <P0-NAME-2>`
     - none
   * - E507
     - :ref:`P0-CALL-1 <P0-CALL-1>`
     - none
   * - E508
     - :ref:`P0-RECORD-1 <P0-RECORD-1>`
     - none
   * - E509
     - :ref:`P0-RECORD-2 <P0-RECORD-2>`
     - none
   * - E510
     - :ref:`P0-TYPE-2 <P0-TYPE-2>`
     - none
   * - E511
     - :ref:`P0-TYPE-3 <P0-TYPE-3>`
     - none
   * - E512
     - :ref:`P0-EFFECT-1 <P0-EFFECT-1>`
     - none
   * - E513
     - :ref:`P0-EFFECT-2 <P0-EFFECT-2>`
     - none
   * - E514
     - :ref:`P0-FORK-1 <P0-FORK-1>`
     - none
   * - E515
     - :ref:`P0-PATH-1 <P0-PATH-1>`
     - none
   * - E516
     - :ref:`P0-REC-1 <P0-REC-1>`
     - none
   * - E520
     - :ref:`P0-ARITH-2 <P0-ARITH-2>`
     - :ref:`P0-FAULT-1 <P0-FAULT-1>`
   * - E521
     - :ref:`P0-LIST-1 <P0-LIST-1>`
     - :ref:`P0-FAULT-1 <P0-FAULT-1>`
   * - E530
     - :ref:`P0-BUDGET-2 <P0-BUDGET-2>`
     - :ref:`P0-BUDGET-1 <P0-BUDGET-1>`
   * - E531
     - :ref:`P0-BUDGET-3 <P0-BUDGET-3>`
     - :ref:`P0-BUDGET-1 <P0-BUDGET-1>`
   * - E532
     - :ref:`P0-BUDGET-4 <P0-BUDGET-4>`
     - :ref:`P0-BUDGET-1 <P0-BUDGET-1>`
   * - E540
     - :ref:`P0-RUN-1 <P0-RUN-1>`
     - none
   * - E600
     - :ref:`MOD-FILE-1 <MOD-FILE-1>`
     - :ref:`SYN-01 <SYN-01>`
   * - E601
     - :ref:`MOD-RESOLVE-1 <MOD-RESOLVE-1>`
     - none
   * - E602
     - :ref:`MOD-RESOLVE-2 <MOD-RESOLVE-2>`
     - none
   * - E603
     - :ref:`MOD-RESOLVE-3 <MOD-RESOLVE-3>`
     - none
   * - E604
     - :ref:`MOD-CYCLE-1 <MOD-CYCLE-1>`
     - none
   * - E605
     - :ref:`MOD-ROOT-1 <MOD-ROOT-1>`
     - none
   * - E606
     - :ref:`MOD-IMPORT-1 <MOD-IMPORT-1>`
     - none
   * - E607
     - :ref:`MOD-IMPORT-2 <MOD-IMPORT-2>`
     - none
   * - E608
     - :ref:`MOD-NAME-1 <MOD-NAME-1>`
     - none
   * - E609
     - :ref:`MOD-EXPORT-1 <MOD-EXPORT-1>`
     - none
   * - E610
     - :ref:`MOD-NET-1 <MOD-NET-1>`
     - none

.. END GENERATED: rule-cross-reference

E421 reports the current analyser's disabled/ambiguous firing. It is not a D0
language-level failure outcome: :ref:`D0-AWAIT-1 <D0-AWAIT-1>` instead requires waiting.

Codes outside the specified fragment
------------------------------------------

The agent kit adds codes that are not language diagnostics. Its pure ``fn``
extension, which lies outside the specified fragment, reports ``P4xx`` codes
whose rules are kit rule IDs defined in the kit's guide (``agent-kit/docs/weave.md``),
not rule IDs of this specification. The kit's pure extension used ``E400`` to
``E427`` until quaat/weave#6; those overlapped the N1 codes here and were moved
to ``P400`` to ``P427`` with the same numbers. ``TOOL_ERROR`` reports a runner
failure outside the checker and has no rule.

.. BEGIN GENERATED: codes-outside-the-fragment

.. list-table::
   :header-rows: 1
   :widths: 14 16 26 44

   * - Code
     - Category
     - Rule
     - Meaning
   * - ``P400``
     - kit-extension
     - ``KIT-PURE-SYNTAX-1``
     - Unsupported or malformed pure syntax, operators, or declarations
   * - ``P401``
     - kit-extension
     - ``KIT-PURE-TYPE-1``
     - Unsupported type, including linear resources, in a pure signature
   * - ``P402``
     - kit-extension
     - ``KIT-PURE-NAME-1``
     - Duplicate declaration or parameter
   * - ``P403``
     - kit-extension
     - ``KIT-PURE-NAME-1``
     - Unknown binding, or a function used as a value
   * - ``P404``
     - kit-extension
     - ``KIT-PURE-NAME-1``
     - Unknown function or primitive
   * - ``P405``
     - kit-extension
     - ``KIT-PURE-CALL-1``
     - Wrong argument count
   * - ``P406``
     - kit-extension
     - ``KIT-PURE-CALL-1``
     - Wrong argument type, including a <= operand
   * - ``P407``
     - kit-extension
     - ``KIT-PURE-PATH-1``
     - Wrong or missing return value
   * - ``P408``
     - kit-extension
     - ``KIT-PURE-PATH-1``
     - Malformed branch: missing else, statements after return or if, or a path without return
   * - ``P409``
     - kit-extension
     - ``KIT-PURE-EFFECT-1``
     - Illegal effect: await, a net or foreign operation, or a flow call
   * - ``P410``
     - kit-extension
     - ``KIT-PURE-EFFECT-1``
     - Flow declared in a pure program
   * - ``P411``
     - kit-extension
     - ``KIT-PURE-RECURSION-1``
     - Mutual or indirect recursion
   * - ``P412``
     - kit-extension
     - ``KIT-PURE-FORK-1``
     - Fork shape or fork-scope violation
   * - ``P413``
     - kit-extension
     - ``KIT-PURE-NAME-1``
     - Rebinding or shadowing
   * - ``P414``
     - kit-extension
     - ``KIT-PURE-TYPE-1``
     - Non-Bool condition
   * - ``P420``
     - kit-extension
     - ``KIT-PURE-RUN-1``
     - head or tail of an empty list at run time
   * - ``P421``
     - kit-extension
     - ``KIT-PURE-LIMIT-1``
     - Fuel budget exhausted
   * - ``P422``
     - kit-extension
     - ``KIT-PURE-LIMIT-1``
     - Call depth limit exceeded
   * - ``P423``
     - kit-extension
     - ``KIT-PURE-LIMIT-1``
     - Live activation limit exceeded
   * - ``P424``
     - kit-extension
     - ``KIT-PURE-ENTRY-1``
     - Entry arguments are not valid JSON of the declared types
   * - ``P425``
     - kit-extension
     - ``KIT-PURE-ENTRY-1``
     - Unknown entry function
   * - ``P426``
     - kit-extension
     - ``KIT-PURE-SCHED-1``
     - Internal scheduler deadlock; never expected
   * - ``P427``
     - kit-extension
     - ``KIT-PURE-SCHED-1``
     - Internal fork/join pairing error; never expected
   * - ``TOOL_ERROR``
     - tool
     - none (not a rule)
     - The agent-kit runner failed outside the checker: unreadable input, invalid usage, a scenario or runtime-model assertion, or a timeout

.. END GENERATED: codes-outside-the-fragment
