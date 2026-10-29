<!--
SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
SPDX-License-Identifier: MIT
-->

# Evidence schemas and tooling

This component defines three versioned evidence formats and the tooling that reads them,
converts existing step records to traces, wraps the existing evidence files in envelopes and
exports canonical nets (quaat/weave#7). It is evidence tooling written in Python with the
standard library only (written for Python 3.11 or later; tested with 3.13). It is not the production checker or runtime
(`docs/development/implementation-language.md`), and it defines no Weave semantics: the
prototype in `inventory-proof/` decides what is accepted, and the specification defines what
the result labels mean.

## Layout

| Path | Contents |
| --- | --- |
| `schemas/` | The three JSON Schemas (draft 2020-12) |
| `weave_evidence/schema.py` | Strict validator for the JSON Schema subset the schemas use |
| `weave_evidence/documents.py` | Format registry, refusal of unknown formats, reader checks, hash verification |
| `weave_evidence/netexport.py` | Canonical-net exporter, reading the prototype's parser output |
| `weave_evidence/traces.py` | Converters from existing step records to traces |
| `weave_evidence/wrap.py` | Wrappers that put each claim of an existing evidence file in an envelope |
| `weave_evidence/__main__.py` | Command line |
| `tests/` | Unit tests |

## Formats

| `format` identifier | Schema | Contents |
| --- | --- | --- |
| `weave-canonical-net-v1` | `schemas/canonical-net.v1.schema.json` | Net name, profile, source hash, parameters, colour sorts, places with owner and indices, initial marking, transitions with binder, guards and arcs (kind, place, weight, inscription) |
| `weave-trace-v1` | `schemas/trace.v1.schema.json` | One ordered list of steps for checker counterexamples, scheduler runs, scenario tests and editor replay (`kind`: `counterexample`, `scheduler-run`, `scenario`, `replay`) |
| `weave-evidence-envelope-v1` | `schemas/evidence-envelope.v1.schema.json` | One per-run claim with its result label, runtime status, profiles, bounds, assumptions, scope, completeness, the wrapped file, source and dependency hashes, tool versions and an optional trace hash |

Every document names its format in the top-level `format` field. Each schema fixes that field
with `const`.

### Reading a document

`documents.assess` accepts a document only if all of these hold:

1. It is one strict JSON document: duplicate keys, `NaN` and `Infinity` are refused.
2. It is an object whose top-level `format` is one of the three identifiers above. A missing
   or non-string `format`, or any other identifier (including `weave-trace-v2`, a
   different spelling, or one of the existing prototype identifiers such as
   `weave-place-invariant-v1`), is refused with a message that names the value found. It is
   never read as a nearby version and never reported as valid.
3. It validates against that format's schema.
4. It passes the format's reader checks:
   - canonical net: place, transition and parameter names are unique; places and
     transitions are sorted by name; guards are sorted and unique; arcs are ordered by kind (take, read, put) then place
     and are unique per kind and place; every arc names a declared place; an inscription
     has as many variables as its place has indices; a binder and each indexed place have as
     many entries as `colour_sorts`; `initial_marking` lists every place once, in place
     order, and names only declared parameters;
   - trace: step `sequence` numbers increase strictly; token counts in a marking are
     unique per place and colour and sorted; `outcome` is not one of the six result labels;
   - envelope: no duplicate paths in `sources` or `dependencies`, no duplicate tool names,
     no duplicate profile names.

The existing evidence files themselves are not documents in these formats, and the reader
refuses them.

### The envelope

- `claim_label` is one of exactly six strings, the first column of the result vocabulary
  table in `specification/docs/chapters/verification.rst`: `PROVED`,
  `CHECKED WITHIN BOUNDS`, `CHECKED flow`, `SCRIPTED / passed scenario`, `VIOLATED`,
  `NOT ESTABLISHED`. The schema enumerates them as a closed set; a test compares the set
  with the specification table. Linting tool output for these labels is quaat/weave#8, not
  this component.
- `runtime_status` is separate from the label: `waiting`, `timed out`, `completed`, or
  `null` when the producer recorded no runtime status. An application outcome such as
  `Unknown` is neither a runtime status nor a label; in a trace it is the `outcome`.
- The schema adds two consistency rules: `CHECKED WITHIN BOUNDS` requires a `bounds` object
  and `completeness.complete` equal to `true`; `VIOLATED` requires a `trace`.
- `profiles` names the profiles the claim was made under, each with the specification
  revision that defines it. The profiles a tool supports are recorded separately, in
  `tools[].supported_profiles`.
- `wrapped` is the evidence file the claim comes from, with the SHA-256 of its bytes and its
  own `format` value (`null` if it has none). `claim.pointer` is a JSON Pointer to the claim
  inside that file.
- `sources` (at least one) and `dependencies` (at least one) are repository-relative paths
  with the SHA-256 of each file's bytes. `trace`, if present, is the SHA-256 of the trace
  document's canonical bytes (below).

## Commands

Run from the repository root.

```bash
python3 -m evidence.weave_evidence formats                    # list the implemented identifiers
python3 -m evidence.weave_evidence validate FILE...           # check documents
python3 -m evidence.weave_evidence wrap [FILE...] [--out DIR] # wrap existing evidence files
python3 -m evidence.weave_evidence verify DIR/envelopes/*.json  # validate envelopes and recompute hashes
python3 -m evidence.weave_evidence export-net --profile N0 inventory-proof/Inventory.weave [--out FILE]
python3 -m evidence.weave_evidence export-net --profile N1 inventory-proof/Inventory.coloured.weave [--out FILE]
python3 -m unittest discover -s evidence/tests -t .           # tests
```

`wrap` with no file names wraps every file in the table below. With `--out DIR` it writes
one envelope per claim to `DIR/envelopes/` (named from the wrapped path, `/` written as
`__`, followed by the claim pointer, `/` written as `_`) and each trace to
`DIR/traces/<sha256>.json`; `verify` finds an envelope's trace at `../traces/<sha256>.json`
relative to the envelope. Written documents use
the canonical byte form: keys sorted, two-space indentation, UTF-8, a final newline.

Exit status: 0 when every input is valid or every hash recomputes; 1 when an input is
refused or invalid, a hash does not recompute, a wrapper refuses its input, or the prototype
parser rejects a net source given to `export-net`; 2 for a usage error.

## Wrapped evidence files

The wrappers only read these files. Each refuses a `format` value or a record shape it does
not implement, and refuses a result value it does not map (for example `status` other than
the one listed).

| File | Its `format` | Envelopes and label |
| --- | --- | --- |
| `inventory-proof/proof.json` | `weave-place-invariant-v1` | One per entry of `invariants`; label from its `status` (`PROVED`) |
| `inventory-proof/ordering.json` | `weave-one-order-check-v2` | One per entry of `properties`; label from its `status` (`CHECKED WITHIN BOUNDS`) |
| `inventory-proof/colour-proof.json` | `weave-colour-invariant-v1` | One per entry of `aggregate` and `families`; label from its `status` (`PROVED`) |
| `inventory-proof/colour-check.json` | `weave-colour-exploration-v1` | One per name in `properties`, which carry no status. `coloured.explore_colours` returns this document only when every listed property held in every explored state; otherwise it raises (E420 for a violation, E422 when a bound or the state budget is exceeded, E400 for an unsupported property); so the label is `CHECKED WITHIN BOUNDS` when `complete` is `true`, else `NOT ESTABLISHED` |
| `inventory-proof/scenarios.json` | none (array) | One per run, with a trace. Runs carry no status; `demo.py` writes the file only after `simulate.simulate` returned for each scripted reply, so the label is `SCRIPTED / passed scenario` |
| `inventory-proof/durable-scenarios.json` | none (array) | One per case, with a trace; `status: PASSED` maps to `SCRIPTED / passed scenario` |
| `specification/validation/report.json` | `weave-specification-validation-v1` | `CHECKED flow` for each case accepted and listed in `accepted_flows_checked_original_and_lowered_against_n0_and_n1`; `VIOLATED` for each entry of `counterexamples`, with the trace read from `validation/counterexample-<code>.txt`; `SCRIPTED / passed scenario` for each entry of `scenarios` |

All of these files except `colour-check.json` are named in quaat/weave#7;
`colour-check.json` is wrapped with them. In `report.json`, the expected-rejection cases
(`/cases/8` to `/cases/24`) and the fields `reference_integrity`, `lease`, `n0` and `n1` are
listed as not wrapped: they record a diagnostic code or summary counts, not a claim under one
of the six labels. No existing file
records a runtime status, so every wrapped envelope has `runtime_status: null`.

Sources and dependencies recorded for each file (paths in the first four rows are under
`inventory-proof/`):

| File | `sources` | `dependencies` |
| --- | --- | --- |
| `proof.json`, `ordering.json` | `Inventory.weave` | `checker.py`, `demo.py` |
| `colour-proof.json`, `colour-check.json` | `Inventory.coloured.weave` | `coloured.py`, `checker.py`, `demo.py` |
| `scenarios.json` | `Inventory.weave`, `examples/checkout_propagating.weave` | `simulate.py`, `checker.py`, `demo.py` |
| `durable-scenarios.json` | `Inventory.coloured.weave` | `durable.py`, `coloured.py`, `checker.py`, `demo.py` |
| `report.json` | the case or scenario source, and the nets it was checked against | `specification/scripts/validate.py`, `specification/examples/manifest.json`, `checker.py`, `coloured.py` and `simulate.py` in `specification/reference/prototype/`; for `VIOLATED`, also the counterexample text |

What the hashes show: each hash identifies the bytes of a file present when the envelope was
made, and `verify` recomputes them. The wrapper does not re-run the producer, so a hash does
not by itself show that the wrapped file was produced from those exact files. Where the
original records its own `source_sha256` (`proof.json`, `ordering.json`,
`colour-proof.json`, `colour-check.json`), the wrapper checks that value against the source
file and refuses on a mismatch. Regeneration of the originals is checked by the
`inventory-proof` and `specification` checks in `AGENTS.md`.

Tool versions: each envelope lists the producing modules, this tooling
(`evidence/weave_evidence`, version `0.1.0`) and, for `report.json`, the Python version the
report records. A prototype module gets version `3`, the `version` of
`weave-inventory-proof.zip` in `specification/PROVENANCE.json`, only if its bytes match that
manifest's hash for the pinned snapshot copy; otherwise its version is `null`. Supported
profiles follow the "Reference" column of the profile table in
`specification/docs/chapters/status.rst`: `checker.py` F0 and N0, `coloured.py` N1,
`durable.py` R0; other modules none.

The wrapped outputs are generated, not committed. Committed copies would repeat hashes of
files that change whenever the prototype or the specification evidence is regenerated, and
nothing in CI would check them yet. The tests regenerate every envelope and trace from the
repository files and check them instead.

## Traces

| Converter | Input | `kind` |
| --- | --- | --- |
| `from_simulation` | an element of `inventory-proof/scenarios.json` | `scenario` |
| `from_durable` | an element of `inventory-proof/durable-scenarios.json` | `scenario` |
| `from_counterexample` | a rendered E320 or E420 diagnostic (`specification/validation/counterexample-*.txt`) | `counterexample` |
| `from_scheduler_run` | an agent-kit pure-runtime trace (`agent-kit/demos/merge_sort/artifacts/trace-*.json`) | `scheduler-run` |

`NET` events become `fire` steps and `RETURN` events become `return` steps. Token counts are
kept as recorded, including zeros, as `{place, colour, count}` entries; a key such as
`sold[tenant,order1]` becomes place `sold` and colour `["tenant", "order1"]`. Fields the
format does not model are kept in `detail` or `context`, which v1 readers do not interpret.
`model` is `null` in converted traces because none of the inputs records the net identity.
No existing artefact is an editor replay, so the `replay` kind is exercised only by a
hand-written test document. The agent-kit traces are converted in a test only; they are not
wrapped in envelopes.

## Canonical nets

`export-net` parses a net source with the prototype parser (`checker.parse_net` for N0,
`coloured.parse_coloured` for N1), imported from `inventory-proof/` without writing bytecode
there, and reorders the result: places and transitions by name, arcs by kind and place,
guards by name (the prototype only tests guards for membership, so their order carries no
meaning). Apart from `source_sha256`, the export does not depend on declaration order, and
repeated exports are byte-for-byte identical; the tests check both. `source_sha256` is
computed as the prototype computes it, from the decoded source text. A source the prototype
parser rejects is refused with its diagnostic code. The tests
check the N0 export against the incidence matrix and initial marking in `proof.json`, and
the N1 export against `transition_inscriptions` in `colour-proof.json`.

A canonical net records net structure only. It does not record invariants, the order-check
model, linear resource declarations, enums, APIs or `runtime_state` declarations. The colour
sorts of an N1 net are the prototype's positional pair (`tenant`, `order`).

## Stability policy

The formats follow the evidence-schema axis of
`specification/docs/chapters/stability.rst`:

- Each identifier has the form `weave-<artefact>-v<N>` in the top-level `format` field.
- Any change to a format's fields, their meaning or the reader checks listed above needs the
  next `N`. An identifier never changes meaning and a retired identifier is never reused.
- Unrecognised versions: the reader refuses a missing or unrecognised identifier, names it,
  and never reports success on it (tests in `tests/test_versions.py`).
- The existing evidence files keep their bytes and their own identifiers; the envelopes wrap
  them alongside. They remain unversioned or prototype-versioned files, and this reader does
  not treat them as documents in the three formats.
- `evidence/weave_evidence` carries its own semantic version (`__version__`, `0.1.0`).

Adding these formats changes no existing artefact, rule ID, diagnostic code, profile or
label, so this change carries no migration note. The specification does not describe the
formats yet; a later change will.

## Tests

`python3 -m unittest discover -s evidence/tests -t .` runs:

- `test_schemas.py`: the three schema files and identifiers, the supported keyword subset,
  the label set against `verification.rst`, and, where the optional `jsonschema` package is
  installed, a meta-schema check and agreement with an independent validator;
- `test_versions.py`: unknown, missing and non-string `format` values are refused by the
  reader, the command line and the wrappers;
- `test_wrap.py`: every file above is wrapped, every envelope and trace is valid, labels
  match the originals' result fields, originals are unchanged (`git diff --exit-code`),
  every hash recomputes, and changed sources, dependencies, wrapped files and traces are
  detected;
- `test_traces_and_nets.py`: the scenario and crash-case trace conversions keep every
  recorded value, the counterexample and scheduler-run conversions produce valid traces,
  malformed traces and nets are rejected, and the canonical-net exports agree with the
  certificates.

The tests check the files listed here; they do not show that any other tool's output
conforms to these formats.
