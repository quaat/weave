Lexical structure
=======================

.. index:: lexical structure, indentation, identifier, comment

Source representation
---------------------------

**Editorial portability rule:** use UTF-8 without a byte-order mark, ASCII
identifiers, and LF or CRLF line endings. A final newline is recommended.
Reference CLIs use Python text-file defaults rather than enforcing an encoding
standard. This package's validator explicitly reads UTF-8.

One complete declaration, statement, branch header, or invariant equality
occupies one physical line. There are no semicolon separators, explicit
continuations, strings, or implicit continuation inside brackets.

Whitespace and blocks
---------------------------

.. _LEX-REQ-1:

**LEX-REQ-1.** Each indentation level is exactly four spaces. The first nonblank line is at
level zero. A nested block increases indentation by one level and MUST follow
a line ending in ``:``. Dedentation closes blocks. Tabs are rejected everywhere,
including comments. Blank/comment-only lines do not affect block structure.
Trailing whitespace is ignored.

The grammar's ``NL``, ``INDENT``, and ``DEDENT`` are conceptual tokens; the
reference parser constructs a line tree. Blank lines do not produce ``NL``.

The grammar-driven parsers (:ref:`chapters/grammar:Single source of syntax`) make
these tokens concrete. ``NL`` ends each nonblank line. ``INDENT`` precedes the
first line of a nested block and ``DEDENT`` follows its last line, one for each
level closed, and the end of the file closes every open block. Indentation is
measured in spaces before the first token; a comment-only line has no
indentation in this sense. A dedent always returns to an enclosing level,
because levels are consecutive multiples of four spaces.

Many parser expressions contain literal spaces. Use canonical spacing:
one space between words, no spaces immediately inside parentheses or brackets,
and one space after commas. Some constructs accept extra whitespace; this does
not imply general whitespace insensitivity.

Comments
--------------

``#`` starts a comment through the end of the line. There are no block comments,
documentation comments, or string escapes. Comments disappear during lowering.
A comment may contain any character except a tab or a carriage return that does
not end the line. The concrete syntax tree keeps comments and blank lines as
trivia (:ref:`chapters/grammar:Concrete syntax tree and spans`).

Tokens and line endings
-----------------------------

The EBNF's terminals are tokens. The grammar-driven parsers read source as
follows. This is the reading of the portable rules above, not a new requirement
on the reference parser; where the reference differs, the difference is recorded
in :ref:`chapters/grammar:Reference parser discrepancies` under the open items
LEX-01 to LEX-04 of :doc:`limitations`.

* A line ends at LF or at CRLF. A carriage return elsewhere, including inside a
  comment, is rejected. Python's line splitting also breaks lines at a lone
  carriage return and other separators (LEX-01).
* Spaces separate tokens and are otherwise insignificant. Canonical spacing
  remains the portable form, because the reference parser matches literal spaces
  (LEX-03).
* A word is a maximal run of ASCII letters, digits and ``_``. A word that starts
  with a letter or ``_`` is an identifier or a contextual word
  (:ref:`LEX-REQ-2 <LEX-REQ-2>`). A word that starts with a digit must consist of digits only
  and is an integer token. Adjacent words therefore need a separator:
  ``letx`` is one identifier, not ``let x``.
* ``->``, ``==``, ``<=``, ``>=`` and ``!=`` are single tokens; the other
  punctuation is one character.
* Any other character outside a comment is rejected, including non-ASCII
  letters (LEX-02), the byte-order mark (LEX-01), no-break and other non-ASCII
  spaces, and control characters other than the line ending.
* An integer token with a leading zero other than ``0`` itself matches neither
  ``"0"`` nor ``POSINT``, so the grammar rejects it (LEX-04).

Identifiers and qualification
-----------------------------------

The portable rule is::

   identifier = (ASCII letter | "_"), { ASCII letter | digit | "_" } ;

Names are case-sensitive. No Unicode normalization or case folding is specified.
Some reference patterns use Unicode-aware Python ``\w`` or permit a leading
digit. Those are nonportable parser behaviours.

Qualified operation names contain identifiers separated by dots. A dot is a
name separator, not a general field-access operator; there is no object receiver.

Contextual words
----------------------

.. code-block:: text

   net place owner domain activation runtime adapter
   linear at issuer cancel registered runtime_state consumers terminal
   enum invariant check for one_order orders admit once observe dispatch
   place_bound guard establishes_paid establishes_rejected nondeterministic
   property marked requires paid_evidence rejected_evidence after forbid
   tokens match firing transition take put read runtime_cancel via api foreign
   pending keyed by correlate client_key or provider_reference outcome
   flow let await return
   fn record if else and fork

``Nat`` and ``Unit`` have special roles. ``Ok``, ``Err``, and ``Unknown`` are
required foreign-result tags and are used by propagation lowering.

.. _LEX-REQ-2:

**LEX-REQ-2.** These words are contextual, not globally reserved. They MAY be used in an
identifier position when the production is unambiguous; the reference protocol
uses ``transition dispatch[t, o]:`` and ``dispatch dispatch``. Special type
spellings retain their defined role. This draft reserves no future keywords.

Punctuation
-----------------

Punctuation is ``(``, ``)``, ``[``, ``]``, ``,``, ``:``, ``.``, ``=``,
``->``, ``==``, ``+``, ``-``, ``*``, and ``?``, and, for P0 pure files
(:doc:`pure`), ``<``, ``<=``, ``>``, ``>=`` and ``!=``. Their presence does not
imply a general expression language: only the P0 grammar derives the five P0
tokens, so a flow or net that contains one is rejected as before, with the same
code, now at the syntax stage (:ref:`chapters/grammar:Syntax diagnostics`).

Integer tokens
--------------------

Portable unsigned integers use decimal digits, with zero written ``0`` and
positive values without leading zeroes. Arc multiplicities and exploration
counts are positive; initial counts are nonnegative. Unary minus supplies
negative invariant terms.

There are no flow literals: strings, floats, Booleans, lists, durations, and
integer expressions are unsupported in flows. P0 pure files have integer
literals, list literals and integer expressions (:doc:`pure`). ``Nat`` constrains the net parameter, not
runtime arithmetic. The reference uses arbitrary-precision Python integers for
accounting. Host numeric forms incidentally accepted by the invariant AST reader,
such as hexadecimal integers, are outside the portable grammar.

