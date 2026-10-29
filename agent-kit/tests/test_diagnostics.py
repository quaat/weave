# SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
# SPDX-License-Identifier: MIT
"""Runner diagnostics: the code-to-rule map, P4xx codes, spans and the weave-diagnostic-v1 schema (quaat/weave#6).

The codes the kit can emit are derived from its sources (and the vendored
prototype) by reading their syntax trees. Every ``--json`` diagnostic is
validated with the repository's evidence reader, which uses only the standard
library; the kit itself has no third-party dependency.
"""
from pathlib import Path
import ast
import json
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
CLI = ROOT / 'scripts/weave.py'
SKILL = ROOT / '.agents/skills/weave'
SCRIPTS = SKILL / 'scripts'
MAP_FILE = SKILL / 'assets/diagnostics.json'
sys.dont_write_bytecode = True
sys.path.insert(0, str(SCRIPTS))

from weave_diagnostics import CODES, from_pure_error, tool_error  # noqa: E402
from weave_pure import IntList, Limits, Machine, PureError, check_source, run_source  # noqa: E402

HAVE_READER = (REPO / 'evidence/weave_evidence/documents.py').is_file()
if HAVE_READER:
    sys.path.insert(0, str(REPO))
    from evidence.weave_evidence.documents import assess  # noqa: E402

CODE = re.compile(r'[EP]\d{3}')


def emitted_codes(paths):
    """Code literals (E000/P000, or a constant under a "code" key) in the given Python sources."""
    codes = set()
    for path in paths:
        for node in ast.walk(ast.parse(Path(path).read_text(encoding='utf-8'))):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and CODE.fullmatch(node.value):
                codes.add(node.value)
            elif isinstance(node, ast.Dict):
                for key, value in zip(node.keys, node.values):
                    if isinstance(key, ast.Constant) and key.value == 'code' and isinstance(value, ast.Constant):
                        codes.add(value.value)
    return codes


def unmapped(paths, codes):
    return sorted(emitted_codes(paths) - set(codes))


KIT_SOURCES = sorted(SCRIPTS.rglob('*.py'))
PROTOTYPE_SOURCES = [SKILL / 'assets/prototype' / n for n in
                     ('checker.py', 'coloured.py', 'durable.py', 'simulate.py', 'verify_certificate.py')]


def fn(body, sig='f(xs: IntList) -> IntList'):
    return f'fn {sig}:\n' + '\n'.join('    ' + line for line in body.strip('\n').splitlines()) + '\n'


HELPER = fn('return xs', 'id(xs: IntList) -> IntList')
SPIN = fn('return spin(xs)', 'spin(xs: IntList) -> IntList')
BOOM = 'fn boom(xs: IntList) -> IntList:\n    fork:\n        let a = boom(xs)\n        let b = boom(xs)\n    return a\n'
FLOW = 'flow settle(result: ChargeOutcome[t, o]):\n    match result:\n        Ok(paid):\n            return\n'


class Stuck(Machine):
    """Simulates the internal defect P426 reports: no runnable activation and no result."""
    def pick(self):
        return None


class Leaky(Machine):
    """Simulates the internal defect P427 reports: a live activation left after the root completed."""
    def complete(self, task, value):
        super().complete(task, value)
        if task.parent is None:
            self.live += 1


def check(source):
    return lambda: check_source(source)


def execute(source, entry, values, machine=None, **limits):
    def run():
        if machine is None:
            run_source(source, entry, values, limits=Limits(**limits))
        else:
            machine(check_source(source)).run(entry, [IntList.from_iter(v) for v in values])
    return run


