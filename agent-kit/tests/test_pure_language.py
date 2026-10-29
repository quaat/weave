"""Language tests for the kit's pure-function extension: parser, checker, and runner integration."""
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / 'scripts/weave.py'
SKILL = ROOT / '.agents/skills/weave'
sys.dont_write_bytecode = True
sys.path.insert(0, str(SKILL / 'scripts'))

from weave_pure import PureError, check_source, run_source  # noqa: E402

MERGE_SORT = ROOT / 'demos/merge_sort/merge_sort.weave'

LAST = '''\
fn last(xs: IntList) -> Int:
    if is_empty(tail(xs)):
        return head(xs)
    else:
        return last(tail(xs))
'''


def fn(body, sig='f(xs: IntList) -> IntList'):
    return f'fn {sig}:\n' + '\n'.join('    ' + line for line in body.strip('\n').splitlines()) + '\n'


class PureLanguageTests(unittest.TestCase):
    def assertRejects(self, source, code, line=None):
        with self.assertRaises(PureError) as ctx:
            check_source(source)
        self.assertEqual(ctx.exception.code, code, ctx.exception.message)
        self.assertEqual(ctx.exception.stage, 'pure')
        if line is not None:
            self.assertEqual(ctx.exception.line, line, ctx.exception.message)
        return ctx.exception

    def run_cli(self, *args):
        proc = subprocess.run([sys.executable, '-B', str(CLI), '--json', *map(str, args)],
                              cwd=ROOT, text=True, capture_output=True, timeout=60)
        self.assertEqual(proc.stderr, '')
        return proc.returncode, json.loads(proc.stdout)

    # Accepted programs
    def test_merge_sort_source_checks(self):
        program = check_source(MERGE_SORT.read_text())
        self.assertEqual([f.name for f in program.functions], ['merge_sort', 'merge'])

    def test_direct_recursion_and_base_case(self):
        value, _ = run_source(LAST, 'last', [[4, -7, 9]])
        self.assertEqual(value, 9)
        value, _ = run_source(LAST, 'last', [[5]])
        self.assertEqual(value, 5)

    def test_nested_return_expressions_and_literals(self):
        src = fn('return cons(head(xs), cons(-3, cons(length(xs), tail(xs))))')
        value, _ = run_source(src, 'f', [[10, 20]])
        self.assertEqual(value.to_list(), [10, -3, 2, 20])
        src = fn('return 2 <= length(xs)', 'f(xs: IntList) -> Bool')
        self.assertIs(run_source(src, 'f', [[1, 2]])[0], True)
        self.assertIs(run_source(src, 'f', [[1]])[0], False)
        src = fn('return (true)', 'f(b: Bool) -> Bool')
        self.assertIs(run_source(src, 'f', [False])[0], True)

    def test_forward_reference_and_pair_projections(self):
        src = fn('return g(split_half(xs))') + fn('return second(p)', 'g(p: IntListPair) -> IntList')
        self.assertEqual(run_source(src, 'f', [[1, 2, 3]])[0].to_list(), [2, 3])

    def test_fork_results_visible_after_join(self):
        src = fn('''
fork:
    let a = id(xs)
    let b = id(tail(xs))
return cons(head(b), a)''') + fn('return ys', 'id(ys: IntList) -> IntList')
        for mode in ('sequential', 'concurrent'):
            self.assertEqual(run_source(src, 'f', [[1, 2]], mode=mode)[0].to_list(), [2, 1, 2])

    # Signatures, returns, calls
    def test_unused_function_body_is_checked(self):
        self.assertRejects(fn('return xs') + fn('return length(xs)', 'unused(xs: IntList) -> IntList'), 'P407', 4)

    def test_return_type_mismatch(self):
        self.assertRejects(fn('return length(xs)'), 'P407', 2)
        self.assertRejects(fn('return'), 'P407', 2)

    def test_argument_type_and_count(self):
        self.assertRejects(fn('return tail(head(xs))'), 'P406', 2)
        self.assertRejects(fn('return cons(true, xs)'), 'P406', 2)
        self.assertRejects(fn('if xs <= xs:\n    return xs\nelse:\n    return xs'), 'P406', 2)
        self.assertRejects(fn('return cons(1)'), 'P405', 2)
        self.assertRejects(fn('return f(xs, xs)'), 'P405', 2)

    def test_unknown_names_and_primitives(self):
        self.assertRejects(fn('return sorted(xs)'), 'P404', 2)
        self.assertRejects(fn('return merge_sorted(xs, xs)'), 'P404', 2)
        self.assertRejects(fn('return ys'), 'P403', 2)
        err = self.assertRejects(fn('let g = head\nreturn xs'), 'P403', 2)
        self.assertIn('higher-order', err.message)

    def test_explicit_types_required(self):
        self.assertRejects('fn f(xs: IntList):\n    return xs\n', 'P400', 1)
        self.assertRejects('fn f(xs) -> IntList:\n    return xs\n', 'P400', 1)

    # Branches
    def test_malformed_branches(self):
        self.assertRejects(fn('if is_empty(xs):\n    return xs'), 'P408', 2)
        self.assertRejects(fn('if is_empty(xs):\n    return xs\nelse:\n    return xs\nreturn xs'), 'P408', 6)
        self.assertRejects(fn('let n = length(xs)'), 'P408', 2)
        self.assertRejects(fn('return xs\nreturn xs'), 'P408', 3)
        self.assertRejects(fn('else:\n    return xs'), 'P408', 2)
        self.assertRejects(fn('if is_empty(xs):\n    return xs\nelif true:\n    return xs'), 'P408')
        self.assertRejects(fn('if is_empty(xs):\n    let y = xs\nelse:\n    return xs'), 'P408', 3)
        self.assertRejects(fn('if length(xs):\n    return xs\nelse:\n    return xs'), 'P414', 2)

    def test_rebinding_rejected(self):
        self.assertRejects(fn('let xs = tail(xs)\nreturn xs'), 'P413', 2)

    def test_duplicates_and_reserved_names(self):
        self.assertRejects(fn('return xs') + fn('return xs'), 'P402', 3)
        self.assertRejects(fn('return xs', 'head(xs: IntList) -> IntList'), 'P402', 1)
        self.assertRejects(fn('return xs', 'fork(xs: IntList) -> IntList'), 'P400', 1)

    # Recursion shape
    def test_mutual_and_indirect_recursion_rejected(self):
        self.assertRejects(fn('return g(xs)') + fn('return f(xs)', 'g(xs: IntList) -> IntList'), 'P411', 1)
        src = (fn('return g(xs)') + fn('return h(xs)', 'g(xs: IntList) -> IntList')
               + fn('return f(xs)', 'h(xs: IntList) -> IntList'))
        self.assertRejects(src, 'P411', 1)

    # Effects and linear resources
    def test_pure_code_cannot_receive_or_return_hold(self):
        err = self.assertRejects(fn('return 0', 'f(hold: Hold[t, o]) -> Int'), 'P401', 1)
        self.assertIn('linear resource', err.message)
        self.assertRejects(fn('return xs', 'f(xs: IntList) -> Escrow[t, o]'), 'P401', 1)
        self.assertRejects(fn('return xs', 'f(xs: List[Int]) -> IntList'), 'P401', 1)

    def test_pure_code_cannot_invoke_effects(self):
        self.assertRejects(fn('let r = Payments.charge(t, o, a, e)\nreturn xs'), 'P409', 2)
        self.assertRejects(fn('return Inventory.reserve(xs)'), 'P409', 2)
        self.assertRejects(fn('let h = await Inventory.reserve(t, o)\nreturn xs'), 'P409', 2)
        self.assertRejects(fn('await Inventory.sell(xs)\nreturn xs'), 'P409', 2)

    def test_pure_code_cannot_call_flow_and_files_cannot_mix(self):
        flow = 'flow settle(result: ChargeOutcome[t, o]):\n    match result:\n        Ok(paid):\n            return\n'
        err = self.assertRejects(fn('let r = settle(xs)\nreturn xs') + flow, 'P409', 2)
        self.assertIn('effectful flow', err.message)
        self.assertRejects(fn('return xs') + flow, 'P410', 3)

    # Fork scope
    def test_fork_scope_violations(self):
        helper = fn('return ys', 'id(ys: IntList) -> IntList')
        self.assertRejects(fn('fork:\n    let a = id(xs)\n    let b = id(a)\nreturn b') + helper, 'P412', 4)
        self.assertRejects(fn('fork:\n    let a = id(b)\n    let b = id(xs)\nreturn b') + helper, 'P412', 3)
        self.assertRejects(fn('fork:\n    let a = id(xs)\nreturn a') + helper, 'P412', 2)
        self.assertRejects(fn('fork:\n    let a = id(xs)\n    let b = id(xs)\n    let c = id(xs)\nreturn a') + helper,
                           'P412', 2)
        self.assertRejects(fn('fork:\n    let a = tail(xs)\n    let b = id(xs)\nreturn a') + helper, 'P412', 3)
        self.assertRejects(fn('fork:\n    let a = id(xs)\n    return a\nreturn xs') + helper, 'P412', 4)
        self.assertRejects(fn('fork:\n    let a = id(xs)\n    let a = id(xs)\nreturn a') + helper, 'P412', 2)
        self.assertRejects(fn('return a\nfork:\n    let a = id(xs)\n    let b = id(xs)') + helper, 'P403', 2)
        self.assertRejects(fn('fork:\n    let a = id(xs)\n    let b = id(xs)') + helper, 'P408', 2)

    # Unsupported syntax stays rejected
    def test_unsupported_constructs(self):
        self.assertRejects(fn('while is_empty(xs):\n    return xs\nreturn xs'), 'P400', 2)
        self.assertRejects(fn('return cons(head(xs) + 1, xs)'), 'P400', 2)
        self.assertRejects(fn('return cons(1 - 1, xs)'), 'P400', 2)
        self.assertRejects(fn('return 1 <= 2 <= 3', 'f(xs: IntList) -> Bool'), 'P400', 2)
        self.assertRejects(fn('match xs:\n    Ok(a):\n        return a'), 'P400', 2)
        self.assertRejects('fn f(xs: IntList) -> IntList:\n\treturn xs\n', 'P400', 2)
        self.assertRejects('fn f(xs: IntList) -> IntList:\n  return xs\n', 'P400', 2)
        self.assertRejects('net N(stock: Nat):\n    place a = 0 owner domain\n', 'P400', 1)
        self.assertRejects('', 'P400')

    # Runner integration
    def test_check_pure_does_not_analyze_inventory_net(self):
        code, data = self.run_cli('check-pure', MERGE_SORT)
        self.assertEqual(code, 0, data)
        self.assertEqual(data['files'][0]['functions'], ['merge_sort', 'merge'])
        self.assertNotIn('accounting', data)
        self.assertNotIn('ordering', data)
        self.assertIn('termination is not checked', data['scope'])

    def test_check_pure_batch_reports_each_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / 'bad.weave'
            bad.write_text(fn('return Payments.charge(xs)'))
            code, data = self.run_cli('check-pure', MERGE_SORT, bad)
        self.assertEqual(code, 1)
        self.assertTrue(data['files'][0]['ok'])
        d = data['files'][1]['diagnostic']
        self.assertEqual((d['code'], d['span']['start']['line'], d['stage']), ('P409', 2, 'pure'))

    def test_effectful_flow_recursion_still_rejected(self):
        code, data = self.run_cli('check', ROOT / 'examples/invalid/recursion.weave')
        self.assertEqual(code, 1)
        self.assertEqual(data['files'][0]['diagnostic']['code'], 'E218')

    def test_flow_checker_does_not_admit_pure_functions(self):
        code, data = self.run_cli('check', MERGE_SORT)
        self.assertEqual(code, 1)
        self.assertEqual(data['files'][0]['diagnostic']['code'], 'E200')

    def test_check_pure_missing_file(self):
        code, data = self.run_cli('check-pure', ROOT / 'missing.weave')
        self.assertEqual(code, 2)
        self.assertEqual(data['diagnostic']['code'], 'TOOL_ERROR')


if __name__ == '__main__':
    unittest.main()
