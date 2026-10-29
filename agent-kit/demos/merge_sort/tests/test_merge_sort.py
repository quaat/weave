"""Merge-sort demo tests: algorithm behavior through the real checker/scheduler, and the CLI contract.

Python's sorted() is used here only as an independent test oracle.
"""
from collections import Counter
from itertools import product
from pathlib import Path
import json
import random
import subprocess
import sys
import tempfile
import unittest

DEMO = Path(__file__).resolve().parents[1]
ROOT = DEMO.parents[1]
APP = DEMO / 'run_demo.py'
SOURCE = (DEMO / 'merge_sort.weave').read_text()
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / '.agents/skills/weave/scripts'))

from weave_pure import IntList, Limits, Machine, check_source  # noqa: E402

PROGRAM = check_source(SOURCE)
SCHEDULES = [dict(mode='sequential'),
             dict(mode='concurrent'),
             dict(mode='concurrent', schedule='lifo', limits=Limits(workers=1, quantum=1)),
             dict(mode='concurrent', schedule='random', seed=11, limits=Limits(workers=3, quantum=2))]


class Tagged(int):
    """Test instrumentation: an int carrying its original position. `<=` compares only the int value."""

    def __new__(cls, value, tag):
        obj = super().__new__(cls, value)
        obj.tag = tag
        return obj


def sort(values, entry='merge_sort', **options):
    machine = Machine(PROGRAM, **options)
    xs = IntList.from_iter(values)
    out = machine.run(entry, [xs])
    return out, xs, machine


class AlgorithmTests(unittest.TestCase):
    CASES = {
        'empty': [], 'singleton': [7], 'two': [2, 1], 'two_sorted': [1, 2], 'sorted': list(range(10)),
        'reverse': list(range(10, 0, -1)), 'duplicates': [3, 1, 3, 1, 2, 3, 1, 2], 'all_equal': [4] * 9,
        'negative': [-3, -10, -1, -7], 'mixed_sign': [5, -2, 5, 0, -2], 'odd': [9, 8, 7, 6, 5],
        'even': [6, 5, 4, 3, 2, 1], 'demo': [8, 3, 5, 1, 9, 2, 7, 4, 6],
    }

    def assertSortedResult(self, values, options):
        out, xs, _ = sort(values, **options)
        result = out.to_list()
        self.assertEqual(result, sorted(values))
        self.assertTrue(all(a <= b for a, b in zip(result, result[1:])))
        self.assertEqual(Counter(result), Counter(values))
        self.assertEqual(xs.to_list(), values, 'input list is unchanged')
        again, _, _ = sort(result, **options)
        self.assertEqual(again.to_list(), result, 'idempotent')
        return result

    def test_named_cases_all_modes(self):
        for name, values in self.CASES.items():
            for options in SCHEDULES:
                with self.subTest(case=name, options=options):
                    self.assertSortedResult(values, options)

    def test_exhaustive_short_inputs(self):
        count = 0
        for n in range(0, 6):
            for values in product((-1, 0, 1), repeat=n):
                for options in (SCHEDULES[0], SCHEDULES[2]):
                    self.assertEqual(sort(list(values), **options)[0].to_list(), sorted(values))
                count += 1
        self.assertEqual(count, 364)

    def test_randomized_cases_reproducible(self):
        rng = random.Random(20261028)
        for _ in range(60):
            values = [rng.randint(-100, 100) for _ in range(rng.randint(0, 80))]
            results = {json.dumps(sort(values, **o)[0].to_list()) for o in SCHEDULES}
            self.assertEqual(results, {json.dumps(sorted(values))}, 'all modes and schedules agree')

    def test_stability_by_original_identity(self):
        rng = random.Random(5)
        for _ in range(20):
            keys = [rng.randint(0, 3) for _ in range(rng.randint(1, 40))]
            values = [Tagged(k, i) for i, k in enumerate(keys)]
            for options in SCHEDULES:
                out = list(sort(values, **options)[0].items())
                self.assertEqual([int(v) for v in out], sorted(keys))
                self.assertTrue(all(isinstance(v, Tagged) for v in out), 'elements keep their identity')
                for a, b in zip(out, out[1:]):
                    if int(a) == int(b):
                        self.assertLess(a.tag, b.tag, 'equal keys keep original order')

    def test_merge_takes_left_on_equal_keys(self):
        left = IntList.from_iter([Tagged(1, 'L')])
        right = IntList.from_iter([Tagged(1, 'R')])
        out = Machine(PROGRAM).run('merge', [left, right])
        self.assertEqual([v.tag for v in out.items()], ['L', 'R'])


