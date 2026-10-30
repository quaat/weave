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

Static restrictions apply after parsing. Grammar acceptance alone does not
establish a valid program.

Single source of syntax
-----------------------------

``grammar/weave.ebnf`` is the one definition of portable syntax. Three consumers
read the same file, and none keeps a copy:

* this chapter shows it with ``literalinclude`` (:ref:`listing-portable-grammar`);
* the Rust parser in ``crates/weave-syntax`` (the first slice of the Rust
  implementation, decision record ``docs/decisions/0009-rust-implementation.md``)
  embeds the file when it is built and interprets it. There is no generated code
  and no build script, and the concrete syntax tree's node kinds are the
  production names;
* ``scripts/grammar_audit.py`` translates it into a Lark grammar for an
  independent generated parser (`Generated-parser agreement`_).

``grammar/weave-n2-delta.ebnf`` is a target-only delta. No parser reads it; the
Rust normalisation tests read it as EBNF and resolve its names against the base
grammar. A change to the grammar is therefore a change to all three consumers,
and the checks below fail if they disagree on the corpus.

Ordered-choice reading and normalisation
------------------------------------------------

The EBNF is a context-free grammar. The Rust parser reads it as an ordered
choice: the alternatives of ``|`` are tried in order, each from the same position;
options ``[ ]`` and repetitions ``{ }`` take their body whenever it matches.
The two readings agree only for grammars without ordered-choice hazards, so a
normalisation check runs whenever the grammar is loaded, and the parser refuses a
grammar that fails it. The check covers:

* **Structure.** No production is defined twice; every referenced name is
  defined; every production is reachable from a start symbol; a special sequence
  is the whole body of a production named after a lexer token (``IDENT``,
  ``POSINT``, ``NL``, ``INDENT``, ``DEDENT``); every quoted terminal is exactly
  one lexer token; no production is left-recursive; and no option or repetition
  body can match the empty string.
* **Choices.** No two alternatives of a choice can both match a prefix of the
  same token sequence. In particular, no alternative is shadowed by an earlier
  alternative that matches a prefix of it.
* **Options and repetitions.** The body cannot match a prefix of input on which
  the continuation after the option or repetition could also start. The
  continuation is followed through every use of the enclosing production up to
  the end of the file.

Both ordered-choice checks compare token classes with up to eight tokens of
lookahead. An identifier counts as possibly equal to every identifier-shaped
terminal, because contextual words are not reserved (:ref:`LEX-REQ-2 <LEX-REQ-2>`). The
current grammar needs at most five tokens. When the checks pass, an
ordered-choice parse succeeds exactly when the EBNF derives the input, and it
builds that derivation: at each choice at most one alternative can match, and a
greedy step never takes tokens that a derivation would leave to what follows.
The check is sufficient, not necessary. It can reject a grammar on which ordered
choice happens to be correct, and alternatives that stay alike for eight tokens
are reported instead of being assumed different. ``weave-syntax grammar`` prints
the check's report.

**Normalisation applied for quaat/weave#9.** ``let-call`` was written
``"let", IDENT, "=", [ "await" ], call, NL``. Because ``await`` may also name an
operation, ``let x = await()`` is derivable with the option empty, but a greedy
option takes ``await`` and then fails. The check reports this as an option
hazard. The production now reads ``( "await", call | call )``, which is the same
option written as two alternatives (``[ a ], b`` and ``a, b | b`` derive the same
strings), so the language of the EBNF is unchanged. Only the ordered-choice
reading changed, to agree with it. The generated Lark parser accepts
``let x = await()`` before and after the change; the reference checker reports
it as E212 (missing ``await``), a static diagnostic after parsing. No other
production needed a change.

Concrete syntax tree and spans
------------------------------------

The Rust parser builds a concrete syntax tree:

* **Nodes.** Each node is one use of a production, and its kind is the
  production name, such as ``flow``, ``let-call`` or ``UINT``. The lexical
  productions ``IDENT``, ``POSINT``, ``NL``, ``INDENT`` and ``DEDENT`` are token
  leaves, not nodes. A leaf records its lexical class and the grammar symbol that
  matched it. Integer literals stay source text: the parser attaches no host
  integer type to them.
