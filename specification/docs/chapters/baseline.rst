.. SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
.. SPDX-License-Identifier: MIT

Claims, baseline and pinned identifiers
=============================================

.. index:: baseline, public claim, reproducibility, pinned identifier

This chapter ties each public claim of the project to the profile it concerns and
a command that supports it, gives the procedure that reproduces the whole
baseline from a fresh clone, and records the identifiers the baseline pins. The
per-profile view is the profile matrix in :doc:`status`; rule-level coverage is in
:doc:`rule-coverage`. Nothing here changes a rule, profile or result label.

Public claims and their evidence
--------------------------------------

The claims below are those of the repository's ``README.md`` (the guarantee table,
"A taste", "Quick start" and "What is not here") and of :doc:`status`. Profiles
are those of :doc:`status`. Commands run in ``specification/`` unless the
"Command" column names another directory. A command
that checks an expected rejection exits 0 when the rejection occurs with the
required code; the corpus case IDs are those of :doc:`conformance`.

.. list-table::
   :header-rows: 1
   :widths: 30 10 32 28

   * - Claim (where)
     - Profile
     - Command
     - Expected result
   * - Live handles cannot be forgotten, ``E204`` (README guarantee table)
     - F0
     - ``python3 scripts/validate.py``
     - Exit 0; cases C010 and C016 report E204
   * - The three flows of "A taste" check (README)
     - F0 with N0 API
     - ``python3 reference/prototype/checker.py check
       examples/nets/Inventory.weave examples/valid/checkout_propagating.weave``
     - Exit 0; three ``CHECKED`` lines
   * - Operations need a permit minted by the net, ``E201``, ``E205``
       (README guarantee table; "A taste")
     - F0 with N0 API
     - ``python3 scripts/validate.py``
     - Exit 0; cases C009 (E201) and C011 (E205)
   * - Conservation proofs for any starting quantity, ``PROVED`` (README
       guarantee table; "What is not here")
     - N0, N1
     - ``python3 reference/prototype/checker.py analyze
       examples/nets/Inventory.weave``; ``python3
       reference/prototype/coloured.py analyze
       examples/nets/Inventory.coloured.weave``
     - Exit 0 each; ``PROVED`` for the declared invariants of these two nets
       only: two in N0, two aggregate and three per-colour families in N1
   * - Bounded exploration finds the in-flight release, ``E320``, ``E420``
       (README guarantee table)
     - N0 (E320), N1 (E420)
     - ``python3 scripts/validate.py``
     - Exit 0; case C025 reports E320, and the coloured walkthrough
       ``examples/nets/cross_order_read.weave`` reports E420
   * - ``Unknown`` cannot be ignored; propagation preserves its obligation
       (README introduction and guarantee table)
     - F0
     - ``python3 scripts/validate.py``
     - Exit 0; cases C014 (E214) and C016 (E204). Regression evidence for these
       inputs and the tests in :doc:`rule-coverage`, not a proof for every
       program
   * - Per-order bookkeeping cannot cross orders (README guarantee table)
     - N1
     - ``python3 reference/prototype/coloured.py analyze
       examples/nets/Inventory.coloured.weave``
     - Exit 0; ``CHECKED WITHIN BOUNDS orders=2, states=841, edges=3712``;
       the property list includes ``token_identity``
   * - A crashed worker does not lose protocol state (README guarantee table)
     - R0
     - ``python3 reference/prototype/durable.py``
     - Exit 0; six ``PASSED`` process-crash scenarios; the model's own closing
       line lists what it does not verify
   * - Analyser output in "A taste" (``PROVED``, ``CHECKED WITHIN BOUNDS
       orders=2, stock=2, states=841, edges=3712``)
     - N1
     - ``python3 demo.py`` in ``inventory-proof/``
     - Exit 0; the lines appear in its output and in
       ``inventory-proof/ACTUAL_OUTPUT.txt``; ``git diff --exit-code -- .``
       then reports no change
   * - 143 prototype tests (README "Quick start")
     - F0, N0, N1, R0
     - ``python3 -m unittest discover -s tests`` in ``inventory-proof/``;
       ``python3 scripts/weave.py test`` in ``agent-kit/``
     - Exit 0; ``Ran 143 tests``
   * - "Every displayed example is re-checked at build time" (README
       repository map)
     - F0, N0, N1
     - ``make validate-offline`` in ``specification/``
     - Exit 0; the build rejects Weave code blocks without ``weave-check``, and
       each block's result matches its expectation (report in
       ``_build/html/weave-check-report.json``). N2 target syntax is shown in
       text blocks and is not checked (:doc:`tooling`)
   * - Profile table and profile matrix (:doc:`status`)
     - F0, N0, N1, R0; D0 and N2 targets
     - The commands in the profile matrix
     - As stated there; D0 and N2 have no command

