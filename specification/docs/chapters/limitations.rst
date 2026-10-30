Implementation discrepancies and open decisions
=====================================================

.. index:: portability, limitation, open decision

This draft distinguishes intentional language restrictions from prototype
implementation accidents. The following register should be resolved before a
stable language release; it is not a list of newly implemented features.

.. list-table::
   :header-rows: 1
   :widths: 10 40 50

   * - ID
     - Observation
     - Draft treatment / next decision
   * - LEX-01
     - CLI text decoding follows Python defaults; no encoding contract
     - Editorial UTF-8, no BOM; enforce explicitly in a future loader
   * - LEX-02
     - Unicode-aware and inconsistent identifier regexes
     - Editorial ASCII identifiers; decide Unicode normalization before widening
   * - LEX-03
     - Literal spaces in regex productions
     - Canonical spacing for portable source; decide token-based whitespace rules
   * - LEX-04
     - Python invariant AST admits some extra numeric spellings
     - Editorial decimal-only integer tokens
   * - NAME-01
     - Contextual keywords and incomplete namespace collision checks
     - Contextual words remain allowed; avoid special-type and operation collisions
   * - DIAG-01
     - Flow CLI labels can use the net filename; a lowered file has its own line
       numbers. Since quaat/weave#6, errors found in a coloured net's erased
       view report the coloured source line, and every diagnostic has a span
     - Preserve source identity; implement a real source map for lowered output
   * - TYPE-01
     - Opaque scalar names have no schema or runtime representation
     - Specify validation, equality, serialization, and ABI in a future profile
   * - TYPE-02
     - Identity checking is symbolic; uniqueness does not follow from a type
     - Preserve identity tokens/admission rules and state assumptions separately
   * - MODEL-01
     - N1 API checking shares the erased N0 structural validator
     - Pair with colour checking; full API-to-coloured-runtime refinement is open
   * - MODEL-02
     - Extra inscription variables can describe cross-order access
     - Keep parsing separate from correlation safety; no implicit equality
   * - MODEL-03
     - N0 restricts admission by abstraction; N1 checks repeated enabled admission
     - Do not transfer the N0 conclusion to multi-order systems
   * - MODEL-04
     - Payment-specific evidence and fixed correlation terminals in N0/N1
     - D-01 adopts N2 declarations; see N2-EVIDENCE-1/2 and N2-CORRELATION-1; unimplemented
   * - MODEL-05
     - Disabled calls fail in the simulator; no general waiting scheduler
     - D-02 selects D0-AWAIT-1/2; flow-level deadlock remains possible
   * - MODEL-06
     - No general bridge from symbolic F0 indices to concrete N1 firing modes
     - D0-COLOR-1/2 define the target; ambiguous signatures rejected; no runtime refinement proof
   * - RUN-01
     - R0 executes Inventory operations, not arbitrary checked F0 continuations
     - General durable execution and compiler refinement remain open
   * - RUN-02
     - Guard names have no general executable language
     - Define adapter contracts and runtime interpretation separately
   * - VER-01
     - Shared parser/certificate machinery; Python code is trusted
     - Independent validation and formal soundness work remain open; see the
       source-to-model trust boundary in :doc:`security`

Editorial portability rules are limited to source encoding/line endings,
identifier character set, canonical decimal integers, and avoidance of
special-type redefinitions or API/helper name collisions. The stricter spellings are
not claimed to be rejected by the current checker.

The grammar-driven parsers, the generated grammar audit and the Rust parser in
``crates/weave-syntax`` (quaat/weave#9), read the EBNF as tokens and do reject
non-portable identifiers, integers, whitespace characters and line breaks
(:ref:`chapters/lexical:Tokens and line endings`). Conversely they accept spacing
that the reference parser's literal spaces reject. Each difference is a probe in
:ref:`chapters/grammar:Reference parser discrepancies`, asserted by
``scripts/grammar_audit.py``. These probes record instances of LEX-01 to LEX-04;
they do not decide those items.

Unsupported source features
---------------------------------

F0/N0/N1 do not include general expressions in flows, pure functions, if/else,
loops, recursion, lists, tuples as values, parallel/fork blocks, higher-order
calls, closures, imports, general generics, subtyping, open unions, borrowing,
effect handlers, retry, within, durations, or statements after a terminal match.
The P0 profile (:doc:`pure`) has pure functions, if/else, direct recursion,
lists and records in separate pure files that flows cannot call yet; it has no
loops, fork/join, higher-order calls, closures, imports or termination
checking.

General arithmetic exists only inside invariant equalities. The net grammar has
no inhibitor arcs, arbitrary colour expressions, timed transitions, or priorities.
Do not infer these features from their presence in other Petri-net tools.

Unestablished guarantees
------------------------------

There is no general proof of termination, liveness, fairness, deadlock freedom,
arbitrary-order ordering, real provider truthfulness, production storage
durability, network authentication, safe upgrades, or compiler/runtime refinement.
Per-colour accounting proofs are broader than the finite exploration but do not
establish those other properties.

Production policy decisions
---------------------------------

A production specification still needs an explicit capability-enforcement model,
wire contracts, identity/key retention rules, Unicode policy, cancellation and
lease scheduling, bounded resource accounting, persistence model, upgrade and
schema migration rules, and an independently reviewable conformance suite.
These should be added as versioned profiles with implementation evidence rather
than inferred from the current Inventory demonstration.

