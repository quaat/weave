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
| Evidence schemas (certificates, conformance artefacts, traces) | Toolchain maintainer | `weave-<artefact>-v<N>` in the `format` field | Seven format strings, for example `weave-place-invariant-v1` (`inventory-proof/proof.json`); many existing files, including scenario results and the agent-kit traces, have no `format` field yet |
| Persisted store format | Runtime maintainer | `weave-store-v<N>` in the store's metadata, checked before any other access (a convention, not a storage design) | None yet; first identifier assigned in M5 (#59) |

The chapter gives the bump rule for each axis, the source of each current identifier, and a
reproducible list of which existing evidence files carry a `format` field and which do not.

## Rules in brief

- **Compatibility anchors.** Diagnostic codes (such as `E204`) and rule IDs (such as
  `F0-CALL-1`) keep their meaning and are never reused. Human wording may change.
- **Deprecation.** Mark deprecated, keep the meaning, keep recognising it, retire only by
  tombstoning, never reuse.
- **Migration notes.** Every semantic change must carry one; use
  [`docs/templates/migration-note.md`](docs/templates/migration-note.md). Changelog entries
  follow [`docs/templates/changelog-entry.md`](docs/templates/changelog-entry.md).
- **Profile meanings are preserved.** New pure syntax, generalised identity and durable
  execution arrive as versioned extensions or new profiles, never by changing F0, N0, N1
  or R0.
- **Unrecognised versions are never success.** A tool must reject evidence or a store whose
  format it does not implement, naming the identifier, or report the claim as not
  established. This binds versioned schemas; the existing unversioned files are not
  treated as conformant versioned evidence until migrated, nor rejected retroactively.
  The v3 prototype meets this only partly; the chapter states the gaps and
  what tracks them.
