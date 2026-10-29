"""Resumable stack machine and bounded cooperative fork/join scheduler for checked pure programs.

Every activation is a task holding explicit interpreter frames (no host recursion). The
scheduler runs on one OS thread: it dispatches up to `workers` runnable tasks per round, each
for at most `quantum` instructions, so sibling activations interleave. This is cooperative
concurrency, not CPU parallelism.
"""
from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass

from .syntax import BoolLit, Call, Fork, If, IntLit, Le, Let, Program, Return, Var
from .values import PRIMITIVES, RuntimeFault

RUNNABLE, WAITING, DONE, FAILED, CANCELLED = "runnable", "waiting", "done", "failed", "cancelled"
MODES = ("sequential", "concurrent")
SCHEDULES = ("fifo", "lifo", "random")


@dataclass(frozen=True)
class Limits:
    fuel: int = 10_000_000      # total interpreter instructions across all tasks
    max_tasks: int = 4096       # live (runnable or waiting) activations
    max_depth: int = 100_000    # interpreter frames per activation
    workers: int = 4            # dispatch slots per scheduling round
    quantum: int = 16           # instructions per slice before a task yields


@dataclass(frozen=True)
class ForkSpec:
    left_fn: str
    left_argc: int
    left_name: str
    right_fn: str
    right_argc: int
    right_name: str
    line: int


class CompiledFn:
    def __init__(self, name: str, params: tuple, code: tuple):
        self.name, self.params, self.code = name, params, code


def compile_program(program: Program) -> dict:
    return {fn.name: CompiledFn(fn.name, tuple(p for p, _ in fn.params), _compile_body(fn.body))
            for fn in program.functions}


def _compile_body(body: tuple) -> tuple:
    code = []

    def expr(e):
        if isinstance(e, (IntLit, BoolLit)):
            code.append(("CONST", e.value, e.line))
        elif isinstance(e, Var):
            code.append(("LOAD", e.name, e.line))
        elif isinstance(e, Le):
            expr(e.left)
            expr(e.right)
            code.append(("LE", None, e.line))
        elif isinstance(e, Call):
            for arg in e.args:
                expr(arg)
            code.append(("PRIM" if e.name in PRIMITIVES else "CALL", (e.name, len(e.args)), e.line))
        else:
            raise TypeError(f"Cannot compile {e!r}")

    def block(stmts):
        for s in stmts:
            if isinstance(s, Let):
                expr(s.expr)
                code.append(("STORE", s.name, s.line))
            elif isinstance(s, Return):
                expr(s.expr)
                code.append(("RET", None, s.line))
            elif isinstance(s, If):
                expr(s.cond)
                jump = len(code)
                code.append(None)
                block(s.then)
                code[jump] = ("JF", len(code), s.line)
                block(s.other)
            elif isinstance(s, Fork):
                left, right = s.branches
                for arg in left.expr.args:
                    expr(arg)
                for arg in right.expr.args:
                    expr(arg)
                code.append(("FORK", ForkSpec(left.expr.name, len(left.expr.args), left.name,
                                              right.expr.name, len(right.expr.args), right.name, s.line), s.line))
            else:
                raise TypeError(f"Cannot compile {s!r}")

    block(body)
    return tuple(code)


class Frame:
    __slots__ = ("fn", "pc", "env", "stack", "store_into", "fork_phase", "fork_hold")

    def __init__(self, fn: CompiledFn, args: list, store_into: str | None = None):
        self.fn, self.pc, self.env, self.stack = fn, 0, dict(zip(fn.params, args)), []
        self.store_into, self.fork_phase, self.fork_hold = store_into, 0, None


class Task:
    __slots__ = ("id", "parent", "fork", "branch", "fn", "frames", "state")

    def __init__(self, task_id, parent, fork, branch, fn):
        self.id, self.parent, self.fork, self.branch, self.fn = task_id, parent, fork, branch, fn
        self.frames, self.state = [], RUNNABLE


class Join:
    __slots__ = ("id", "parent", "left", "right", "left_name", "right_name", "results")

    def __init__(self, fork_id, parent, left, right, left_name, right_name):
        self.id, self.parent, self.left, self.right = fork_id, parent, left, right
        self.left_name, self.right_name, self.results = left_name, right_name, {}


