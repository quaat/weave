# Claude Code task: recursive concurrent merge sort in Weave

Initialize from this project's existing instructions, extend the implemented Weave fragment where necessary, and implement, run, and test a small recursive concurrent merge-sort application. Complete the implementation and verification; do not stop at a design or provide pseudocode as a finished application.

## 1. Establish the actual starting point

Read the applicable `CLAUDE.md`, `AGENTS.md`, the local `weave` skill and its canonical instructions, `docs/weave.md`, `docs/commands.md`, and `docs/prototype-status.md`. Inspect Git status and preserve unrelated changes and applications, including Tiny Shop if present.

The inspected starter-kit snapshot rejects recursive flow calls with `E218`. Its documented exclusions include ordinary conditionals, scalar computations, and parallel flows; it has no general list-processing runtime. Check whether this project's implementation has advanced before adding anything.

This task explicitly requests the minimal language/runtime extension needed for the demo. It is therefore an implementation task, rather than ordinary application authoring under the existing restricted fragment. Follow the repository's implementation-change workflow and update tests and documentation. Do not simply remove the recursion rejection or add unsupported-looking source while leaving the evaluator unchanged.

Use the existing Python environment and standard library. Run and record the applicable baseline commands from the kit root:

```bash
python3 scripts/weave.py doctor
python3 scripts/weave.py examples
python3 scripts/weave.py test
python3 -B -m unittest discover -s tests -q
```

If the kit is installed as a portable skill, resolve its actual runner and available test paths. Distinguish pre-existing failures from failures introduced by this work.

## 2. Implement a narrowly scoped computation extension

The demo is a stable ascending merge sort over integer lists. Its control flow, recursive calls, comparisons, and merge procedure must be written in `.weave`. The host language implements generic language primitives and execution machinery.

Prefer existing supported constructs. Where they are missing, implement only what this program needs:

- A pure function declaration with explicit parameter and return types, function calls, local bindings, return expressions, and direct self-recursion.
- Immutable integer-list values, integer and Boolean values, and a pair of lists. Monomorphic `IntList` and list-pair types are sufficient; general generics are unnecessary.
- Integer literals, `<=`, and terminal `if`/`else` branches with compatible return types.
- A closed set of documented list primitives: length, empty test, head, tail, prepend, balanced split, and pair projections. Empty-list behavior and invalid head/tail calls must have defined diagnostics. Head, tail, and prepend should support linear-time merging; use persistent list nodes or an equivalent representation rather than repeatedly copying array suffixes.
- A scoped fork/join construct for two independent pure calls. Both results must be available before the parent continues.

Keep pure functions distinct from effectful `flow` declarations. Pure functions may accept and return immutable data; they may not accept, capture, construct, duplicate, or discard existing linear resource handles, invoke foreign operations, or call effectful flows. Keep recursive effectful flows unsupported unless a separately justified implementation is essential; it is not needed for this demo. Mutual recursion and higher-order functions are also out of scope.

Register function signatures before checking bodies so direct recursion can be type-checked. Check every function body, including unused functions. Add source-located diagnostics for invalid calls, incorrect return types, malformed branches, illegal effects, and fork scope violations. Use a real parser/AST and evaluator; do not use host `eval`/`exec` or identify this program by its filename or function names.

Document the extension before calling it supported. Make it explicit whether termination is checked statically. A finite runtime fuel or depth budget is a resource limit, not a termination proof.

## 3. Write the algorithm in Weave

Create `demos/merge_sort/merge_sort.weave` containing the recursive sort and recursive merge. The following is the intended source shape, using **proposed extension syntax**. It is not accepted by the original kit. Reuse newer project syntax if it already exists; otherwise implement and test the equivalent syntax before treating this as runnable Weave.

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

fn merge(left: IntList, right: IntList) -> IntList:
    if is_empty(left):
        return right
    else:
        if is_empty(right):
            return left
        else:
            if head(left) <= head(right):
                return cons(head(left), merge(tail(left), right))
            else:
                return cons(head(right), merge(left, tail(right)))
