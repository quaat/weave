# Changelog

All notable changes to the agent kit. Entries are newest first. The documentation map
(`docs/development/documentation-map.md` at the repository root) requires an entry for every
change to the kit's runner, skills, examples or policy.

## Unreleased

- **Axis and identifier:** tools: agent kit (version unchanged until the next release).
- **Kind:** compatible addition.
- **Change:** the specification added the P0 profile (quaat/weave#10) with diagnostic codes
  in the new E5xx range and the result label CHECKED pure. The skill's byte-identical copy of
  `specification/diagnostics.json` (`assets/diagnostics.json`) is synced by
  `scripts/sync_skill_reference.py`, and the label lint (`weave_labels.RESULT_LABELS`)
  accepts the seventh label. The kit emits no P0 diagnostic and no CHECKED pure claim, and
  its pure `fn` extension (`weave_pure`, `P4xx`) is unchanged; its migration to P0 is a
  follow-up. The evidence envelope (`weave-evidence-envelope-v1`) keeps its six labels.
- **Semantic change:** no. Every program is accepted or rejected as before with the same
  codes, exit codes and result labels.
- **Codes and rule IDs:** none in the kit; the copied map gains the P0 codes (the E5xx range).

## 2026-10-29: 0.3.0

- **Axis and identifier:** tools: agent kit `0.2.0` -> `0.3.0`.
- **Kind:** minor (an incompatible interface change while MAJOR is 0: the runner's and the
  demos' text and `--json` output changed shape).
- **Change:** every claim the runner and the demo runners emit carries exactly one of the
  specification's six result labels, attached to that claim; tool status and runtime status
  are reported separately; a lint test fails on any other label presented as a claim
  (quaat/weave#8). Updated `README.md`, `AGENTS.md`, `docs/commands.md`, `docs/weave.md` and
  its synced skill copy, `docs/prototype-status.md`, `docs/validation.md`, the skill's
  `SKILL.md`, both demo READMEs, both demo runners and their tests, a note in both demo test
  reports, the regenerated demo artifacts and `PROVENANCE.json` (`kit_version` only).
- **Semantic change:** yes, see the migration note below. Every program is accepted or
  rejected as before with the same diagnostic codes and exit codes, and no label changes
  meaning, but for some inputs the result label a result receives changes, which the
  stability policy (Migration notes) counts as a semantic change.
- **Codes and rule IDs:** none.

| Output | 0.2.0 | 0.3.0 |
| --- | --- | --- |
| Net claims (JSON) | `accounting.status: PROVED`, `ordering.status: CHECKED WITHIN BOUNDS` | `accounting.claim_label`, `ordering.claim_label` |
| `E320` / `E321` in a net | diagnostic only | also `ordering.claim_label` `VIOLATED` (with `property`, `trace`, `marking`, bounds) / `NOT ESTABLISHED` (with the specific `reason`, `trace`, bounds) and the `accounting` claim |
| `check` (JSON) | `files[i].ok`, `flows` | adds `files[i].claim_label: CHECKED flow` |
| `lower` | `status: CHECKED LOWERING`; text `CHECKED LOWERING -> PATH` | `files`: a `CHECKED flow` claim for the source and for the output (`lowered_from`); text `CHECKED flow PATH (lowered from SRC): …` |
| `simulate` | top-level `status: SCRIPTED`; text `SCRIPTED Ok via …` | per run `claim_label: SCRIPTED / passed scenario` and `runtime_status: completed`; text `SCRIPTED / passed scenario Ok via …` plus `  runtime status: completed` |
| `verify` | `status: RECHECKED`, `invariants` (count), `scope`; text `RECHECKED …` | `accounting`: `claim_label: PROVED`, `invariants` (names), `method: certificate recheck`, `scope`; `certificate`; text `PROVED … rechecked from …` |
| `check-pure` | `status: CHECKED`; text `CHECKED FILE: …` | per file `claim_label: NOT ESTABLISHED`, `reason`; text `NOT ESTABLISHED FILE: …` |
| `run-pure` | `status: EXECUTED`, `check: CHECKED`; text `CHECKED …; EXECUTED …`, `RESULT`, `STATS` | `check` (the `NOT ESTABLISHED` claim), `runtime_status: completed`; text claim line, `runtime status:`, `result:`, `stats:` |
| `doctor`, `examples`, `test` (text) | `READY …`, `PASS n/m …`, `FAILED: …`, raw unittest output | `tool status: READY …`, `tool status: PASS n/m …`, `tool status: FAIL …`; raw output indented under `raw output (…; not a claim):` |
| Net claims (text) | `PROVED 2 accounting invariants; CHECKED WITHIN BOUNDS …` on one line | one `LABEL statement` line per claim |
| Demo runners | `status` relayed; `Net accounting: PROVED`; `FAILED CODE …` on stderr; Tiny Shop scenario `result` | `claim_label` and `runtime_status` relayed; `LABEL …` lines; `error: CODE …` on stderr; the scenario's `result` is renamed `settlement` (a member named `result` holds only a computed value) |
| `examples` scenario lesson | `Scripted final marking` | `Final marking of a scripted run` |

Pure programs report `NOT ESTABLISHED` because they are outside F0 and every specified
profile; a separate passing field for the kit's own check would state a verification result
without a label.

### Migration note: one result label per claim in runner output

- **Change:** quaat/weave#8
- **Decided by:** maintainer (ANSWER ev-20261029181318-318b9b91 on quaat/weave#8: relabel at
  the kit and envelope layer; the prototype is unchanged)
- **Axes affected:** tools (agent kit runner, pure extension commands and demo runners)

| Axis | Before | After | Source of the identifier |
| --- | --- | --- | --- |
| Tools | agent kit `0.2.0` | `0.3.0` | `PROVENANCE.json` (`kit_version`) |
| Tools | prototype version 3 | unchanged | `PROVENANCE.json` (`source.version`) |

**What changes.** No program is accepted or rejected differently, no diagnostic code, exit
code or dynamic outcome changes, and no label changes meaning. The label a result receives
changes for these inputs:

| Input | Before (0.2.0) | After (0.3.0) |
| --- | --- | --- |
| a net whose ordering check reports `E320` | diagnostic only, no claim | ordering claim `VIOLATED`, with property, trace, marking and bounds |
| a net whose ordering check reports `E321` | diagnostic only, no claim | ordering claim `NOT ESTABLISHED`, with the specific cause, any trace and the bounds |
| `verify` of a certificate | `RECHECKED` (not one of the six labels) | `PROVED`, scoped to the recheck (shared parser; ordering not rechecked) |
| `check-pure` of an accepted file; `run-pure` | `CHECKED` (a kit word the guide listed beside the labels), `EXECUTED` | `NOT ESTABLISHED` (outside every specified profile); the run is `runtime_status: completed` |
| `check` of an accepted flow file | `ok: true`, text `CHECKED FILE: …` | `CHECKED flow` (the same label, now attached and spelled in full) |
| `lower` of a flow file | `status: CHECKED LOWERING` (not one of the six labels), text `CHECKED LOWERING -> PATH` | two `CHECKED flow` claims in `files`: the source and the lowered output (`lowered_from`) |
| each `simulate` run | top-level `SCRIPTED` for the command | `SCRIPTED / passed scenario` per run (the same label, spelled in full and per claim) |

`PROVED` accounting and `CHECKED WITHIN BOUNDS` ordering (`check`, `analyze`, `lower`,
`simulate`, `examples`) keep their labels. The other 0.2.0 status words were not claims and
still are not: `READY`/`NOT READY` (`doctor`), `PASS`/`FAIL` (`examples`), `FAILED` (`test`),
`CERTIFICATE ->` (`analyze --certificate`), `EXECUTED`, `RESULT` and `STATS` (`run-pure`) became
`tool status:`, `certificate:`, `runtime status:`, `result:` and `stats:` lines, and
`EXECUTED` became `runtime_status: completed`. Every 0.2.0 command is covered: `doctor`,
`check`, `analyze`, `lower`, `simulate`, `verify`, `examples`, `test`, `check-pure`, `run-pure`.

**Who is affected.** Weave programs: none. Implementations claiming a profile: none.
Evidence and artefact consumers: scripts that read the runner's or the demos' JSON or text
(the table above lists every shape change); the evidence envelopes and their formats are
unchanged. Persisted stores: none.

**Diagnostic codes and rule IDs.** None added, deprecated or tombstoned.

**Required action.**
1. Read `claim_label` instead of `status` (or `check`), `runtime_status` for a run, and
   `ok` for tool status; treat `NOT ESTABLISHED` from `check-pure` and `run-pure` as "no
   specified guarantee", not as a failed kit check (`ok` and the exit code report that).
2. Expect `ordering` claims on `E320`/`E321` failures, with `ok: false` and the diagnostic.
3. Regenerate any stored runner output; the demo artifacts here were regenerated.
4. Persisted state: none.

**Compatibility and deprecation period.** None: the old `status` fields and text lines end
at 0.3.0 (MINOR increments for an incompatible change while MAJOR is 0).

**Verification.** Recorded in `docs/validation.md` (quaat/weave#8 addendum):
`tests/test_result_labels.py` runs every runner command and both demos in text and
`--json` and fails on any claim label outside the six; kit tests, `examples`, `test` and both
demo suites exit 0.

**Not established.** Consumers of the old output outside this repository were not searched
for.

## 2026-10-29: 0.2.0

- **Axis and identifier:** tools: agent kit `0.1.0` -> `0.2.0`; evidence schemas:
  `weave-diagnostic-v1` added.
- **Kind:** minor (an incompatible change while MAJOR is 0: kit diagnostic codes moved and the
  JSON diagnostic shape changed); new schema version.
- **Change:** `--json` diagnostics are `weave-diagnostic-v1` documents with the code's rule
  and source spans, the pure-extension codes moved to `P4xx`, and the vendored prototype was
  refreshed once from `inventory-proof/` for diagnostic spans (quaat/weave#6). Updated
  `README.md`, `docs/commands.md`, `docs/weave.md` and its synced skill copy,
  `docs/prototype-status.md`, `docs/validation.md`, the skill's `SKILL.md`, the
  `merge_sort` demo README and both demo runners' text output, `PROVENANCE.json`, the
  teaching manifest and the comment line of the four `invalid/pure_*.weave` fixtures.
- **Semantic change:** yes, see the migration note below.
- **Codes and rule IDs:** added `P400`–`P414` and `P420`–`P427` (the former kit codes with
  an `E` prefix, same numbers and meanings) and the kit rule IDs `KIT-PURE-*` listed in
  `docs/weave.md`; the specification minted N1-COLOUR-1, N1-FIRE-1, N1-FAMILY-1,
  N1-FAMILY-2 and N1-ORDER-1 for existing N1 checks.

### Migration note: kit pure-extension codes and JSON diagnostics

- **Change:** quaat/weave#6
- **Decided by:** maintainer (ANSWER ev-20261029163316-c9543754 on quaat/weave#6)
- **Axes affected:** tools (agent kit runner and pure extension); evidence schemas

| Axis | Before | After | Source of the identifier |
| --- | --- | --- | --- |
| Tools | agent kit `0.1.0` | `0.2.0` | `PROVENANCE.json` (`kit_version`) |
| Tools | prototype version 3 | version 3, refreshed once | `PROVENANCE.json` (`prototype_history`) |
| Evidence schemas | none for diagnostics | `weave-diagnostic-v1` | `evidence/schemas/diagnostic.v1.schema.json` |

**What changes.** The pure `fn` extension reported `E4nn` codes whose numbers overlapped
the specification's N1 codes with other meanings (for example the kit's empty-list fault
and the specification's coloured counterexample shared one number). Each kit code now
has the prefix `P` and the same digits and meaning: `P400`–`P414` from checking and
`P420`–`P427` from running. No program is accepted or rejected differently. The runner's
`--json` `diagnostic` object is now a `weave-diagnostic-v1` document: `file` and `line`
are replaced by `span.file` and `span.start.line` (with columns and an end), and
`format`, `category`, `rule`, `secondary_rules`, `severity`, `related` and `details` are
added. `TOOL_ERROR` keeps its code, has category `tool`, no rule and no span, and keeps
its file in `details.file`. Text output now prints `file:line:column: CODE (RULE) [stage]`.

**Who is affected.** Weave programs: none. Implementations claiming a profile: none; the
specification's codes are unchanged. Consumers of the runner's JSON or of the pure
extension's codes: scripts that compare `E4nn` codes from `check-pure`, `run-pure` or the
`pure` examples, or that read `diagnostic.file` or `diagnostic.line`. Persisted stores:
none.

| Code or rule ID | Action | Meaning | Replacement |
| --- | --- | --- | --- |
| kit `E4nn` codes of the pure extension | retired in the kit (never specification codes) | as before | `P4nn` with the same digits |
| `P400`–`P414`, `P420`–`P427` | added | the meanings listed in `docs/weave.md` | none |
| `KIT-PURE-SYNTAX-1` and the other `KIT-PURE-*` rule IDs | added | kit rules, listed in `docs/weave.md` | none |

**Required action.**
1. Replace `E4nn` by `P4nn` wherever a pure-extension code is compared, for example in
   teaching manifests (`examples/manifest.json` was updated).
2. Read `diagnostic.span.file` and `diagnostic.span.start.line` instead of
   `diagnostic.file` and `diagnostic.line`; validate against the schema if needed.
3. Persisted state: none.

**Compatibility and deprecation period.** None: the kit's `E4nn` pure codes stop at
this change, because they collided with specification codes. The specification's
`E400`, `E411`, `E412` and `E420`–`E422` keep their N1 meanings.

**Verification.** Recorded in the quaat/weave#6 pull request: `python3 scripts/weave.py
doctor`, `python3 -B -m unittest discover -s tests`, `python3 scripts/weave.py examples`,
`python3 scripts/weave.py test` and both demo suites, all exit 0.

**Not established.** Other consumers of the old JSON shape outside this repository were
not searched for.

### Earlier changes included in 0.2.0

- Added this changelog as the target of the documentation-currency rule for the kit.
- Clarified in `docs/prototype-status.md` that the kit and the vendored prototype are
  released under the MIT License.

## 2026-10-28: prototype v3

- Replaced the vendored prototype with the complete v3 snapshot from
  `specification/reference/prototype/`, hash-verified against `specification/PROVENANCE.json`
  and recorded in `PROVENANCE.json` (`prototype_history`).
- v3 adds coloured nets (`coloured.py`) and the R0 process-crash model (`durable.py`) with
  their tests.
- Updated `README.md`, `docs/prototype-status.md`, `docs/validation.md` and `docs/weave.md`
  (with its synced skill reference) for v3.

## 2026-10-28: starter kit 0.1.0

- Initial kit: `AGENTS.md`, the portable `weave` skill with the vendored v2 prototype and CLI
  (`scripts/weave.py`), teaching examples with expected diagnostics, the `tiny_shop` and
  `merge_sort` demos, and the separate pure-`fn` extension (`check-pure`, `run-pure`).
- Validation record: `docs/validation.md`.
