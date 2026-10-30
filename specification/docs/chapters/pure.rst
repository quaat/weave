.. SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
.. SPDX-License-Identifier: MIT

Pure computation (P0)
===========================

.. index:: P0, pure function, fuel, budget, record, list

This chapter defines **P0**, the pure computation profile, in 0.2-draft. P0
programs are files of typed pure functions over immutable integers, Booleans,
lists and records, with arithmetic, comparisons, terminal conditionals and
direct self-recursion bounded by run budgets. It is normative for P0. It adopts
the pure-computation proposal (:doc:`proposals`) with the maintainer's decisions
recorded on quaat/weave#10 and the core decisions of quaat/weave#5
(:doc:`core-decisions`): exact integers with reported budgets (1A), Euclidean
division (D3), decimal literals (L1), faulting partial primitives (E1), a closed
fault set kept apart from budget exhaustion and left-to-right evaluation (2B).

P0 is a new profile, not a change to F0, N0 or N1
(:ref:`chapters/stability:Profile meanings are preserved`). A P0 file is a
separate file kind with its own start symbol, ``pure-file``. F0 flows do not
call P0 functions in this revision: a flow file names only flows and net or
foreign operations, so an F0 checker still rejects any other call (E206), and
an F0, N0 or N1 checker still rejects every P0 construct. P0 has no fork/join,
no higher-order functions, no modules or imports, and no termination checking:
a budget bounds a run, it does not prove that a function terminates.

Implementations: the Rust crates ``crates/weave-check`` (static rules) and
``crates/weave-eval`` (evaluation), with the ``weave`` command of
``crates/weave-cli``; and the independent Python reference evaluator
``scripts/p0_reference.py`` in this specification's tooling. The agent kit's
experimental ``fn`` extension is not P0 (see `Relation to the agent kit`_).

Pure files
----------------

.. _P0-FILE-1:

**P0-FILE-1 — Pure-file syntax.** A P0 file MUST be derived from the start
symbol ``pure-file`` of ``grammar/weave.ebnf`` (:ref:`SYN-01 <SYN-01>`), read
through :doc:`lexical`. In ``name-expr``, the word before a ``prefixed`` part
MUST be ``await``. A lexical fault, input the grammar does not derive, another
word before a ``prefixed`` part, or nesting beyond the limits of
`Nesting limits`_ is reported as E500. Layout faults are E001, as for every
file kind (:ref:`LEX-REQ-1 <LEX-REQ-1>`).

Nesting limits
~~~~~~~~~~~~~~~~~~~~

Both P0 implementations reject, with E500 at stage ``limit``, a file whose
nesting exceeds either of two limits. They are limits of these
implementations, which keep recursion within a fixed stack, not properties of
the grammar; a program within them is portable between the two.

* **Syntax depth** at most **300**: the largest number of nested production
  nodes in the file's derivation tree from ``pure-file``, the root counting 1,
  not counting the lexical productions (``IDENT``, ``UINT``, ``POSINT``,
  ``NL``, ``INDENT``, ``DEDENT``). A parenthesised level costs seven
  productions, so ``return`` with 41 parentheses around a literal is at depth
  300, and a call nested in a call costs ten. The Rust parser's own limit of 400
  productions (:ref:`chapters/grammar:Syntax diagnostics`) is never reached
  first by a derivable file within this limit.
* **Expression depth** at most **256**: a literal has depth 1; ``-e`` one more
  than ``e``; a binary operator one more than its deeper operand; a list
  literal one more than its deepest element; a name with ``k`` dotted parts
  ``k``, plus the depth of its deepest argument (or argument label) if it is a
  call. Parentheses add nothing. A chain of ``n`` operands such as
  ``x + x + ... + x`` has depth ``n``, so at most 256 operands; a flat chain is
  shallow in the syntax tree, so the syntax depth alone would not bound it.

Each implementation checks the syntax depth after parsing and the expression
depth while it builds each expression, before any recursive pass over it.

The P0 productions of the shared grammar are:

