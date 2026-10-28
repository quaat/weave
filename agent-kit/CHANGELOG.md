# Changelog

All notable changes to the agent kit. Entries are newest first. The documentation map
(`docs/development/documentation-map.md` at the repository root) requires an entry for every
change to the kit's runner, skills, examples or policy.

## Unreleased

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