class Machine:
    def __init__(self, program: Program, mode: str = "concurrent", limits: Limits = Limits(),
                 schedule: str = "fifo", seed: int = 0, trace: bool = False, chooser=None, on_event=None):
        if mode not in MODES:
            raise ValueError(f"Unknown mode {mode}")
        if schedule not in SCHEDULES:
            raise ValueError(f"Unknown schedule {schedule}")
        if min(limits.fuel, limits.max_tasks, limits.max_depth, limits.workers, limits.quantum) < 1:
            raise ValueError("Resource limits must be positive")
        self.program = compile_program(program)
        self.mode, self.limits, self.schedule = mode, limits, schedule
        self.rng = random.Random(seed)
        self.chooser, self.on_event, self.trace = chooser, on_event, trace
        self.events = []
        self.tasks, self.joins, self.waiting_on = {}, {}, {}
        self.queue = deque()
        self.next_task = self.next_fork = 1
        self.live = self.steps = 0
        self.stats = {"tasks_created": 0, "max_live_tasks": 0, "forks": 0, "joins": 0,
                      "slices": 0, "max_frames": 0}
        self.root_value = self.root_fault = None

    # -- events -------------------------------------------------------------------------------
    def emit(self, kind: str, **fields) -> None:
        event = {"seq": len(self.events) + 1 if self.trace else None, "event": kind, **fields}
        if self.trace:
            self.events.append(event)
        if self.on_event:
            self.on_event(event)

    # -- tasks --------------------------------------------------------------------------------
    def spawn(self, fn_name, args, parent=None, fork=None, branch=None, line=0) -> Task:
        if self.live + 1 > self.limits.max_tasks:
            raise RuntimeFault("P423", f"Live activation limit {self.limits.max_tasks} exceeded.", line)
        task = Task(self.next_task, parent, fork, branch, fn_name)
        self.next_task += 1
        self.tasks[task.id] = task
        self.live += 1
        self.stats["tasks_created"] += 1
        self.stats["max_live_tasks"] = max(self.stats["max_live_tasks"], self.live)
        self.push_frame(task, fn_name, args, line)
        self.queue.append(task.id)
        self.emit("activation_created", task=task.id, parent=parent, fork=fork, branch=branch, fn=fn_name)
        return task

    def push_frame(self, task: Task, fn_name: str, args: list, line: int, store_into=None) -> None:
        if len(task.frames) >= self.limits.max_depth:
            raise RuntimeFault("P422", f"Call depth limit {self.limits.max_depth} exceeded in `{fn_name}`.", line)
        task.frames.append(Frame(self.program[fn_name], args, store_into))
        self.stats["max_frames"] = max(self.stats["max_frames"], len(task.frames))

    def pick(self):
        while self.queue:
            if self.chooser is not None:
                ids = [t for t in self.queue if self.tasks[t].state == RUNNABLE]
                if not ids:
                    self.queue.clear()
                    return None
                chosen = ids[self.chooser(ids)]
                self.queue.remove(chosen)
                return self.tasks[chosen]
            if self.schedule == "fifo":
                task_id = self.queue.popleft()
            elif self.schedule == "lifo":
                task_id = self.queue.pop()
            else:
                index = self.rng.randrange(len(self.queue))
                task_id = self.queue[index]
                del self.queue[index]
            if self.tasks[task_id].state == RUNNABLE:
                return self.tasks[task_id]
        return None

    # -- execution ----------------------------------------------------------------------------
    def run(self, entry: str, args: list):
        if entry not in self.program:
            raise RuntimeFault("P425", f"Unknown entry function `{entry}`.")
        root = self.spawn(entry, args)
        while self.root_value is None and self.root_fault is None:
            batch = []
            while len(batch) < self.limits.workers:
                task = self.pick()
                if task is None:
                    break
                batch.append(task)
            if not batch:
                raise RuntimeFault("P426", "Scheduler deadlock: no runnable activation and no root result.")
            self.stats["slices"] += 1
            for task in batch:
                if task.state != RUNNABLE:
                    continue
                steps = 0
                try:
                    while steps < self.limits.quantum and task.state == RUNNABLE:
                        if self.steps >= self.limits.fuel:
                            frame = task.frames[-1]
                            raise RuntimeFault("P421", f"Fuel budget of {self.limits.fuel} instructions exhausted "
                                                       f"in `{frame.fn.name}` (resource limit; termination is "
                                                       "not checked).", frame.fn.code[frame.pc][2])
                        self.steps += 1
                        steps += 1
                        self.execute(task)
                except RuntimeFault as fault:
                    self.emit("run", task=task.id, steps=steps)
                    self.fail(task, fault)
                    continue
                self.emit("run", task=task.id, steps=steps)
                if task.state == RUNNABLE:
                    self.queue.append(task.id)
        pending = self.live, len(self.joins), len(self.waiting_on)
        if pending != (0, 0, 0):
            raise RuntimeFault("P427", f"Internal error: pending tasks/joins after root completion: {pending}.")
        self.stats.update(steps=self.steps, pending_tasks=self.live, pending_joins=len(self.joins),
                          root_task=root.id)
        if self.root_fault is not None:
            raise self.root_fault
        return self.root_value

    def execute(self, task: Task) -> None:
        frame = task.frames[-1]
        op, arg, line = frame.fn.code[frame.pc]
        stack = frame.stack
        if op == "CONST":
            stack.append(arg)
        elif op == "LOAD":
            stack.append(frame.env[arg])
        elif op == "STORE":
            frame.env[arg] = stack.pop()
        elif op == "LE":
            right = stack.pop()
            stack.append(stack.pop() <= right)
        elif op == "PRIM":
            name, argc = arg
            args = self.pop_args(stack, argc)
            stack.append(PRIMITIVES[name][2](*args, line))
        elif op == "JF":
            frame.pc = frame.pc + 1 if stack.pop() else arg
            return
        elif op == "CALL":
            name, argc = arg
            args = self.pop_args(stack, argc)
            frame.pc += 1
            self.push_frame(task, name, args, line)
            return
        elif op == "RET":
            self.ret(task, stack.pop())
            return
        elif op == "FORK":
            self.fork(task, frame, arg)
            return
        frame.pc += 1

    @staticmethod
    def pop_args(stack: list, argc: int) -> list:
        if not argc:
            return []
        args = stack[-argc:]
        del stack[-argc:]
        return args

    def ret(self, task: Task, value) -> None:
        done = task.frames.pop()
        if task.frames:
            caller = task.frames[-1]
            if done.store_into is not None:
                caller.env[done.store_into] = value
            else:
                caller.stack.append(value)
            return
        self.complete(task, value)

    def fork(self, task: Task, frame: Frame, spec: ForkSpec) -> None:
        if self.mode == "sequential":
            # Run the two calls one after the other in this activation; the FORK pc is revisited.
            if frame.fork_phase == 0:
                right_args = self.pop_args(frame.stack, spec.right_argc)
                left_args = self.pop_args(frame.stack, spec.left_argc)
                frame.fork_phase, frame.fork_hold = 1, right_args
                self.emit("fork_inline", task=task.id, left_fn=spec.left_fn, right_fn=spec.right_fn, line=spec.line)
                self.push_frame(task, spec.left_fn, left_args, spec.line, store_into=spec.left_name)
            elif frame.fork_phase == 1:
                frame.fork_phase = 2
                self.push_frame(task, spec.right_fn, frame.fork_hold, spec.line, store_into=spec.right_name)
            else:
                frame.fork_phase, frame.fork_hold = 0, None
                frame.pc += 1
                self.emit("join_inline", task=task.id, line=spec.line)
            return
        right_args = self.pop_args(frame.stack, spec.right_argc)
        left_args = self.pop_args(frame.stack, spec.left_argc)
        frame.pc += 1
        if self.live + 2 > self.limits.max_tasks:
            raise RuntimeFault("P423", f"Live activation limit {self.limits.max_tasks} would be exceeded by a fork.",
                               spec.line)
        fork_id = self.next_fork
        self.next_fork += 1
        self.stats["forks"] += 1
        self.emit("fork", task=task.id, fork=fork_id, line=spec.line)
        left = self.spawn(spec.left_fn, left_args, task.id, fork_id, "left", spec.line)
        right = self.spawn(spec.right_fn, right_args, task.id, fork_id, "right", spec.line)
        self.joins[fork_id] = Join(fork_id, task.id, left.id, right.id, spec.left_name, spec.right_name)
        self.waiting_on[task.id] = fork_id
        task.state = WAITING
        self.emit("wait", task=task.id, fork=fork_id, left=left.id, right=right.id)

    def complete(self, task: Task, value) -> None:
        task.state = DONE
        self.live -= 1
        if task.parent is None:
            self.root_value = value
            self.emit("root_complete", task=task.id)
            return
        join = self.joins[task.fork]
        if task.branch in join.results or task.id not in (join.left, join.right):
            raise RuntimeFault("P427", f"Internal error: duplicate or mismatched completion for task {task.id}.")
        join.results[task.branch] = value
        self.emit("child_complete", task=task.id, parent=task.parent, fork=task.fork, branch=task.branch)
        if len(join.results) == 2:
            del self.joins[join.id]
            del self.waiting_on[join.parent]
            parent = self.tasks[join.parent]
            env = parent.frames[-1].env
            env[join.left_name] = join.results["left"]
            env[join.right_name] = join.results["right"]
            parent.state = RUNNABLE
            self.queue.append(parent.id)
            self.stats["joins"] += 1
            self.emit("join", task=parent.id, fork=join.id, left=join.left, right=join.right)

    def fail(self, task: Task, fault: RuntimeFault) -> None:
        """Fail `task`, cancel its sibling subtree, and propagate the failure to each ancestor."""
        cause = None
        while task is not None:
            task.state = FAILED
            self.live -= 1
            self.emit("failure", task=task.id, code=fault.code, message=fault.message, cause=cause)
            if task.parent is None:
                self.root_fault = fault
                return
            join = self.joins.pop(task.fork)
            del self.waiting_on[join.parent]
            sibling = join.right if task.branch == "left" else join.left
            self.cancel(sibling)
            cause, task = task.id, self.tasks[task.parent]

    def cancel(self, task_id: int) -> None:
        pending = [task_id]
        while pending:
            task = self.tasks[pending.pop()]
            if task.state not in (RUNNABLE, WAITING):
                continue
            if task.state == WAITING:
                join = self.joins.pop(self.waiting_on.pop(task.id))
                pending.extend((join.left, join.right))
            task.state = CANCELLED
            self.live -= 1
            self.emit("cancelled", task=task.id)
