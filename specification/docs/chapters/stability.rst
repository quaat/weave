.. SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
.. SPDX-License-Identifier: MIT

Stability and versioning policy
=====================================

.. index:: stability, versioning, deprecation, migration note, compatibility anchor

This chapter is the project's stability and versioning policy. It is normative
for every Weave artefact kept in the project repository: this specification, its
profiles, the tools, the evidence they write and, from the durable service
milestone, persisted runtime state. The root ``STABILITY.md`` summarises it; where
the two differ, this chapter is authoritative.

The policy elaborates :ref:`CONF-REQ-3 <CONF-REQ-3>` in :doc:`status`. It adds no
rule ID and does not change any existing rule, diagnostic code, profile meaning or
version identifier; it states how they may change from now on. Every artefact,
claim or report SHOULD name its identifier on each axis it depends on. This
extends two existing requirements: :ref:`CONF-REQ-1 <CONF-REQ-1>` requires a
conformance claim to name the document revision and supported profiles, and
:ref:`CONF-REQ-3 <CONF-REQ-3>` asks programs and evidence to include the source
and tool revision.

Version axes
------------------

Weave is versioned on five independent axes. A change on one axis does not imply
a change on another: a new tool release does not create a new language revision,
and a new evidence format does not change a profile.

.. list-table::
   :header-rows: 1
   :widths: 16 30 18 36

   * - Axis
     - Covers
     - Owner (role)
     - Format
   * - Language
     - This specification: grammar, static and dynamic semantics, rule IDs,
       diagnostic code meanings, result vocabulary
     - Language maintainer
     - ``MAJOR.MINOR``; a draft carries the ``-draft`` suffix
   * - Tools
     - Each tool separately: checker, analyser, runtime, command-line interface,
       and the distributions that bundle them
     - Toolchain maintainer
     - Semantic versioning ``MAJOR.MINOR.PATCH`` per tool
   * - Profiles
     - F0, N0, N1 and R0; the targets D0 and N2; later profiles and versioned
       extensions
     - Language maintainer
     - Profile name qualified by the specification revision that defines it;
       an extension has a name and an integer version
   * - Evidence schemas
     - Machine-readable output that carries or supports a claim: certificates,
       exploration results, conformance artefacts, scenario results, traces,
       machine-readable diagnostics
     - Toolchain maintainer
     - ``weave-<artefact>-v<N>`` in the top-level ``format`` field
   * - Persisted store format
     - Durable runtime state: admissions, markings, operation and result
       ledgers, continuations, timers
     - Runtime maintainer
     - ``weave-store-v<N>`` in the store's metadata, checked before any other
       access; first identifier assigned in M5

Owners are roles, not people. The repository does not record who holds each
role; until it does, the maintainer holds all of them, and decisions that change
semantics stay with the maintainer (``CLAUDE.md``). The development workflow
tooling in ``tools/weave_workflow/`` is not a Weave tool; its own version string
and event schema are outside this policy.

Language
~~~~~~~~~~~~~~

The language identifier is the specification revision. ``version`` in
``specification/docs/conf.py`` holds ``MAJOR.MINOR``; ``release`` adds
``-draft`` while the document is a draft. The HTML title (``html_title`` in
the same file) and the index page show "Draft 0.2".
``specification/PROVENANCE.json`` records the same identifier as ``document``.

Bump rule:

* While MAJOR is 0, each published draft increments MINOR, as 0.1-draft was
  followed by 0.2-draft. Changes merged between published drafts accumulate
  under the current identifier and are summarised in the change history in
  :doc:`provenance` when the next draft is cut.
* From 1.0, MAJOR increments for a change that can make a previously conformant
  program or implementation non-conformant, such as removing a profile or
  extension, or tombstoning a rule ID or diagnostic code.
* MINOR increments for compatible additions: a new profile, a new versioned
  extension, a new rule ID or diagnostic code, or a clarification that changes
  no accepted program, diagnostic code, outcome or guarantee.
* Editorial changes (wording, examples, presentation) need no new identifier.

A specification release is to be tagged with the ``spec-v`` prefix; on such a
tag ``.github/workflows/pdf.yml`` builds the PDF and attaches it to the release.
Tagging and releasing are maintainer actions.

Tools
~~~~~~~~~~~

Each tool carries its own semantic version. Bump rule:

