# Working with Weave

This repository teaches the **implemented restricted Weave fragment** for
functional Petri nets. It includes a Python reference checker and a scripted
single-order executor. It is not a full language implementation.

## Find the right context

- For writing or changing `.weave`, read the relevant sections of `docs/weave.md`
  and the nearest example in `examples/valid/`.
- For checking, lowering, simulating, or testing, use the `weave` skill at
  `.agents/skills/weave/SKILL.md`. Its scripts run without loading their source
  or the full prototype into the conversation.
- For implementation boundaries, consult `docs/prototype-status.md`.
- Pure `fn` programs (the kit's fork/join extension) are checked with `check-pure`
  and run with `run-pure`; see the extension section of `docs/weave.md` and
  `demos/merge_sort/`. They are separate from flows and never analyze a net.
- Treat `examples/manifest.json` as the list of expected acceptances and errors.
  Invalid examples are intentional teaching fixtures; do not repair them unless
  the task explicitly asks to change the fixtures.

## Commands from the repository root

```bash
python3 scripts/weave.py check examples/valid/checkout.weave
python3 scripts/weave.py check examples/valid/checkout_composed.weave examples/valid/checkout_propagating.weave
python3 scripts/weave.py simulate examples/valid/checkout_propagating.weave --entry checkout_propagating --outcome all
python3 scripts/weave.py examples
python3 scripts/weave.py test
python3 -B -m unittest discover -s tests -q
```

Use `--json` **before** the subcommand for machine-readable results. Use `--net`
when working with a modified net; otherwise the bundled `Inventory.weave` is used.
Batch related flow checks in one command so the net is checked once. Run targeted
checks during edits; run the example suite for example/guide changes and the full
regressions for checker, lowering, runner, or net changes. These checks are local
and require no services or credentials.

## Semantic rules

- Use only implemented constructs. Do not borrow syntax from Rust, Python,
  Haskell, or an earlier Weave proposal without checking support.
- Linear handles and outcomes move at calls, returns, matches, and `?`. Every
  return path must transfer or discharge every live obligation.
- `Unknown` is unresolved protocol state. It carries `Uncertain`, preserves the
  recovery obligation, and requires explicit handling or propagation.
- `?` propagates matching `Err` and `Unknown` payloads; it inserts no cleanup.
- Do not weaken invariants, consumer lists, identity checks, or evidence guards
  just to make a caller pass. Report a contract disagreement; change the contract
  only when that is part of the requested work.
- Distinguish `PROVED` accounting, `CHECKED WITHIN BOUNDS` ordering, and `SCRIPTED`
  execution. Do not call bounded exploration a multi-order proof.

Keep the vendored prototype unchanged for ordinary flow work. For an explicitly
requested implementation change, update its tests and the documented boundary.
Report commands actually run, failures, and remaining limits. Do not claim tests
or execution that you did not perform.
