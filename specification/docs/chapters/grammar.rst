Grammar
=============

.. index:: grammar, EBNF

Notation
--------------

Quoted strings are terminals; comma means concatenation; ``|`` means alternatives;
brackets mark optional syntax; braces mark repetition; parentheses group terms;
semicolon terminates a production. EBNF punctuation is not a source character
unless quoted. ``IDENT``, ``UINT``, and ``POSINT`` are lexical classes.

``NL``, ``INDENT``, and ``DEDENT`` follow :doc:`lexical`. Between-token spacing is
omitted; use the canonical examples when targeting the reference parser.

This EBNF also feeds a generated-parser audit. That audit is not a claim of
equivalence to every accepted regex spelling. Static restrictions apply after
parsing. Grammar acceptance alone does not establish a valid program.

Start symbols
-------------------

``n0-file`` selects N0, ``n1-file`` selects N1, and ``flow-file`` selects F0.
SYN-01 requires exactly one start symbol per file. Common declarations refer to places
without indices; N1 inscriptions appear on places, transitions, arcs, and
invariant families.

.. literalinclude:: ../../grammar/weave.ebnf
   :language: text
   :caption: Consolidated portable grammar
   :name: listing-portable-grammar

Precedence
----------------

Only invariant arithmetic has an expression grammar. From highest to lowest:
parenthesized atoms, unary minus, multiplication, addition/subtraction.
Binary arithmetic associates to the left. Equality separates the two sides of
one invariant and cannot be chained.

``?`` is a statement transformation, not a general expression operator.
Calls accept existing binding names, without nested calls or arithmetic.


Centralized static constraints
------------------------------------

The EBNF deliberately recognizes some syntax that static checking rejects.
The following numbered constraints are normative and applied after parsing.

.. _SYN-01:

**SYN-01 — File kind.** A file MUST select exactly one start symbol: N0 net,
N1 net, or F0 flows. A net file contains exactly one net.

.. _SYN-02:

**SYN-02 — Check cardinality.** N0 permits zero or one check block; requesting
ordering analysis requires one. N1 requires exactly one. Multiple syntactically
recognized check blocks MUST be rejected.

.. _SYN-03:

**SYN-03 — Check contents.** A check block MUST have exactly one admission,
dispatch observation and positive place bound, classifications for every used
guard, and at least one ordinary property. N1 additionally requires exactly one
tokens-match-firing property.

.. _SYN-04:

**SYN-04 — Declarations.** A net MUST contain places, transitions and aggregate
invariants. Names are unique in their respective namespaces. N1 also has family
invariants and an explicit colour on every transition.

.. _SYN-05:

**SYN-05 — Arcs.** Arc counts MUST be positive; initial counts nonnegative or
the net parameter. Duplicate kind/place arcs are rejected. N1 indexed arcs have
the place's arity and consistent positional sorts.

.. _SYN-06:

**SYN-06 — Scalar parameters.** Indexed scalar spellings recognized by the
type production MUST be rejected. Scalars are unindexed, non-Unit parameters;
resources and enums use their declared arities.

.. _SYN-07:

**SYN-07 — Type indices.** Result indices MUST be bound by parameter identities.
There is no nested generic type, arithmetic index, or implicit equality of two
distinct scalar bindings.

.. _SYN-08:

**SYN-08 — Ownership.** Every activation place MUST have one sealed resource;
every runtime place one closed consumer declaration. API signatures, issuers,
cancellation and foreign outcomes must satisfy the ownership contracts.

.. _SYN-09:

**SYN-09 — Foreign clauses.** Required dispatch, pending, key and correlation
clauses appear once. The outcome enum and transition map MUST have exactly
Ok, Err, Unknown with matching resource identities.

.. _SYN-10:

**SYN-10 — Return interpretation.** A bare return has Unit. In return IDENT,
IDENT MUST resolve as a binding, never as a nullary enum constructor. Parentheses
select a constructor: return Case() requires a Unit payload, and return Case(x)
requires the exact instantiated payload type of the declared result enum.

.. _SYN-11:

**SYN-11 — Enum cases.** Cases MUST be unique and nonempty; each payload is a
resource or Unit. Match tags equal the scrutinee's full declared case set.

.. _SYN-12:

**SYN-12 — Flow control.** Every path MUST explicitly terminate. No statements
follow a return or terminal match. Recursion and shadowing are rejected.

.. _SYN-13:

**SYN-13 — Affine expressions.** Invariant expressions MUST meet their profile's
name, initialization and affine restrictions. Recognizing multiplication in the
grammar does not permit products of variable-bearing expressions.

.. _SYN-14:

**SYN-14 — Calls and propagation.** Operations MUST use await and existing
argument bindings. The grammar permits an omitted await solely so semantic
checking can distinguish sealed-constructor E205 from missing-await E212.
Question-mark forms are checked through F0-TRY-1/2/3.

Generated-parser agreement
--------------------------------

``scripts/grammar_audit.py`` translates this EBNF into a Lark grammar and uses
an independent layout pass and generated Earley parser. It parses each of the
25 corpus inputs (net-append fragments are first attached to their named net).

The reference checker combines parsing and semantic rejection for flows.
Accordingly the comparison is between two **acceptance pipelines**: the generated
syntax front end followed by reference semantics, and the original checker.
All 25 agree on the required acceptance/diagnostic result. The unsupported-if
case is rejected syntactically; semantic negatives parse before rejection.

This is stronger than a manual grammar audit, but it is not a second independent
type checker or a proof of parser equivalence for all inputs. N1 and the lease
example are parsed additionally. Reports include syntax acceptance separately
from semantic outcomes. The N2 delta is explicitly excluded.