The README's "What is not here" list and the :doc:`limitations` register state
what is *not* claimed; they need no supporting command.

Reproducible baseline
---------------------------

The baseline is the set of results that the continuous-integration workflow
``.github/workflows/ci.yml`` produces. The commands below are those of its four
jobs, in the same directories, adapted to a local shell: ``python3`` instead of
the job's ``python``, and a virtual environment for the specification's packages. CI runs ``inventory-proof`` and
``agent-kit`` on Python 3.11, 3.12 and 3.13, the specification on 3.12 and the
workflow tooling on 3.11; the workflow file is authoritative where it and this
list differ. Only the specification job needs third-party packages, pinned in
``specification/requirements.txt`` and installed from the network.

Start from a fresh clone at the baseline commit (the tag proposed below, once the
maintainer has created it):

.. code-block:: bash

   git clone https://github.com/quaat/weave.git weave-baseline
   cd weave-baseline
   git checkout --detach baseline-0.2-draft-prototype-v3   # or the commit ID

**inventory-proof** (from ``inventory-proof/``):

.. code-block:: bash

   python3 -m unittest discover -s tests -v
   python3 demo.py
   git diff --exit-code -- .
   python3 durable.py

Expected: ``Ran 143 tests`` and ``OK``; ``demo.py`` exits 0 and the diff is empty
(the committed outputs are reproduced byte for byte); ``durable.py`` prints six
``PASSED`` scenario lines and exits 0.

**agent-kit** (from ``agent-kit/``):

