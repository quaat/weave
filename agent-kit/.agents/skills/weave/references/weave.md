# Weave: implemented language fragment

This guide describes the source in the bundled prototype, not the entire proposed
Weave language. Reference environment: CPython 3.12.14; minimum Python 3.11.
The checker uses only the standard library. The
[pure-function extension](#pure-function-extension-kit-addition) is a kit addition
implemented outside the unchanged vendored prototype; everything before that
section describes the original flow fragment.

Contents: [syntax](#syntax), [nets](#nets-and-ownership),
[flows](#flows-and-linear-values), [propagation](#question-mark-propagation),
[checks](#what-the-results-mean), [diagnostics](#diagnostics),
[pure extension](#pure-function-extension-kit-addition),
[boundaries](#unsupported-and-unestablished).

## Syntax

- Use four spaces per indentation level. Tabs and skipped levels are rejected.
- `#` starts a comment. There is no string-literal syntax in this fragment.
- Put one declaration or statement on a line. Blocks end their opening line in `:`.
- Types are nominal: `Hold[t, o]`, `Escrow[t, o]`, `ChargeOutcome[t, o]`.
  Indices are symbolic identifiers, not expressions or runtime integer arguments.
- A net file contains exactly one `net Name(stock: Nat):` block. A flow file
  contains one or more `flow` blocks. Check them as separate files with `--net`.
- Function arguments are existing binding names. Literals, arithmetic expressions,
  general assignments, imports, and module resolution are not implemented.

## Nets and ownership

`Inventory.weave` is the complete reference net. A marking maps each place to a
nonnegative token count. Transitions consume `take` arcs, preserve `read` arcs,
and add `put` arcs. A transition requires enough tokens for every take/read arc.
Named guards are abstract conditions, not executable Python or provider queries.

```weave
transition arm:
    take 1 held
    put 1 escrow
    put 1 registrations
```

The excerpt belongs inside a net, indented one additional level. It moves a held
item to escrow and creates its recovery registration in the same transition.

| Declaration | Meaning in this implementation |
| --- | --- |
| `place available = stock owner domain` | Initial count is the net parameter |
| `place held = 0 owner activation` | An activation-owned place must have one linear resource declaration |
| `place inflight = 0 owner runtime` | Runtime-owned state requires an explicit closed consumer list |
| `place charge_requests = 0 owner adapter` | Adapter-owned token count; no real adapter is run |
| `take 1 held` | Consume one token when firing |
| `read 1 registrations` | Require one token without consuming it |
| `put 1 escrow` | Produce one token |

Arc counts are positive integer literals. Initial counts are nonnegative integer
literals or the net's `Nat` parameter. Duplicate arcs of the same kind/place are
rejected. Read arcs over activation-owned places are unsupported.

The reference resource declaration is:

```weave
linear Escrow[t, o] at escrow issuer arm cancel cancel_escrow registered registrations
```

The validator requires `arm` to be the only producer of that activation-owned
place and to issue exactly one token. Registration is created atomically with
escrow. Consumers must be declared APIs whose signatures account for the handle,
or the resource's declared cancellation route. Clients cannot construct escrow.
Cancellation routes cannot wait on guards or read arcs, and must put their outputs
under durable ownership. This validates declarations; it does not implement a
durable cancellation service.

```weave
runtime_state inflight consumers charge_ok, charge_err, charge_unknown, cancel_inflight
```

Each listed transition must consume exactly one token from the named runtime
place. An omitted declaration does not open access. A place with no permitted
consumer uses `runtime_state name terminal`.

An API binds a callable signature to a transition:

```weave
api arm(h: Hold[t, o]) -> Escrow[t, o] via arm
```

Clients call `Inventory.arm`. Private transition names are not callable APIs.
Local APIs return a resource or `Unit`; their signatures must account for all
activation-owned inputs and outputs. Foreign calls additionally declare dispatch,
pending state, key fields, correlation, and all outcome transitions. See the full
`Payments.charge` declaration in `Inventory.weave` rather than inventing a shorter
foreign declaration.

## Flows and linear values

A helper moves a handle through an API and returns its replacement:

```weave
flow arm_hold(hold: Hold[t, o]) -> Escrow[t, o]:
    let escrow = await Inventory.arm(hold)
    return escrow
```

After the call, `hold` is moved and cannot be reused. Returning `escrow` transfers
it to the caller. A declared cancellation route does not permit silently dropping
it at an ordinary return. Every live linear binding must be transferred or
discharged on every branch, including helper and propagation boundaries.

Supported statements are `let name = await operation(arguments)`,
`await operation(arguments)` for `Unit` results, `return`, `return binding`,
`return Case(payload)`, `return Case()` for a `Unit` payload, and terminal matches.
A missing return type means `Unit`. Forward helper references are accepted, but
all helper bodies, including unused helpers, are checked. Recursion and shadowing
are rejected. A flow may return `Unit`, a declared handle, or a declared enum.

The payment result is a nominal closed enum:

```weave
enum ChargeOutcome[t, o]:
    Ok(Paid[t, o])
    Err(Unpaid[t, o])
    Unknown(Uncertain[t, o])
```

The enum itself is linear. Its cases preserve the identity indices of the permit.
Matching consumes the enum and introduces the selected payload obligation.
Do not interchange `Paid`, `Unpaid`, and `Uncertain` simply because their indices
match. `Unknown` is neither successful payment nor final rejection.

```weave
flow settle(result: ChargeOutcome[t, o]):
    match result:
        Ok(paid):
            await Inventory.sell(paid)
            return
        Err(unpaid):
            await Inventory.release(unpaid)
            return
        Unknown(uncertain):
            await Inventory.handoff(uncertain)
            return
```

Matches must be exhaustive and terminal: there are no statements after the match
in its containing block. Every branch must end in return or another exhaustive
terminal match. Scalar parameters such as `tenant: TenantId` are opaque symbols
in this prototype. Identity consistency is checked symbolically; cross-order
runtime correlation is not proved.

## Question-mark propagation

Two forms are implemented:

```weave
let paid = result?
let paid = (await Payments.charge(tenant, order, amount, escrow))?
```

These are alternative statement examples, not a complete program. Each lowers to
a terminal exhaustive match: `Ok` continues with the payload; `Err` and `Unknown`
return their corresponding tagged payload immediately. The enclosing return enum
must accept exactly those residual payload types and indices. Its success type
may differ: `CheckoutOutcome` has `Ok(Unit)` after sale is committed.

Propagation inserts no cleanup, cancellation, payload conversion, or net firing.
Any other live handle must also be accounted for on early-return branches.
Discharging it only after `?` is insufficient. The curated `early_return_leak`
example demonstrates this failure; `checkout_propagating` demonstrates valid
propagation across helper boundaries with explicit caller handling.

Use the runner's `lower` command to inspect and recheck generated source. Internal
diagnostics retain the original `?` line; a serialized lowered file has its own
line numbers and does not contain a separate source map. Comments are not retained.

## What the results mean

| Label | Established scope |
| --- | --- |
| `PROVED` | Exact integer P-invariant accounting for every finite firing sequence and nonnegative initial stock, under the parsed net semantics |
| `CHECKED WITHIN BOUNDS` | Exhaustive exploration of the declared one-order abstraction within its explicit bounds and assumptions |
| `CHECKED` flow | Nominal types, indexed identities, exhaustive outcomes, linear moves, and no normal drops in the supported fragment |
| `SCRIPTED` | A concrete synchronous run with a chosen foreign outcome |
| `VIOLATED` | A counterexample was found |
| `NOT ESTABLISHED` | Missing model, exceeded bounds/budget, or an unimplemented guarantee |

An invariant has one equality whose left side is affine in place counts and whose
right side is affine in the stock parameter. The checker validates the initial
marking and zero change for each transition. Supported arithmetic is integer
constants, names, addition, subtraction, unary minus, and scalar multiplication.
This aggregate argument ignores guards and does not establish identity correlation.

The Inventory order model fixes stock to one, admits `reserve` at most once, and
bounds each place to one token. Its supplied source explores 20 states and 43
edges, covering all 21 transitions. The default search budget is 10,000 states.
Exceeding a bound or budget fails; successors are not silently pruned.

Paid/rejected evidence witnesses arise at guards classified as establishing them.
Other guards may enable nondeterministically. Witnesses persist; the checker does
not assume they are mutually exclusive. Provider truthfulness, consistency, and
correlation remain assumptions. The model excludes re-reservation, concurrent
orders, independent late replies, and liveness/fairness guarantees.

The scripted executor accepts an entry with scalar parameters, uses stock one,
and permits at most one foreign operation per scenario. It executes checked,
lowered flow source against net transitions. Guard truth is supplied by the
scenario. It does not drain the adapter queue, so `charge_requests` may remain.

## Diagnostics

| Code | Typical meaning |
| --- | --- |
| `E001`–`E003` | Indentation, types, declarations, or unsupported net syntax |
| `E100` / `E101` | Invalid ownership contract / unauthorized sealed consumer |
| `E110` / `E111` / `E112` | Invalid invariant / initial mismatch / nonzero transition effect |
| `E200` | Unsupported flow declaration or statement |
| `E201` / `E202` | Wrong argument count / discarded linear result or payload |
| `E203` / `E204` | Reuse after move / live obligation at normal return |
| `E205` / `E206` | Sealed constructor / unknown or private operation |
| `E208` / `E209` | Wrong nominal type / identity mismatch |
| `E213` / `E214` | Invalid or nonterminal match / non-exhaustive match |
| `E216` / `E217` | Invalid indexed signature / incompatible return |
| `E218` / `E219` | Recursion / incompatible return constructor |
| `E300` / `E320` / `E321` | Invalid or missing order model / counterexample / bound or budget exceeded |

This table is a shortcut, not an exhaustive diagnostic specification. Preserve
the code, source line, and explanatory message when reporting a failure.

## Pure-function extension (kit addition)

Implemented in `.agents/skills/weave/scripts/weave_pure/`, not in the vendored
prototype. Flow checking and simulation are unchanged: `check` still rejects `fn`
declarations (`E200`) and recursive flows (`E218`). Pure programs live in their own
files, are checked with `check-pure`, and run with `run-pure`. Neither command reads
or analyzes a net, so their results say nothing about Inventory accounting.

```weave
fn merge_sort(xs: IntList) -> IntList:
    if length(xs) <= 1:
        return xs
    else:
        let halves = split_half(xs)
        fork:
            let left_sorted = merge_sort(first(halves))
            let right_sorted = merge_sort(second(halves))
        return merge(left_sorted, right_sorted)
```

This excerpt is from `demos/merge_sort/merge_sort.weave`, which also defines the
recursive `merge`.

| Construct | Implemented form |
| --- | --- |
| Declaration | `fn name(param: Type, ...) -> Type:` with explicit parameter and return types |
| Types | `Int`, `Bool`, `IntList` (immutable), `IntListPair`; no generics |
| Statements | `let name = expr`, `return expr`, terminal `if cond:` / `else:`, `fork:` |
| Expressions | integer literals (optional leading `-`), `true`, `false`, names, calls, parentheses, one `Int <= Int` |
| Calls | primitives below, or user functions (forward references allowed) |

| Primitive | Type | Behavior |
| --- | --- | --- |
| `length(xs)` | `IntList -> Int` | O(1); cached in each node |
| `is_empty(xs)` | `IntList -> Bool` | O(1) |
| `head(xs)` | `IntList -> Int` | O(1); `E420` at run time on an empty list |
| `tail(xs)` | `IntList -> IntList` | O(1), shares nodes; `E420` on an empty list |
| `cons(x, xs)` | `Int, IntList -> IntList` | O(1) new node; `xs` is shared, not copied |
| `split_half(xs)` | `IntList -> IntListPair` | Order-preserving; first half has floor(n/2) items (copied), second half shares the suffix |
| `first(p)`, `second(p)` | `IntListPair -> IntList` | Pair projections |

Checking rules: all signatures are registered before any body is checked, and
every body is checked, including unused functions. Each path must end in `return`
or a terminal `if`/`else` (no `elif`, no statements after either). Conditions must
be `Bool`; return values must match the declared type. Bindings cannot be rebound
or shadowed. Direct self-recursion is allowed; mutual or indirect recursion is
rejected (`E411`). Functions are not values. Pure functions cannot take or return
linear or nominal flow types such as `Hold[t, o]` (`E401`), use `await`, call
`Inventory.*`/`Payments.*`, or call a flow (`E409`). A file that declares a flow is
not a pure program (`E410`).

`fork:` contains exactly two `let name = function(args)` lines, each calling a
user-defined pure function. The parent evaluates both argument lists first. A
branch cannot read its sibling's binding (`E412`); both bindings become visible
only after the join. A fork is a statement and must be followed by more statements.

Execution: the checked program is compiled to a small instruction list. Each
activation (task) keeps explicit interpreter frames, so deep recursion does not use
the Python stack. In `concurrent` mode a fork creates two child activations with
fresh task IDs that share one fork ID. The parent waits outside the run queue. Each
child result is recorded once, and the join fires only when both results exist.
It then binds the results in left/right source order and requeues the parent once.
The scheduler is cooperative and runs on one OS thread. Each round it dispatches
up to `workers` runnable tasks, each for at most `quantum` instructions, in `fifo`,
`lifo`, or seeded `random` order. Siblings therefore interleave, but this is not
CPU parallelism. `sequential` mode runs the two fork calls one after the other in
the same activation. Both modes execute the same compiled source.

When a child fails, its parent fails, the sibling subtree is cancelled, and the
failure propagates to the root. No join result is fabricated and no output is
returned. Resource limits are explicit errors: `fuel` caps total instructions
(`E421`), `max_depth` caps frames per activation (`E422`), and `max_tasks` caps live
activations (`E423`). Termination is **not** checked statically. The fuel and depth
limits are resource limits, not termination proofs. Trace events are
`activation_created`, `run`, `fork`, `wait`, `child_complete`, `join`,
`root_complete`, `failure`, and `cancelled`, plus `fork_inline` and `join_inline`
in sequential mode.

| Code | Meaning |
| --- | --- |
| `E400` | Unsupported or malformed pure syntax, operators, or declarations |
| `E401` | Unsupported type, including linear resources, in a pure signature |
| `E402` / `E403` / `E404` | Duplicate declaration / unknown binding or function used as a value / unknown function |
| `E405` / `E406` / `E407` | Wrong argument count / wrong argument type / wrong or missing return value |
| `E408` | Malformed branch: missing `else`, statements after `return` or `if`, or a path without `return` |
| `E409` / `E410` | Illegal effect (`await`, net/foreign operation, flow call) / flow declared in a pure program |
| `E411` / `E412` / `E413` / `E414` | Mutual recursion / fork-scope violation / rebinding / non-Bool condition |
| `E420`–`E423` | Runtime: empty `head`/`tail`, fuel, depth, live-task limit |
| `E424` / `E425` | Entry argument decoding / unknown entry function |
| `E426` / `E427` | Internal scheduler deadlock / pairing error; never expected |

Status labels: `CHECKED` (pure) means the rules above passed. `EXECUTED` means one
run completed within its limits. Scheduler pairing, cleanup, and identical results
across modes are **tested**, not proved. No net or certificate covers this task
system.

## Unsupported and unestablished

In the original flow fragment, unsupported syntax includes `within`, `retry`,
ordinary conditionals, loops, `parallel`, recursion, higher-order flows, scalar
computations, open unions, subtyping, borrowing, and statements after a terminal
match. The pure extension adds only the constructs listed in its section. It
still has no loops, arithmetic other than `<=`, mutual recursion, higher-order
functions, generics, or effects, and none of its constructs are available in
flows. Unsupported syntax is rejected; do not treat it as pseudocode in a file
claimed to be executable.

There is no provider I/O, persistence, crash recovery, distributed scheduling,
asynchronous cancellation, webhook validation, or upgrade implementation. The
prototype does not establish multi-order identity preservation, idempotency
retention, escalation budget correctness, or compiler/runtime refinement.
The certificate verifier shares the parser. The Python implementation itself
has not been formally verified. Passing checks is evidence within these scopes,
not a general proof of business correctness.
