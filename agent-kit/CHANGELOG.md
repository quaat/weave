# Changelog

All notable changes to the agent kit. Entries are newest first. The documentation map
(`docs/development/documentation-map.md` at the repository root) requires an entry for every
change to the kit's runner, skills, examples or policy.

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