* **Spans.** Every node and every token has a byte span and 1-based line and
  column positions. Columns count characters, and an end column is one past the
  last character, as in ``weave-diagnostic-v1``. A node's span runs from its
  first token to its last and excludes the leading trivia of its first token.
* **Trivia.** Spaces, comments and the line endings of blank or comment-only
  lines are trivia. Each attaches to the token that follows it. Trailing spaces
  and a trailing comment belong to the line's ``NL`` token. ``INDENT`` and
  ``DEDENT`` are zero-width tokens placed directly after the preceding ``NL``,
  before any blank lines. The root node of a start symbol ends with an
  end-of-file leaf that carries the trailing trivia.
* **Round trip.** Printing a tree writes each leaf's trivia and text in order,
  so it reproduces the source byte for byte, including CRLF line endings.
  Re-parsing the printed text gives an equal tree. The Rust tests check this,
  and the span invariants, on every syntactically valid file of the conformance
  corpus; for the syntactically invalid files they check the diagnostic's code,
  rule ID and span instead.
  Normalised printing is the formatter's task (quaat/weave#14).

The syntax layer performs no lowering, so every node maps directly to its source
text. The ``?`` lowering of the reference checker (:doc:`flow-semantics`) is not
part of it, and source maps for lowered forms belong to the IR
(quaat/weave#15).

Syntax diagnostics
------------------------

The Rust parser reports the first fault as one ``weave-diagnostic-v1`` document
with a code from ``diagnostics.json`` and that code's rules
(:doc:`diagnostics`). It uses the reference checker's syntax family and mints no
code:

.. list-table::
   :header-rows: 1
   :widths: 30 12 18 40

   * - Fault
     - Code
     - Stage
     - Principal rule
   * - Tab, indentation not a multiple of four spaces, skipped level, indented
       first line, block after a line not ending in ``:``
     - E001
     - ``layout``
     - :ref:`LEX-REQ-1 <LEX-REQ-1>`
   * - Character outside every token, carriage return outside a CRLF ending, a
       word starting with a digit, invalid UTF-8
     - E200 in a flow file, E003 in a net file
     - ``lexical``
     - :ref:`CONF-REQ-1 <CONF-REQ-1>` (E200), :ref:`SYN-04 <SYN-04>` (E003)
   * - Input the grammar does not derive
     - E200 or E003, as above
     - ``syntax``
     - as above
   * - Nesting deeper than the parser's limit (400 productions by default)
     - E200 or E003, as above
     - ``limit``
     - as above

The message names the expected symbols and the token found. The span covers the
offending character or token. The reference checker reports some of the same
faults as E002 (types, brackets and parameter lists) or, in a coloured net,
E400. The audits compare acceptance, not those codes. The nesting limit is an
implementation limit, not a grammar rule: it keeps the parser within a fixed
stack, and the input is not checked further.

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
an independent layout pass and generated Earley parser. Quoted words and numerals
end at a word boundary, as in :doc:`lexical`, so the generated lexer does not
split ``letx`` into ``let x``. The audit parses each of the 27 inputs of
``examples/manifest.json`` (net-append fragments are first attached to their
named net). Layout faults are classed as E001 and other syntax faults as E200 or
E003.

The reference checker combines parsing and semantic rejection for flows.
Accordingly the comparison is between two **acceptance pipelines**: the generated
syntax front end followed by reference semantics, and the original checker.
All 27 agree on the required acceptance/diagnostic result. The unsupported-if and
skipped-level cases are rejected syntactically; semantic negatives parse before
rejection.

The audit also parses every other ``.weave`` file in ``examples/`` (the N0, N1
and lease nets and the lease client), 32 files in all, and requires the
supplementary ones to be accepted. It checks the 22 syntax probes of
`Reference parser discrepancies`_ against their documented verdicts.

**Rust differential.** When ``WEAVE_SYNTAX_BIN`` names the ``weave-syntax``
binary, or ``cargo`` is on ``PATH`` (the audit then builds it with
``cargo build --offline --locked``), the audit runs the Rust parser on the
32 corpus files and the 22 probes. Every verdict must equal the generated
parser's. Every accepted input must round-trip. Where the generated pipeline
gives a syntax code, the Rust code must be the same. Without ``cargo`` and
without the variable, the comparison is skipped and
``validation/grammar-report.json`` records it as not established, never as
agreement.

This is stronger than a manual grammar audit, but it is not a second independent
type checker or a proof of parser equivalence for all inputs. Reports include
syntax acceptance separately from semantic outcomes. The N2 delta is explicitly
excluded.

Reference parser discrepancies
------------------------------------

The reference checker parses with a line tree and regular expressions, not with
this grammar. The probes below compare its syntax verdict with the EBNF read
through :doc:`lexical`. A reference verdict of REJECT means a syntax-family code
(E001, E002, E003 or E200); the EBNF verdict is that of both grammar-driven
parsers. ``scripts/grammar_audit.py`` asserts every verdict in this table, and
``tests/test_grammar_audit.py`` keeps the table equal to the audit's probe list.
Probes ``SD-*`` differ; probes ``SA-*`` agree and guard comments, blank lines and
spacing that both accept or both reject. The differences are instances of the
open portability items LEX-01 to LEX-04 in :doc:`limitations`; recording them
does not decide those items, and the reference snapshot is unchanged.

.. list-table::
   :header-rows: 1
   :widths: 10 54 18 18

   * - Probe
     - Input
     - Reference
     - EBNF
   * - SD-01
     - Extra spaces between tokens of a flow header (LEX-03)
     - REJECT
     - ACCEPT
   * - SD-02
     - No spaces between tokens of a flow header (LEX-03)
     - REJECT
     - ACCEPT
   * - SD-03
     - Two spaces after ``return`` (LEX-03)
     - REJECT
     - ACCEPT
   * - SD-04
     - Spaces inside the parentheses of a propagated call (LEX-03)
     - REJECT
     - ACCEPT
   * - SD-05
     - Two spaces in a place declaration (LEX-03)
     - REJECT
     - ACCEPT
   * - SD-06
     - Spaces inside a net header's parentheses (LEX-03)
     - REJECT
     - ACCEPT
   * - SD-07
     - Non-ASCII identifier; the reference uses Unicode-aware ``\w`` (LEX-02)
     - ACCEPT
     - REJECT
   * - SD-08
     - Flow name starting with a digit (LEX-02)
     - ACCEPT
     - REJECT
   * - SD-09
     - Hexadecimal integer in an invariant, read by the host AST reader (LEX-04)
     - ACCEPT
     - REJECT
   * - SD-10
     - Trailing no-break space; Python strips Unicode whitespace (LEX-01)
     - ACCEPT
     - REJECT
   * - SD-11
     - Trailing form feed (LEX-01)
     - ACCEPT
     - REJECT
   * - SD-12
     - Carriage return alone as a line break; Python ``splitlines`` (LEX-01)
     - ACCEPT
     - REJECT
   * - SA-01
     - Comment after a block header
     - ACCEPT
     - ACCEPT
   * - SA-02
     - Trailing spaces
     - ACCEPT
     - ACCEPT
   * - SA-03
     - Blank lines at the start of a block
     - ACCEPT
     - ACCEPT
   * - SA-04
     - Comment-only line at an indentation that is not a level
     - ACCEPT
     - ACCEPT
   * - SA-05
     - Tab inside a comment (E001)
     - REJECT
     - REJECT
   * - SA-06
     - Keyword glued to an identifier (``letescrow``)
     - REJECT
     - REJECT
   * - SA-07
     - Spaces inside call parentheses
     - ACCEPT
     - ACCEPT
   * - SA-08
     - Operation named ``await`` without the ``await`` keyword; the reference
       then reports E212, a static diagnostic
     - ACCEPT
     - ACCEPT
   * - SA-09
     - Arc count with a leading zero
     - REJECT
     - REJECT
   * - SA-10
     - Comment after a net header
     - ACCEPT
     - ACCEPT


Portable source avoids every ``SD-*`` form: it uses canonical spacing, ASCII
identifiers, decimal integers and LF or CRLF line endings (:doc:`lexical`).
