"""`check-pure` and `run-pure` runner commands. They never parse or analyze an Inventory net."""
from __future__ import annotations

import json
from pathlib import Path

from weave_diagnostics import from_pure_error
from weave_labels import NOT_ESTABLISHED, claim_line, labelled

from . import Limits, MODES, SCHEDULES, PureError, check_source, encode, run_source

# Pure fn programs are a kit extension outside F0 and every specified profile, so no
# specified guarantee is established for them: each accepted file is one NOT ESTABLISHED
# claim (missing model). What the kit's own checker accepted is stated in the scope, and
# the outcome of a run is its runtime_status, which is not evidence.
SCOPE = ("Pure fn kit extension, outside F0 and every specified profile: no specified guarantee is "
         "established. The kit checker covers types, terminal branches, effect exclusion, fork scope, "
         "and recursion shape; termination is not checked. A run-pure run is one execution under the "
         "stated resource limits; its runtime_status is not evidence.")


def pure_claim(file: Path, functions: list[str]) -> dict:
    return {"file": str(file), "ok": True,
            **labelled(NOT_ESTABLISHED, functions=functions, reason="pure fn kit extension outside F0; missing model")}


def claim_text(item: dict) -> str:
    return claim_line(item["claim_label"], f"{item['file']}: {', '.join(item['functions'])} (pure fn kit "
                                           "extension outside F0; accepted by the kit checker; "
                                           "termination not checked)")


def add_commands(sub, positive_int) -> None:
    s = sub.add_parser("check-pure", help="Check pure fn programs (extension; no net analysis)")
    s.add_argument("files", nargs="+", type=Path)
    s = sub.add_parser("run-pure", help="Check and execute a pure fn entry (extension; no net analysis)")
    s.add_argument("file", type=Path)
    s.add_argument("--entry", required=True)
    s.add_argument("--args", default="[]", help="JSON array of entry arguments")
    s.add_argument("--mode", choices=MODES, default="concurrent")
    s.add_argument("--schedule", choices=SCHEDULES, default="fifo")
    s.add_argument("--seed", type=int, default=0)
    s.add_argument("--trace", action="store_true", help="Include scheduler events")
    defaults = Limits()
    for name in ("workers", "quantum", "fuel", "max_tasks", "max_depth"):
        s.add_argument("--" + name.replace("_", "-"), type=positive_int, default=getattr(defaults, name))


def diagnostic(error: PureError, path: Path, source: str = "") -> dict:
    """A weave-diagnostic-v1 document; the span is the reported statement of ``source``."""
    return from_pure_error(error, str(path), source)


def execute(args) -> tuple[dict, int]:
    if args.command == "check-pure":
        result = {"command": "check-pure", "ok": True, "scope": SCOPE, "files": []}
        for file in args.files:
            try:
                source = file.read_text(encoding="utf-8")
            except OSError as error:
                raise ValueError(f"{file}: {error}") from None
            try:
                program = check_source(source)
                result["files"].append(pure_claim(file, [f.name for f in program.functions]))
            except PureError as error:
                result["ok"] = False
                result["files"].append({"file": str(file), "ok": False,
                                        "diagnostic": diagnostic(error, file, source)})
        return result, 0 if result["ok"] else 1
    source = ""
    try:
        source = args.file.read_text(encoding="utf-8")
        try:
            json_args = json.loads(args.args)
        except json.JSONDecodeError as error:
            raise PureError("P424", f"--args is not valid JSON: {error}", stage="input") from None
        limits = Limits(fuel=args.fuel, max_tasks=args.max_tasks, max_depth=args.max_depth,
                        workers=args.workers, quantum=args.quantum)
        value, machine = run_source(source, args.entry, json_args, mode=args.mode, limits=limits,
                                    schedule=args.schedule, seed=args.seed, trace=args.trace)
    except PureError as error:
        result = {"command": "run-pure", "ok": False, "diagnostic": diagnostic(error, args.file, source)}
        return result, 1 if error.stage == "pure" else 2
    result = {"command": "run-pure", "ok": True, "scope": SCOPE,
              "check": pure_claim(args.file, list(machine.program)), "runtime_status": "completed",
              "file": str(args.file), "entry": args.entry, "result": encode(value),
              "execution": {"mode": args.mode,
                            "scheduler": "cooperative, single OS thread" if args.mode == "concurrent"
                            else "sequential, single activation",
                            "schedule": args.schedule, "seed": args.seed,
                            "limits": {"workers": args.workers, "quantum": args.quantum, "fuel": args.fuel,
                                       "max_tasks": args.max_tasks, "max_depth": args.max_depth}},
              "stats": machine.stats}
    if args.trace:
        result["events"] = machine.events
    return result, 0


def render(result: dict, print_diagnostic) -> None:
    if "diagnostic" in result:  # a failure before any file was checked or any run started
        print_diagnostic(result["diagnostic"])
        return
    if result["command"] == "check-pure":
        for item in result["files"]:
            if item["ok"]:
                print(claim_text(item))
            else:
                print_diagnostic(item["diagnostic"])
        return
    ex, stats = result["execution"], result["stats"]
    print(claim_text(result["check"]))
    print(f"runtime status: {result['runtime_status']} ({result['entry']} in {ex['mode']} mode; {ex['scheduler']})")
    print(f"result: {json.dumps(result['result'])}")
    print(f"stats: steps={stats['steps']} activations={stats['tasks_created']} forks={stats['forks']} "
          f"joins={stats['joins']} max_live={stats['max_live_tasks']} max_frames={stats['max_frames']}")
    for event in result.get("events", []):
        print("  " + json.dumps(event, ensure_ascii=False))
