# SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
# SPDX-License-Identifier: MIT
"""The `use net` flow header (modules-1, quaat/weave#12).

The runner resolves the header from the project root (--root, or the flow file's
directory), then hands the unchanged pinned prototype the flow with the header line
blanked. These tests show that a header flow checks exactly like the --net form, with
the same diagnostics at the same lines and columns; that a conflicting --net is E610;
that resolution follows the modules-1 rules (E600-E603); and that the pinned
prototype is not modified.
"""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / 'scripts/weave.py'
PROTOTYPE = ROOT / '.agents/skills/weave/assets/prototype'
NET = ROOT / 'examples/nets/Inventory.weave'
CHECKOUT = ROOT / 'examples/valid/checkout.weave'
FORGE = ROOT / 'examples/invalid/forge_escrow.weave'
REUSE = ROOT / 'examples/invalid/reuse_hold.weave'


def run_cli(*args, cwd=None):
    proc = subprocess.run([sys.executable, '-B', str(CLI), '--json', *map(str, args)],
                          cwd=cwd or ROOT, text=True, capture_output=True, timeout=60)
    assert proc.stderr == '', proc.stderr
    return proc.returncode, json.loads(proc.stdout)


class UseNet(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        (self.tmp / 'nets').mkdir()
        shutil.copy(NET, self.tmp / 'nets/Inventory.weave')
        shutil.copy(ROOT / 'examples/nets/unsafe_paid_release.weave', self.tmp / 'nets/Unsafe.weave')

    def pair(self, name, body, header='use net nets.Inventory'):
        """A header flow and its --net twin, whose first line is a comment instead."""
        header_file, twin = self.tmp / f'{name}.weave', self.tmp / f'{name}.twin.weave'
        header_file.write_text(f'{header}\n{body}', encoding='utf-8')
        twin.write_text(f'# net given with --net\n{body}', encoding='utf-8')
        return header_file, twin

    def assert_same_result(self, header_file, twin):
        code_h, with_header = run_cli('check', header_file)
        code_t, with_net = run_cli('check', twin, '--net', self.tmp / 'nets/Inventory.weave')
        self.assertEqual(code_h, code_t)
        for key in ('ok', 'accounting', 'ordering'):
            self.assertEqual(with_header[key], with_net[key], key)
        h, t = with_header['files'][0], with_net['files'][0]
        self.assertEqual(h['ok'], t['ok'])
        if 'diagnostic' in h:
            dh, dt = dict(h['diagnostic']), dict(t['diagnostic'])
            self.assertEqual(dh['span'].pop('file'), str(header_file))
            dt['span'].pop('file')
            for r in dh['related'] + dt['related']:
                r['span'].pop('file')
            self.assertEqual(dh, dt)
        else:
            self.assertEqual(h['flows'], t['flows'])
        return with_header

    def test_a_header_flow_checks_like_the_net_form(self):
        header_file, twin = self.pair('checkout', CHECKOUT.read_text(encoding='utf-8'))
        result = self.assert_same_result(header_file, twin)
        self.assertEqual(result['files'][0]['claim_label'], 'CHECKED flow')
        self.assertEqual(Path(result['net']), self.tmp / 'nets/Inventory.weave')

    def test_diagnostics_keep_their_lines_and_columns(self):
        for source, code in ((FORGE, 'E205'), (REUSE, 'E203')):
            with self.subTest(code=code):
                header_file, twin = self.pair(code, source.read_text(encoding='utf-8'))
                result = self.assert_same_result(header_file, twin)
                d = result['files'][0]['diagnostic']
                self.assertEqual(d['code'], code)
                # Line numbers count the header line: the error is where it is in the file.
                original = run_cli('check', source)[1]['files'][0]['diagnostic']
                self.assertEqual(d['span']['start']['line'], original['span']['start']['line'] + 1)
                self.assertEqual(d['span']['start']['column'], original['span']['start']['column'])
                for r, o in zip(d['related'], original['related']):
                    self.assertEqual(r['span']['start']['line'], o['span']['start']['line'] + 1)

    def test_blank_lines_and_comments_may_precede_the_header(self):
        body = '\n# selects the net\n\nuse net nets.Inventory  # trailing comment\n' + FORGE.read_text(encoding='utf-8')
        file = self.tmp / 'commented.weave'
        file.write_text(body, encoding='utf-8')
        code, data = run_cli('check', file)
        self.assertEqual(code, 1)
        self.assertEqual(data['files'][0]['diagnostic']['span']['start'], {'line': 6, 'column': 5})

    def test_a_conflicting_net_argument_is_e610(self):
        header_file, _ = self.pair('conflict', CHECKOUT.read_text(encoding='utf-8'))
        code, data = run_cli('check', header_file, '--net', self.tmp / 'nets/Unsafe.weave')
        self.assertEqual(code, 1)
        d = data['diagnostic']
        self.assertEqual((d['code'], d['rule'], d['category']), ('E610', 'MOD-NET-1', 'specification'))
        self.assertEqual(d['span']['start'], {'line': 1, 'column': 1})
        # No net was checked: a header failure stops the command first.
        self.assertNotIn('accounting', data)
        # The same net through another path is not a conflict.
        code, data = run_cli('check', header_file, '--net', self.tmp / 'nets/../nets/Inventory.weave')
        self.assertEqual(code, 0, data)

    def test_existing_net_arguments_keep_working(self):
        code, data = run_cli('check', CHECKOUT, '--net', NET)
        self.assertEqual(code, 0)
        self.assertEqual(data['net'], str(NET))
        code, data = run_cli('check', CHECKOUT)
        self.assertEqual(code, 0)
        self.assertTrue(data['net'].endswith('prototype/Inventory.weave'))

    def test_resolution_failures(self):
        body = CHECKOUT.read_text(encoding='utf-8')
        cases = {
            'missing': ('use net nets.Nowhere', 'E601', 'MOD-RESOLVE-1', 9),
            'case': ('use net Nets.Inventory', 'E602', 'MOD-RESOLVE-2', 9),
            'file_case': ('use net nets.inventory', 'E602', 'MOD-RESOLVE-2', 9),
            'malformed': ('use net', 'E600', 'MOD-FILE-1', 1),
            'dotdot': ('use net ..nets.Inventory', 'E600', 'MOD-FILE-1', 1),
            'other_word': ('use nets.Inventory', 'E600', 'MOD-FILE-1', 1),
        }
        for name, (header, code, rule, column) in cases.items():
            with self.subTest(name=name):
                file, _ = self.pair(name, body, header)
                status, data = run_cli('check', file)
                self.assertEqual(status, 1, data)
                d = data['diagnostic']
                self.assertEqual((d['code'], d['rule']), (code, rule))
                self.assertEqual(d['span']['start'], {'line': 1, 'column': column})
                self.assertEqual(d['span']['file'], str(file))

    def test_a_header_after_a_flow_is_left_to_the_prototype(self):
        file = self.tmp / 'late.weave'
        file.write_text(CHECKOUT.read_text(encoding='utf-8') + '\nuse net nets.Inventory\n', encoding='utf-8')
        code, data = run_cli('check', file)
        self.assertEqual(code, 1)
        self.assertEqual(data['files'][0]['diagnostic']['code'], 'E200')

    @unittest.skipIf(os.name == 'nt', 'symbolic links')
    def test_a_header_may_not_leave_the_root_through_a_link(self):
        outside = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, outside, True)
        shutil.copy(NET, outside / 'Inventory.weave')
        (self.tmp / 'away').symlink_to(outside)
        file, _ = self.pair('escape', CHECKOUT.read_text(encoding='utf-8'), 'use net away.Inventory')
        code, data = run_cli('check', file)
        self.assertEqual((code, data['diagnostic']['code']), (1, 'E603'))
        # A link inside the root is fine.
        (self.tmp / 'alias.weave').symlink_to(self.tmp / 'nets/Inventory.weave')
        file, _ = self.pair('inside', CHECKOUT.read_text(encoding='utf-8'), 'use net alias')
        self.assertEqual(run_cli('check', file)[0], 0)

    def test_the_root_is_the_flow_directory_or_the_root_argument(self):
        (self.tmp / 'flows').mkdir()
        file = self.tmp / 'flows/checkout.weave'
        file.write_text('use net nets.Inventory\n' + CHECKOUT.read_text(encoding='utf-8'), encoding='utf-8')
        code, data = run_cli('check', file)
        self.assertEqual((code, data['diagnostic']['code']), (1, 'E601'))
        code, data = run_cli('check', file, '--root', self.tmp)
        self.assertEqual(code, 0, data)
        # The working directory does not take part, whatever it contains.
        decoy = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, decoy, True)
        (decoy / 'nets').mkdir()
        shutil.copy(ROOT / 'examples/nets/unsafe_paid_release.weave', decoy / 'nets/Inventory.weave')
        for cwd in (decoy, ROOT, self.tmp / 'flows'):
            with self.subTest(cwd=str(cwd)):
                self.assertEqual(run_cli('check', file, '--root', self.tmp, cwd=cwd), (code, data))

    def test_an_explicit_root_must_contain_the_flow(self):
        """MOD-ROOT-1 in MOD-NET-1: E605 before any net is selected (F-14)."""
        prototype = ROOT / '.agents/skills/weave/assets/prototype'
        flow = self.tmp / 'f.weave'
        flow.write_text('use net Inventory\nflow f():\n    return\n', encoding='utf-8')
        # The reproduction: the header would resolve from that root, but the file is outside it.
        code, data = run_cli('check', flow, '--root', prototype)
        self.assertEqual(code, 1, data)
        d = data['diagnostic']
        self.assertEqual((d['code'], d['rule'], d['category']), ('E605', 'MOD-ROOT-1', 'specification'))
        self.assertEqual((d['span']['file'], d['span']['start']), (str(flow), {'line': 1, 'column': 1}))
        self.assertNotIn('accounting', data)
        # Every command, and a flow without a header too: --root names the project.
        headerless = self.tmp / 'plain.weave'
        headerless.write_text(CHECKOUT.read_text(encoding='utf-8'), encoding='utf-8')
        for args in (('check', headerless, '--root', prototype),
                     ('lower', flow, '--output', self.tmp / 'x.weave', '--root', prototype),
                     ('simulate', flow, '--entry', 'f', '--root', prototype)):
            with self.subTest(args=args[0]):
                code, data = run_cli(*args)
                self.assertEqual((code, data['diagnostic']['code']), (1, 'E605'))
        self.assertFalse((self.tmp / 'x.weave').exists())
        # Inside the root: accepted, header or not.
        file, _ = self.pair('inside', CHECKOUT.read_text(encoding='utf-8'))
        self.assertEqual(run_cli('check', file, '--root', self.tmp)[0], 0)
        self.assertEqual(run_cli('check', headerless, '--root', self.tmp)[0], 0)
        # Whole path components: a sibling whose name extends the root's is outside it.
        sibling = Path(str(self.tmp) + '-sibling')
        sibling.mkdir()
        self.addCleanup(shutil.rmtree, sibling, True)
        shutil.copy(headerless, sibling / 'plain.weave')
        self.assertEqual(run_cli('check', sibling / 'plain.weave', '--root', self.tmp)[1]['diagnostic']['code'],
                         'E605')
        # A --root that is not a directory is a usage error.
        code, data = run_cli('check', file, '--root', self.tmp / 'nowhere')
        self.assertEqual((code, data['diagnostic']['code']), (2, 'TOOL_ERROR'))

    @unittest.skipIf(os.name == 'nt', 'symbolic links')
    def test_a_symlinked_flow_and_an_explicit_root(self):
        """As the Rust weave command: a link is judged by its target against --root;
        without --root its own directory is the root and there is no E605."""
        target_dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, target_dir, True)
        (target_dir / 'nets').mkdir()
        shutil.copy(NET, target_dir / 'nets/Inventory.weave')
        target = target_dir / 'checkout.weave'
        target.write_text('use net nets.Inventory\n' + CHECKOUT.read_text(encoding='utf-8'), encoding='utf-8')
        link = self.tmp / 'linked.weave'
        link.symlink_to(target)
        # No --root: the link's directory is the root; its nets/Inventory.weave is used.
        code, data = run_cli('check', link)
        self.assertEqual(code, 0, data)
        self.assertEqual(Path(data['net']), self.tmp / 'nets/Inventory.weave')
        # --root at the link's directory: the target is outside it.
        code, data = run_cli('check', link, '--root', self.tmp)
        self.assertEqual((code, data['diagnostic']['code']), (1, 'E605'))
        self.assertEqual(data['diagnostic']['span']['file'], str(link))
        # --root at the target's directory contains the target: accepted, resolved from there.
        code, data = run_cli('check', link, '--root', target_dir)
        self.assertEqual(code, 0, data)
        self.assertEqual(Path(data['net']), target_dir / 'nets/Inventory.weave')

    def test_lower_and_simulate_use_the_header(self):
        file, _ = self.pair('checkout', CHECKOUT.read_text(encoding='utf-8'))
        out = self.tmp / 'lowered.weave'
        code, data = run_cli('lower', file, '--output', out)
        self.assertEqual(code, 0, data)
        lowered = out.read_text(encoding='utf-8')
        # Next to the source, the header selects the same net, so it is kept.
        self.assertTrue(lowered.startswith('use net nets.Inventory\n'))
        self.assertEqual(Path(data['net']), self.tmp / 'nets/Inventory.weave')
        self.assertEqual(run_cli('check', out)[0], 0)
        code, data = run_cli('simulate', file, '--entry', 'checkout', '--outcome', 'Ok')
        self.assertEqual(code, 0, data)
        self.assertEqual(data['runs'][0]['claim_label'], 'SCRIPTED / passed scenario')

    def lowered_elsewhere(self, decoy: bool):
        """Lower a header flow into another directory, optionally beside a decoy net."""
        file, _ = self.pair('checkout', CHECKOUT.read_text(encoding='utf-8'))
        elsewhere = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, elsewhere, True)
        if decoy:
            (elsewhere / 'nets').mkdir()
            shutil.copy(ROOT / 'examples/nets/unsafe_paid_release.weave', elsewhere / 'nets/Inventory.weave')
        out = elsewhere / 'lowered.weave'
        code, data = run_cli('lower', file, '--output', out)
        self.assertEqual(code, 0, data)
        return file, out, data

    def test_lower_elsewhere_blanks_a_header_that_would_not_resolve(self):
        file, out, data = self.lowered_elsewhere(decoy=False)
        lowered = out.read_text(encoding='utf-8')
        # A blank line takes the header's place; the lowered lines are unchanged.
        self.assertTrue(lowered.startswith('\n'))
        self.assertNotIn('use net', lowered)
        kept_file, _ = self.pair('kept', CHECKOUT.read_text(encoding='utf-8'))
        kept_out = self.tmp / 'kept.lowered.weave'
        self.assertEqual(run_cli('lower', kept_file, '--output', kept_out)[0], 0)
        self.assertEqual(lowered.splitlines()[1:], kept_out.read_text(encoding='utf-8').splitlines()[1:])
        # The result names the net (JSON ``net``; text, under the output's claim), so the
        # output can be checked with --net.
        self.assertEqual(Path(data['net']), self.tmp / 'nets/Inventory.weave')
        self.assertNotIn('_output_header', data)
        self.assertEqual(run_cli('check', out, '--net', data['net'])[0], 0)
        text = subprocess.run([sys.executable, '-B', str(CLI), 'lower', str(file), '--output', str(out)],
                              cwd=ROOT, text=True, capture_output=True, timeout=60).stdout
        self.assertIn(f"  net: {self.tmp / 'nets/Inventory.weave'} (its use net header would select", text)
        self.assertIn('check it with --net', text)

    def test_lower_never_lets_a_decoy_net_be_selected(self):
        _, out, data = self.lowered_elsewhere(decoy=True)
        lowered = out.read_text(encoding='utf-8')
        self.assertNotIn('use net', lowered)
        # Checked as written, the output would use the bundled default, never the decoy;
        # with the reported net it checks against the original one.
        code, checked = run_cli('check', out, '--net', data['net'])
        self.assertEqual(code, 0, checked)
        self.assertEqual(Path(checked['net']), self.tmp / 'nets/Inventory.weave')

    def test_lower_keeps_the_header_when_the_root_argument_resolves_it(self):
        file, _ = self.pair('checkout', CHECKOUT.read_text(encoding='utf-8'))
        elsewhere = self.tmp / 'out'
        elsewhere.mkdir()
        out = elsewhere / 'lowered.weave'
        code, data = run_cli('lower', file, '--output', out, '--root', self.tmp)
        self.assertEqual(code, 0, data)
        self.assertTrue(out.read_text(encoding='utf-8').startswith('use net nets.Inventory\n'))
        self.assertEqual(run_cli('check', out, '--root', self.tmp)[0], 0)

    def test_files_of_one_command_select_one_net(self):
        file, _ = self.pair('one', CHECKOUT.read_text(encoding='utf-8'))
        other, _ = self.pair('two', CHECKOUT.read_text(encoding='utf-8'), 'use net nets.Unsafe')
        code, data = run_cli('check', file, other)
        self.assertEqual((code, data['diagnostic']['code']), (2, 'TOOL_ERROR'))
        self.assertEqual(run_cli('check', file, file)[0], 0)

    def test_the_pinned_prototype_is_unchanged(self):
        provenance = json.loads((ROOT / 'PROVENANCE.json').read_text(encoding='utf-8'))
        for name, digest in provenance['original_files_sha256'].items():
            with self.subTest(name=name):
                self.assertEqual(hashlib.sha256((PROTOTYPE / name).read_bytes()).hexdigest(), digest)
        # The prototype itself still rejects the header: only the runner reads it.
        sys.path.insert(0, str(PROTOTYPE))
        try:
            from checker import CheckError, check_flow, parse_net
        finally:
            sys.path.remove(str(PROTOTYPE))
        with self.assertRaises(CheckError) as raised:
            check_flow(parse_net(NET.read_text(encoding='utf-8')),
                       'use net nets.Inventory\n' + CHECKOUT.read_text(encoding='utf-8'))
        self.assertEqual(raised.exception.code, 'E200')


if __name__ == '__main__':
    unittest.main()
