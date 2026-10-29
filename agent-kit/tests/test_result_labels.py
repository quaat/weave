# SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
# SPDX-License-Identifier: MIT
"""Result-label lint (quaat/weave#8): every claim the kit emits carries one of the six labels.

Each runner command and both demo runners are run in text and ``--json`` form. The
claims are found from the output structure (``claim_label`` members in JSON; unindented
lines that begin with a label in text, see ``weave_labels``), every one must be one of the six labels,
and the text and JSON forms must present the same claims in the same order. Where the
repository's evidence package is present, every wrapped envelope is linted the same way.
Negative tests show the lint failing on non-canonical labels such as ``PASSED`` and
``NOT PROVED`` presented as claims, including the runner's own 0.2.0 output forms.
"""
from pathlib import Path
import json
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
CLI = ROOT / 'scripts/weave.py'
SCRIPTS = ROOT / '.agents/skills/weave/scripts'
VERIFICATION = REPO / 'specification/docs/chapters/verification.rst'
sys.dont_write_bytecode = True
sys.path.insert(0, str(SCRIPTS))

from weave_labels import (RESULT_LABELS, RUNTIME_STATUSES, json_claims, labelled, lint_json,  # noqa: E402
                          lint_text, text_claims)

HAVE_EVIDENCE = (REPO / 'evidence/weave_evidence/wrap.py').is_file()
GOOD = ROOT / 'examples/valid/checkout_propagating.weave'
MERGE_SORT = ROOT / 'demos/merge_sort/merge_sort.weave'
P, B, F, S, V, N = RESULT_LABELS


def spec_labels():
    """First-column entries of the Result vocabulary table in verification.rst."""
    text = VERIFICATION.read_text(encoding='utf-8')
    table = text.split('Result vocabulary', 1)[1].split('Aggregate invariants', 1)[0]
    return tuple(m for m in re.findall(r'(?m)^   \* - (.+)$', table) if m != 'Label')


def run(script, *args, cwd=ROOT):
    proc = subprocess.run([sys.executable, '-B', str(script), *map(str, args)], cwd=cwd,
                          capture_output=True, text=True, timeout=300)
    return proc.returncode, proc.stdout, proc.stderr


class LabelSetTests(unittest.TestCase):
    def test_six_labels_verbatim(self):
        self.assertEqual(RESULT_LABELS, ('PROVED', 'CHECKED WITHIN BOUNDS', 'CHECKED flow',
                                         'SCRIPTED / passed scenario', 'VIOLATED', 'NOT ESTABLISHED'))
        self.assertFalse(set(RUNTIME_STATUSES) & set(RESULT_LABELS))

    @unittest.skipUnless(VERIFICATION.is_file(), 'the specification is not next to this kit')
    def test_labels_match_the_specification_table(self):
        self.assertEqual(RESULT_LABELS, spec_labels())

    @unittest.skipUnless(HAVE_EVIDENCE, 'the evidence package is not next to this kit')
    def test_labels_match_the_envelope_schema(self):
        sys.path.insert(0, str(REPO))
        from evidence.weave_evidence import documents, schema
        envelope = schema.load(documents.SCHEMA_FILES[documents.ENVELOPE])
        self.assertEqual(tuple(envelope['properties']['claim_label']['enum']), RESULT_LABELS)
        self.assertEqual(documents.RUNTIME_STATUSES, RUNTIME_STATUSES)

    def test_claim_constructor_refuses_other_labels(self):
        for label in ('PASSED', 'NOT PROVED', 'RECHECKED', 'CHECKED', 'SCRIPTED', 'proved', 'Unknown'):
            with self.assertRaises(ValueError, msg=label):
                labelled(label)
        self.assertEqual(labelled(P, invariants=[]), {'claim_label': P, 'invariants': []})


