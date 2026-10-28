# Validation report

Specification: **0.2-draft**  
Date: **28 October 2026**  
Environment: **CPython 3.12.14; Sphinx 8.2.3; Lark 1.3.1**

## Results

| Check | Observed result |
|---|---|
| Reference-file checksums | PASS; all pinned version-3 files unchanged |
| Normative source expectations | 25/25, including required rejection codes |
| Generated grammar front end | 68 productions; 25/25 pipeline agreements; N1 and Lease syntax parsed |
| Grammar independence | Independent layout/syntax parser; shared reference semantic checking |
| Rule catalogue | 60 stable rule IDs; generated catalogue and corpus references checked |
| Scripted outcome scenarios | 3/3 |
| Valid flow sources and lowerings | All 8 checked against N0 and N1 API environments |
| N0 exploration | Complete: 20 states, 43 edges |
| N1 accounting | 2 aggregate invariants, 3 invariant families |
| N1 exploration | Complete: 841 states, 3,712 edges; all 24 transitions reached |
| N1 finite unfolding | 32 cells, 48 firing modes |
| Lease tutorial | Net accounting and F0 client accepted; ordering E300 as documented |
| Counterexamples | E320 and E420 regenerated from included mutations |
| Upstream regression suite | 143 tests passed, including process-crash cases |
| Documentation-tooling suite | 9 tests passed |
| Executable documentation | 20/20 displayed examples matched expected results in each builder |
| HTML, single-page HTML, text | All three strict Sphinx builds passed |
| HTML local-link/asset/anchor audit | 33 pages; 2,315 references; zero errors or duplicate IDs |
| Single-page local audit | 1 page; 470 references; zero errors or duplicate IDs |
| External linkcheck | PASS; all five referenced URLs checked |
| Snapshot footer | Correct source-archive SHA-256 present on every HTML page |
| Diagrams | Three static SVGs rendered to PNG and visually inspected |

The source audit, grammar comparison, rule-drift check, documentation tests,
reference tests, strict HTML, and external linkcheck passed through `make validate`.
After final documentation/link corrections, all three strict builders and both
local HTML audits passed again. The unchanged reference suite was not needlessly
repeated after presentation-only changes.

## Reproduce

Install the pinned dependencies as described in `README.md`, then run:

```bash
make validate
make singlehtml text
python scripts/audit_html.py
python scripts/audit_html.py _build/singlehtml
```

Use `make validate-offline` when external link access is unavailable.
`python scripts/test_reference.py` sets the original tests' required working
directory. The local single-page extension repairs Sphinx's double-fragment
links and suppresses unavailable index/search navigation. Browser Find is the
single-page search interface.

## Evidence files

- `report.json`: source, scenario, net analysis, Lease and counterexample results.
- `grammar-report.json`: generated syntax and combined pipeline outcomes.
- `generated-weave.lark`: grammar generated from the shipped EBNF.
- `weave-check-report.json`: all 20 displayed example checks.
- `validate-output.txt`: actual full validation output, including both test suites.
- `build-output.txt` and `singlehtml-final-output.txt`: successful strict builds.
- `html-audit.json` and `singlehtml-audit.json`: final local-link/asset/anchor checks.
- `linkcheck-output.json`: Sphinx external-link results.
- `counterexample-E320.txt` and `counterexample-E420.txt`: actual diagnostics.
- `REVIEW_RESPONSE.md`: item-by-item disposition of the review.
- `../PROVENANCE.json`: source identities and included-file checksums.

## Limits

These are regression and documentation-build results, not a soundness proof.
The generated parser is not an independent semantic checker and the finite
corpus does not prove grammar equivalence. No result here implements or tests
the new general D0 waiting scheduler or N2 evidence/correlation profile.

The four historical design drafts were not recovered. Their exact chronology
and feature-removal motivations are not invented.

HTML structure, links, anchors and generated text were checked. Browser screenshot
inspection was unavailable because the browser binary could not be installed.
No browser-rendering pass is claimed. The three SVG figures were separately
rasterized and visually inspected.

HTML mathematics uses Sphinx's MathJax CDN at viewing time; the plain-text edition
does not require it. Language validation uses scripted providers; external
linkcheck is a separate documentation check.