# code: (source, action, principal rule, (line, exact text of the primary span) or None for the whole source)
FIXTURES = {
    'P400': (fn('while is_empty(xs):\n    return xs\nreturn xs'), None, 'KIT-PURE-SYNTAX-1', (2, 'while is_empty(xs):')),
    'P401': (fn('return 0', 'f(hold: Hold[t, o]) -> Int'), None, 'KIT-PURE-TYPE-1', (1, 'fn f(hold: Hold[t, o]) -> Int:')),
    'P402': (fn('return xs') + fn('return xs'), None, 'KIT-PURE-NAME-1', (3, 'fn f(xs: IntList) -> IntList:')),
    'P403': (fn('return ys'), None, 'KIT-PURE-NAME-1', (2, 'return ys')),
    'P404': (fn('return sorted(xs)'), None, 'KIT-PURE-NAME-1', (2, 'return sorted(xs)')),
    'P405': (fn('return cons(1)'), None, 'KIT-PURE-CALL-1', (2, 'return cons(1)')),
    'P406': (fn('return cons(true, xs)'), None, 'KIT-PURE-CALL-1', (2, 'return cons(true, xs)')),
    'P407': (fn('return length(xs)'), None, 'KIT-PURE-PATH-1', (2, 'return length(xs)')),
    'P408': (fn('return xs\nreturn xs'), None, 'KIT-PURE-PATH-1', (3, 'return xs')),
    'P409': (fn('return Inventory.reserve(xs)'), None, 'KIT-PURE-EFFECT-1', (2, 'return Inventory.reserve(xs)')),
    'P410': (fn('return xs') + FLOW, None, 'KIT-PURE-EFFECT-1', (3, 'flow settle(result: ChargeOutcome[t, o]):')),
    'P411': (fn('return g(xs)') + fn('return f(xs)', 'g(xs: IntList) -> IntList'), None, 'KIT-PURE-RECURSION-1',
             (1, 'fn f(xs: IntList) -> IntList:')),
    'P412': (fn('fork:\n    let a = id(xs)\nreturn a') + HELPER, None, 'KIT-PURE-FORK-1', (2, 'fork:')),
    'P413': (fn('let xs = tail(xs)\nreturn xs'), None, 'KIT-PURE-NAME-1', (2, 'let xs = tail(xs)')),
    'P414': (fn('if length(xs):\n    return xs\nelse:\n    return xs'), None, 'KIT-PURE-TYPE-1', (2, 'if length(xs):')),
    'P420': (fn('return head(xs)', 'f(xs: IntList) -> Int'), ('f', [[]]), 'KIT-PURE-RUN-1', (2, 'return head(xs)')),
    'P421': (SPIN, ('spin', [[1]], {'fuel': 20}), 'KIT-PURE-LIMIT-1', (2, 'return spin(xs)')),
    'P422': (SPIN, ('spin', [[1]], {'max_depth': 50}), 'KIT-PURE-LIMIT-1', (2, 'return spin(xs)')),
    'P423': (BOOM, ('boom', [[1]], {'max_tasks': 2}), 'KIT-PURE-LIMIT-1', (2, 'fork:')),
    'P424': (HELPER, ('id', ['not a list']), 'KIT-PURE-ENTRY-1', None),
    'P425': (HELPER, ('missing', [[1]]), 'KIT-PURE-ENTRY-1', None),
    'P426': (HELPER, ('id', [[1]], Stuck), 'KIT-PURE-SCHED-1', None),
    'P427': (HELPER, ('id', [[1]], Leaky), 'KIT-PURE-SCHED-1', None),
}


def action(source, run):
    if run is None:
        return check(source)
    entry, values, *rest = run
    if rest and isinstance(rest[0], dict):
        return execute(source, entry, values, **rest[0])
    if rest:
        return execute(source, entry, values, machine=rest[0])
    return execute(source, entry, values)


def span_text(source, span):
    assert span['start']['line'] == span['end']['line'], span
    return source.splitlines()[span['start']['line'] - 1][span['start']['column'] - 1:span['end']['column'] - 1]


class MapTests(unittest.TestCase):
    def test_every_code_the_kit_can_emit_is_mapped(self):
        self.assertEqual(unmapped(KIT_SOURCES + PROTOTYPE_SOURCES, CODES), [])

    def test_unmapped_code_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'extra.py'
            path.write_text('raise PureError("P499", "new")\nd = {"code": "OTHER_ERROR"}\n', encoding='utf-8')
            self.assertEqual(unmapped([path], CODES), ['OTHER_ERROR', 'P499'])
        self.assertEqual(unmapped(KIT_SOURCES, {c: e for c, e in CODES.items() if c != 'P420'}), ['P420'])

    def test_pure_codes_moved_to_p4xx(self):
        kit = emitted_codes(KIT_SOURCES)
        self.assertFalse({c for c in kit if c.startswith('E4')}, 'pure-extension codes use the P4xx range')
        pure = {c for c, e in CODES.items() if e['category'] == 'kit-extension'}
        self.assertEqual(pure, {c for c in kit if c.startswith('P')})
        self.assertEqual(set(FIXTURES), pure)
        self.assertEqual(CODES['TOOL_ERROR']['category'], 'tool')
        self.assertIsNone(CODES['TOOL_ERROR']['rule'])

    def test_kit_rules_are_defined_in_the_guide(self):
        guide = (ROOT / 'docs/weave.md').read_text(encoding='utf-8')
        defined = set(re.findall(r'^\| `(KIT-PURE-[A-Z]+-\d+)` \|', guide, re.M))
        used = {CODES[c]['rule'] for c in FIXTURES} | {r for c in FIXTURES for r in CODES[c]['secondary_rules']}
        self.assertEqual(used, defined)

    @unittest.skipUnless((REPO / 'specification/diagnostics.json').is_file(),
                         'the specification is not beside this kit; the copy is checked in the repository')
    def test_map_is_a_copy_of_the_specification_map(self):
        self.assertEqual(MAP_FILE.read_bytes(), (REPO / 'specification/diagnostics.json').read_bytes())


