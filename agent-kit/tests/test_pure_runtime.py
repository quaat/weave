"""Runtime and scheduler tests for the pure extension: primitives, limits, fork/join pairing, failure."""
from collections import Counter
from pathlib import Path
import json
import random
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / 'scripts/weave.py'
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / '.agents/skills/weave/scripts'))

from weave_pure import IntList, Limits, Machine, RuntimeFault, check_source, run_source  # noqa: E402
from weave_pure.values import PRIMITIVES  # noqa: E402

MERGE_SORT = (ROOT / 'demos/merge_sort/merge_sort.weave').read_text()

SPIN = '''\
fn spin(xs: IntList) -> IntList:
    return spin(xs)
'''

BOOM = '''\
fn boom(xs: IntList) -> IntList:
    fork:
        let a = boom(xs)
        let b = boom(xs)
    return a
'''

# Non-commutative join: rebuilds the input from its two halves, left then right.
REBUILD = '''\
fn rebuild(xs: IntList) -> IntList:
    let halves = split_half(xs)
    fork:
        let l = copy(first(halves))
        let r = copy(second(halves))
    return append(l, r)

fn copy(xs: IntList) -> IntList:
    if is_empty(xs):
        return xs
    else:
        return cons(head(xs), copy(tail(xs)))

fn append(a: IntList, b: IntList) -> IntList:
    if is_empty(a):
        return b
    else:
        return cons(head(a), append(tail(a), b))
'''

CHILD_FAILURE = '''\
fn top(xs: IntList, ys: IntList) -> IntList:
    fork:
        let a = slow(xs)
        let b = bad(ys)
    return a

fn slow(xs: IntList) -> IntList:
    if is_empty(xs):
        return xs
    else:
        return cons(head(xs), slow(tail(xs)))

fn bad(xs: IntList) -> IntList:
    return tail(tail(xs))
'''


def machine(source, **options):
    return Machine(check_source(source), trace=True, **options)


def run(source, entry, *values, **options):
    m = machine(source, **options)
    return m.run(entry, [IntList.from_iter(v) for v in values]), m


def check_pairing(test, m):
    """Structural checks on a completed concurrent trace."""
    events = m.events
    created = [e for e in events if e['event'] == 'activation_created']
    ids = [e['task'] for e in created]
    test.assertEqual(len(ids), len(set(ids)), 'task IDs must be unique')
    roots = [e for e in created if e['parent'] is None]
    test.assertEqual(len(roots), 1)
    forks = {e['fork']: e for e in events if e['event'] == 'fork'}
    by_fork = {}
    for e in created:
        if e['fork'] is not None:
            by_fork.setdefault(e['fork'], []).append(e)
    test.assertEqual(set(by_fork), set(forks))
    for fork_id, children in by_fork.items():
        test.assertEqual(sorted(c['branch'] for c in children), ['left', 'right'])
        test.assertEqual({c['parent'] for c in children}, {forks[fork_id]['task']})
    completions = Counter(e['task'] for e in events if e['event'] == 'child_complete')
    test.assertTrue(all(n == 1 for n in completions.values()), 'no duplicate completion')
    test.assertEqual(set(completions), {c['task'] for cs in by_fork.values() for c in cs})
    joins = [e for e in events if e['event'] == 'join']
    test.assertEqual(sorted(j['fork'] for j in joins), sorted(forks), 'exactly one join per fork')
    seq = {(e['event'], e.get('task')): e['seq'] for e in events}
    for j in joins:
        test.assertEqual(j['task'], forks[j['fork']]['task'])
        test.assertEqual({j['left'], j['right']}, {c['task'] for c in by_fork[j['fork']]})
        for child in (j['left'], j['right']):
            test.assertLess(seq[('child_complete', child)], j['seq'])
        resumed = [e for e in events if e['event'] == 'run' and e['task'] == j['task'] and e['seq'] > j['seq']]
        test.assertTrue(resumed, 'parent resumes after join')
        wait = next(e for e in events if e['event'] == 'wait' and e['fork'] == j['fork'])
        parent_runs = [e for e in events if e['event'] == 'run' and e['task'] == j['task']
                       and wait['seq'] < e['seq'] < j['seq'] and e['steps'] > 0]
        # The slice that executed FORK is reported after the wait event; no further parent work before the join.
        test.assertLessEqual(len(parent_runs), 1)
    test.assertEqual([e['event'] for e in events].count('root_complete'), 1)
    test.assertEqual(m.stats['pending_tasks'], 0)
    test.assertEqual(m.stats['pending_joins'], 0)
    test.assertEqual(m.joins, {})