class CliTests(unittest.TestCase):
    def app(self, *args, cwd=ROOT):
        return subprocess.run([sys.executable, '-B', str(APP), *map(str, args)], cwd=cwd,
                              capture_output=True, text=True, timeout=120)

    def test_contract_commands(self):
        proc = self.app('--values', '[8,3,5,1,9,2,7,4,6]', '--mode', 'sequential')
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn('Sorted: [1, 2, 3, 4, 5, 6, 7, 8, 9]', proc.stdout)
        self.assertIn('0 forks', proc.stdout)
        proc = self.app('--values', '[8,3,5,1,9,2,7,4,6]', '--mode', 'concurrent', '--trace')
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn('Sorted: [1, 2, 3, 4, 5, 6, 7, 8, 9]', proc.stdout)
        for event in ('activation_created', 'fork', 'wait', 'child_complete', 'join', 'root_complete'):
            self.assertIn(event, proc.stdout)
        proc = self.app('--values', '[]', '--mode', 'concurrent')
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn('Sorted: []', proc.stdout)
        proc = self.app('--values', '[5,-2,5,0,-2]', '--mode', 'concurrent', '--json')
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = json.loads(proc.stdout)
        self.assertEqual(data['output'], [-2, -2, 0, 5, 5])
        self.assertEqual((data['status'], data['check']), ('EXECUTED', 'CHECKED'))
        self.assertEqual(data['stats']['forks'], 4)
        self.assertEqual(data['stats']['pending_tasks'], 0)

    def test_json_trace_is_single_document(self):
        proc = self.app('--values', '[3,1,2]', '--json', '--trace')
        self.assertEqual(proc.returncode, 0)
        data = json.loads(proc.stdout)
        self.assertEqual(data['events'][-1]['event'], 'run')
        self.assertIn('root_complete', [e['event'] for e in data['events']])

    def test_modes_agree_via_cli(self):
        outputs = set()
        for args in (['--mode', 'sequential'], ['--schedule', 'lifo', '--workers', '1', '--quantum', '1'],
                     ['--schedule', 'random', '--seed', '3']):
            proc = self.app('--values', '[4,-1,4,2,0,-1,9]', '--json', *args)
            outputs.add(json.dumps(json.loads(proc.stdout)['output']))
        self.assertEqual(outputs, {json.dumps([-1, -1, 0, 2, 4, 4, 9])})

    def test_invalid_input_rejected(self):
        for value in ('[true]', '[1.0]', '["a"]', '[[1]]', '{"a": 1}', 'nope', '5', 'null', '[1, null]'):
            with self.subTest(value=value):
                proc = self.app('--values', value, '--json')
                self.assertEqual(proc.returncode, 2)
                self.assertEqual(json.loads(proc.stdout)['diagnostic']['code'], 'INPUT')
        proc = self.app('--values', json.dumps(list(range(11))), '--max-values', '10')
        self.assertEqual(proc.returncode, 2)
        self.assertIn('limit', proc.stderr)
        for args in (['--mode', 'parallel', '--values', '[]'], ['--bogus'], []):
            self.assertEqual(self.app(*args).returncode, 2)

    def test_help(self):
        proc = self.app('--help')
        self.assertEqual(proc.returncode, 0)
        self.assertIn('--max-values', proc.stdout)

    def test_runtime_errors_and_resource_exhaustion(self):
        for args, code in ((['--fuel', '20'], 'P421'), (['--max-tasks', '2'], 'P423'), (['--max-depth', '2'], 'P422')):
            proc = self.app('--values', '[5,4,3,2,1]', '--json', *args)
            self.assertEqual(proc.returncode, 2, proc.stdout)
            data = json.loads(proc.stdout)
            self.assertFalse(data['ok'])
            self.assertNotIn('output', data, 'no partial output')
            self.assertEqual(data['diagnostic']['code'], code)

    def test_check_failure_and_runtime_failure_from_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            broken = Path(tmp) / 'merge_sort.weave'
            broken.write_text(SOURCE.replace('return merge(left_sorted, right_sorted)', 'return left_sorted + 1'))
            proc = self.app('--values', '[2,1]', '--source', broken)
            self.assertEqual(proc.returncode, 1)
            self.assertEqual(proc.stdout, '')
            self.assertIn('P400', proc.stderr)
            faulty = Path(tmp) / 'faulty.weave'
            faulty.write_text(SOURCE.replace('return cons(head(right), merge(left, tail(right)))',
                                             'return cons(head(right), merge(left, tail(tail(right))))'))
            proc = self.app('--values', '[2,1]', '--source', faulty, '--json')
            self.assertEqual(proc.returncode, 2)
            self.assertEqual(json.loads(proc.stdout)['diagnostic']['code'], 'P420')

    def test_absolute_path_from_other_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = self.app('--values', '[3,2,1]', '--json', cwd=tmp)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)['output'], [1, 2, 3])


if __name__ == '__main__':
    unittest.main()