.. code-block:: bash

   python3 scripts/weave.py doctor
   python3 -B -m unittest discover -s tests -v
   python3 scripts/weave.py examples
   python3 scripts/weave.py test
   for demo in demos/*/; do (cd "$demo" && python3 -B -m unittest discover -s tests -v); done

Expected: ``doctor`` prints ``READY``; ``Ran 59 tests`` and ``OK``;
``PASS 34/34 example expectations``; ``Ran 143 tests`` and ``OK``; the demo
suites report ``Ran 13 tests`` (``merge_sort``) and ``Ran 17 tests``
(``tiny_shop``), each ``OK``.

**specification** (from ``specification/``):

.. code-block:: bash

   python3 -m venv .venv && . .venv/bin/activate
   python -m pip install -r requirements.txt
   make validate-offline PYTHON=python
   make singlehtml text PYTHON=python
   python scripts/audit_html.py _build/singlehtml

Expected from ``make validate-offline``, in order: ``PASS: 25 source
expectations; 3 scripted scenarios``; ``PASS: 8 valid flows and their lowerings
checked with N0 and N1 APIs``; ``PASS: N0 20 states / 43 edges; N1 841 states /
3712 edges``; ``PASS: unchanged reference snapshot; 32 coloured cells / 48 firing
modes``; ``PASS: 68 EBNF productions; 25/25 corpus pipeline agreements; N1 and
lease syntax parsed``; ``PASS: conformance table and rule catalogue current``;
``Ran 58 tests`` and ``OK`` (the specification's own tests, including the rule
coverage check); ``Ran 143 tests`` and ``OK`` (the snapshot's tests); a Sphinx
HTML build without warnings; and an HTML audit whose ``errors`` list is empty.
The single-page and text builds succeed and the single-page audit's ``errors``
list is empty. ``scripts/validate.py`` rewrites ``validation/report.json``, whose
``python`` field records the interpreter version; under an interpreter other than
the one recorded, that field differs and ``git checkout --
validation/report.json`` restores it.

**workflow tooling** (from the repository root):

.. code-block:: bash

   python3 -m unittest discover -s tools/weave_workflow/tests -t . -v
   python3 -m tools.weave_workflow docs-audit
   python3 -m tools.weave_workflow docs-map

Expected: ``Ran 163 tests`` and ``OK``; ``docs-audit PASS``; ``docs-map`` prints
``current``. Test counts belong to the baseline commit; later commits can change
them.

Pinned identifiers
-------------------------

A baseline record names these identifiers. Every value below can be recomputed
from the baseline commit with the command shown, run from the repository root.

.. list-table::
   :header-rows: 1
   :widths: 24 40 36

   * - Item
     - Value at the baseline
     - How to recompute
   * - Repository commit
     - The merge commit of the change that adds this chapter; recorded on
       quaat/weave#4 when the tag is created (a commit cannot name its own ID)
     - ``git rev-parse baseline-0.2-draft-prototype-v3^{commit}``
   * - Specification revision
     - ``0.2-draft`` (``version`` ``0.2``)
     - ``version`` and ``release`` in ``specification/docs/conf.py``;
       ``document`` in ``specification/PROVENANCE.json``
   * - Prototype source archive
     - ``weave-inventory-proof.zip`` version ``3``, SHA-256
       ``5f67ee8430b68f3ed970f4484e653acc85c68c72cf59f68929ba1b136a2c4ba2``
     - ``sources`` in ``specification/PROVENANCE.json``; ``source`` in
       ``agent-kit/PROVENANCE.json``
   * - Specification snapshot files
     - SHA-256 of each of the 39 files of ``specification/reference/prototype/``,
       recorded in ``specification/PROVENANCE.json``
       (``reference_files``), whose own SHA-256 is
       ``454773e91f70cbd6477e7ce717cb8c84fc355a494c3f6bed0bc7bf706ad82bba``
     - ``sha256sum specification/PROVENANCE.json``;
       ``scripts/validate.py`` checks every listed file
   * - Agent-kit snapshot files
     - SHA-256 of each of the 39 files of
       ``agent-kit/.agents/skills/weave/assets/prototype/``, recorded in
       ``agent-kit/PROVENANCE.json`` (``original_files_sha256``), whose own
       SHA-256 is
       ``7c31b0a37256185b083abee21c3f90c807d5727d4419f3e1b4934a126634c387``
     - ``sha256sum agent-kit/PROVENANCE.json``; the documentation audit checks
       every listed file
   * - Working copy ``inventory-proof/``
     - Each of its files named in ``specification/PROVENANCE.json``
       (``reference_files``) has the recorded SHA-256
     - Compare ``sha256sum`` of ``inventory-proof/<file>`` with the entry for
       ``reference/prototype/<file>``
   * - Specification build dependencies
     - ``specification/requirements.txt``, SHA-256
       ``cff42a1e6c878882e5c3ff73d0b36bf1d433b926c26d0d37b469070988b3d98b``
     - ``sha256sum specification/requirements.txt``
   * - Evidence formats
     - The format strings listed in :doc:`stability`; the rule-coverage map
       ``specification/tests/rule-coverage.json`` adds
       ``weave-rule-coverage-v1``
     - ``format`` field of each file

The SHA-256 values above are those at the baseline commit; a later reviewed
snapshot refresh changes them, and the record then still describes the tagged
commit. To recompute a value for the tag rather than the working tree, read the
file from the tag, for example
``git show baseline-0.2-draft-prototype-v3:specification/PROVENANCE.json | sha256sum``.

Proposed baseline tag
---------------------------

Creating the tag is a maintainer action; this specification only proposes it.

* **Name:** ``baseline-0.2-draft-prototype-v3``.
* **Target:** the merge commit on ``main`` of the pull request that adds this
  chapter for quaat/weave#4, after the procedure above passes on that commit.
* **Why not** ``spec-v``: :doc:`stability` reserves the ``spec-v`` prefix for a
  specification release, and pushing such a tag makes
  ``.github/workflows/pdf.yml`` create a GitHub release with the PDF. The
  baseline pins the repository state that the checks reproduce, not a new
  language revision.
* **Why this name:** it names the identifiers the baseline pins on the two axes
  of :doc:`stability` that it depends on, the language revision (``0.2-draft``)
  and the prototype tool version (``3``). The ``baseline-`` prefix matches no
  workflow trigger: ``ci.yml`` and ``docs.yml`` run on branch pushes, pull
  requests and manual dispatch, and ``pdf.yml`` on ``spec-v*`` tags.

Command for the maintainer, with ``<merge-commit>`` replaced by the full commit
ID:

.. code-block:: bash

   git fetch origin
   git tag -a baseline-0.2-draft-prototype-v3 <merge-commit> \
     -m "Weave baseline: specification 0.2-draft, prototype version 3 (quaat/weave#4)"
   git push origin baseline-0.2-draft-prototype-v3