class PrimitiveTests(unittest.TestCase):
    def test_persistent_list_sharing(self):
        xs = IntList.from_iter([1, 2, 3, 4, 5])
        pair = PRIMITIVES['split_half'][2](xs, 0)
        self.assertEqual((pair.first.to_list(), pair.second.to_list()), ([1, 2], [3, 4, 5]))
        self.assertIs(pair.second, xs.tail.tail, 'second half shares the original suffix')
        ys = PRIMITIVES['cons'][2](0, xs, 0)
        self.assertIs(PRIMITIVES['tail'][2](ys, 0), xs, 'cons/tail do not copy')
        self.assertEqual(xs.to_list(), [1, 2, 3, 4, 5])

    def test_split_half_balance(self):
        for n in range(0, 12):
            pair = PRIMITIVES['split_half'][2](IntList.from_iter(range(n)), 0)
            a, b = pair.first.to_list(), pair.second.to_list()
            self.assertEqual(a + b, list(range(n)))
            self.assertLessEqual(abs(len(a) - len(b)), 1)
            if n > 1:
                self.assertLess(max(len(a), len(b)), n)

    def test_empty_head_and_tail_fail_with_location(self):
        for name in ('head', 'tail'):
            src = f'fn f(xs: IntList) -> IntList:\n    return cons(1, {name}(xs))\n' if name == 'tail' else \
                f'fn f(xs: IntList) -> Int:\n    return {name}(xs)\n'
            with self.assertRaises(RuntimeFault) as ctx:
                run(src, 'f', [])
            self.assertEqual((ctx.exception.code, ctx.exception.line, ctx.exception.stage), ('P420', 2, 'runtime'))


class LimitTests(unittest.TestCase):
    def test_nonterminating_function_exhausts_fuel_via_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'spin.weave'
            path.write_text(SPIN)
            proc = subprocess.run([sys.executable, '-B', str(CLI), '--json', 'run-pure', path, '--entry', 'spin',
                                   '--args', '[[1]]', '--fuel', '5000'], capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 2)
        d = json.loads(proc.stdout)['diagnostic']
        self.assertEqual((d['code'], d['stage'], d['span']['start']['line']), ('P421', 'runtime', 2))

    def test_depth_limit_is_structured(self):
        with self.assertRaises(RuntimeFault) as ctx:
            run(SPIN, 'spin', [1], limits=Limits(max_depth=50))
        self.assertEqual(ctx.exception.code, 'P422')

    def test_fork_bomb_hits_task_limit_and_cleans_up(self):
        for workers in (1, 3):
            m = machine(BOOM, limits=Limits(max_tasks=64, workers=workers))
            with self.assertRaises(RuntimeFault) as ctx:
                m.run('boom', [IntList.from_iter([1])])
            self.assertEqual(ctx.exception.code, 'P423')
            self.assertLessEqual(m.stats['max_live_tasks'], 64)
            self.assertEqual((m.stats['pending_tasks'], m.stats['pending_joins']), (0, 0))
            self.assertIsNone(m.root_value)

    def test_large_input_uses_interpreter_frames_not_host_stack(self):
        n = 3 * sys.getrecursionlimit()
        values = list(range(n, 0, -1))
        for mode in ('sequential', 'concurrent'):
            value, m = run(MERGE_SORT, 'merge_sort', values, mode=mode, limits=Limits(max_tasks=4 * n))
            self.assertEqual(value.to_list(), sorted(values))
            self.assertGreater(m.stats['max_frames'], sys.getrecursionlimit())
        for mode in ('sequential', 'concurrent'):
            with self.assertRaises(RuntimeFault) as ctx:
                run(MERGE_SORT, 'merge_sort', values, mode=mode, limits=Limits(max_depth=100, max_tasks=4 * n))
            self.assertEqual(ctx.exception.code, 'P422')

    def test_input_decoding_and_entry_errors(self):
        for args, code in (([[1, True]], 'P424'), ([[1.5]], 'P424'), ([['a']], 'P424'), ([[[1]]], 'P424'),
                           ([5], 'P424'), ([], 'P424')):
            with self.assertRaises(RuntimeFault) as ctx:
                run_source(MERGE_SORT, 'merge_sort', args)
            self.assertEqual(ctx.exception.code, code, args)
        with self.assertRaises(RuntimeFault) as ctx:
            run_source(MERGE_SORT, 'nope', [[1]])
        self.assertEqual(ctx.exception.code, 'P425')


