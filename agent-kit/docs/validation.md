# Validation of starter kit 0.1.0

Date: 2026-10-28. Environment: CPython 3.12.14 on Linux.

| Check | Result |
| --- | --- |
| Original prototype regression suite | 107 tests passed |
| Additional runner/integration suite | 14 tests passed |
| Teaching manifest | 28 expectations matched: 8 accepted flows, 10 rejected flows, 6 rejected net fragments, 1 rejected full net, 3 scripted outcomes |
| Canonical skill and Claude adapter metadata | Both validated |
| Original bundled source integrity | Every original file matches its input snapshot |
| Portable skill | Copied to a directory containing spaces and run from another working directory; check and targeted tests passed |
| Relative links in new Markdown documents | Resolved successfully |
| Language-reference copy | Identical to authoritative `docs/weave.md` |

Commands used:

```bash
python3 scripts/weave.py doctor
python3 scripts/weave.py examples
python3 scripts/weave.py test
python3 -B -m unittest discover -s tests -q
python3 scripts/weave.py simulate examples/valid/checkout_propagating.weave --entry checkout_propagating --outcome all
```

The integration suite exercises mixed valid/invalid batches, unsafe-net rejection
before flow success, exhausted search budgets, original `?` source locations,
checked lowering, refusing to overwrite inputs, preserving outputs on failure,
all three outcome traces, unsupported simulation entries, missing files,
source-bound certificate rejection, empty test selection, incorrect corpus
expectations, relocated skills, and snapshot/reference integrity.

A separate agent used the skill instructions with no prior task history to check
the propagating checkout, run its Unknown trace, and diagnose the early-return
leak. It correctly reported `recovery_queue=1`, `registrations=1`, the outstanding
adapter request, and `E204` at the original `?` line. It distinguished static
accounting, bounded ordering, and scripted execution. No extra explanatory setup
or implementation edits were needed.

The checks establish this package's tested behavior, not general language or
runtime correctness. Python 3.11 compatibility is inherited from the prototype's
declared minimum; this release was executed on 3.12.14. Windows, macOS, and the
Claude Code UI were not exercised. There are no symlinks or shell-only runtime
dependencies, and the Claude adapter was validated as a file, not installed in a
live Claude session. No model-token or cost reduction has been benchmarked.

## Addendum: pure-function extension (2026-10-28)

Environment: Python 3.13.5 on Linux. The kit added `weave_pure`, its
`check-pure`/`run-pure` commands, 6 pure corpus fixtures, and
`demos/merge_sort`. The vendored prototype is unchanged, and the provenance
hashes still match.

| Check | Result |
| --- | --- |
| Original prototype regression suite | 107 tests passed |
| Kit tests (`tests/`) | 59 passed: 14 runner/integration + 24 pure language + 21 pure runtime |
| Teaching manifest | 34 expectations matched (original 28 + 2 accepted and 4 rejected pure programs) |
| Merge-sort demo tests | 13 passed |
| Tiny Shop demo tests | 17 passed |

Details and limits are in `demos/merge_sort/TEST_REPORT.md`. Termination is not
checked. The scheduler's pairing and cleanup properties are tested, not proved.

## Addendum: prototype version 3 (2026-10-28)

Environment: Python 3.13.5 on Linux. The vendored prototype was replaced in full
with version 3, copied from the specification's reference snapshot and
hash-verified against `specification/PROVENANCE.json`. `PROVENANCE.json` records
the new source and per-file hashes. No kit code, example, or expectation changed.

| Check | Result |
| --- | --- |
| Original prototype regression suite (`weave.py test`) | 143 tests passed |
| Kit tests (`tests/`) | 59 passed, including the provenance hash check |
| Teaching manifest (`weave.py examples`) | 34 expectations matched |
| Merge-sort demo tests | Passed; `run_demo.py` concurrent run succeeded |
| Tiny Shop demo tests | Passed; `run_demo.py` succeeded |
| `weave.py doctor` | READY |

The only behaviour difference observed is the more specific `E204` message for
`?` early returns. Demo artifacts were not regenerated.

## Addendum: diagnostics with rules and spans (2026-10-29, quaat/weave#6)

Environment: Python 3.13 on Linux. The vendored prototype was refreshed once from
`inventory-proof/` (`checker.py`, `coloured.py`, `durable.py`, `README.md` and three test
files), byte-identical to the specification's reference snapshot; `PROVENANCE.json`
records the hashes before and after. The pure extension's codes moved to `P4xx`, the
teaching manifest's four pure expectations and fixture comments were updated, and
`--json` diagnostics became `weave-diagnostic-v1` documents.

| Check | Result |
| --- | --- |
| Original prototype regression suite (`weave.py test`) | 143 tests passed |
| Kit tests (`tests/`) | 69 passed, including the provenance hash check and `test_diagnostics.py` |
| Teaching manifest (`weave.py examples`) | 34 expectations matched |
| Merge-sort demo tests | 13 passed |
| Tiny Shop demo tests | 17 passed |
| `weave.py doctor` | READY |

Accepted and rejected programs are unchanged; only the pure-extension code prefix and the
diagnostic format changed. Demo artifacts and test reports were not regenerated.

## Addendum: result labels in runner output (2026-10-29, quaat/weave#8)

Environment: Python 3.13.5 on Linux. The vendored prototype is unchanged. The runner and
both demo runners now emit each claim with one of the six result labels and report tool
and runtime status separately (kit `0.3.0`); `tests/test_result_labels.py` lints the text
and `--json` output of every runner command, both demos and every wrapped evidence
envelope. The demo artifacts were regenerated with the commands in the demo READMEs.

| Check | Result |
| --- | --- |
| Original prototype regression suite (`weave.py test`) | 143 tests passed |
| Kit tests (`tests/`) | 92 passed, including `test_result_labels.py` and the provenance hash check |
| Teaching manifest (`weave.py examples`) | 34 expectations matched |
| Merge-sort demo tests | 13 passed |
| Tiny Shop demo tests | 17 passed |
| `weave.py doctor` | `tool status: READY` |

Accepted and rejected programs, diagnostic codes and exit codes are unchanged. The output
shape and, for some inputs, the label a result receives changed; see the migration note in
`CHANGELOG.md`.
