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
not an independently implemented type checker. Corpus stage results are recorded
separately in ``validation/grammar-report.json``.

``make validate`` includes the grammar audit, rule-catalogue drift check, the
specification's 59 tests (nine documentation tests, the rule cases and the rule
coverage check), 143 upstream tests, strict HTML with weave-check, the local
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