.. literalinclude:: ../../grammar/weave.ebnf
   :language: text
   :start-at: (* P0 pure files
   :caption: P0 productions of the portable grammar
   :name: listing-p0-grammar

The grammar recognises ``await`` before a qualified name, qualified calls and
``fork`` blocks only so that static checking can reject them with a specific
rule (`Purity`_), as it recognises an omitted ``await`` in F0
(:ref:`SYN-14 <SYN-14>`). A call argument is written ``expr, [ ":", expr ]``
for the same reason: static checking requires a field name before ``:``
(:ref:`P0-CALL-1 <P0-CALL-1>`).

**Lexical items.** P0 uses the tokens of :doc:`lexical`, plus the punctuation
``<``, ``<=``, ``>``, ``>=`` and ``!=``; the lexer matches the two-character
forms first. These tokens exist in every file kind, but only the P0 grammar
derives them, so F0, N0 and N1 files that contain them are still rejected.
Integer literals are ``UINT``: decimal ASCII digits, ``0`` or without a leading
zero (decision L1, :ref:`LEX-REQ-1 <LEX-REQ-1>`); a negative number is written
with unary minus. The words ``fn``, ``record``, ``let``, ``return``, ``if``,
``else``, ``fork``, ``and``, ``or`` and ``await`` are contextual
(:ref:`LEX-REQ-2 <LEX-REQ-2>`). ``true``, ``false``, ``not`` and the primitives
are built-in names, resolved by static checking; they are not grammar words.
P0 reserves no word.

**Precedence.** From lowest to highest: ``or``; ``and``; comparison;
``+`` and ``-``; ``*``; unary minus; primary expressions (literals, names,
field access, calls, list literals and parenthesised expressions). ``or``,
``and``, ``+``, ``-`` and ``*`` associate to the left. A comparison has at most
one operator: ``a < b < c`` is not derivable (E500). Arithmetic follows the
precedence of invariant expressions (:ref:`chapters/grammar:Precedence`).
Negation is the built-in function ``not(e)``, a primary expression: a prefix
word operator could not be told apart from a call of a function named ``not``
without reserving the word.

.. weave-check::
   :profile: P0
   :expect: ACCEPT
   :caption: A P0 file: a record, arithmetic, conditionals and self-recursion

   record Route:
       dest: Int
       cost: Int

   fn cheapest(routes: List[Route], best: Route) -> Route:
       if is_empty(routes):
           return best
       else:
           let r = head(routes)
           if r.cost < best.cost or r.cost == best.cost and r.dest < best.dest:
               return cheapest(tail(routes), r)
           else:
               return cheapest(tail(routes), best)

   fn average_cost(routes: List[Route], total: Int, count: Int) -> Int:
       if is_empty(routes):
           if count == 0:
               return 0
           else:
               return div(total, count)
       else:
           let r = head(routes)
           return average_cost(tail(routes), total + r.cost, count + 1)

Declarations, names and types
-----------------------------------

A file declares records and functions, in any order. **Built-in names** are the
types ``Int``, ``Bool`` and ``List``, the constants ``true`` and ``false``, and
the primitives ``length``, ``is_empty``, ``head``, ``tail``, ``cons``, ``div``,
``mod`` and ``not``. P0 has a single namespace: types, records, functions,
built-in names and local bindings share it.

.. _P0-DECL-1:

**P0-DECL-1 — Top-level names.** The names of the records and functions of a
file MUST be distinct, and none MAY be a built-in name (E501).

.. _P0-DECL-2:

**P0-DECL-2 — Record fields.** A record declares at least one field (the
grammar requires one), and its field names MUST be distinct (E502).

.. _P0-DECL-3:

**P0-DECL-3 — No recursive records.** No record MAY reach itself through the
types of its fields, directly or through other records or ``List`` (E503).
P0 has no optional type, so a recursive record would have no finite value.

.. _P0-DECL-4:

**P0-DECL-4 — Signatures first.** Every record and every function signature of
the file is in scope in every body, whatever the declaration order. Every
function body is checked, whether or not anything calls it.

.. _P0-TYPE-1:

**P0-TYPE-1 — P0 types.** A type written in a field, a parameter or a result
MUST be ``Int``, ``Bool``, ``List[T]`` with exactly one P0 type ``T``, or the
name of a record of the file without brackets (E504). Every other spelling is
rejected, including indexed nominal types such as ``Hold[t, o]``, ``Nat``,
``Unit`` and undeclared names. Pure code therefore never receives, returns,
constructs or holds a linear handle (:ref:`TYPE-REQ-1 <TYPE-REQ-1>`).
Types are equal when they are the same built-in type, ``List`` types with equal
element types, or the same record (records are nominal, :doc:`types`).

.. _P0-NAME-1:

**P0-NAME-1 — Names in values.** A name used as a value, not called, MUST be a
local binding in scope, optionally followed by field selections, or ``true``
or ``false`` (E505). Functions, records and primitives are not values.

.. _P0-NAME-2:

**P0-NAME-2 — No shadowing.** The name of a parameter or ``let`` binding MUST
differ from every binding in scope, from every top-level name of the file and
from every built-in name; the parameters of one function MUST be distinct
(E506). Parameters are in scope in the whole body. A ``let`` binding is in
scope after its statement, to the end of its block, including nested blocks.
The blocks of ``if`` and ``else`` are separate scopes, so both may bind the
same name.

Static semantics
----------------------

Typing
~~~~~~~~~~~~

An expression either *synthesises* a type or is *checked against* an expected
type. Checking synthesises the type, with the expected type available to
``[]``, list literals and ``cons``, and then requires it to equal the expected
type. The positions that check against a type are: the value of ``return``
(the function's result type), the arguments of a user function (its parameter
types), the fields of a record construction (the field types), the condition
of ``if`` (``Bool``) and the operands named in the table. The value of ``let``
is synthesised.

.. list-table::
   :header-rows: 1
   :widths: 34 66

   * - Expression
     - Typing
   * - integer literal
     - ``Int``
   * - ``true``, ``false``
     - ``Bool``
   * - ``x``, ``x.f``, ``x.f.g``
     - ``x`` is a local binding (field selection applies only to a binding, not to
       a call or a parenthesised expression); each selection applies to a record type that
       declares the field (:ref:`P0-RECORD-2 <P0-RECORD-2>`); the type of the
       last field
   * - ``-e``
     - ``e`` checks against ``Int``; ``Int``
   * - ``e1 + e2``, ``e1 - e2``, ``e1 * e2``
     - both check against ``Int``; ``Int``
   * - ``e1 < e2``, ``<=``, ``>``, ``>=``
     - both check against ``Int``; ``Bool``
   * - ``e1 == e2``, ``e1 != e2``
     - ``e1`` synthesises ``Int`` or ``Bool``; ``e2`` checks against it;
       ``Bool``. Lists and records have no equality.
   * - ``e1 and e2``, ``e1 or e2``
     - both check against ``Bool``; ``Bool``
   * - ``[]``
     - against ``List[T]``: ``List[T]``; against another type: E510; without an
       expected type: E511 (:ref:`P0-TYPE-3 <P0-TYPE-3>`)
   * - ``[e1, ..., en]``
     - against ``List[T]``: each element checks against ``T``. Otherwise
       ``e1`` synthesises ``T`` and the others check against ``T``.
       ``List[T]``
   * - ``f(e1, ..., en)``
     - ``f`` is a function of the file with ``n`` parameters; each ``ei``
       checks against its parameter type; the result type of ``f``
   * - ``R(f1: e1, ..., fn: en)``
     - ``R`` is a record; the fields follow :ref:`P0-RECORD-1 <P0-RECORD-1>`;
       each ``ei`` checks against the type of its field; ``R``
   * - ``length(e)``, ``is_empty(e)``
     - ``e`` synthesises ``List[T]``; ``Int``, ``Bool``
   * - ``head(e)``, ``tail(e)``
     - ``e`` synthesises ``List[T]``; ``T``, ``List[T]``
   * - ``cons(e1, e2)``
     - against ``List[T]``: ``e1`` checks against ``T`` and ``e2`` against
       ``List[T]``. Otherwise ``e1`` synthesises ``T`` and ``e2`` checks
       against ``List[T]``. ``List[T]``
   * - ``div(e1, e2)``, ``mod(e1, e2)``
     - both check against ``Int``; ``Int``
   * - ``not(e)``
     - ``e`` checks against ``Bool``; ``Bool``

.. _P0-TYPE-2:

**P0-TYPE-2 — Types agree.** Every expression in a checking position MUST have
the expected type, every operand the type the table requires, and every list
element the list's element type (E510).

.. _P0-TYPE-3:

**P0-TYPE-3 — Typed empty lists.** ``[]`` MUST appear where a list type is
expected (E511): as a returned value, an argument, a field value, an element of
a list with an expected type, or an argument of ``cons`` that the table
types. ``let xs = []`` and ``length([])`` are rejected.

.. _P0-CALL-1:

**P0-CALL-1 — Calls.** A call target MUST be an unqualified name of a
primitive, a function of the file or a record (E507). Primitives and functions
take positional arguments, exactly as many as they have parameters. A record
takes only named arguments, each named by a plain identifier before ``:``. A
call with a local binding or an unknown name as its target, the wrong number
of arguments, a named argument to a function or primitive, or a positional
argument to a record is rejected.

.. _P0-RECORD-1:

**P0-RECORD-1 — Record construction.** A record construction MUST name every
declared field of the record exactly once and no other field (E508). The
fields may be written in any order.

.. _P0-RECORD-2:

**P0-RECORD-2 — Field access.** A field selection ``.f`` MUST apply to a value
of a record type that declares ``f`` (E509).

Purity
~~~~~~~~~~~~

A P0 function computes a value from its arguments. It cannot touch a handle
(:ref:`P0-TYPE-1 <P0-TYPE-1>`), call a flow, a net API or a foreign operation,
wait, or start concurrent work.

.. _P0-EFFECT-1:

**P0-EFFECT-1 — No operations.** A call whose target is a qualified name, such
as ``Payments.charge(x)``, MUST be rejected (E512): it names a net, foreign or
flow operation. Flow declarations are not ``pure-file`` syntax
(:ref:`P0-FILE-1 <P0-FILE-1>`).

.. _P0-EFFECT-2:

**P0-EFFECT-2 — No waiting.** ``await`` before a qualified name MUST be
rejected (E513). ``await`` before an unqualified call is not derivable (E500).

.. _P0-FORK-1:

**P0-FORK-1 — Sequential.** A ``fork`` block MUST be rejected (E514). P0
evaluation is sequential; fork/join belongs to a later profile.

.. weave-check::
   :profile: P0
   :expect: E512
   :caption: An operation call in pure code is rejected with its span and rule

   fn pay(amount: Int) -> Int:
       return Payments.charge(amount)

Control flow and recursion
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. _P0-PATH-1:

**P0-PATH-1 — Terminal blocks.** Every block (a function body, or the block of
an ``if`` or ``else``) MUST consist of ``let`` statements followed by exactly
one terminal statement: ``return`` or an ``if`` with an ``else``. An ``if``
without ``else``, a statement after a terminal statement, and a block that
ends with ``let`` are rejected (E515). Every path through a function therefore
ends in exactly one ``return``.

.. _P0-REC-1:

**P0-REC-1 — Direct recursion only.** A function MAY call itself. A file MUST
NOT contain two distinct functions each of which calls the other, directly or
through other functions (E516). Calls are those written in the bodies, whether
or not they would run.

Checking order
~~~~~~~~~~~~~~~~~~~~

This order is informative: :doc:`conformance` fixes only the required code of
each corpus case, each of which has one violation. Both P0 implementations
report the first violation found in this order and share the
`Nesting limits`_, so their codes can be compared on any input:

#. syntax and layout (E001, E500), including the nesting limits and the
   prefix word of :ref:`P0-FILE-1 <P0-FILE-1>`;
#. top-level names in file order (E501);
#. records in file order, each field in order: duplicate name (E502), then
   type (E504);
#. recursive records: the first record in file order that reaches itself
   (E503, at its name);
#. function signatures in file order: each parameter's name (E506) and type
   (E504), then the result type (E504);
#. function bodies in file order. First the block structure, walking the
   statements in source order and an ``if``'s blocks before what follows it
   (E514, E515). Then the statements in order and each expression in
   evaluation order (`Evaluation`_): ``await`` (E513), a qualified call (E512),
   the call target, the argument forms and count, the record fields
   (E507, E508), then the arguments; a ``let`` value before its name (E506);
#. mutual recursion: the first function in file order on a cycle, at its first
   call in source order to another function of the cycle (E516).

Result
~~~~~~~~~~~~

When a file satisfies every static rule, a checker states one claim for the
file with the result label **CHECKED pure**: P0 type, effect, path and
recursion-shape checks passed for every function of the file
(:doc:`verification`). The label says nothing about termination, faults or
budgets. A P0 file is not a flow, so it never receives CHECKED flow.

Dynamic semantics
-----------------------

A run evaluates one function of a checked file, the *entry*, on arguments
given as JSON (:ref:`P0-RUN-1 <P0-RUN-1>`), under three budgets
(`Budgets`_). Its outcome is exactly one of a value, a pure fault or an
exhausted budget.

Values
~~~~~~~~~~~~

.. _P0-VALUE-1:

**P0-VALUE-1 — Values.** A value of type ``Int`` is a mathematical integer,
of ``Bool`` one of ``true`` and ``false``, of ``List[T]`` a finite sequence of
values of type ``T``, and of a record ``R`` one value for each declared field
of ``R``. Values are immutable and have no identity: the only observation of
equality is ``==`` and ``!=`` on ``Int`` and ``Bool``. A list operation never
copies or changes another list; an implementation may share list suffixes.

Evaluation
~~~~~~~~~~~~~~~~

.. _P0-EVAL-1:

**P0-EVAL-1 — Left to right.** Statements run in order. ``let`` evaluates its
value and binds the name; ``return`` evaluates its value and ends the call
with it; ``if`` evaluates its condition and then runs exactly one of its two
blocks. Within an expression, the operands of a binary operator are evaluated
left before right (except as :ref:`P0-EVAL-2 <P0-EVAL-2>` states), the
arguments of every call and the fields of a record construction in the order
written, and the elements of a list literal from left to right. A field
selection evaluates the value it selects from. The value of a run, or its first
fault, is that of this sequential order (decision 2B).

.. _P0-EVAL-2:

**P0-EVAL-2 — Short circuit.** ``e1 and e2`` evaluates ``e1``; if it is
``false`` the result is ``false`` and ``e2`` is not evaluated, otherwise the
result is the value of ``e2``. ``e1 or e2`` evaluates ``e1``; if it is
``true`` the result is ``true`` and ``e2`` is not evaluated, otherwise the
result is the value of ``e2``. An operand that is not evaluated calls no
function, uses no budget and raises no fault.

.. _P0-EVAL-3:

**P0-EVAL-3 — Calls.** A call of a function of the file evaluates its
arguments, then takes one unit of fuel (:ref:`P0-BUDGET-2 <P0-BUDGET-2>`)
and then an active-call slot (:ref:`P0-BUDGET-3 <P0-BUDGET-3>`), binds the
parameters to the argument values and runs the body; the value of the ``return`` that ends the
body is the value of the call. The entry is called the same way, with the
run's arguments. Primitive calls and record constructions are not function
calls and use neither fuel nor depth.

Arithmetic and lists
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. _P0-ARITH-1:

**P0-ARITH-1 — Exact integers.** ``+``, ``-``, ``*`` and unary minus are the
operations of the mathematical integers, and ``<``, ``<=``, ``>`` and ``>=``
their order. ``==`` and ``!=`` compare two integers or two Booleans. No result
is wrapped, saturated or approximated; an integer outside the size budget
ends the run with exhaustion (:ref:`P0-BUDGET-4 <P0-BUDGET-4>`), never with a
host error (decision 1A).

.. _P0-ARITH-2:

**P0-ARITH-2 — Euclidean division.** If ``d`` is zero, ``div(a, d)`` and
``mod(a, d)`` raise the fault ``division-by-zero`` (E520). Otherwise they
return the unique ``q`` and ``r`` with ``a = d * q + r`` and
``0 <= r < abs(d)`` (decision D3): ``div`` returns ``q`` and ``mod`` returns
``r``. Neither Python's floor division nor Rust's truncating division is this
operation for every sign.

.. list-table::
   :header-rows: 1
   :widths: 25 25 25 25

   * - ``a``, ``d``
     - ``div(a, d)``
     - ``mod(a, d)``
     - check
   * - ``7``, ``2``
     - ``3``
     - ``1``
     - ``2 * 3 + 1``
   * - ``-7``, ``2``
     - ``-4``
     - ``1``
     - ``2 * -4 + 1``
   * - ``7``, ``-2``
     - ``-3``
     - ``1``
     - ``-2 * -3 + 1``
   * - ``-7``, ``-2``
     - ``4``
     - ``1``
     - ``-2 * 4 + 1``

.. _P0-LIST-1:

**P0-LIST-1 — List primitives.** ``length(xs)`` is the number of elements of
``xs``; ``is_empty(xs)`` is ``true`` exactly when it is zero; ``head(xs)`` is
the first element; ``tail(xs)`` is ``xs`` without its first element;
``cons(x, xs)`` is ``x`` followed by the elements of ``xs``; ``[e1, ..., en]``
is the values of ``e1`` to ``en`` in order. ``head`` and ``tail`` of an empty
list raise the fault ``empty-list`` (E521); there is no default value
(decision E1).

.. _P0-FAULT-1:

**P0-FAULT-1 — Pure faults.** The faults of P0 are exactly
``division-by-zero`` and ``empty-list``. A fault ends the whole run: P0 has no
handler, the run has no value, and the fault is reported with its code, rule
and the span of the primitive call that raised it. Budget exhaustion is not a
fault (decision 2B).

.. weave-check::
   :profile: P0
   :expect: ACCEPT
   :caption: Accepted statically; a run of mean on [] raises division-by-zero (E520) at the div call

   fn total(xs: List[Int]) -> Int:
       if is_empty(xs):
           return 0
       else:
           return head(xs) + total(tail(xs))

   fn mean(xs: List[Int]) -> Int:
       return div(total(xs), length(xs))

Budgets
-------------

.. _P0-BUDGET-1:

**P0-BUDGET-1 — Run budgets.** Every run has three budgets, nonnegative
integers given as run parameters: **fuel** ``F``, **depth** ``D`` and
**integer size** ``B`` in bits. A tool supplies defaults for those not given,
and reports all three, with what the run used of each, whatever the outcome.
Usage is the number of calls that took fuel (a call that then exceeds the
depth budget counts), the largest number of calls active at once, and the
largest bit length of an integer admitted. Budgets bound calls, depth and
integer size, not memory or time (:doc:`limitations`). A run that exceeds a
budget ends with the outcome *exhausted* and that budget's kind (``fuel``,
``depth`` or ``int-size``). Exhaustion is not a fault and is not a value: it
says nothing about whether the program would terminate, fault or return with a
larger budget.

