# Verification and independent review

## Before coding

Every acceptance criterion gets a stable ID (`AC-1`, `AC-2`, … in document order, from the
issue's "Acceptance criteria" and "Definition of done" checklists), a verification plan and a
preserved text digest. The PLAN event records them with the issue's requirements digest
(title, milestone, scope, criteria, dependencies; checkbox ticks are ignored). The
orchestrator maintains the matrix

> criterion → implementation location → test or check → result → evidence → documentation location

as the `criteria_map` of IMPLEMENTATION_READY. A material requirement change invalidates the
plan and any review; the bar is never lowered silently.

The roadmap's definition of done applies to every feature: grammar and rules,
implementation, positive and negative examples, adversarial behaviour, diagnostics, source
mapping, documentation and conformance metadata. Justified non-applicability is recorded
explicitly. Evidence labels keep their meaning: accounting proofs, bounded checking,
scripted behaviour and general runtime claims are different things.

## Checks

Derived from current CI and the affected components, run in each component's directory
(`claim` lists them in the packet):

| Component | Checks |
| --- | --- |
| `inventory-proof/` | unit tests; `demo.py` regenerates committed outputs (`git diff --exit-code`); `durable.py` crash model |
| `agent-kit/` | `weave.py doctor`; kit tests; `weave.py examples`; `weave.py test`; demo tests |
| `specification/` | `make validate-offline`; `make singlehtml text`; HTML audits |
| Workflow | `python3 -m unittest discover -s tools/weave_workflow/tests -t .` |
| Every change | `python3 -m tools.weave_workflow docs-audit` (and `--base` for the change) |
| Rust workspace (`Cargo.toml`, `crates/`; from the repository root) | `cargo fmt --all --check`, `cargo clippy --all-targets -- -D warnings`, `cargo test --all` (corpus round trip and spans, diagnostics, adversarial input). The differential test against the generated grammar audit runs in the specification's `make validate-offline` when `cargo` is on `PATH`; without it the comparison is reported as not established, so a verifier that reports it must have `cargo` available |

## Independent review

`python3 -m tools.weave_workflow review N --worktree PATH` builds the packet (dry run);
`--apply` publishes REVIEW_REQUESTED and launches the reviewer. The packet contains: issue
and milestone scope, criteria, the state of every blocking prerequisite and of the predecessor
milestones' exit gates (from `plan`), maintainer decisions; the base (merge-base) and head SHAs
and requirements digest of a clean committed candidate, with the commands to inspect the diff
in the worktree; the published VERIFICATION_RESULT checks with exit codes, CI links
(`--ci-link`), accepted limitations (`--limitation`) and further evidence files (`--evidence`);
the documentation impact list, documents changed and the DOCS_AUDIT_RESULT; local and safety
review results and finding dispositions; earlier change requests. Codex is not told to agree
with anything.

The reviewer is a **fresh, ephemeral, read-only** `codex exec` session: `--sandbox read-only
--ephemeral -c mcp_servers={}`, run from the candidate worktree, with `GH_TOKEN`,
`GITHUB_TOKEN`, `SSH_AUTH_SOCK` and similar variables removed and `GH_CONFIG_DIR` pointed at
an empty directory. Its final message must satisfy
`tools/weave_workflow/schemas/review-result.v1.schema.json` (`--output-schema`), and is then
validated again independently. `codex exec review` is not used, because it is not known to
honour an arbitrary schema.

The result must carry run, attempt and request identity, base and head SHAs, requirements
digest, `PASS`, `REQUEST_CHANGES` or `BLOCKED`, a criterion-by-criterion assessment including
the documentation criteria (`DOC-n`), findings with stable IDs (`F-n`), severity, blocking
flag, location, reproduction and required correction, checks actually run, limitations and a
summary. CLI, version and session id are recorded as provenance. The orchestrator publishes
the result in the issue and, when the task's PR (`agent/N-…`) exists, mirrors it there as a
relayed comment, never as a GitHub approval. A PASS also publishes READY_TO_MERGE and sets
`agent:ready-to-merge`.

The reviewer runs in a read-only sandbox, so it cannot create temporary files and may be
unable to rerun test suites; the packet's verification results and CI links carry that
evidence, and the reviewer reports what it could not rerun as a limitation.

## Accepting a result

`review.accept` rejects the result unless the schema, identity, current head, base and
requirements all match the request. A PASS is rejected as inconsistent if any criterion is
missing or not satisfied, or any finding is blocking or high or critical. Process exit,
silence, or prose containing "pass" is never approval; a rejected result is recorded as a
review outage (BLOCKED), not as a verdict.

Every blocking finding and unmet criterion must be resolved; severity does not excuse a
failed criterion. Each finding gets a FINDING_DISPOSITION: fixed (with evidence), rejected
(with evidence and reviewer concurrence in a later round), or accepted by an authorised
maintainer where policy permits. Findings are never dismissed unilaterally to obtain PASS.

After fixes, affected checks and the documentation audit are rerun and a fresh review of the
current candidate is requested, reusing finding IDs and stating whether the review is full or
a justified delta. An old approval is never relabelled with a new SHA. The budget is three
standard review-and-fix rounds per attempt plus up to two extra rounds (five in total,
`review.max_rounds_per_attempt`), with a per-review timeout (`review.timeout_seconds`). The
extra rounds, authorised by the maintainer (#72), are used only when the remaining findings
are narrow (wording, documentation, small fixes), and the coordinator records on the issue
why each one is used. For larger findings after the standard rounds, or when findings remain
after the fifth round, the work is preserved, genuine rework returns to In Progress,
`agent:needs-human` is added, and the disagreement is summarised for the maintainer.
