Building, validating, and maintaining the specification
=============================================================

.. index:: Sphinx, build, validation, documentation maintenance

Sphinx project
--------------------

The editable sources use reStructuredText. Sphinx supplies numbered navigation,
cross-references, general index, glossary, code highlighting, HTML search, and
HTML, text, and PDF builders. HTML uses the Furo theme with ``sphinx-design``,
``sphinx-copybutton``, and accessible Pygments styles; the PDF is typeset with
XeLaTeX and the local ``docs/_latex/weave.sty`` style. A local Pygments lexer highlights Weave; it does not parse
or type-check it. A separate local weave-check extension validates every
displayed implemented Weave example against the unchanged checker. For an
expected rejection it shows the code, its principal rule from ``diagnostics.json``
and the primary span, and records the ``weave-diagnostic-v1`` document in its
build report.

The dependency lock is ``requirements.txt``. It pins Sphinx 8.2.3, Furo, Lark 1.3.1, and the exact
dependency versions used for this build; this is a validated baseline, not a
claim that it is the newest Sphinx release. Python 3.11 or newer is required.

From the package root:

.. code-block:: bash

   python3 -m venv .venv
   . .venv/bin/activate
   python -m pip install -r requirements.txt
   python -m sphinx -n -W --keep-going -b html docs _build/html

On Windows Command Prompt, activate using ``.venv\Scripts\activate``.
The equivalent convenience commands are ``make html`` or ``make.bat html``.

``-n`` checks unresolved cross-references and ``-W`` makes warnings fail the build.
The project does not suppress warning categories. Dependency installation needs
package access; normal builds use local sources without external documentation
inventories or API access.

HTML mathematics uses Sphinx's MathJax rendering. The default renderer loads
MathJax from a CDN when viewed. For fully offline formula rendering, configure
``mathjax_path`` to a locally hosted MathJax distribution. Plain-text output
retains the mathematical notation without requiring JavaScript.

Additional outputs
------------------------

.. code-block:: bash

   python -m sphinx -n -W -b singlehtml docs _build/singlehtml
   python -m sphinx -n -W -b text docs _build/text
   python -m sphinx -M latexpdf docs _build -n -W --keep-going

Build output is not kept under version control. Serve ``_build/html`` with any
static host or open its index locally; publication is not performed by this
package. The PDF is written to ``_build/latex/weave-specification.pdf`` and
needs XeLaTeX, ``latexmk``, ``makeindex``, and the DejaVu font family.
LaTeX warnings are not fatal, so inspect the final ``.log`` as well.

Figures are stored as SVG for HTML with a PDF companion for LaTeX and are
referenced as ``diagram.*``. ``make diagrams`` regenerates both; the PDF step
needs the optional ``cairosvg`` package.

Validation
----------------

.. code-block:: bash

   python scripts/validate.py
   python scripts/test_reference.py
   python scripts/grammar_audit.py
   make validate

The first command verifies source provenance, checks all manifest expectations,
checks accepted F0 files and lowerings against both net API environments, executes
the three legacy outcome scenarios, proves and explores N0/N1, and emits
``validation/report.json`` plus the checkout lowering. It uses the unchanged
reference checker, not a replacement implementation of Weave.

The second command runs the prototype's complete regression suite, including
coloured mutation and durable process-crash cases. The supplied run passes
143 tests. Expected rejection examples are intentional and must not be repaired
merely to make every file accepted.

``python scripts/rule_coverage.py`` regenerates :doc:`rule-coverage` from
``rules.json``, ``examples/manifest.json`` and ``tests/rule-coverage.json``;
``--check`` fails if a rule has no conformance case, test or pending entry, if a
listed test is missing, or if the page is stale. ``tests/test_rule_coverage.py``
runs that check in ``make validate`` and ``make validate-offline``.

Rust crates
-----------------------

The grammar-driven parser is the Rust crate ``crates/weave-syntax`` in the
repository's Cargo workspace (decision record
``docs/decisions/0009-rust-implementation.md``). ``rust-toolchain.toml`` pins
Rust 1.89.0 with ``rustfmt`` and ``clippy``; the crate uses only the standard
library. From the repository root:

.. code-block:: bash

   cargo fmt --all --check
   cargo clippy --all-targets -- -D warnings
   cargo test --all
   cargo run -q -p weave-syntax -- parse --start flow-file specification/examples/valid/checkout.weave
   cargo run -q -p weave-syntax -- roundtrip --start n1-file specification/examples/nets/Inventory.coloured.weave
   cargo run -q -p weave-syntax -- grammar