.. _P0-BUDGET-2:

**P0-BUDGET-2 — Fuel.** Each call of a function of the file, the entry call
included, takes one unit of fuel before it runs. If ``F`` calls have already
taken fuel, the call takes none, does not run, and the run ends with fuel
exhaustion (E530) at the span of the call (for the entry call, the entry
function's name). Fuel counts calls, so the exhaustion point is the same in
every implementation. With no loops, a call does a bounded amount of work, so
every non-terminating P0 run exhausts fuel or depth.

.. _P0-BUDGET-3:

**P0-BUDGET-3 — Depth.** A call is active from the moment it takes its slot
until its ``return``. If, after the call has taken its fuel, ``D`` calls are
already active, the call takes no slot, does not run, and the run ends with
depth exhaustion (E531) at the span of the call.

.. _P0-BUDGET-4:

**P0-BUDGET-4 — Integer size.** The size of an integer is the bit length of
its magnitude: 0 for zero, otherwise ``floor(log2(abs(n))) + 1``. An integer
is admitted only if its size is at most ``B``. Before the entry call, every
integer in the run's arguments is checked. During evaluation, every integer an
expression produces is checked: a literal, unary minus, ``+``, ``-``, ``*``,
``div``, ``mod`` and ``length``. Otherwise the run ends with integer-size
exhaustion (E532) at the span of the expression, or of the entry function's
name for an argument.

.. weave-check::
   :profile: P0
   :expect: ACCEPT
   :caption: Accepted statically; a run of spin ends with fuel exhaustion (E530)

   fn spin(n: Int) -> Int:
       return spin(n + 1)

The ``weave`` command's defaults are fuel 1,000,000 calls, depth 10,000 active
calls and integers of 65,536 bits; the reference evaluator uses the same.
They are tool defaults, not part of P0, and every report names the values used.

Runs
----------

.. _P0-RUN-1:

**P0-RUN-1 — Run request.** A run names a function of a checked file and gives
a JSON array with one value per parameter. An ``Int`` is a JSON number written
as an integer, without fraction or exponent; a ``Bool`` is ``true`` or
``false``; a ``List[T]`` is an array of ``T``; a record is an object with each
declared field exactly once and no other member. An unknown function, a wrong
number of arguments or a value of another shape is an invalid request (E540):
nothing is evaluated and no budget is used. The integer-size check of the
arguments (:ref:`P0-BUDGET-4 <P0-BUDGET-4>`) follows a valid decoding.

.. _P0-RUN-2:

**P0-RUN-2 — Run report.** A run reports exactly one outcome: a value, encoded
as JSON (an ``Int`` as a JSON integer of any size, a ``Bool`` as ``true`` or
``false``, a list as an array, a record as an object with its fields in
declaration order); a fault, with its kind and its E52x diagnostic; or an
exhausted budget, with its kind and its E53x diagnostic. The report also gives
the budgets and their usage (:ref:`P0-BUDGET-1 <P0-BUDGET-1>`). A run's
outcome is runtime status, not evidence; a run whose outcome is compared with
an asserted expectation, as in the conformance corpus, is a scripted scenario
(SCRIPTED / passed scenario).

Diagnostics
-----------------

Every P0 diagnostic is a ``weave-diagnostic-v1`` document with a code from
``diagnostics.json``, the code's principal rule and a source span
(:doc:`diagnostics`). Static diagnostics have the stage ``static``, syntax
diagnostics ``lexical``, ``syntax`` or ``limit``, run-time faults and
exhaustion ``runtime``, and invalid run requests ``run``.

.. list-table::
   :header-rows: 1
   :widths: 12 22 66

   * - Code
     - Principal rule
     - Condition
   * - E500
     - :ref:`P0-FILE-1 <P0-FILE-1>`
     - Lexical or grammar fault in a pure file, nesting limit, or a word other
       than ``await`` before a qualified name
   * - E501
     - :ref:`P0-DECL-1 <P0-DECL-1>`
     - Duplicate or built-in top-level name
   * - E502
     - :ref:`P0-DECL-2 <P0-DECL-2>`
     - Duplicate field in a record
   * - E503
     - :ref:`P0-DECL-3 <P0-DECL-3>`
     - Recursive record
   * - E504
     - :ref:`P0-TYPE-1 <P0-TYPE-1>`
     - Type outside P0, including handles
   * - E505
     - :ref:`P0-NAME-1 <P0-NAME-1>`
     - Unknown name, or a function, record or primitive used as a value
   * - E506
     - :ref:`P0-NAME-2 <P0-NAME-2>`
     - Shadowing or duplicate parameter
   * - E507
     - :ref:`P0-CALL-1 <P0-CALL-1>`
     - Unknown call target, wrong argument count or form
   * - E508
     - :ref:`P0-RECORD-1 <P0-RECORD-1>`
     - Record construction without every field exactly once
   * - E509
     - :ref:`P0-RECORD-2 <P0-RECORD-2>`
     - Field access on a non-record or of an undeclared field
   * - E510
     - :ref:`P0-TYPE-2 <P0-TYPE-2>`
     - Type mismatch
   * - E511
     - :ref:`P0-TYPE-3 <P0-TYPE-3>`
     - ``[]`` without an expected list type
   * - E512
     - :ref:`P0-EFFECT-1 <P0-EFFECT-1>`
     - Qualified (operation) call
   * - E513
     - :ref:`P0-EFFECT-2 <P0-EFFECT-2>`
     - ``await``
   * - E514
     - :ref:`P0-FORK-1 <P0-FORK-1>`
     - ``fork``
   * - E515
     - :ref:`P0-PATH-1 <P0-PATH-1>`
     - Block not ending in a terminal statement, ``if`` without ``else``, or a
       statement after a terminal statement
   * - E516
     - :ref:`P0-REC-1 <P0-REC-1>`
     - Mutual recursion
   * - E520
     - :ref:`P0-ARITH-2 <P0-ARITH-2>`
     - Fault ``division-by-zero``
   * - E521
     - :ref:`P0-LIST-1 <P0-LIST-1>`
     - Fault ``empty-list``
   * - E530
     - :ref:`P0-BUDGET-2 <P0-BUDGET-2>`
     - Fuel exhausted
   * - E531
     - :ref:`P0-BUDGET-3 <P0-BUDGET-3>`
     - Depth exhausted
   * - E532
     - :ref:`P0-BUDGET-4 <P0-BUDGET-4>`
     - Integer size exhausted
   * - E540
     - :ref:`P0-RUN-1 <P0-RUN-1>`
     - Invalid run request

Source mapping
--------------------

Each implementation lowers the parse tree to an abstract syntax tree and then
to a typed program; the Rust evaluator lowers that further to a flat
instruction list. Every node and instruction keeps the span of the source text
it comes from, so a static diagnostic, a fault and an exhaustion point to
source, never to a generated form. The intermediate representation of
quaat/weave#15 is not part of P0.

Implementations and evidence
----------------------------------

**Rust.** ``weave check FILE`` prints ``CHECKED pure FILE: f, g, ...`` and
exits 0, or prints the first diagnostic and exits 1.
``weave run FILE --entry NAME --args JSON [--fuel N] [--max-depth N]
[--int-bits N]`` checks the file and then runs it, printing the outcome and
the budgets; it exits 0 for a value, 3 for a fault and 4 for exhaustion, 1
for a rejected file or an invalid request, and 70 for an internal error of
the implementation, which is never reported as a rejection. ``--json`` prints one JSON object
with the claims, the outcome, the budgets and ``weave-diagnostic-v1``
diagnostics. Calls use an explicit frame stack, never the host stack; integers
use an arbitrary-precision implementation in the crate; neither crate panics
for a Weave outcome.

**Python reference.** ``scripts/p0_reference.py`` parses with the Lark parser
that ``scripts/grammar_audit.py`` generates from ``grammar/weave.ebnf``, and
checks and evaluates from this chapter, independently of the Rust code.
``python3 scripts/p0_reference.py check FILE`` and
``python3 scripts/p0_reference.py run FILE --entry NAME --args JSON`` mirror
the ``weave`` command.

**Differential.** ``scripts/p0_differential.py``, part of
``make validate-offline``, runs both implementations on the P0 corpus
(``examples/pure/manifest.json``), on seeded generated programs and inputs,
and on inputs just under and just over the `Nesting limits`_, and requires
equal static codes, outcome kinds, values, fault and exhaustion
kinds and budget usage. When ``cargo`` is not on ``PATH`` and
``WEAVE_BIN`` does not name the ``weave`` binary, the comparison is recorded as
not established in ``validation/p0-differential.json``, never as agreement.
Agreement of two implementations is regression evidence on the inputs
compared, not a proof that either follows this chapter for every input.

Relation to the agent kit
-------------------------------

The agent kit's experimental ``fn`` extension (``agent-kit/docs/weave.md``) is
unchanged and is not P0; its ``P4xx`` codes and ``KIT-PURE-*`` rules stay
kit-only, and its migration to P0 is a follow-up. P0 differs from it in these
respects: P0 accepts only ASCII identifiers and decimal literals without
leading zeros, with negative numbers from unary minus; reserves no words; has
arithmetic, ``div`` and ``mod``, all six comparisons, ``and``, ``or`` and
``not``, records and ``List[T]`` for every P0 type, but no ``IntListPair``,
``split_half``, ``first`` or ``second``; rejects ``fork``; counts fuel in calls,
not instructions; has an integer-size budget; and reports faults and
exhaustion as separate outcome classes at the span of the expression.