* MAJOR: an incompatible interface change, such as a command or option removed
  or given a different meaning, a changed exit-status meaning, or a supported
  profile, extension or schema version dropped.
* MINOR: a compatible addition, such as a new command or option, or a newly
  supported profile, extension or schema version.
* PATCH: a fix that changes no interface.
* While MAJOR is 0, an incompatible change increments MINOR instead.

A tool version never redefines a profile. Where a tool's behaviour differs from
the profile it claims, the difference is a discrepancy to report (:doc:`status`).
A tool change that alters which programs are accepted or rejected, the diagnostic
code reported or a dynamic outcome is a semantic change and needs a migration
note.

The prototype keeps the integer snapshot version it already has ("version 3").
Its pinned snapshots change only through a reviewed snapshot refresh recorded in
``PROVENANCE.json``; a refresh that changes behaviour takes the next integer.

Profiles
~~~~~~~~~~~~~~

A profile is identified by its name and the specification revision that defines
it, for example "F0 as defined in 0.2-draft". A versioned extension has a name
and an integer version, and names the profile it extends. Bump rule:

* New capability arrives as a new profile or a versioned extension, never by
  changing an existing profile (see `Profile meanings are preserved`_).
* A correction of a defect in an existing profile that changes which programs it
  accepts or rejects, its diagnostic codes or its guarantees is a semantic
  change. It needs a maintainer decision, a migration note and a new language
  revision, and conformance claims then name the revision they follow.
* An editorial clarification that changes no accepted program, diagnostic code or
  guarantee does not change the profile identifier.
* An existing extension's integer version increments for any change to what it
  accepts, rejects or guarantees; such a change is a semantic change and needs a
  migration note. Editorial changes do not increment it. An extension name and
  version pair is never reused with a changed meaning, and a retired extension
  name is tombstoned as for diagnostic codes (see `Deprecation`_).

Evidence schemas
~~~~~~~~~~~~~~~~~~~~~~

