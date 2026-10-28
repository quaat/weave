"""`check-pure` and `run-pure` runner commands. They never parse or analyze an Inventory net."""
from __future__ import annotations

import json
from pathlib import Path

from . import Limits, MODES, SCHEDULES, PureError, check_source, encode, run_source

SCOPE = ("CHECKED covers types, terminal branches, effect exclusion, fork scope, and recursion shape; "
         "termination is not checked. EXECUTED is one run under the stated resource limits.")


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


def diagnostic(error: PureError, path: Path) -> dict:
    return {"code": error.code, "message": error.message, "file": str(path), "line": error.line,
            "stage": error.stage}


def execute(args) -> tuple[dict, int]:
    if args.command == "check-pure":
        result = {"command": "check-pure", "ok": True, "status": "CHECKED", "scope": SCOPE, "files": []}
        for file in args.files:
            try:
                source = file.read_text(encoding="utf-8")
            except OSError as error:
                raise ValueError(f"{file}: {error}") from None
            try:
                program = check_source(source)
                result["files"].append({"file": str(file), "ok": True,
                                        "functions": [f.name for f in program.functions]})
            except PureError as error:
                result["ok"] = False
                result["files"].append({"file": str(file), "ok": False, "diagnostic": diagnostic(error, file)})
        return result, 0 if result["ok"] else 1
    try:
        source = args.file.read_text(encoding="utf-8")
        try:
            json_args = json.loads(args.args)
        except json.JSONDecodeError as error:
            raise PureError("E424", f"--args is not valid JSON: {error}", stage="input") from None
        limits = Limits(fuel=args.fuel, max_tasks=args.max_tasks, max_depth=args.max_depth,
                        workers=args.workers, quantum=args.quantum)
        value, machine = run_source(source, args.entry, json_args, mode=args.mode, limits=limits,
                                    schedule=args.schedule, seed=args.seed, trace=args.trace)
    except PureError as error:
        result = {"command": "run-pure", "ok": False, "diagnostic": diagnostic(error, args.file)}
        return result, 1 if error.stage == "pure" else 2
    result = {"command": "run-pure", "ok": True, "status": "EXECUTED", "check": "CHECKED", "scope": SCOPE,
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
    if result["command"] == "check-pure":
        for item in result["files"]:
            if item["ok"]:
                print(f"CHECKED {item['file']}: {', '.join(item['functions'])} (pure; termination not checked)")
            else:
                print_diagnostic(item["diagnostic"])
        return
    if "diagnostic" in result:
        print_diagnostic(result["diagnostic"])
        return
    ex, stats = result["execution"], result["stats"]
    print(f"CHECKED {result['file']}; EXECUTED {result['entry']} in {ex['mode']} mode ({ex['scheduler']})")
    print(f"RESULT {json.dumps(result['result'])}")
    print(f"STATS steps={stats['steps']} activations={stats['tasks_created']} forks={stats['forks']} "
          f"joins={stats['joins']} max_live={stats['max_live_tasks']} max_frames={stats['max_frames']}")
    for event in result.get("events", []):
        print("  " + json.dumps(event, ensure_ascii=False))