class SchedulerTests(unittest.TestCase):
    def test_siblings_interleave_before_either_completes(self):
        value, m = run(MERGE_SORT, 'merge_sort', [8, 3, 5, 1, 9, 2, 7, 4], limits=Limits(quantum=1, workers=2))
        self.assertEqual(value.to_list(), [1, 2, 3, 4, 5, 7, 8, 9])
        root_fork = next(e for e in m.events if e['event'] == 'wait' and e['task'] == 1)
        first_completion = min(e['seq'] for e in m.events
                               if e['event'] == 'child_complete' and e['fork'] == root_fork['fork'])
        for child in (root_fork['left'], root_fork['right']):
            progressed = [e for e in m.events if e['event'] == 'run' and e['task'] == child and e['steps'] > 0
                          and e['seq'] < first_completion]
            self.assertGreaterEqual(len(progressed), 2, f'task {child} progressed before any completion')
        check_pairing(self, m)

    def completion_order(self, m, fork_id):
        return [e['branch'] for e in m.events if e['event'] == 'child_complete' and e['fork'] == fork_id]

    def test_left_first_and_right_first_completion_join_in_source_order(self):
        values = list(range(1, 21))
        lowest = lambda ids: ids.index(min(ids))   # noqa: E731 - always resume the oldest activation
        highest = lambda ids: ids.index(max(ids))  # noqa: E731 - always resume the newest activation
        orders = {}
        for name, chooser in (('left_first', lowest), ('right_first', highest)):
            value, m = run(REBUILD, 'rebuild', values, chooser=chooser, limits=Limits(quantum=1, workers=1))
            self.assertEqual(value.to_list(), values, 'append(l, r) sees left/right in source order')
            orders[name] = self.completion_order(m, 1)
            check_pairing(self, m)
        self.assertEqual(orders['left_first'], ['left', 'right'])
        self.assertEqual(orders['right_first'], ['right', 'left'])
        # Merge sort too: both completion orders give the same sorted output.
        for chooser in (lowest, highest):
            value, m = run(MERGE_SORT, 'merge_sort', [5, 1, 4, 2, 3, 0], chooser=chooser,
                           limits=Limits(quantum=1, workers=1))
            self.assertEqual(value.to_list(), [0, 1, 2, 3, 4, 5])

    def test_pairing_invariants_across_schedules(self):
        rng = random.Random(7)
        values = [rng.randint(-50, 50) for _ in range(40)]
        expected = sorted(values)
        for schedule in ('fifo', 'lifo', 'random'):
            for workers in (1, 2, 8):
                for quantum in (1, 5, 64):
                    value, m = run(MERGE_SORT, 'merge_sort', values, schedule=schedule, seed=workers * quantum,
                                   limits=Limits(workers=workers, quantum=quantum))
                    self.assertEqual(value.to_list(), expected)
                    self.assertEqual(m.stats['forks'], len(values) - 1)
                    check_pairing(self, m)

    def test_minimal_concurrency_limit_and_deep_forks(self):
        values = list(range(256, 0, -1))
        value, m = run(MERGE_SORT, 'merge_sort', values, limits=Limits(workers=1, quantum=1))
        self.assertEqual(value.to_list(), sorted(values))
        self.assertEqual(m.stats['forks'], 255)
        self.assertLessEqual(m.stats['max_live_tasks'], 2 * len(values))
        check_pairing(self, m)

    def test_waiting_parent_occupies_no_worker(self):
        value, m = run(MERGE_SORT, 'merge_sort', [4, 3, 2, 1], limits=Limits(workers=1))
        waiting = set()
        for e in m.events:
            if e['event'] == 'wait':
                waiting.add(e['task'])
            elif e['event'] == 'join':
                waiting.discard(e['task'])
            elif e['event'] == 'run' and e['steps'] > 0 and e['task'] in waiting:
                # The only permitted run of a waiting task is the slice that executed its FORK.
                prior_wait = max(x['seq'] for x in m.events if x['event'] == 'wait' and x['task'] == e['task']
                                 and x['seq'] < e['seq'])
                between = [x for x in m.events if prior_wait < x['seq'] < e['seq'] and x['event'] == 'run']
                self.assertEqual(between, [], 'a waiting parent was dispatched')

    def test_child_failure_fails_parent_and_cancels_sibling(self):
        m = machine(CHILD_FAILURE, limits=Limits(quantum=2))
        with self.assertRaises(RuntimeFault) as ctx:
            m.run('top', [IntList.from_iter(range(60)), IntList.from_iter([1])])
        self.assertEqual((ctx.exception.code, ctx.exception.line), ('P420', 14))
        kinds = [(e['event'], e['task']) for e in m.events]
        self.assertIn(('failure', 3), kinds)
        self.assertIn(('cancelled', 2), kinds)
        parent_failure = next(e for e in m.events if e['event'] == 'failure' and e['task'] == 1)
        self.assertEqual(parent_failure['cause'], 3)
        self.assertNotIn('join', [e['event'] for e in m.events])
        self.assertNotIn('root_complete', [e['event'] for e in m.events])
        self.assertEqual((m.stats['pending_tasks'], m.stats['pending_joins']), (0, 0))
        self.assertEqual(m.joins, {})

    def test_deep_failure_cancels_whole_tree(self):
        src = MERGE_SORT.replace('        return xs\n    else:\n        let halves',
                                 '        return tail(tail(xs))\n    else:\n        let halves')
        m = machine(src)
        with self.assertRaises(RuntimeFault) as ctx:
            m.run('merge_sort', [IntList.from_iter(range(32))])
        self.assertEqual(ctx.exception.code, 'P420')
        ended = {e['task'] for e in m.events if e['event'] in ('failure', 'cancelled', 'child_complete')}
        created = {e['task'] for e in m.events if e['event'] == 'activation_created'}
        self.assertEqual(ended, created, 'every activation completed, failed, or was cancelled')
        self.assertEqual((m.stats['pending_tasks'], m.stats['pending_joins']), (0, 0))

    def test_sequential_mode_has_no_child_activations(self):
        value, m = run(MERGE_SORT, 'merge_sort', [3, 1, 2], mode='sequential')
        self.assertEqual(value.to_list(), [1, 2, 3])
        self.assertEqual(m.stats['tasks_created'], 1)
        self.assertEqual([e['event'] for e in m.events].count('fork_inline'), 2)


