"""Negative tests for documentation checks and the generated grammar."""
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from grammar_audit import layout, parser, generate
from spec_checks import check_example
from lark import UnexpectedInput

class DocumentationChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.p,_,_=parser()
    def test_unsupported_if_is_syntax_rejected(self):
        with self.assertRaises(UnexpectedInput):
            self.p.parse(layout((ROOT/"examples/invalid/unsupported_if.weave").read_text()),start="flow_file")
    def test_semantic_negative_still_parses(self):
        s=(ROOT/"examples/invalid/wrong_order.weave").read_text()
        self.p.parse(layout(s),start="flow_file")
        self.assertEqual(check_example(s),"E209")
    def test_changed_inline_enum_cannot_silently_pass(self):
        s="enum ChargeOutcome[t, o]:\n    Ok(Unpaid[t, o])\n    Err(Unpaid[t, o])\n    Unknown(Uncertain[t, o])\n"
        self.assertEqual(check_example(s,"N1","net-fragment"),"E100")
    def test_changed_runtime_consumer_fragment_is_rejected(self):
        self.assertEqual(check_example("runtime_state inflight terminal\n","N1","net-fragment"),"E101")
    def test_fragment_missing_context_fails(self):
        with self.assertRaises(ValueError):
            check_example("place invented = 0 owner domain\n","N1","net-fragment")
    def test_generated_parser_rejects_trailing_garbage(self):
        source=(ROOT/"examples/valid/arm_hold.weave").read_text()+"garbage\n"
        with self.assertRaises(UnexpectedInput):self.p.parse(layout(source),start="flow_file")
    def test_layout_rejects_tab_in_comment(self):
        with self.assertRaises(ValueError):layout("#\tbad\nflow x():\n    return\n")
    def test_grammar_undefined_reference_is_fatal(self):
        with self.assertRaises(ValueError):generate('start = missing ;')
    def test_lease_does_not_use_inventory_environment(self):
        source=(ROOT/"examples/valid/lease_roundtrip.weave").read_text()
        self.assertEqual(check_example(source,net_path=ROOT/"examples/nets/Lease.weave"),"ACCEPT")
        self.assertEqual(check_example(source),"E206")

if __name__=="__main__":unittest.main()

