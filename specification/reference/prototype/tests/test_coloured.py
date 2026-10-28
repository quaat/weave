import unittest
from pathlib import Path

from checker import CheckError, check_flow
from coloured import Unfolding, explore_colours, parse_coloured, prove_colours

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT/'Inventory.coloured.weave').read_text()


def cross_sell(source=SOURCE):
    return source.replace('transition sell[t, o]:\n        take 1 paid[t, o]\n        take 1 registrations[t, o]',
                          'transition sell[t, o]:\n        take 1 paid[t, o]\n        take 1 registrations[t, other]')


class ColourChecks(unittest.TestCase):
    def setUp(self): self.net = parse_coloured(SOURCE)

    def error(self, code, action):
        with self.assertRaises(CheckError) as raised: action()
        self.assertEqual(raised.exception.code, code, raised.exception.message)
        return raised.exception

    def test_family_proofs_and_two_order_graph(self):
        proof = prove_colours(self.net)
        self.assertEqual({p['name'] for p in proof['families']}, {'identity_conservation','registration_balance','job_accounting'})
        result = explore_colours(self.net)
        self.assertEqual((result['states'],result['edges']), (841,3712))
        self.assertEqual(result['unreached_transitions'], [])
        self.assertTrue(all(result['premise_states'].values()))

    def test_unfolded_matrix_retains_colour_rows_and_columns(self):
        proof = prove_colours(self.net); unfolding = Unfolding(self.net)
        matrix = proof['finite_unfolding']
        self.assertEqual(len(matrix['rows']), 32)
        self.assertEqual(len(matrix['columns']), 48)
        self.assertIn('registrations[tenant,order1]', matrix['rows'])
        self.assertIn('registrations[tenant,order2]', matrix['rows'])
        for family in proof['families']:
            for colour in unfolding.colours:
                weights = [family['weights'].get(p,0) if c == colour else 0 for p,c in unfolding.rows]
                self.assertEqual(sum(w*n for w,n in zip(weights,matrix['initial'])),family['target'])
                for j in range(len(matrix['columns'])):
                    self.assertEqual(sum(w*matrix['incidence'][i][j] for i,w in enumerate(weights)),0)

    def test_cross_order_registration_fails_family_and_exploration(self):
        net = parse_coloured(cross_sell())
        self.error('E412',lambda:prove_colours(net))
        e = self.error('E420',lambda:explore_colours(net))
        self.assertIn('take registrations[tenant,order2]',e.message)
        self.assertIn('sell[t=tenant,o=order1,other=order2]',e.message)
        self.assertGreater(e.line,0)

    def test_cross_order_read_preserves_counts_but_fails_correlation(self):
        source = SOURCE.replace('read 1 registrations[t, o]', 'read 1 registrations[t, other]')
        net = parse_coloured(source)
        prove_colours(net)
        e = self.error('E420',lambda:explore_colours(net))
        self.assertIn('read registrations',e.message)

    def test_cross_tenant_is_explored(self):
        source = SOURCE.replace('read 1 registrations[t, o]', 'read 1 registrations[other, o]')
        net = parse_coloured(source)
        prove_colours(net)
        self.error('E420',lambda:explore_colours(net,colours=[('tenant1','order'),('tenant2','order')]))

    def test_each_order_can_sell_only_its_own_registration(self):
        u = Unfolding(self.net); a,b = u.colours; marking = u.initial
        for c in (a,b):
            for t in ('reserve','arm','dispatch','charge_ok'): marking=u.fire(marking,u.select(t,c))
        marking=u.fire(marking,u.select('sell',a))
        self.assertEqual(marking[u.index['registrations',a]],0)
        self.assertEqual(marking[u.index['registrations',b]],1)

    def test_second_reserve_same_identity_is_disabled(self):
        u=Unfolding(self.net); c=u.colours[0]; reserve=u.select('reserve',c)
        marking=u.fire(u.initial,reserve)
        self.error('E421',lambda:u.fire(marking,reserve))

    def test_removing_identity_consumption_fails_proof_and_uniqueness(self):
        source=SOURCE.replace('        take 1 identities[t, o]\n','')
        source=source.replace('runtime_state identities consumers reserve','runtime_state identities terminal')
        net=parse_coloured(source)
        self.error('E412',lambda:prove_colours(net))
        e=self.error('E420',lambda:explore_colours(net))
        self.assertIn('unique_admission',e.message)

    def test_family_cannot_mix_bare_and_indexed_counts(self):
        source=SOURCE.replace('registrations[t, o] - escrow[t, o]', 'registrations[t, o] + registrations - escrow[t, o]')
        self.error('E411',lambda:prove_colours(parse_coloured(source)))

    def test_family_wrong_binder_is_rejected(self):
        source=SOURCE.replace('registrations[t, o] - escrow[t, o]', 'registrations[t, other] - escrow[t, o]')
        self.error('E411',lambda:prove_colours(parse_coloured(source)))

    def test_arc_cannot_silently_erase_colour(self):
        source=SOURCE.replace('read 1 registrations[t, o]','read 1 registrations')
        self.error('E400',lambda:parse_coloured(source))

    def test_sort_mix_is_rejected(self):
        source=SOURCE.replace('read 1 registrations[t, o]','read 1 registrations[o, t]')
        self.error('E400',lambda:parse_coloured(source))

    def test_nested_ignored_syntax_is_rejected(self):
        source=SOURCE.replace('guard authoritative_paid_evidence\n','guard authoritative_paid_evidence:\n            unsafe unknown\n',1)
        self.error('E003',lambda:parse_coloured(source))

    def test_budget_exhaustion_is_not_success(self):
        self.error('E422',lambda:explore_colours(self.net,max_states=1))

    def test_initial_paid_without_evidence_is_detected(self):
        source=SOURCE.replace('place sold[t, o] = 0','place sold[t, o] = 1')
        self.error('E420',lambda:explore_colours(parse_coloured(source)))

    def test_existing_flows_typecheck_against_coloured_api_projection(self):
        source=(ROOT/'examples/checkout_propagating.weave').read_text()
        self.assertEqual(len(check_flow(self.net.base,source)),3)

    def test_question_diagnostic_names_original_line_and_action(self):
        source='''flow fail(result: ChargeOutcome[t, o], hold2: Paid[u, v]) -> ChargeOutcome[t, o]:
    # Preparation.
    # Keep the next expression on line four.
    let paid = result?
    await Inventory.sell(hold2)
    return Ok(paid)
'''
        e=self.error('E204',lambda:check_flow(self.net.base,source))
        self.assertEqual(e.line,4)
        self.assertIn("'?' on line 4",e.message)
        self.assertIn('Err/Unknown',e.message)
        self.assertIn('hold2',e.message)
        self.assertNotIn('normal return',e.message)
        self.assertIn('example.weave:4',e.render('example.weave'))


if __name__=='__main__':unittest.main()
