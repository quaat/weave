<!--
SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
SPDX-License-Identifier: MIT
-->

# Migration note: <short title of the change>

<!-- Required for every semantic change; see the "Stability and versioning policy" chapter of
the specification (specification/docs/chapters/stability.rst). Replace every <...>.
Write "none" for a section that does not apply; do not delete it. State facts with
their sources and name the commands you ran. -->

- **Change:** <issue and pull request, for example quaat/weave#NN>
- **Decided by:** <role that approved the change, for example language maintainer>
- **Axes affected:** <language | tools | profiles | evidence schemas | persisted store>

## Identifiers

| Axis | Before | After | Source of the identifier |
| --- | --- | --- | --- |
| <axis> | <identifier before> | <identifier after, or "unchanged"> | <file that records it> |

## What changes

<Describe the behaviour before and after. Name the profiles, rule IDs and diagnostic codes
involved. Say whether previously accepted programs are now rejected, previously rejected
programs are now accepted, a diagnostic code or result changes for the same input, a
dynamic outcome changes, or an evidence or store format changes.>

## Who is affected

- **Weave programs:** <which programs, and how to recognise them>
- **Implementations claiming a profile:** <what they must change>
- **Evidence and artefact consumers:** <which formats, and what older readers do>
- **Persisted stores:** <which stores, or "none">

## Diagnostic codes and rule IDs

<List codes and rule IDs that are added, deprecated or tombstoned, with their meaning.
Existing codes and rule IDs keep their meaning and are never reused; only human wording
may change.>

| Code or rule ID | Action (added, deprecated, tombstoned) | Meaning | Replacement, if any |
| --- | --- | --- | --- |
| <E2xx or RULE-ID-n> | <action> | <meaning> | <replacement or "none"> |

## Required action

1. <Step a program author or implementer takes, including any mechanical rewrite>
2. <Evidence to regenerate: certificates, exploration results, conformance artefacts,
   source hashes>
3. <Persisted state to drain, keep under the old revision or migrate, or "none">

## Compatibility and deprecation period

<What keeps working and for how long; when a deprecated item may be tombstoned.>

## Verification

<Commands run, with exit codes, that show the new behaviour and the migration. Do not list
commands that were not run.>

## Not established

<What this note does not show, for example behaviour outside the checked corpus or
untested store migrations.>