An evidence document MUST name its schema in a top-level ``format`` field of
the form ``weave-<artefact>-v<N>``. Seven existing format strings already use
this form, but many existing evidence files have no ``format`` field; both
groups are listed under `Existing evidence files`_. Bump rule: any change to
the fields, their meaning or the checks a reader performs needs the next ``N``.
A format string never changes meaning, and a retired format string is never
reused. The machine-readable diagnostics schema (quaat/weave#6) and the trace,
canonical-net and evidence-envelope schemas (quaat/weave#7) are versioned under
this axis.

Persisted store format
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This section fixes the identifier convention now; it is a format convention, not
a storage design. The first durable store, its layout and its migration mechanism
belong to the durable service milestone (M5, quaat/weave#59).

* **Format.** A store format identifier has the form ``weave-store-v<N>``, where
  ``N`` is a positive integer major version. It is recorded in the store's own
  metadata, and a runtime reads and checks it before any other access to the
  store: before creating, reading or writing any other data.
* **Bump rule.** Any change that a runtime implementing ``weave-store-v<N>``
  could not safely read or write raises ``N``: a changed layout, a changed
  meaning of stored data, or a new constraint that older writers could violate.
  Every such change needs a migration note.
* **Unrecognised identifiers.** A runtime that does not implement the recorded
  identifier, or finds none, MUST NOT open or modify the store
  (see `Unrecognised versions`_).

No store uses this convention yet; the first concrete identifier is assigned when
M5 specifies the store. How stores are migrated is not decided here;
:doc:`limitations` lists upgrade and schema migration rules as an open
production decision.

Current identifiers
-------------------------

These are the identifiers in the repository at the time this policy was written.
"None yet" means the repository has no identifier for that item.

.. list-table::
   :header-rows: 1
   :widths: 18 26 24 32

   * - Axis
     - Item
     - Identifier
     - Source
   * - Language
     - This specification
     - ``0.2-draft`` (``version`` ``0.2``), displayed as "Draft 0.2"
     - ``specification/docs/conf.py`` (``version``, ``release``);
       ``specification/PROVENANCE.json`` (``document``); :doc:`status`
       (:ref:`CONF-REQ-3 <CONF-REQ-3>`); root ``README.md``
   * - Tools
     - Prototype (``checker.py``, ``coloured.py``, ``simulate.py``,
       ``durable.py``, ``verify_certificate.py``)
     - Version ``3`` of ``weave-inventory-proof.zip``; no per-tool version
     - ``specification/PROVENANCE.json`` and ``agent-kit/PROVENANCE.json``
       (``version`` of the source archive)
   * - Tools
     - Agent kit, including its CLI ``agent-kit/scripts/weave.py``
     - ``0.1.0``; the CLI has no version option
     - ``agent-kit/PROVENANCE.json`` (``kit_version``)
   * - Tools
     - Production checker, runtime and CLI
     - None yet
     - The repository contains no production compiler or runtime: no Rust
       source exists yet (``docs/development/implementation-language.md``
       sets Rust as the default), and the root ``README.md`` states there is
       no general compiler and no distributed runtime
   * - Profiles
     - F0, N0, N1, R0
     - Defined by 0.2-draft; no separate revision
     - Profile table in :doc:`status`
   * - Profiles
     - D0, N2 (targets, unimplemented)
     - Defined by 0.2-draft; no separate revision
     - Decisions D-01 and D-02 in :doc:`status`; :doc:`evidence-design`
       (N2); :doc:`execution-contract` (D0)
   * - Profiles
     - Pure ``fn`` extension of the agent kit
     - None yet; outside the specified fragment
     - Root ``README.md``; ``agent-kit/README.md``
   * - Evidence schemas
     - Place-invariant certificate (``proof.json``)
     - ``weave-place-invariant-v1``
     - ``format`` in ``inventory-proof/proof.json``
   * - Evidence schemas
     - One-order check (``ordering.json``)
     - ``weave-one-order-check-v2``
     - ``format`` in ``inventory-proof/ordering.json``
   * - Evidence schemas
     - Coloured invariants (``colour-proof.json``)
     - ``weave-colour-invariant-v1``
     - ``format`` in ``inventory-proof/colour-proof.json``
   * - Evidence schemas
     - Coloured exploration (``colour-check.json``)
     - ``weave-colour-exploration-v1``
     - ``format`` in ``inventory-proof/colour-check.json``
   * - Evidence schemas
     - Conformance corpus manifest
     - ``weave-conformance-v1``
     - ``format`` in ``specification/examples/manifest.json``
   * - Evidence schemas
     - Specification validation report
     - ``weave-specification-validation-v1``
     - ``format`` in ``specification/validation/report.json``
   * - Evidence schemas
     - Agent-kit teaching manifest
     - ``weave-teaching-examples-v1``
     - ``format`` in ``agent-kit/examples/manifest.json``
   * - Evidence schemas
     - Scenario results, agent-kit demo traces and artefacts, specification
       audit reports
     - None yet
     - These files have no ``format`` field; see `Existing evidence files`_
   * - Evidence schemas
     - Traces, machine-readable diagnostics, canonical net, evidence envelope
     - None yet
     - To be defined by quaat/weave#6 and quaat/weave#7
   * - Persisted store format
     - Durable runtime store
     - None yet
     - The R0 model's SQLite store records only the net source digest
       (``metadata`` key ``source`` in ``inventory-proof/durable.py``)

Existing evidence files
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The command below prints every JSON file tracked at base commit ``0d3185f``
(the revision this policy was written against) with its top-level ``format``
value. Run it from the repository root. The lists after it give its output,
omitting the files under ``.claude/`` and ``tools/weave_workflow/``, which are
outside this policy.

.. code-block:: bash

   git ls-tree -r --name-only 0d3185f | grep '\.json$' | while read p; do
     printf '%s %s\n' "$p" "$(git show "0d3185f:$p" | python3 -c 'import json,sys
   try: d=json.load(sys.stdin)
   except ValueError: print("(not one JSON document)")
   else: print(d.get("format", "(no format field)") if isinstance(d, dict) else "(array, no format field)")')"
   done

Files with a ``format`` field (seven distinct format strings):

* ``weave-place-invariant-v1``: ``inventory-proof/proof.json``,
  ``agent-kit/demos/tiny_shop/artifacts/inventory-proof.json``
* ``weave-one-order-check-v2``: ``inventory-proof/ordering.json``
* ``weave-colour-invariant-v1``: ``inventory-proof/colour-proof.json``
* ``weave-colour-exploration-v1``: ``inventory-proof/colour-check.json``
* ``weave-conformance-v1``: ``specification/examples/manifest.json``
* ``weave-specification-validation-v1``: ``specification/validation/report.json``
* ``weave-teaching-examples-v1``: ``agent-kit/examples/manifest.json``

The byte-identical prototype copies in
``agent-kit/.agents/skills/weave/assets/prototype/`` and
``specification/reference/prototype/`` carry the same four prototype format
strings.

Evidence and artefact files without a ``format`` field:

* Prototype scenario results, JSON arrays: ``inventory-proof/scenarios.json``,
  ``inventory-proof/durable-scenarios.json`` and their copies in both pinned
  snapshots.
* Agent-kit demo artefacts, JSON objects:
  ``agent-kit/demos/merge_sort/artifacts/mixed-sign.json``,
  ``trace-concurrent.json``, ``trace-concurrent-quantum1.json`` and
  ``trace-sequential.json`` in the same directory;
  ``agent-kit/demos/tiny_shop/artifacts/lowered-trace.json``,
  ``scenarios.json`` and ``source-trace.json`` in the same directory.
* Specification build reports: ``specification/validation/grammar-report.json``,
  ``html-audit.json`` and ``singlehtml-audit.json`` (objects),
  ``weave-check-report.json`` (an array) and ``linkcheck-output.json`` (one JSON
  object per line, written by Sphinx), all in ``specification/validation/``.

``specification/rules.json`` (the generated rule index) and the two
``PROVENANCE.json`` manifests also have no ``format`` field; they are index and
provenance records rather than evidence of a claim, and this policy does not
classify them as evidence schemas.

Tracking: the context of quaat/weave#7 names ``proof.json``, ``ordering.json``,
``colour-proof.json``, ``scenarios.json``, ``durable-scenarios.json`` and
``specification/validation/report.json`` as the existing evidence files, and its
criteria include "Existing evidence files converted or wrapped". The migration of
the two scenario files is therefore tracked by quaat/weave#7. The agent-kit demo
traces and artefacts and the specification build reports are not named in its
scope, so their migration is not yet tracked.

Compatibility anchors
---------------------------

Diagnostic codes (the table in :doc:`diagnostics`) and rule IDs (indexed in
:doc:`rule-catalogue` and ``specification/rules.json``) are compatibility
anchors:

* A code or rule ID keeps its meaning in every later language revision, tool
  version and profile.
* A code or rule ID is never reused for another meaning, including after it is
  retired.
* A narrower or new condition gets a new code or rule ID; it does not change the
  meaning of an existing one.
* Human wording may evolve: diagnostic messages, rule titles, explanatory prose,
  and the order of several diagnostics except where :doc:`conformance` requires
  a particular first diagnostic. Chapter, line and section numbers are not
  anchors.

This agrees with :doc:`status` ("Reference diagnostic codes are compatibility
anchors, not a complete portable ABI") and :doc:`diagnostics` ("Exact wording
and ordering are not stable language semantics"). Profile names and evidence
format strings are never reused either.

Deprecation
~~~~~~~~~~~~~~~~~

A code or rule ID is withdrawn only in these steps:

#. **Mark it deprecated.** Its entry states that it is deprecated, the language
   revision that deprecated it and its replacement, if any. The change carries a
   migration note.
#. **Keep its meaning.** A deprecated code or rule ID means what it meant before.
#. **Keep recognising it.** Tools, manifests and evidence readers that emit or
   read the code continue to accept it with its meaning until it is tombstoned.
#. **Retire it only by tombstoning,** in a language revision later than the one
   that deprecated it. The entry stays, marked retired, with its last meaning and
   the revision that retired it. A reader that meets a tombstoned code reports it
   as that retired code and never as any other.
#. **Never reuse it.**

No code or rule ID is deprecated today. Neither the diagnostics table nor
``specification/rules.json`` has a deprecated or retired marker yet; the first
deprecation must add one, for rule IDs through
``specification/scripts/refresh_reference_pages.py``, which generates the
catalogue.

Migration notes
---------------------

Every semantic change MUST carry a migration note. A semantic change is any
change that alters, for some input, which programs a profile or tool accepts or
rejects, the diagnostic code reported, the dynamic outcome of an accepted
program, the meaning of a rule ID, diagnostic code, profile or result label, or
how an evidence document or persisted store is read. Editorial changes and
compatible additions that leave every existing input's result unchanged do not
need one.

The note is part of the change's pull request and is recorded in the changelog
of each affected component: the change history in :doc:`provenance` for the
specification, ``agent-kit/CHANGELOG.md`` for the agent kit. Use the template
``docs/templates/migration-note.md``
(`repository copy <https://github.com/quaat/weave/blob/main/docs/templates/migration-note.md>`_),
reproduced below. Changelog entries follow
``docs/templates/changelog-entry.md``.

.. literalinclude:: ../../../docs/templates/migration-note.md
   :language: markdown
   :start-after: -->

Profile meanings are preserved
------------------------------------

F0, N0, N1 and R0 keep the meanings defined in 0.2-draft. The following arrive as
versioned extensions or new profiles, never by changing those four:

* **New pure syntax**: pure functions, arithmetic, lists, conditionals, loops
  and recursion in flows. F0 flows have none of them; the root ``README.md``
  places this computation only in the agent kit's separate ``fn`` extension,
  outside the specified fragment.
* **Generalised identity**: identity sorts beyond N1's two positional colour
  sorts, tenant and order (:doc:`net-semantics`).
* **Durable execution**: execution of arbitrary flows with persisted state,
  beyond R0's concrete process-crash model of the Inventory protocol.

A checker for an existing profile MUST continue to reject such constructs, as
:ref:`CONF-REQ-1 <CONF-REQ-1>` requires for unsupported constructs. Supporting a
profile or extension implies nothing about another; :doc:`status` already states
this for N1 and R0. D0 and N2 are targets specified in 0.2-draft; D0's colour
rules use one tenant/order pair (:ref:`D0-COLOR-2 <D0-COLOR-2>`), so arbitrary
declared identity sorts need a documented amendment with a migration note, not a
reinterpretation of D0.

Unrecognised versions
---------------------------

A tool that reads an evidence document, conformance artefact or persisted store
whose format or version it does not implement MUST NOT treat it as success. It
MUST NOT report a passing result, MUST NOT read it as a nearby version it does
implement, and MUST NOT open or modify such a store. It MUST reject the input
with a message naming the unrecognised identifier, or report that the claim is
not established. An input that lacks a version identifier where its schema
requires one is treated the same way. The same holds for a conformance claim
naming a language revision or profile the tool does not implement.
The format-field requirement under `Evidence schemas`_ and these rules bind
tools that read or write versioned schemas; they do not reinterpret the
unversioned files listed under `Existing evidence files`_: until those files are
migrated (by quaat/weave#7 for the files it names; otherwise not yet tracked), a
tool does not treat them as conformant versioned evidence and reports no
passing result on them, and this policy does not require rejecting them
retroactively.

The existing prototype predates this rule. It has two partial safeguards, and
neither meets the rule in full:

* ``inventory-proof/verify_certificate.py`` (lines 19--20) rejects a certificate
  whose ``format`` is not ``weave-place-invariant-v1``, including one with no
  ``format`` field, so an unrecognised certificate is never accepted. The
  message, "Unsupported certificate format", does not name the unrecognised
  identifier, as the rule requires.
* The R0 model in ``inventory-proof/durable.py`` checks a source digest, not a
  store format. Lines 100--108 compare the SHA-256 of the net source with the
  ``metadata`` key ``source`` and refuse a mismatch ("Persisted net revision
  differs; migration is required"). The store records no store format
  identifier; lines 92--99 create its tables before that check; and a store
  without a ``source`` entry is initialised rather than refused (lines
  104--106).

The copies of both files in the pinned snapshots
(``agent-kit/.agents/skills/weave/assets/prototype/`` and
``specification/reference/prototype/``) are byte-identical to these.
The prototype is pinned regression evidence and is not changed by this policy.

Tracking: quaat/weave#7 implements this rule for the trace, canonical-net and
evidence-envelope schemas it defines, adds a test that unknown schema versions
are never interpreted as successful evidence, and converts or wraps the existing
evidence files it names (see `Existing evidence files`_). Neither quaat/weave#6 (machine-readable diagnostics) nor
quaat/weave#7 covers the wording of the prototype verifier's message or the R0
store's checks; bringing those into line is not yet tracked. Stores first follow
the ``weave-store-v<N>`` convention in the durable service milestone
(quaat/weave#59).