class LintNegativeTests(unittest.TestCase):
    """The lint fails on any other label presented as a claim, in text and in JSON."""

    def test_text_claims_with_other_labels_fail(self):
        for line in ('PASSED 6 crash scenarios', 'NOT PROVED stock_conservation', 'RECHECKED 2 accounting invariants',
                     'CHECKED examples/valid/checkout.weave: checkout', 'CHECKED LOWERING -> lowered.weave',
                     'CHECKED 2 linear resources', 'CHECKED checkout_propagating:', 'SCRIPTED Ok via checkout: sold=1',
                     'SCRIPTED / passed', 'EXECUTED merge_sort', 'FAILED: tests failed',
                     'PASS 34/34 example expectations', 'RESULT [1, 2]', 'PROVEDX 2 invariants',
                     'CHECKED WITHIN 20 states', 'NOT_ESTABLISHED ordering', 'EXPECTED E320 FAILURE'):
            with self.subTest(line=line):
                errors = lint_text(f'tool status: PASS\n{line}\n')
                self.assertEqual(len(errors), 1, errors)
                self.assertIn('line 2', errors[0])

    def test_text_non_claims_pass(self):
        text = '\n'.join([
            'PROVED 2 accounting invariants',
            'CHECKED flow examples/valid/checkout.weave: checkout',
            'SCRIPTED / passed scenario Unknown via checkout: recovery_queue=1',
            '  runtime status: completed',
            'NOT ESTABLISHED ordering: token bound or state budget exhausted (E321 below)',
            'VIOLATED',
            'tool status: PASS 34/34 example expectations',
            'Inventory.weave:46:5: E321 (N0-ORDER-1) [net]',
            '  NOT ESTABLISHED: state budget 1 exhausted.',
            'raw output (bundled prototype unittest; not a claim):',
            '  OK',
            'E204 has no span here',
            '{"file": "x.weave", "ok": false}',
        ])
        self.assertEqual(lint_text(text), [])
        self.assertEqual([label for _, label in text_claims(text)], [P, F, S, N, V])

    def test_json_claims_with_other_labels_fail(self):
        cases = {
            'claim label PASSED': {'runs': [{'claim_label': 'PASSED'}]},
            'claim label NOT PROVED': {'accounting': {'claim_label': 'NOT PROVED'}},
            'claim label CHECKED': {'files': [{'claim_label': 'CHECKED'}]},
            'status member (0.2.0 verify)': {'command': 'verify', 'status': 'RECHECKED'},
            'status member (0.2.0 run-pure)': {'command': 'run-pure', 'status': 'EXECUTED'},
            'status member with a label': {'accounting': {'status': 'PROVED'}},
            'label outside claim_label': {'command': 'run-pure', 'check': 'CHECKED flow'},
            'label in a list': {'labels': ['VIOLATED']},
            'application outcome as runtime status': {'runtime_status': 'Unknown'},
            'label as runtime status': {'runtime_status': 'NOT ESTABLISHED'},
        }
        for name, document in cases.items():
            with self.subTest(name):
                self.assertEqual(len(lint_json(document)), 1, lint_json(document))

    def test_json_non_claims_pass(self):
        document = {'command': 'check', 'ok': False, 'accounting': {'claim_label': P, 'invariants': ['a']},
                    'runs': [{'claim_label': S, 'runtime_status': 'completed', 'outcome': 'Unknown'}],
                    'diagnostic': {'code': 'E112', 'message': 'NOT PROVED: residual', 'details': {'status': 'X'}},
                    'output': 'PASSED\nOK', 'upstream_output': 'CHECKED 2 linear resources',
                    'scope': 'NOT ESTABLISHED for anything outside the tool', 'runtime_status': None}
        self.assertEqual(lint_json(document), [])
        self.assertEqual(json_claims(document), [('/accounting/claim_label', P), ('/runs/0/claim_label', S)])

    def test_mutated_real_output_fails(self):
        """Claim positions come from the structure: edit one claim of real output and the lint fails."""
        _, out, _ = run(CLI, '--json', 'check', GOOD)
        data = json.loads(out)
        data['files'][0]['claim_label'] = 'PASSED'
        self.assertEqual(lint_json(data), ["/files/0/claim_label: claim label 'PASSED' is not one of the six result labels"])
        _, text, _ = run(CLI, 'check', GOOD)
        self.assertEqual(len(lint_text(text.replace('CHECKED flow ', 'CHECKED '))), 1)
        self.assertEqual(len(lint_text(text.replace('PROVED ', 'NOT PROVED '))), 1)
        self.assertEqual(len(lint_text(text.replace('CHECKED WITHIN BOUNDS ', 'PASSED '))), 1)


