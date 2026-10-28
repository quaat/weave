"""Integration and rejection tests for the Tiny Shop demo, using the real Weave runner."""
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest

DEMO = Path(__file__).resolve().parents[1]
ROOT = DEMO.parents[1]
CLI = ROOT / 'scripts' / 'weave.py'
APP = DEMO / 'run_demo.py'
SHOP = DEMO / 'shop.weave'

EXPECTED_FINAL = {
    'Ok': dict(available=0, sold=1, recovery_queue=0, registrations=0),
    'Err': dict(available=1, sold=0, recovery_queue=0, registrations=0),
    'Unknown': dict(available=0, sold=0, recovery_queue=1, registrations=1),
}
EXPECTED_NET = {
    'Ok': ['reserve', 'arm', 'dispatch', 'charge_ok', 'sell'],
    'Err': ['reserve', 'arm', 'dispatch', 'charge_err', 'release'],
    'Unknown': ['reserve', 'arm', 'dispatch', 'charge_unknown', 'handoff'],
}
EXPECTED_RESULT = {
    'Ok': 'Purchase completed',
    'Err': 'Payment rejected; item released',
    'Unknown': 'Payment unresolved; item held for recovery',
}
TRANSIENT = ('held', 'escrow', 'inflight', 'paid', 'unpaid', 'uncertain', 'manual')
STOCK_TERMS = ('available', 'held', 'escrow', 'inflight', 'paid', 'unpaid', 'uncertain',
               'recovery_queue', 'manual', 'sold')
REGISTERED_TERMS = ('escrow', 'inflight', 'paid', 'unpaid', 'uncertain', 'recovery_queue', 'manual')


def runner(*args, cwd=ROOT):
    proc = subprocess.run([sys.executable, '-B', str(CLI), '--json', *map(str, args)],
                          cwd=cwd, text=True, capture_output=True, timeout=120)
    return proc.returncode, json.loads(proc.stdout)


def app(*args, cwd=ROOT):
    return subprocess.run([sys.executable, '-B', str(APP), *map(str, args)],
                          cwd=cwd, text=True, capture_output=True, timeout=120)


def net_names(run):
    return [e['name'] for e in run['events'] if e['kind'] == 'NET']


class TinyShopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.lowered = Path(cls.tmp.name) / 'shop.lowered.weave'
        cls.lower_code, cls.lower_data = runner('lower', SHOP, '--output', cls.lowered)
        code, data = runner('simulate', SHOP, '--entry', 'checkout', '--outcome', 'all', '--trace')
        assert code == 0 and data['ok'], data
        cls.source_runs = {r['outcome']: r for r in data['runs']}
        cls.source_sim = data

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    # 1. Checking and lowering
    def test_flow_checks_and_lowers(self):
        code, data = runner('check', SHOP)
        self.assertEqual(code, 0, data)
        self.assertTrue(data['ok'])
        self.assertEqual(data['accounting']['status'], 'PROVED')
        self.assertEqual(data['ordering']['status'], 'CHECKED WITHIN BOUNDS')
        self.assertTrue(data['files'][0]['ok'], data['files'][0])
        self.assertEqual(self.lower_code, 0, self.lower_data)
        lowered = self.lowered.read_text()
        self.assertNotIn('?', lowered)
        self.assertIn('Unknown(', lowered)
        self.assertEqual(runner('check', self.lowered)[0], 0)

    # 2. Final markings
    def test_all_scenarios_reach_expected_final_marking(self):
        self.assertEqual(self.source_sim['status'], 'SCRIPTED')
        self.assertEqual(set(self.source_runs), set(EXPECTED_FINAL))
        for outcome, expected in EXPECTED_FINAL.items():
            with self.subTest(outcome=outcome):
                m = self.source_runs[outcome]['marking']
                for place, count in expected.items():
                    self.assertEqual(m[place], count, place)
                for place in TRANSIENT:
                    self.assertEqual(m[place], 0, place)
                self.assertEqual(m['charge_requests'], 1)
                self.assertEqual(self.source_runs[outcome]['return_type'], 'Unit')

    # 3. Exact NET transition sequences
    def test_net_transition_sequences(self):
        for outcome, expected in EXPECTED_NET.items():
            with self.subTest(outcome=outcome):
                self.assertEqual(net_names(self.source_runs[outcome]), expected)

    # 4. Accounting equations at every recorded marking
    def test_invariants_hold_at_every_marking(self):
        for outcome, run in self.source_runs.items():
            markings = [e['marking'] for e in run['events']] + [run['marking']]
            self.assertGreater(len(markings), 5)
            for i, m in enumerate(markings):
                with self.subTest(outcome=outcome, step=i):
                    self.assertTrue(all(v >= 0 for v in m.values()), m)
                    self.assertEqual(sum(m[p] for p in STOCK_TERMS), 1, m)
                    self.assertEqual(m['registrations'], sum(m[p] for p in REGISTERED_TERMS), m)

    # 5. Path-specific safety
    def test_paths_never_take_forbidden_settlements(self):
        unknown = self.source_runs['Unknown']
        names = net_names(unknown)
        self.assertNotIn('sell', names)
        self.assertNotIn('release', names)
        self.assertTrue(all(e['marking']['sold'] == 0 for e in unknown['events']))
        self.assertEqual(unknown['marking']['registrations'], 1)
        self.assertEqual(unknown['marking']['recovery_queue'], 1)
        err = self.source_runs['Err']
        self.assertNotIn('sell', net_names(err))
        self.assertTrue(all(e['marking']['sold'] == 0 for e in err['events']))
        self.assertNotIn('release', net_names(self.source_runs['Ok']))

    def test_propagation_crosses_helper_boundary(self):
        for outcome in ('Err', 'Unknown'):
            returns = [(e['name'], e['tag']) for e in self.source_runs[outcome]['events']
                       if e['kind'] == 'RETURN']
            self.assertIn(('charge_payment', outcome), returns)
            self.assertIn(('buy_last_item', outcome), returns)

    # 6. Source/lowered agreement
    def test_source_and_lowered_execution_agree(self):
        code, data = runner('simulate', self.lowered, '--entry', 'checkout', '--outcome', 'all', '--trace')
        self.assertEqual(code, 0, data)
        lowered_runs = {r['outcome']: r for r in data['runs']}
        self.assertEqual(set(lowered_runs), set(self.source_runs))
        for outcome, src in self.source_runs.items():
            with self.subTest(outcome=outcome):
                low = lowered_runs[outcome]
                self.assertEqual(low['marking'], src['marking'])
                self.assertEqual((low['return_type'], low['return_tag']),
                                 (src['return_type'], src['return_tag']))
                self.assertEqual(net_names(low), net_names(src))

    # 7. Application behavior
    def test_app_json_matches_runner(self):
        proc = app('--outcome', 'all', '--json')
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = json.loads(proc.stdout)
        self.assertTrue(report['ok'])
        self.assertEqual(report['status'], 'SCRIPTED')
        self.assertEqual(report['accounting']['status'], 'PROVED')
        by_outcome = {s['outcome']: s for s in report['scenarios']}
        for outcome in EXPECTED_NET:
            s = by_outcome[outcome]
            self.assertEqual(s['net_transitions'], EXPECTED_NET[outcome])
            self.assertEqual(s['result'], EXPECTED_RESULT[outcome])
            self.assertEqual(s['final_marking'], self.source_runs[outcome]['marking'])
            self.assertNotIn('events', s)

    def test_app_single_outcome_trace_text(self):
        for outcome in EXPECTED_NET:
            with self.subTest(outcome=outcome):
                proc = app('--outcome', outcome, '--trace')
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertIn(f'Payment outcome: {outcome} -> {EXPECTED_RESULT[outcome]}', proc.stdout)
                self.assertIn(' -> '.join(EXPECTED_NET[outcome]), proc.stdout)
                self.assertEqual(proc.stdout.count('== Payment outcome:'), 1)
                self.assertIn('Trace:', proc.stdout)

    def test_app_default_is_all(self):
        proc = app()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.count('== Payment outcome:'), 3)

    def test_app_rejects_invalid_cli_input(self):
        for args in (['--outcome', 'Maybe'], ['--bogus'], ['extra']):
            with self.subTest(args=args):
                proc = app(*args)
                self.assertNotEqual(proc.returncode, 0)
                self.assertEqual(proc.stdout, '')
                self.assertIn('usage:', proc.stderr)

    def test_app_works_from_other_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = app('--outcome', 'Unknown', '--json', cwd=tmp)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            s = json.loads(proc.stdout)['scenarios'][0]
            self.assertEqual(s['net_transitions'], EXPECTED_NET['Unknown'])

    def test_app_surfaces_runner_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / 'shop.weave'
            bad.write_text(SHOP.read_text().replace('await Inventory.sell(paid)', 'await Inventory.release(paid)'))
            proc = app('--source', bad, '--json')
            self.assertEqual(proc.returncode, 1)
            report = json.loads(proc.stdout)
            self.assertFalse(report['ok'])
            self.assertNotIn('scenarios', report)
            self.assertEqual(report['diagnostic']['code'], 'E208')
            text = app('--source', bad)
            self.assertEqual(text.returncode, 1)
            self.assertEqual(text.stdout, '')
            self.assertIn('E208', text.stderr)
            missing = app('--source', Path(tmp) / 'absent.weave', '--json')
            self.assertNotEqual(missing.returncode, 0)
            self.assertFalse(json.loads(missing.stdout)['ok'])

    # 8. Deliberately invalid variants (temporary copies only)
    def check_variant(self, old, new, code, count=1):
        source = SHOP.read_text()
        self.assertEqual(source.count(old), count, old)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'variant.weave'
            path.write_text(source.replace(old, new))
            rc, data = runner('check', path)
        self.assertEqual(rc, 1, data)
        self.assertFalse(data['ok'])
        self.assertEqual(data['files'][0]['diagnostic']['code'], code, data['files'][0]['diagnostic'])

    def test_rejects_missing_unknown_arm(self):
        arm = ('        Unknown(uncertain):\n'
               '            await Inventory.handoff(uncertain)\n'
               '            return\n')
        self.check_variant(arm, '', 'E214')

    def test_rejects_reused_moved_hold(self):
        self.check_variant('    let escrow = await Inventory.arm(hold)\n',
                           '    let escrow = await Inventory.arm(hold)\n'
                           '    let second = await Inventory.arm(hold)\n', 'E203')

    def test_rejects_paid_passed_to_release(self):
        self.check_variant('await Inventory.sell(paid)', 'await Inventory.release(paid)', 'E208')

    def test_reference_fixtures_have_matching_codes(self):
        for name, code in (('missing_unknown', 'E214'), ('reuse_hold', 'E203'), ('paid_release', 'E208')):
            with self.subTest(fixture=name):
                rc, data = runner('check', ROOT / 'examples/invalid' / f'{name}.weave')
                self.assertEqual(rc, 1)
                self.assertEqual(data['files'][0]['diagnostic']['code'], code)


if __name__ == '__main__':
    unittest.main()