The tests read ``examples/manifest.json`` and every ``.weave`` file of
``examples/`` in place. They check the round trip and the span invariants on
every syntactically valid file, and the code, rule and span of the diagnostic on
every invalid one. Adversarial tests cover tabs, three- and five-space
indentation, an indented first line, dedents to unknown levels, truncated
files, 10,000 nested parentheses, very long lines, non-ASCII identifiers, NUL
bytes, CRLF and lone carriage returns, invalid UTF-8 and empty files; each must
give a diagnostic or a correct parse, never a panic. ``parse`` prints the
``weave-cst-v1`` tree or a JSON array of ``weave-diagnostic-v1`` diagnostics
(exit 0 or 1), ``roundtrip`` exits 0 exactly when printing reproduces the source
and re-parsing gives an equal tree, and ``grammar`` prints the normalisation
report (:ref:`chapters/grammar:Ordered-choice reading and normalisation`).
Usage and input errors exit 2. The binary is a test and audit driver, not the
user-facing Weave command.

``scripts/grammar_audit.py`` builds the binary with ``cargo build --offline
--locked`` when ``cargo`` is on ``PATH``, or uses the binary named by
``WEAVE_SYNTAX_BIN``, and compares it with the generated parser
(:ref:`chapters/grammar:Generated-parser agreement`). Without either, the
specification's offline validation still passes and the report records the Rust
comparison as not established.

P0 crates
~~~~~~~~~~~~~~~

The P0 profile (:doc:`pure`) adds three crates to the workspace, also standard
library only: ``crates/weave-check`` (static rules, a typed AST with spans),
``crates/weave-eval`` (values, an in-house arbitrary-precision integer,
Euclidean division, an explicit call-frame stack, fuel, depth and
integer-size budgets) and ``crates/weave-cli``, the user-facing ``weave``
command:

.. code-block:: bash

   cargo run -q -p weave-cli -- check specification/examples/pure/valid/routing.weave
   cargo run -q -p weave-cli -- run specification/examples/pure/valid/merge_sort.weave \
       --entry merge_sort --args '[[5, -2, 5, 0, -2]]'
   cargo run -q -p weave-cli -- run specification/examples/pure/valid/budgets.weave \
       --entry spin --args '[0]' --fuel 1000 --json

``check`` prints one ``CHECKED pure`` claim or the first diagnostic; ``run``
also prints the outcome (a value, a fault or an exhausted budget) and every
budget with its usage. Exit status 0 is a checked file or a value, 1 a
rejected file or invalid run request, 2 a usage error, 3 a fault and 4 an
exhausted budget. The tests check every static rule with its code, rule and
span, every P0 corpus case, Euclidean division for every sign, the budgets
(including recursion 300,000 calls deep on a 256 KiB thread stack, integers of
66,000 bits and a list of a million elements), the nesting limits of
:ref:`chapters/pure:Nesting limits` (operator chains of 100,000 operands,
10,000 nested parentheses, 3,000 chained records and list values nested
5,000 deep are limit diagnostics, never a stack overflow, and a value at the
type depth limit is returned, printed and dropped),
renaming and source edits that must change behaviour, and the command's
output. Exit status 70 reports an internal error, never a rejection.

``scripts/p0_reference.py`` is the Python P0 reference evaluator and
``scripts/p0_differential.py`` compares it with the ``weave`` binary, built with
``cargo build --offline --locked`` or named by ``WEAVE_BIN``, on the P0 corpus,
on merge sort against Python ``sorted``, on seeded generated programs and on
inputs at the nesting limits.
Without either, ``validation/p0-differential.json`` records the comparison as
not established. ``tests/test_p0.py`` tests the P0 rules through the reference
and the differential's not-established path.