class RunnerOutputTests(unittest.TestCase):
    """Every runner command, in both forms: only the six labels, the same claims, nothing vacuous."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        tmp = Path(cls.tmp.name)
        cert, lowered, lowered_json = tmp / 'proof.json', tmp / 'lowered.weave', tmp / 'lowered-json.weave'
        commands = {
            'doctor': (['doctor'], []),
            'check': (['check', GOOD, ROOT / 'examples/valid/checkout.weave', ROOT / 'examples/invalid/reuse_hold.weave'],
                      [P, B, F, F]),
            'check violated': (['check', GOOD, '--net', ROOT / 'examples/nets/unsafe_paid_release.weave'], [P, V]),
            'analyze exhausted': (['analyze', '--max-states', '1'], [P, N]),
            'analyze': (['analyze', '--certificate', cert], [P, B]),
            'verify': (['verify', cert], [P]),
            'lower': (['lower', GOOD, '--output', lowered], [P, B, F, F]),
            'simulate': (['simulate', GOOD, '--entry', 'checkout_propagating', '--outcome', 'all', '--trace'],
                         [P, B, S, S, S]),
            'simulate failure': (['simulate', ROOT / 'examples/valid/arm_hold.weave', '--entry', 'arm_hold'], []),
            'examples': (['examples'], [P, B]),
            'test': (['test', '--pattern', 'test_composition.py'], []),
            'test empty': (['test', '--pattern', 'no_such_test_*.py'], []),
            'check-pure': (['check-pure', MERGE_SORT, ROOT / 'examples/invalid/pure_mutual.weave'], [N]),
            'run-pure': (['run-pure', MERGE_SORT, '--entry', 'merge_sort', '--args', '[[3,1,2]]', '--trace'], [N]),
            'run-pure fault': (['run-pure', MERGE_SORT, '--entry', 'merge_sort', '--args', '[[3,1,2]]',
                                '--fuel', '5'], []),
        }
        cls.outputs = {}
        for name, (args, expected) in commands.items():
            if name == 'lower':  # the JSON run writes its own output file
                json_args = ['lower', GOOD, '--output', lowered_json]
            else:
                json_args = args
            text = run(CLI, *args)
            data = run(CLI, '--json', *json_args)
            cls.outputs[name] = (text, data, expected)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_every_command_ran(self):
        for name, ((text_code, _, _), (json_code, out, err), _) in self.outputs.items():
            with self.subTest(name):
                self.assertEqual(text_code, json_code)
                self.assertEqual(err, '')
                json.loads(out)

    def test_json_claims_use_only_the_six_labels(self):
        for name, (_, (_, out, _), expected) in self.outputs.items():
            with self.subTest(name):
                data = json.loads(out)
                self.assertEqual(lint_json(data), [])
                self.assertEqual([label for _, label in json_claims(data)], expected)

    def test_text_claims_use_only_the_six_labels(self):
        for name, ((_, out, err), _, expected) in self.outputs.items():
            with self.subTest(name):
                self.assertEqual(lint_text(out + err), [])
                self.assertEqual([label for _, label in text_claims(out)], expected)

    def test_unknown_outcome_is_a_scripted_scenario_not_an_evidence_result(self):
        runs = {r['outcome']: r for r in json.loads(self.outputs['simulate'][1][1])['runs']}
        self.assertEqual(runs['Unknown']['claim_label'], S)
        self.assertEqual(runs['Unknown']['runtime_status'], 'completed')

    def test_failed_ordering_checks_are_labelled_not_passed(self):
        violated = json.loads(self.outputs['check violated'][1][1])
        self.assertEqual((violated['ordering']['claim_label'], violated['diagnostic']['code']), (V, 'E320'))
        exhausted = json.loads(self.outputs['analyze exhausted'][1][1])
        self.assertEqual((exhausted['ordering']['claim_label'], exhausted['diagnostic']['code']), (N, 'E321'))
        self.assertFalse(violated['ok'] or exhausted['ok'])

    def test_pure_extension_claims_nothing_specified(self):
        data = json.loads(self.outputs['run-pure'][1][1])
        self.assertEqual(data['check']['claim_label'], N)
        self.assertEqual(data['runtime_status'], 'completed')
        fault = json.loads(self.outputs['run-pure fault'][1][1])
        self.assertEqual(fault['diagnostic']['code'], 'P421')
        self.assertNotIn('runtime_status', fault)


class DemoOutputTests(unittest.TestCase):
    """The demo runners relay runner claims with the same labels."""

    def check(self, script, args, expected):
        code, out, err = run(script, *args)
        self.assertEqual(code, 0, err)
        self.assertEqual(lint_text(out + err), [])
        self.assertEqual([label for _, label in text_claims(out)], expected)
        code, out, err = run(script, *args, '--json')
        self.assertEqual(code, 0, err)
        data = json.loads(out)
        self.assertEqual(lint_json(data), [])
        self.assertEqual([label for _, label in json_claims(data)], expected)
        return data

    def test_tiny_shop(self):
        data = self.check(ROOT / 'demos/tiny_shop/run_demo.py', ['--outcome', 'all'], [P, B, S, S, S])
        self.assertEqual({s['runtime_status'] for s in data['scenarios']}, {'completed'})

    def test_merge_sort(self):
        data = self.check(ROOT / 'demos/merge_sort/run_demo.py', ['--values', '[3,1,2]'], [N])
        self.assertEqual(data['runtime_status'], 'completed')

    def test_demo_failures_present_no_claim(self):
        for script, args in ((ROOT / 'demos/merge_sort/run_demo.py', ['--values', '[5,4,3]', '--fuel', '5']),
                             (ROOT / 'demos/tiny_shop/run_demo.py', ['--source', ROOT / 'missing.weave'])):
            with self.subTest(script.parent.name):
                code, out, err = run(script, *args)
                self.assertNotEqual(code, 0)
                self.assertEqual(lint_text(out + err), [])
                self.assertEqual(text_claims(out + err), [])


@unittest.skipUnless(HAVE_EVIDENCE, 'the evidence package is not next to this kit')
class EnvelopeTests(unittest.TestCase):
    """Wrapped envelopes: exactly one claim each, at /claim_label, with one of the six labels."""

    def test_every_wrapped_envelope_passes_the_lint(self):
        sys.path.insert(0, str(REPO))
        from evidence.weave_evidence.wrap import wrap_all
        count = 0
        for wrapped in wrap_all(REPO):
            for envelope in wrapped.envelopes:
                self.assertEqual(lint_json(envelope), [], (wrapped.path, envelope['claim']['pointer']))
                claims = json_claims(envelope)
                self.assertEqual(len(claims), 1)
                self.assertEqual(claims[0][0], '/claim_label')
                count += 1
        self.assertGreater(count, 0)

    def test_edited_envelope_label_fails_the_lint(self):
        sys.path.insert(0, str(REPO))
        from evidence.weave_evidence.wrap import wrap
        envelope = wrap(REPO, 'inventory-proof/durable-scenarios.json').envelopes[0]
        self.assertEqual(lint_json(envelope), [])
        self.assertEqual(len(lint_json(dict(envelope, claim_label='PASSED'))), 1)
        self.assertEqual(len(lint_json(dict(envelope, runtime_status='Unknown'))), 1)


if __name__ == '__main__':
    unittest.main()
