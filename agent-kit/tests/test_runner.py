"""Integration tests for the kit boundary; original semantic tests are vendored."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / 'scripts/weave.py'
SKILL = ROOT / '.agents/skills/weave'
GOOD = ROOT / 'examples/valid/checkout_propagating.weave'


class RunnerTests(unittest.TestCase):
    def run_cli(self, *args, cwd=None, script=CLI):
        proc = subprocess.run([sys.executable, '-B', str(script), '--json', *map(str, args)],
                              cwd=cwd or ROOT, text=True, capture_output=True, timeout=30)
        self.assertEqual(proc.stderr, '', proc.stderr)
        return proc.returncode, json.loads(proc.stdout)

    def test_valid_batch_and_expected_rejection_have_separate_results(self):
        code, data = self.run_cli('check', GOOD, ROOT/'examples/invalid/reuse_hold.weave')
        self.assertEqual(code, 1)
        self.assertTrue(data['files'][0]['ok'])
        self.assertEqual(data['files'][1]['diagnostic']['code'], 'E203')
        self.assertFalse(data['ok'])

    def test_unsafe_net_fails_before_flow_success(self):
        code, data = self.run_cli('check', GOOD, '--net', ROOT/'examples/nets/unsafe_paid_release.weave')
        self.assertEqual(code, 1)
        self.assertEqual(data['diagnostic']['code'], 'E320')
        self.assertEqual(data['diagnostic']['stage'], 'net')
        self.assertNotIn('files', data)

    def test_exhausted_budget_is_not_success(self):
        code, data = self.run_cli('analyze', '--max-states', '1')
        self.assertEqual(code, 1)
        self.assertEqual(data['diagnostic']['code'], 'E321')

    def test_check_reports_original_question_line(self):
        path = ROOT/'examples/invalid/early_return_leak.weave'
        code, data = self.run_cli('check', path)
        self.assertEqual(code, 1)
        d = data['files'][0]['diagnostic']
        self.assertEqual(d['code'], 'E204')
        self.assertEqual(d['span']['start'], {'line': 3, 'column': 5})
        self.assertEqual(d['rule'], 'F0-RETURN-1')

    def test_lowering_is_written_only_after_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)/'lowered.weave'
            code, data = self.run_cli('lower', GOOD, '--output', out)
            self.assertEqual(code, 0, data)
            lowered = out.read_text()
            self.assertNotIn('?', lowered)
            self.assertIn('Unknown(', lowered)
            self.assertEqual(self.run_cli('check', out)[0], 0)
            before = out.read_bytes()
            code, _ = self.run_cli('lower', ROOT/'examples/invalid/early_return_leak.weave', '--output', out)
            self.assertEqual(code, 1)
            self.assertEqual(out.read_bytes(), before)

    def test_output_cannot_overwrite_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp)/'flow.weave'
            file.write_bytes(GOOD.read_bytes())
            before = file.read_bytes()
            code, data = self.run_cli('lower', file, '--output', file)
            self.assertEqual(code, 2, data)
            self.assertEqual(file.read_bytes(), before)

    def test_scripted_outcomes_preserve_distinct_obligations(self):
        code, data = self.run_cli('simulate', GOOD, '--entry', 'checkout_propagating', '--outcome', 'all', '--trace')
        self.assertEqual(code, 0, data)
        runs = {r['outcome']:r for r in data['runs']}
        self.assertEqual(runs['Ok']['marking']['sold'], 1)
        self.assertEqual(runs['Err']['marking']['available'], 1)
        self.assertEqual(runs['Unknown']['marking']['registrations'], 1)
        returns = [e for e in runs['Unknown']['events'] if e['kind']=='RETURN' and e['tag']=='Unknown']
        self.assertEqual([e['name'] for e in returns], ['pay_with','place_order'])
        self.assertTrue(all(e['marking']['uncertain']==1 for e in returns))

    def test_simulation_rejects_linear_entry(self):
        code, data = self.run_cli('simulate', ROOT/'examples/valid/arm_hold.weave', '--entry', 'arm_hold')
        self.assertEqual(code, 2)
        self.assertIn('scalar', data['diagnostic']['message'])

    def test_missing_file_has_machine_readable_diagnostic(self):
        code, data = self.run_cli('check', ROOT/'does-not-exist.weave')
        self.assertEqual(code, 2)
        self.assertEqual(data['diagnostic']['stage'], 'flow')

    def test_certificate_recheck_detects_modified_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            cert = Path(tmp)/'proof.json'
            net = Path(tmp)/'Inventory.weave'
            net.write_bytes((ROOT/'examples/nets/Inventory.weave').read_bytes())
            self.assertEqual(self.run_cli('analyze','--net',net,'--certificate',cert)[0],0)
            self.assertEqual(self.run_cli('verify',cert,'--net',net)[0],0)
            net.write_text(net.read_text()+'\n# changed\n')
            code,data = self.run_cli('verify',cert,'--net',net)
            self.assertEqual(code,2)
            self.assertIn('exact source',data['diagnostic']['message'])

    def test_empty_test_selection_fails(self):
        code, data = self.run_cli('test', '--pattern', 'no_such_test_*.py')
        self.assertEqual(code, 1)
        self.assertFalse(data['ok'])

    def test_examples_match_and_detect_unexpected_acceptance(self):
        code, data = self.run_cli('examples')
        self.assertEqual(code, 0, data)
        # 28 original expectations plus 6 pure-extension fixtures.
        self.assertEqual(data['passed'], 34)
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp)/'manifest.json'
            manifest.write_text(json.dumps({'net':str(ROOT/'examples/nets/Inventory.weave'),
                'cases':[{'file':str(GOOD),'kind':'flow','expect':'E204','lesson':'Detect unexpected acceptance'}]}))
            code, data = self.run_cli('examples','--manifest',manifest)
            self.assertEqual(code,1)
            self.assertEqual(data['results'][0]['actual'],'ACCEPT')

    def test_portable_skill_works_after_copy_from_unrelated_cwd(self):
        with tempfile.TemporaryDirectory(prefix='weave skill ') as tmp:
            copied = Path(tmp)/'copied skill'
            shutil.copytree(SKILL,copied,ignore=shutil.ignore_patterns('__pycache__'))
            script = copied/'scripts/weave.py'
            code, data = self.run_cli('check',GOOD,cwd=tmp,script=script)
            self.assertEqual(code,0,data)
            self.assertTrue(data['files'][0]['ok'])
            code,data = self.run_cli('test', '--pattern','test_rejection_and_propagation.py',cwd=tmp,script=script)
            self.assertEqual(code,0,data)

    def test_no_upstream_files_changed_and_reference_is_synchronized(self):
        metadata = json.loads((ROOT/'PROVENANCE.json').read_text())
        for name, expected in metadata['original_files_sha256'].items():
            self.assertEqual(hashlib.sha256((SKILL/'assets/prototype'/name).read_bytes()).hexdigest(),expected,name)
        self.assertEqual((ROOT/'docs/weave.md').read_bytes(),(SKILL/'references/weave.md').read_bytes())
        self.assertEqual((ROOT/'examples/nets/Inventory.weave').read_bytes(),(SKILL/'assets/prototype/Inventory.weave').read_bytes())


if __name__ == '__main__':
    unittest.main()
