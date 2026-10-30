# Teaching examples

Run `python3 scripts/weave.py examples` from the kit root. Expected rejections are successes for this corpus only when their exact diagnostic code matches.

The manifest is executable metadata. Valid helper-only files are statically checked; they need an existing linear input and are not scalar-entry simulations. Run the checkout examples to obtain scripted traces.

| File | Expected | Lesson |
| --- | --- | --- |
| [valid/return_hold.weave](valid/return_hold.weave) | `ACCEPT` | Return moves a handle without changing its type. |
| [valid/arm_hold.weave](valid/arm_hold.weave) | `ACCEPT` | An API changes state and preserves identity indices. |
| [valid/finish_paid.weave](valid/finish_paid.weave) | `ACCEPT` | Consume paid evidence by committing the sale. |
| [valid/settle.weave](valid/settle.weave) | `ACCEPT` | Exhaustively discharge each outcome. |
| [valid/propagate_bound.weave](valid/propagate_bound.weave) | `ACCEPT` | Propagate an already bound closed outcome with ?. |
| [valid/checkout.weave](valid/checkout.weave) | `ACCEPT` | Reserve, arm, charge, and settle all outcomes. |
| [valid/checkout_composed.weave](valid/checkout_composed.weave) | `ACCEPT` | Move handles and enums across helper boundaries. |
| [valid/checkout_propagating.weave](valid/checkout_propagating.weave) | `ACCEPT` | Propagate across helpers; caller handles residual obligations. |
| [invalid/direct_charge.weave](invalid/direct_charge.weave) | `E201` | Foreign dispatch requires a sealed escrow permit. |
| [invalid/drop_hold.weave](invalid/drop_hold.weave) | `E204` | A cancellation route does not allow normal dropping. |
| [invalid/forge_escrow.weave](invalid/forge_escrow.weave) | `E205` | Clients cannot construct sealed resources. |
| [invalid/wrong_order.weave](invalid/wrong_order.weave) | `E209` | Permit identity must match the requested order. |
| [invalid/reuse_hold.weave](invalid/reuse_hold.weave) | `E203` | Moved handles cannot be reused. |
| [invalid/missing_unknown.weave](invalid/missing_unknown.weave) | `E214` | Matches must include Unknown. |
| [invalid/paid_release.weave](invalid/paid_release.weave) | `E208` | Paid evidence cannot be treated as final rejection. |
| [invalid/early_return_leak.weave](invalid/early_return_leak.weave) | `E204` | ? must account for other handles on early-return paths. |
| [invalid/recursion.weave](invalid/recursion.weave) | `E218` | Recursive helper calls are unsupported. |
| [invalid/unsupported_if.weave](invalid/unsupported_if.weave) | `E200` | Familiar conditional syntax is not supported Weave syntax. |
| [mutations/skim.weave](mutations/skim.weave) | `E101` | An undeclared transition cannot consume sealed activation/runtime state. |
| [mutations/lose_paid.weave](mutations/lose_paid.weave) | `E101` | An undeclared transition cannot consume sealed activation/runtime state. |
| [mutations/bogus_sell.weave](mutations/bogus_sell.weave) | `E101` | An undeclared transition cannot consume sealed activation/runtime state. |
| [mutations/quick_recover.weave](mutations/quick_recover.weave) | `E101` | An undeclared transition cannot consume sealed activation/runtime state. |
| [mutations/leak.weave](mutations/leak.weave) | `E101` | An undeclared transition cannot consume sealed activation/runtime state. |
| [mutations/manual_leak.weave](mutations/manual_leak.weave) | `E101` | An undeclared transition cannot consume sealed activation/runtime state. |
| [nets/unsafe_paid_release.weave](nets/unsafe_paid_release.weave) | `E320` | Even an authorized cancellation with balanced accounting can violate payment ordering. |
| [valid/commented_blocks.weave](valid/commented_blocks.weave) | `ACCEPT` | Comments and blank lines in every block position are trivia. |
| [invalid/skipped_level.weave](invalid/skipped_level.weave) | `E001` | A block must be indented by exactly one four-space level. |

## Scenario expectations

| Outcome | Expected final accounting |
| --- | --- |
| `Ok` | `available=0`, `sold=1`, `registrations=0` |
| `Err` | `available=1`, `sold=0`, `registrations=0` |
| `Unknown` | `available=0`, `uncertain=0`, `recovery_queue=1`, `registrations=1` |

Append mutations are net fragments, not standalone flow files. Their diagnostics use the line numbers of the combined net. `nets/unsafe_paid_release.weave` is a full alternative net: it preserves aggregate accounting but fails bounded ordering. All examples use the prototype fragment, not future design syntax.

## P0 pure files

`pure/` holds the P0 corpus (`docs/chapters/pure.rst`): `pure/valid/` and `pure/invalid/`, with
`pure/manifest.json` (format `weave-p0-conformance-v1`) listing a check case per file and run
cases with entry functions, JSON arguments, budgets and required outcomes. The conformance
appendix lists every case. Check a file with `python3 scripts/p0_reference.py check FILE` from
`specification/`, or with `cargo run -q -p weave-cli -- check FILE` from the repository root.

## P0 modules (modules-1)

`modules/` holds the modules-1 corpus (`docs/chapters/names.rst`, "P0 modules (modules-1)"
and "Net selection"), with `modules/manifest.json` (format `weave-modules-conformance-v1`).
Each directory is a small project whose root is the entry file's directory unless the case
gives a root: `shapes/` (selective imports, an alias, a module imported twice and loaded
once), `identity/` (same-named records from two modules, aliases of one record), `private/`
(an imported function's private helper), `rooted/` (`--root`), `faults/` and `unused_body/`
(P0 errors inside an imported module), and one directory per rejected form (`syntax/`,
`missing/`, `resolution/`, `cycle/`, `self_import/`, `recursion/`, `record_cycle/`, `names/`,
`export/`, `entry/`). Files under `flows/` are flow files with a `use net` header, resolved
from `examples/` as the root. Check and run the P0 cases with
`cargo run -q -p weave-cli -- check FILE [--root DIR]` from the repository root; check a flow
with the agent kit's runner, `python3 scripts/weave.py check FILE --root DIR`.
`scripts/modules_conformance.py` runs every case. Expected rejections are intentional.