Conformance applications
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Two ordinary P0 programs serve as conformance applications (quaat/weave#11):
sequential merge sort, ``examples/pure/valid/merge_sort.weave`` (``merge_sort``
on ``List[Int]`` and ``sort_items`` on records with a ``key`` and an ``id``),
and a record-based routing function, ``examples/pure/valid/routing.weave``
(``route``). They use only P0 as specified in :doc:`pure`, and they run with the
ordinary ``weave`` command, without any agent-kit command. From the repository
root:

.. code-block:: bash

   cargo run -q -p weave-cli -- run specification/examples/pure/valid/merge_sort.weave \
       --entry merge_sort --args '[[5, -2, 5, 0, -2]]'
   cargo run -q -p weave-cli -- run specification/examples/pure/valid/merge_sort.weave \
       --entry sort_items --args '[[{"key": 2, "id": 1}, {"key": 1, "id": 2}, {"key": 2, "id": 3}]]'
   cargo run -q -p weave-cli -- run specification/examples/pure/valid/routing.weave \
       --entry route --args '[[{"dest": 1, "cost": 5, "hops": 2}, {"dest": 3, "cost": 3, "hops": 17}], 10]'
   cargo run -q -p weave-cli -- run specification/examples/pure/valid/routing.weave \
       --entry route --args '[[{"dest": 1, "cost": 2}], 10]'

The first three print ``result: [-2,-2,0,5,5]``, ``result:
[{"key":1,"id":2},{"key":2,"id":1},{"key":2,"id":3}]`` and ``result:
{"accepted":true,"dest":1,"cost":5}``, each with exit status 0; the last
request lacks the ``hops`` field and is an invalid run request
(:ref:`P0-RUN-1 <P0-RUN-1>`, with the code :doc:`pure` gives it) at stage
``run``, with exit status 1 and no budget used.

The routing rule, which the oracle below is written from: a route is valid when
``0 <= cost <= limit`` and ``1 <= hops <= 16``; ``route`` accepts the valid
route of least cost, ties going to the lower destination, and returns
``Decision(accepted: false, dest: 0, cost: 0)`` when no route is valid.

``scripts/p0_applications.py`` (in ``make validate-offline``) runs both programs
through ``weave run FILE --entry NAME --args JSON --json`` and through the Python
P0 reference evaluator, and requires both to equal an oracle on every input:

* ``merge_sort`` against Python ``sorted`` on every list of length 0 to 6 over
  {0, 1, 2} (1,093 lists) and on seeded random lists of up to 256 integers,
  including negative integers and integers of up to 200 bits;
* ``sort_items`` against Python's stable ``sorted`` by key, on every key
  sequence of length 0 to 6 over {0, 1, 2} with ids equal to positions and on
  seeded lists of up to 256 items with distinct, shuffled ids. Every id is
  distinct, so the whole output, ids included, shows whether equal keys keep
  their input order: stability is checked observably on these inputs, not
  proved;
* ``route`` against an oracle written from the routing rule above, which does
  not call the reference: named valid and invalid records (negative cost, hops 0
  and negative, hops 16 and 17, cost equal to and one over the limit, a negative
  limit, ties on cost in both orders, an empty list, all routes invalid,
  integers wider than 64 bits), every single route of a boundary grid and
  seeded route lists;
* malformed run requests for all three entry functions (a missing, extra,
  repeated or wrongly typed field, a wrong argument count, an unknown function),
  each of which must be an invalid run request with the code of
  :ref:`P0-RUN-1 <P0-RUN-1>` at stage ``run`` on both sides, with exit status 1
  and no budget used.

Results compared with the Rust side must also agree with the reference on the
outcome and the budget usage. The seed, the input counts, the invalid records
by reason and the Rust status are written to ``validation/p0-applications.json``.
As in the differential, the binary is built with ``cargo build --offline
--locked`` or named by ``WEAVE_BIN``; without either, the reference is still
compared with the oracles and the Rust comparison is recorded as not
established, never as agreement. Any disagreement fails the step. This is
regression evidence on these inputs, not a proof of correctness or stability
for every input. ``tests/test_p0_applications.py`` checks that the harness
fails on a descending sort, on an unstable merge, on four changed routing rules
and on a disagreeing binary. The Rust tests
``crates/weave-eval/tests/applications.rs`` and
``crates/weave-cli/tests/applications.rs`` repeat the exhaustive sets in
process against Rust's stable sort and run the commands above as written.

These applications are sequential. The concurrent fork/join merge sort of the
brief ``agent-kit/claude-code-weave-merge-sort.md`` is not implemented by P0
and is not complete: it is quaat/weave#42, in milestone M6, and fork/join
remains a proposal (:doc:`proposals`). The agent kit's ``merge_sort`` demo runs
on the kit's separate pure extension, not on P0.

For direct reference commands:

.. code-block:: bash

   python reference/prototype/coloured.py analyze examples/nets/Inventory.coloured.weave
   python reference/prototype/coloured.py check examples/nets/Inventory.coloured.weave examples/valid/checkout_propagating.weave
   python reference/prototype/durable.py

The durable demonstration creates temporary local databases and contacts no
external service. To preserve its data, use its documented fresh-directory
option; existing evidence is not overwritten.

Maintenance workflow
--------------------------

#. Select and record the authoritative prototype revision.
#. Read changed parser, checker, runtime, and test contracts before changing prose.
#. Update grammar, semantics, examples, diagnostics, and profile boundaries together.
#. Preserve unknowns as explicit decisions rather than inventing implementation.
#. Run documentation validation and the relevant upstream regressions.
#. Build with warnings treated as errors; inspect rendered long lines, tables,
   navigation, and formulas.
#. Record exact commands and results, update provenance, and package the source
   with generated output.

An incompatible change to syntax, type rules, or protocol semantics requires a
document version change and migration discussion. A clarification should record
its effect in the changelog even when no source changes.

This delivery's validation
--------------------------------

Actual command output and structural checks are in ``validation/BUILD_REPORT.md``
and ``validation/report.json``. Source examples are checked, but the EBNF and
prose are not machine-verified equivalents of the implementation. There is no
claim of a complete language soundness proof.

Sphinx references
-----------------------

* `sphinx-build command reference <https://www.sphinx-doc.org/en/master/man/sphinx-build.html>`_
* `reStructuredText primer <https://www.sphinx-doc.org/en/master/usage/restructuredtext/basics.html>`_
* `Sphinx 8.2.3 release metadata <https://pypi.org/project/Sphinx/8.2.3/>`_

These external references concern documentation tooling, not the definition of
Weave.


Executable documentation and grammar audits
-------------------------------------------------

``weave-check`` requires an expected result and profile on every implemented
Weave block. File examples are checked whole; displayed slices are drawn from
the checked file. Inline net declarations replace the corresponding declarations
in a complete N1 context before validation and accounting. Flow fragments have
explicit result-body or await-body contexts. The body being shown is the body
being checked, not a separately maintained valid copy.

All document sources are re-read on incremental builds too, so a changed checker
or fragment template cannot be hidden by a cached doctree.

The local single-page extension repairs document-local double-fragment links in
the pinned Sphinx build and removes links to absent index/search pages. The
single-page edition uses browser Find. ``scripts/audit_html.py`` checks local
links, assets, anchors and snapshot footers in either HTML edition.

Every build rejects unannotated ``code-block:: weave`` and Weave literalinclude
directives. Target-only N2 examples use clearly labelled text blocks and are
excluded. The builder emits ``weave-check-report.json``. Nine documentation tests
include changed inline enum/runtime contracts, missing fragment context, unknown
grammar references, trailing syntax, and a lease checked against the wrong net.
``tests/test_rule_cases.py`` adds 34 positive and negative rule cases against the
reference checker, and ``tests/test_rule_coverage.py`` adds 16 tests of the rule
coverage check.

The generated Earley grammar is derived directly from weave.ebnf. Its independent
syntax/layout front end is followed by shared reference semantic checks; it is
not an independently implemented type checker. Corpus stage results, the syntax
probes and the Rust differential are recorded separately in
``validation/grammar-report.json``. ``tests/test_grammar_audit.py`` adds six
tests: the discrepancy table equals the audited probes, the probes keep their
verdicts, layout faults map to E001 and words end at boundaries, and the Rust
comparison is skipped as not established without ``cargo``, requires a named
binary to exist, and fails on a disagreeing verdict.

``make validate`` includes the grammar audit, rule-catalogue drift check, the
specification's 133 tests (nine documentation tests, the rule cases, the rule
coverage check, the diagnostic map tests, the result-label lint of
:ref:`chapters/verification:Result labels in tool output`, the grammar-audit
tests, the P0 tests and 14 tests of the conformance applications), the P0
differential, the P0 conformance applications, 143 upstream tests, strict HTML with weave-check, the local
HTML link and anchor audit, and Sphinx linkcheck. ``make validate-offline`` runs the same steps except external links.
A linkcheck transport error is a failed/unestablished external check, not success.
No unreachable URL is silently ignored.

The HTML footer and the PDF cover identify the original version-3 archive hash.
``sphinx.ext.autosectionlabel`` uses document-prefixed labels; normative rules
also have explicit stable IDs, because section-title labels change on renaming.
Static SVGs are shipped and regenerate with ``make diagrams`` using the standard
library; their PDF companions are converted with ``cairosvg``. The
``sphinx.ext.graphviz`` extension is enabled for future diagrams, but no current
chapter uses it, so Graphviz is not yet a build dependency.

* `Sphinx autosectionlabel <https://www.sphinx-doc.org/en/master/usage/extensions/autosectionlabel.html>`_
* `Lark grammar reference <https://lark-parser.readthedocs.io/en/stable/grammar.html>`_