```

Requirements:

1. `split_half` preserves the input order and yields two lists whose lengths differ by at most one. For inputs longer than one, both halves are strictly shorter than the original.
2. Each half is recursively sorted. Their computations are independent and eligible to execute concurrently.
3. The parent joins both results and then calls the Weave `merge` function. Merge takes from the left on equal keys, preserving stable order through the original contiguous split.
4. Empty and singleton inputs return immediately. Negative integers and duplicates are valid.
5. Ordinary recursive calls must work independently of fork/join; the recursive merge exercises this path.

List splitting, inspection, and construction may be runtime primitives. Sorting and the merge algorithm may not be hidden in Python, implemented with a host `sorted()`/`.sort()`, or supplied by a special `merge_sorted` host operation. Host sorting is allowed as an independent test oracle only.

This algorithm performs O(n log n) work with suitable list primitives. Its merge is sequential, so the ideal span is O(n), not O(log n). Do not promise speedup from the small demo.

## 4. Give fork/join concrete execution semantics

Integrate the extension through the project's Weave runner. Do not create a second, unrelated interpreter that merely happens to accept a `.weave` extension, and do not run the sorting program through the payment simulator.

Use a small generic task scheduler consistent with the functional Petri-net model:

- A fork creates two child activations with distinct IDs and one parent/fork correlation ID.
- Each child receives its immutable input and produces exactly one result for its corresponding branch.
- Join becomes enabled only when both matching child results exist. It consumes those result envelopes once and resumes the correct parent once.
- A parent waiting for a join does not occupy a worker needed by its children.
- Bound resource use. Avoid recursively creating an OS thread or process for every call or blocking all workers in nested `Future.result()` calls. Reject resource exhaustion explicitly; never silently drop tasks or return partial output.
- Handle child failure by failing the parent and cleaning up pending work. Never manufacture the missing result or leave a permanently waiting join.

A bounded cooperative scheduler with explicit runnable tasks and resumable continuations is sufficient for this demo. It must actually schedule independently runnable child activations; a depth-first evaluator with fabricated fork events is not concurrent execution. Label cooperative concurrency accurately. CPU-parallel workers are optional and must not be claimed unless actually implemented and verified.

Support sequential and concurrent execution modes for the same Weave source. In sequential mode, the fork's calls may execute one after the other. In concurrent mode, runnable siblings can make progress before either is joined. Results must be identical across modes.

Use interpreter frames or a trampoline, or enforce a documented limit with a structured error. The recursive merge has linear call depth; do not allow larger inputs to fail with an unexplained Python `RecursionError`. A cooperative interpreter must yield at defined evaluation steps so a long pure call does not prevent sibling progress indefinitely.

Emit trace events from the actual scheduler: activation creation, execution/progress, fork, child completion, join, root completion, and failure. Include enough task, parent, and branch identity to check pairing. The root completes with one result and no pending child tasks or join records.

These are execution and testing requirements. Do not claim that the existing Inventory accounting certificate proves properties of this new task system. If you add formal net checks, state their precise abstraction and scope separately.

## 5. Provide a small runnable demo

Create:

- `demos/merge_sort/merge_sort.weave` with the executable algorithm.
- `demos/merge_sort/run_demo.py`, a thin CLI using the integrated Weave execution path.
- `demos/merge_sort/tests/` with language, runtime, and demo tests in appropriate project locations.
- `demos/merge_sort/README.md` with prerequisites, exact commands, actual syntax, scheduling semantics, and limits.
- `demos/merge_sort/requirements.txt`, stating that no third-party packages are required. If a dependency is unavoidable, pin its exact version and justify it.
- `demos/merge_sort/TEST_REPORT.md` with commands executed, observed output, test results, and remaining limits.

Define and implement this demo CLI contract; these are new application commands, not pre-existing kit capabilities:

```bash
python3 demos/merge_sort/run_demo.py --values '[8,3,5,1,9,2,7,4,6]' --mode sequential
python3 demos/merge_sort/run_demo.py --values '[8,3,5,1,9,2,7,4,6]' --mode concurrent --trace
python3 demos/merge_sort/run_demo.py --values '[]' --mode concurrent
python3 demos/merge_sort/run_demo.py --values '[5,-2,5,0,-2]' --mode concurrent --json
```

The expected results are respectively `[1,2,3,4,5,6,7,8,9]`, the same sorted sequence with a real trace, `[]`, and `[-2,-2,0,5,5]`.

Provide `--help`, a documented resource limit, and nonzero exits for invalid input, check failures, runtime errors, or resource exhaustion. Accept JSON lists of integers only; reject booleans, floats, strings, nested lists, and non-list input. Emit one valid JSON document with `--json`, keeping informational text off stdout. Resolve project and source paths so invocation by absolute path works from another working directory.

The Python demo wrapper may parse input and render results, but must invoke the checked Weave program. Add or extend a general runner command for pure programs with an entry function and input values; document the actual flags you implement. Pure checking must not implicitly analyze the unrelated default Inventory net or report its proof status as evidence about sorting.

Keep generated traces under `demos/merge_sort/artifacts/`. No web UI or external service is needed.

## 6. Test the new language and actual execution

Use standard-library tests and the real parser, checker, interpreter, and scheduler. Include:

**Algorithm behavior**

- Empty, singleton, two-element, sorted, reverse-sorted, duplicate-heavy, all-equal, negative, and mixed-sign inputs; odd and even lengths.
- Exhaustive short inputs over a small integer alphabet and reproducible randomized cases. Compare against Python's `sorted()` as a test-only oracle.
- Nondecreasing output, equality of input/output element counts, unchanged input, and idempotence.
- Sequential and concurrent modes produce equal output across varied schedules.
- The merge's equal-key branch selects the left input. Repeated plain integers cannot reveal stability on their own: use traceable original element identities in test instrumentation, if available, or report this as a checked implementation rule rather than claiming an identity-based stability test was performed.

**Language and runtime behavior**

- Direct recursive pure calls, base-case branching, nested return expressions, signature/return checking, and rejection of unsupported constructs.
- Pure code cannot receive a `Hold`, call `Payments.charge`, or escape existing effect/linearity rules.
- A fork branch cannot depend on a sibling's result before the join; result bindings become visible in the continuation only after the join.
- Generic execution: a differently named recursive function works. Modify a valid Weave comparison or branch in a temporary copy and observe changed behavior, showing that the runtime executes source rather than a hard-coded host sort.
- Wrong types, unknown primitives, malformed input, invalid head access, and resource exhaustion produce useful diagnostics and nonzero exits.
- Large-enough inputs exercise the chosen stack strategy. Test a nonterminating pure function under a small fuel budget: it must fail cleanly rather than hang. Use explicit timeouts on tests that could otherwise hang.

**Concurrency and join behavior**

- Deterministically make both sibling activations progress before either completes; use scheduler hooks or a controlled schedule, not wall-clock speedup or sleeps as evidence.
- Exercise both left-first and right-first completion. The parent merges only after both results, in the original left/right order.
- Verify unique task IDs, correct parent correlation, no duplicate completion or join consumption, and no pending tasks after root completion.
- Exercise a minimal concurrency limit, deeper recursive forks, and child failure. There must be no pool starvation, deadlock, or unbounded task growth. If limits are reached, return an explicit error.

Run the demo commands, targeted extension tests, and all existing example, prototype, and runner regressions. Existing invalid recursive **effectful** flows should continue to fail with their documented diagnostic. If a previously invalid pure construct legitimately becomes supported, update only the affected expectation, add a positive test, and explain the change. Do not delete unrelated negative tests or weaken assertions to obtain a pass.

## 7. Document and finish

Update the language guide, prototype status, command reference, relevant skill guidance, and tests to distinguish the original fragment from this extension. Synchronize duplicated guide content using the project's existing helper where appropriate. Preserve upstream provenance; if vendored code changes, record the derived revision honestly rather than retaining a false byte-for-byte claim. Prefer small focused modules and avoid unrelated refactoring.

Run and fix the implementation until the required checks pass, or report a concrete blocker. In the final response, provide the source and report locations, exact run commands, actual test results, one observed sorting result, and the implemented concurrency model. State any resource limits and whether termination or task properties were proved, bounded-checked, or tested only.

Do not label proposed syntax as working, call sequential evaluation concurrent, claim CPU parallelism from a cooperative trace, or claim tests you did not run. Do not commit, push, or publish unless separately requested.
