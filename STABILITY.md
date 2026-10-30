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
| Tools (checker, analyser, runtime, CLI) | Toolchain maintainer | Semantic versioning per tool | Prototype version 3 (`specification/PROVENANCE.json`); agent kit `0.3.0` (`agent-kit/PROVENANCE.json`); evidence tooling `0.2.0` (`evidence/weave_evidence/__init__.py`); Rust crates `weave-syntax`, `weave-check` and `weave-cli` (command `weave`) `0.2.0` and `weave-eval` `0.1.0` (`crates/*/Cargo.toml`; modules-1 and `--root`, #12, were a compatible addition), the last three for P0 only; no general production toolchain yet |
| Profiles (F0, N0, N1, R0, P0; targets D0, N2) and versioned extensions | Language maintainer | Profile name plus the specification revision that defines it; an extension has a name and an integer version | Defined by 0.2-draft (P0 added by #10); extension `modules-1` of P0 added by #12 |
| Evidence schemas (certificates, conformance artefacts, traces, machine-readable diagnostics) | Toolchain maintainer | `weave-<artefact>-v<N>` in the `format` field | Format strings such as `weave-place-invariant-v1` (`inventory-proof/proof.json`); machine-readable diagnostics use `weave-diagnostic-v1` (`evidence/schemas/diagnostic.v1.schema.json`, added by #6); many existing files, including scenario results and the agent-kit traces, have no `format` field yet |
| Persisted store format | Runtime maintainer | `weave-store-v<N>` in the store's metadata, checked before any other access (a convention, not a storage design) | None yet; first identifier assigned in M5 (#59) |

The chapter gives the bump rule for each axis, the source of each current identifier, and a
reproducible list of which existing evidence files carry a `format` field and which do not.

## Rules in brief

- **Compatibility anchors.** Diagnostic codes (such as `E204`) and rule IDs (such as
  `F0-CALL-1`) keep their meaning and are never reused. Human wording may change. Each
  code maps to one principal rule and optional secondary rules in
  `specification/diagnostics.json`; the P0 profile's codes use the `E5xx` range, the
  modules-1 extension's codes the `E600`–`E619` range, and the agent kit's pure-extension
  codes the `P4xx` range.
- **Deprecation.** Mark deprecated, keep the meaning, keep recognising it, retire only by
  tombstoning, never reuse.
- **Migration notes.** Every semantic change must carry one; use
  [`docs/templates/migration-note.md`](docs/templates/migration-note.md). Changelog entries
  follow [`docs/templates/changelog-entry.md`](docs/templates/changelog-entry.md).
- **Result labels.** Tool output names each claim with exactly one of the seven result
  labels (`PROVED`, `CHECKED WITHIN BOUNDS`, `CHECKED flow`, `CHECKED pure`,
  `SCRIPTED / passed scenario`, `VIOLATED`, `NOT ESTABLISHED`) and reports tool and runtime
  status separately; changing which label a result receives is a semantic change (the
  verification chapter, "Result labels in tool output"). `CHECKED pure` was added with the
  P0 profile (#10) as a compatible addition.
- **Profile meanings are preserved.** New pure syntax, generalised identity and durable
  execution arrive as versioned extensions or new profiles, never by changing F0, N0, N1
  or R0. Pure computation arrived this way as the new profile P0 (#10), and local modules
  and the `use net` header as the versioned extension modules-1 of P0 (#12), with its own
  corpus manifest (`weave-modules-conformance-v1`).
- **Unrecognised versions are never success.** A tool must reject evidence or a store whose
  format it does not implement, naming the identifier, or report the claim as not
  established. This binds versioned schemas; the existing unversioned files are not
  treated as conformant versioned evidence or given a passing result until migrated, nor
  rejected retroactively.
  The v3 prototype meets this only partly; the chapter states the gaps and
  what tracks them.
