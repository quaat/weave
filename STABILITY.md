<!--
SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
SPDX-License-Identifier: MIT
-->

# Stability and versioning

This is a summary. The authoritative policy is the specification chapter
[Stability and versioning policy](specification/docs/chapters/stability.rst)
(published in the [specification](https://quaat.github.io/weave/)). Where this summary and
the chapter differ, the chapter wins.

## Five independent axes

| Axis | Owner (role) | Format | Current identifier |
| --- | --- | --- | --- |
| Language (this specification) | Language maintainer | `MAJOR.MINOR`, `-draft` suffix for drafts | `0.2-draft` (`specification/docs/conf.py`, `specification/PROVENANCE.json`) |
| Tools (checker, analyser, runtime, CLI) | Toolchain maintainer | Semantic versioning per tool | Prototype version 3 (`specification/PROVENANCE.json`); agent kit `0.1.0` (`agent-kit/PROVENANCE.json`); production toolchain: none yet |
| Profiles (F0, N0, N1, R0; targets D0, N2) | Language maintainer | Profile name plus the specification revision that defines it | Defined by 0.2-draft |
| Evidence schemas (certificates, conformance artefacts, traces) | Toolchain maintainer | `weave-<artefact>-v<N>` in the `format` field | For example `weave-place-invariant-v1` (`inventory-proof/proof.json`); traces: none yet |
| Persisted store format | Runtime maintainer | Reserved until the durable store is specified (M5) | None yet |

The chapter gives the bump rule for each axis and the source of every current identifier.

## Rules in brief

- **Compatibility anchors.** Diagnostic codes (such as `E204`) and rule IDs (such as
  `F0-CALL-1`) keep their meaning and are never reused. Human wording may change.
- **Deprecation.** Mark deprecated, keep the meaning, keep recognising it, retire only by
  tombstoning, never reuse.
- **Migration notes.** Every semantic change carries one; use
  [`docs/templates/migration-note.md`](docs/templates/migration-note.md). Changelog entries
  follow [`docs/templates/changelog-entry.md`](docs/templates/changelog-entry.md).
- **Profile meanings are preserved.** New pure syntax, generalised identity and durable
  execution arrive as versioned extensions or new profiles, never by changing F0, N0, N1
  or R0.
- **Unrecognised versions are never success.** A tool rejects evidence or a store whose
  format it does not implement, or reports the claim as not established.