@unittest.skipUnless(HAVE_READER, "the repository's evidence reader (evidence/) is needed to validate the schema")
class SchemaTests(unittest.TestCase):
    def assertValid(self, document):
        result = assess(document)
        self.assertTrue(result.accepted, (result.errors, document))

    def test_one_diagnostic_per_pure_code(self):
        for code, (source, run, rule, primary) in FIXTURES.items():
            with self.subTest(code=code):
                with self.assertRaises(PureError) as raised:
                    action(source, run)()
                self.assertEqual(raised.exception.code, code, raised.exception.message)
                document = from_pure_error(raised.exception, f'{code}.weave', source)
                self.assertValid(document)
                self.assertEqual((document['code'], document['category'], document['rule']), (code, 'kit-extension', rule))
                self.assertEqual(document['span']['file'], f'{code}.weave')
                if primary is None:
                    lines = source.splitlines()
                    self.assertEqual((document['span']['start'], document['span']['end']),
                                     ({'line': 1, 'column': 1}, {'line': len(lines), 'column': len(lines[-1]) + 1}))
                else:
                    self.assertEqual(document['span']['start']['line'], primary[0])
                    self.assertEqual(span_text(source, document['span']), primary[1])

    def test_tool_error_has_no_rule(self):
        document = tool_error('missing.weave: No such file', 'missing.weave', 'pure')
        self.assertValid(document)
        self.assertEqual((document['code'], document['rule'], document['span']), ('TOOL_ERROR', None, None))

    def run_cli(self, *args):
        proc = subprocess.run([sys.executable, '-B', str(CLI), '--json', *map(str, args)],
                              cwd=ROOT, text=True, capture_output=True, timeout=60)
        self.assertEqual(proc.stderr, '', proc.stderr)
        return proc.returncode, json.loads(proc.stdout)

    def diagnostics(self, data):
        found = [data['diagnostic']] if 'diagnostic' in data else []
        for key in ('files', 'results'):
            found += [item['diagnostic'] for item in data.get(key, []) if 'diagnostic' in item]
        return found

    def test_json_output_conforms_to_the_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / 'bad.weave'
            bad.write_text(fn('return Payments.charge(xs)'))
            spin = Path(tmp) / 'spin.weave'
            spin.write_text(SPIN)
            runs = [
                ('check', ROOT / 'examples/invalid/early_return_leak.weave', ROOT / 'examples/invalid/reuse_hold.weave'),
                ('analyze', '--max-states', '1'),
                ('check', ROOT / 'examples/valid/checkout.weave', '--net', ROOT / 'examples/nets/unsafe_paid_release.weave'),
                ('check-pure', bad),
                ('run-pure', spin, '--entry', 'spin', '--args', '[[1]]', '--fuel', '20'),
                ('run-pure', spin, '--entry', 'spin', '--args', 'not json'),
                ('check', ROOT / 'missing.weave'),
                ('examples',),
            ]
            seen = set()
            for args in runs:
                with self.subTest(args=args):
                    _, data = self.run_cli(*args)
                    found = self.diagnostics(data)
                    self.assertTrue(found, data)
                    for document in found:
                        self.assertValid(document)
                        seen.add(document['code'])
        self.assertTrue({'E204', 'E203', 'E321', 'E320', 'P409', 'P421', 'P424', 'TOOL_ERROR'} <= seen, seen)

    def test_ownership_diagnostic_has_related_spans(self):
        path = ROOT / 'examples/invalid/early_return_leak.weave'
        _, data = self.run_cli('check', path)
        document = data['files'][0]['diagnostic']
        source = path.read_text(encoding='utf-8')
        self.assertEqual((document['code'], document['rule']), ('E204', 'F0-RETURN-1'))
        self.assertEqual(span_text(source, document['span']), 'let paid = result?')
        related = {r['role']: span_text(source, r['span']) for r in document['related']}
        self.assertEqual(related, {'binding': 'extra', 'propagation': '?'})

    def test_appended_net_fragment_is_located_in_its_own_file(self):
        _, data = self.run_cli('examples')
        appended = [r for r in data['results'] if r['file'].startswith('mutations/')]
        self.assertEqual(len(appended), 6)
        for item in appended:
            with self.subTest(file=item['file']):
                document = item['diagnostic']
                self.assertEqual((document['code'], document['rule']), ('E101', 'N0-SEAL-1'))
                fragment = ROOT / 'examples' / item['file']
                self.assertEqual(Path(document['span']['file']).resolve(), fragment.resolve())
                self.assertTrue(span_text(fragment.read_text(encoding='utf-8'), document['span']).startswith('transition '))

if __name__ == '__main__':
    unittest.main()