class GenericExecutionTests(unittest.TestCase):
    def test_renamed_recursive_function_runs(self):
        src = MERGE_SORT.replace('merge_sort', 'order_numbers').replace('merge(', 'combine(')
        value, _ = run(src, 'order_numbers', [3, -1, 2])
        self.assertEqual(value.to_list(), [-1, 2, 3])

    def test_modified_comparison_changes_behavior(self):
        old = 'if head(left) <= head(right):'
        self.assertEqual(MERGE_SORT.count(old), 1)
        src = MERGE_SORT.replace(old, 'if head(right) <= head(left):')
        value, _ = run(src, 'merge_sort', [3, 1, 2, 5, 4])
        self.assertEqual(value.to_list(), [5, 4, 3, 2, 1])

    def test_modified_branch_changes_behavior(self):
        src = MERGE_SORT.replace('    if length(xs) <= 1:\n        return xs',
                                 '    if length(xs) <= 1:\n        return cons(0, xs)')
        value, _ = run(src, 'merge_sort', [2, 1])
        self.assertEqual(value.to_list(), [0, 0, 1, 2])


class RunnerCommandTests(unittest.TestCase):
    def cli(self, *args):
        return subprocess.run([sys.executable, '-B', str(CLI), *map(str, args)], cwd=ROOT,
                              capture_output=True, text=True, timeout=120)

    def test_run_pure_json_and_text(self):
        path = ROOT / 'demos/merge_sort/merge_sort.weave'
        proc = self.cli('--json', 'run-pure', path, '--entry', 'merge_sort', '--args', '[[2,1]]', '--trace')
        self.assertEqual(proc.returncode, 0, proc.stdout)
        data = json.loads(proc.stdout)
        self.assertEqual((data['runtime_status'], data['result']), ('completed', [1, 2]))
        # The pure extension is outside F0: its only claim is NOT ESTABLISHED, never a passing label.
        self.assertEqual(data['check']['claim_label'], 'NOT ESTABLISHED')
        self.assertEqual(data['check']['functions'], ['merge_sort', 'merge'])
        self.assertNotIn('status', data)
        self.assertNotIn('accounting', data)
        self.assertIn('fork', [e['event'] for e in data['events']])
        proc = self.cli('run-pure', path, '--entry', 'merge_sort', '--args', '[[2,1]]', '--mode', 'sequential')
        self.assertEqual(proc.returncode, 0)
        self.assertIn('result: [1, 2]', proc.stdout)
        self.assertIn('runtime status: completed', proc.stdout)
        self.assertTrue(proc.stdout.startswith('NOT ESTABLISHED '), proc.stdout)

    def test_run_pure_failures(self):
        path = ROOT / 'demos/merge_sort/merge_sort.weave'
        for args, code, diag in ((['--args', '[[1,true]]'], 2, 'P424'), (['--args', 'nope'], 2, 'P424'),
                                 (['--args', '[[3,2,1]]', '--max-tasks', '2'], 2, 'P423')):
            proc = self.cli('--json', 'run-pure', path, '--entry', 'merge_sort', *args)
            self.assertEqual(proc.returncode, code, proc.stdout)
            self.assertEqual(json.loads(proc.stdout)['diagnostic']['code'], diag)
        proc = self.cli('--json', 'run-pure', path, '--entry', 'merge_sort', '--workers', '0')
        self.assertEqual(proc.returncode, 2)
        self.assertIn('positive', proc.stderr)
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / 'bad.weave'
            bad.write_text(path.read_text().replace('head(left) <= head(right)', 'head(left) <= right'))
            proc = self.cli('--json', 'run-pure', bad, '--entry', 'merge_sort', '--args', '[[1]]')
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(json.loads(proc.stdout)['diagnostic']['code'], 'P406')


if __name__ == '__main__':
    unittest.main()
