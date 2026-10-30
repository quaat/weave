Design history and rejected or deferred alternatives
==========================================================

Evidence status
---------------------

The review refers to four earlier design drafts. They were not recovered from
the available project files or context retrieval for this revision. Their
titles, dates, ordering, and per-draft changes cannot be reconstructed reliably.
This appendix deliberately does not invent a four-draft chronology.

The available evidence consists of the version-3 DESIGN_NOTES.md, version-2
agent-kit boundary, the later merge-sort brief, the delivered 0.1 specification,
and the user's current review. The table distinguishes recorded decisions from
current exclusions and new rationale.

.. list-table::
   :header-rows: 1
   :widths: 16 25 34 25

   * - Construct
     - Established status
     - Reason supported by available material
     - Evidence / missing history
   * - Open unions
     - Explicitly withdrawn from initial design
     - Closed nominal enums; no implicit widening; explicit mapping for a future
       general language
     - DESIGN_NOTES.md, Closed error types
   * - General resumable handlers
     - Excluded from proposed version-one providers
     - Statically selected typed providers retain capabilities and uncertainty
     - DESIGN_NOTES.md, Non-foreign effects
   * - Effect rows
     - Not implemented; historical removal unverified
     - This draft keeps explicit signatures; it does not infer that all future
       effect abstraction was rejected
     - Current boundary; four-draft rationale unavailable
   * - Task
     - No implemented first-class Task type
     - Merge-sort brief asks for scoped child activations and correlated joins,
       not proof of a general task API
     - Review names earlier construct; no retrieved removal decision
   * - within
     - Unsupported; not established as permanently rejected
     - A timeout cannot establish that an external mutation failed; deadline,
       lease, and obligation lifetime require separate contracts
     - Boundary + DESIGN_NOTES timing discussion; original syntax decision absent
   * - retry
     - Unsupported source construct; R0 has a concrete recovery policy
     - Stable keys, retention horizons, evidence, and budgets must survive retries
     - DESIGN_NOTES + R0; no recovered general syntax history
   * - dataflow
     - Unsupported; historical design status unverified
     - No rationale attributed to absent drafts
     - User review only
   * - Recursive effectful flows
     - Rejected by the implemented fragment (E218)
     - The pure merge-sort extension is deliberately separate; it does not need
       recursive resource-bearing flows
     - Checker and merge-sort brief
   * - Pure functions / fork-join
     - Pure functions adopted as P0 (quaat/weave#10), with sequential merge sort
       and routing as conformance applications (quaat/weave#11); fork/join is a
       proposed extension, unimplemented (quaat/weave#42, M6)
     - Immutable computation separated from effects; scoped joins with explicit
       identity and bounded resources
     - Merge-sort brief, not a completed implementation
   * - Modules / imports
     - Local P0 modules adopted as modules-1 (quaat/weave#12); cross-project
       imports (quaat/weave#13), protocol packages (quaat/weave#19) and net
       composition (quaat/weave#91) deferred
     - Code reuse across files with declaration identity kept: nominal records,
       private helpers, no shadowing; flows keep one net
     - Maintainer decision on quaat/weave#12 (scope amended from protocol imports)

The explanation of why obligations are not garbage and why waiting is selected
is this draft's :doc:`rationale`. It must not be misread as a quotation from a
missing historical source.

Known evolution
---------------------

* Agent-kit snapshot: restricted N0/F0, 107 prototype tests, no durable runtime.
* Prototype version 3: N1 colour accounting/correlation and R0 process-crash
  cases; 143 tests in the delivered snapshot.
* Specification 0.1: implementation profiles, EBNF, result vocabulary and limits.
* Specification 0.2: D-01 declared evidence/correlation direction; D-02 waiting
  execution contract; explicit N0/N1 difference; formal rules and conformance.
* Stability policy, added during 0.2-draft (quaat/weave#3): five independent
  version axes; diagnostic codes and rule IDs as never-reused compatibility
  anchors; migration notes for semantic changes; new capability as versioned
  extensions or new profiles rather than changes to F0, N0, N1 or R0. No
  identifier, rule or profile changed. See :doc:`stability`.
* Profile matrix and baseline, added during 0.2-draft (quaat/weave#4): a profile
  matrix in :doc:`status`, the public claims with their profile and command and a
  reproducible baseline procedure with pinned identifiers in :doc:`baseline`, a
  generated :doc:`rule-coverage` page, and the source-to-model trust boundary in
  :doc:`security`. No identifier, rule or profile changed.
* Core semantic decisions, recorded during 0.2-draft (quaat/weave#5): the
  maintainer adopted exact integers with run budgets, Euclidean division, ASCII
  decimal literals and faulting partial list primitives; a closed set of pure
  faults with left-to-right, sequential-equivalent outcomes; nominal identity
  values; ``within`` as an observation deadline; declared-route cancellation
  ownership; the current N1 fragment for M4; and the full durable state
  inventory for M5. They bind later milestones. A note after D0-COLOR-2 states
  that D0's colour rules assume one tenant/order pair. No identifier, rule or
  profile changed. See :doc:`core-decisions`.
* Machine-readable diagnostics, added during 0.2-draft (quaat/weave#6): the
  evidence format ``weave-diagnostic-v1``; source spans for every reference
  diagnostic and related spans for E203 and E204, from one reviewed refresh of
  both pinned prototype snapshots (the prototype stays version 3: the same
  programs are accepted and rejected with the same codes); the code-to-rule map
  ``diagnostics.json``, from which :doc:`diagnostics` is generated, with one
  principal rule per code; new rule IDs N1-COLOUR-1, N1-FIRE-1, N1-FAMILY-1,
  N1-FAMILY-2 and N1-ORDER-1 for the existing N1 checks; corrected rule
  mappings for E110 to E112, E210, E215 and E217; E003 documented for a
  duplicated match tag; and the agent kit's pure-extension codes moved from
  ``E4xx`` to ``P4xx``. No code changed meaning. The prototype stays version 3:
  under :doc:`stability` (Tools), behaviour means accepted and rejected programs,
  diagnostic codes and dynamic outcomes, none of which changed; the refresh adds
  span metadata and corrects reported locations. E210 and E215 map to
  :ref:`SYN-12 <SYN-12>` rather than :ref:`SYN-10 <SYN-10>`, because SYN-12
  states exactly those checks (no statement after a return, every path
  terminates) and SYN-10 governs how a return is interpreted.
* Result labels in tool output, added during 0.2-draft (quaat/weave#8): a
  policy in :doc:`verification` that a label attaches to one claim, that tool
  and runtime status are separate and are not evidence, that ``Unknown`` is an
  application outcome and never NOT ESTABLISHED, and that the prototype's console
  lines are raw tool output. The prototype and its pinned snapshots are
  unchanged; the agent kit's runner (0.3.0) and the evidence envelopes label
  each claim, and tests in the agent kit and the specification lint tool output
  for any other label. The migration definition in :doc:`stability` now names
  a change of the label a result receives; the kit change carries a migration
  note. No label, rule, diagnostic code or profile changed.
* Grammar normalisation and a grammar-driven parser, added during 0.2-draft
  (quaat/weave#9): the Rust crate ``crates/weave-syntax`` interprets
  ``grammar/weave.ebnf`` as an ordered-choice grammar, guarded by a
  normalisation check, and keeps comments and spans in a concrete syntax tree
  (:doc:`grammar`). ``let-call`` was rewritten from ``[ "await" ], call`` to the
  equivalent ``( "await", call | call )``, so the EBNF's language is unchanged.
  :doc:`lexical` states how the grammar-driven parsers form tokens and line
  endings, and :doc:`grammar` lists the reference parser's differences as
  probes under the open items LEX-01 to LEX-04. The generated audit's words and
  numerals now end at word boundaries, and it classes layout faults as E001.
  Conformance cases C026 (comments and blank lines in every block position) and
  C027 (a skipped indentation level, E001) were added. The reference snapshot is
  unchanged. No rule, diagnostic code or profile changed.
* Pure computation, added during 0.2-draft (quaat/weave#10): a new profile, P0
  (:doc:`pure`), with rule IDs ``P0-*``, diagnostic codes E500 to E540 and the
  result label CHECKED pure (:doc:`verification`). The ``pure-file`` start symbol
  and its productions were added to ``grammar/weave.ebnf``, and SYN-01 now lists
  the pure file kind; the lexer gained the tokens ``<``, ``<=``, ``>``, ``>=`` and
  ``!=``. F0, N0 and N1 accept and reject exactly the files they did before: the
  Rust and generated parsers give the same verdicts and codes on the earlier 32
  corpus files and 22 probes, and two probes were added. The Rust crates
  ``weave-check``, ``weave-eval`` and ``weave-cli`` (command ``weave``) and the
  Python reference evaluator ``scripts/p0_reference.py`` implement P0, and
  ``scripts/p0_differential.py`` compares them. The P0 corpus is
  ``examples/pure/manifest.json`` (``weave-p0-conformance-v1``). These are
  compatible additions (MINOR at the next draft cut, :doc:`stability`); no
  existing rule, code, profile or label changed meaning. The proposal in
  :doc:`proposals` is marked adopted; the agent kit's ``fn`` extension is
  unchanged.
* Conformance applications for P0, added during 0.2-draft (quaat/weave#11):
  ``scripts/p0_applications.py`` runs sequential merge sort and the routing
  function of ``examples/pure/valid/`` through the ``weave`` command and the
  reference evaluator against Python oracles, on exhaustive short lists, seeded
  larger inputs, valid and invalid route records and malformed run requests
  (:ref:`chapters/tooling:Conformance applications`). Stability of
  ``sort_items`` is checked on output ids. The concurrent fork/join merge-sort
  brief remains incomplete (quaat/weave#42, M6). No rule, diagnostic code,
  profile, label or corpus case changed.
* Local modules, added during 0.2-draft (quaat/weave#12): a versioned extension
  of P0, modules-1 (:ref:`chapters/names:P0 modules (modules-1)`), with rule IDs
  ``MOD-*`` and diagnostic codes E600 to E610 (of the range E600 to E619). The
  ``module-file`` start symbol and its productions (``import-decl``,
  ``import-name``, ``module-item``) were added to ``grammar/weave.ebnf``, SYN-01
  now lists the module file kind, and ``flow-file`` gained the optional
  ``use-net`` header. ``pure-file`` is unchanged, a P0 file without imports or
  ``export`` is checked and run exactly as before, and a P0 error inside an
  imported module keeps its E5xx code. The Rust and generated parsers agree on
  every earlier corpus file and probe; the probes SD-13 and SA-13 were added for
  the header, which the reference checker predates. The ``weave`` command gained
  ``--root`` and checks and runs programs of several modules, with every span
  carrying its file; the agent kit's runner reads ``use net`` and hands the
  unchanged prototype the flow with the header blanked. The modules corpus is
  ``examples/modules/manifest.json`` (``weave-modules-conformance-v1``), run by
  ``scripts/modules_conformance.py``; ``weave-conformance-v1`` and
  ``weave-p0-conformance-v1`` are unchanged. The crates ``weave-syntax``,
  ``weave-check`` and ``weave-cli`` moved to ``0.2.0``: a compatible addition for
  the ``weave`` command and an incompatible change of the library API (new public
  fields of ``Span`` and ``Diagnostic``), each a MINOR increment while MAJOR is 0.
  For the language these are compatible additions
  (MINOR at the next draft cut, :doc:`stability`); no existing rule, code,
  profile, label or manifest changed meaning. The scope was amended by the
  maintainer: protocol imports across projects became quaat/weave#13,
  quaat/weave#19 and quaat/weave#91.

To complete the four-draft appendix, the original texts are still needed.
When available, record each draft's identity/hash and cite concrete changes.
Absence from an implementation is not, by itself, evidence of a rejected design.

