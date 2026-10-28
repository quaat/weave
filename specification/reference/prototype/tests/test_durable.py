import tempfile
import unittest
from pathlib import Path

from durable import COLOURS, Runtime, crash_child, run_crash_cases


class DurableChecks(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.path=Path(self.temp.name)
        self.runtime=Runtime(self.path); self.a,self.b=COLOURS

    def tearDown(self):
        if self.runtime is not None:self.runtime.close()
        self.temp.cleanup()

    def reopen(self):
        self.runtime.close();self.runtime=Runtime(self.path)

    def crash(self,action,point):
        self.runtime.close();self.runtime=None
        crash_child(self.path,action,point)
        self.runtime=Runtime(self.path)

    def prepare(self,colour=None):
        c=colour or self.a
        self.runtime.admit(c,{'sku':'one'});self.runtime.start(c)

    def test_all_six_process_crash_scenarios(self):
        results=run_crash_cases(self.path/'cases')
        self.assertEqual(len(results),6)
        self.assertTrue(all(r['status']=='PASSED' for r in results))

    def test_uncommitted_admission_rolls_back(self):
        self.crash('admit','before_admission_commit')
        self.assertEqual(self.runtime.summary()['jobs'],[])
        self.assertEqual(self.runtime.count('identities',self.a),1)
        self.runtime.admit(self.a,{'sku':'one'})

    def test_uncommitted_start_rolls_back_all_net_steps(self):
        self.runtime.admit(self.a,{'sku':'one'})
        self.crash('start','before_start_commit')
        self.assertEqual(self.runtime.count('identities',self.a),1)
        self.assertEqual(self.runtime.count('registrations',self.a),0)
        self.assertEqual(self.runtime.summary()['operations'],[])

    def test_crash_between_dequeue_and_provider_send_is_retryable(self):
        self.prepare();self.crash('send','after_dequeue_commit')
        self.assertEqual(self.runtime.count('charge_requests',self.a),0)
        self.assertEqual(self.runtime.summary()['provider'],[])
        receipt=self.runtime.send(self.a)
        self.runtime.receive(self.a,receipt);self.runtime.settle(self.a,generation=self.runtime.generation(self.a))
        self.assertEqual(self.runtime.summary()['provider'][0]['charges'],1)

    def test_lost_reply_resend_uses_same_provider_key(self):
        self.prepare();self.crash('send','after_provider_commit')
        receipt=self.runtime.send(self.a)
        self.runtime.receive(self.a,receipt);self.runtime.settle(self.a)
        provider=self.runtime.summary()['provider'][0]
        self.assertEqual(provider['attempts'],2)
        self.assertEqual(provider['charges'],1)

    def test_receipt_transaction_rolls_back_on_crash(self):
        self.prepare();self.runtime.send(self.a)
        self.crash('receive','before_receipt_commit')
        self.assertEqual(self.runtime.count('inflight',self.a),1)
        self.assertEqual(self.runtime.count('paid',self.a),0)
        self.runtime.reconcile(self.a)
        self.assertEqual(self.runtime.count('sold',self.a),1)

    def test_result_and_completion_and_credit_are_atomic(self):
        self.prepare();self.runtime.receive(self.a,self.runtime.send(self.a))
        self.crash('settle','before_result_commit')
        self.assertEqual(self.runtime.count('sold',self.a),1)
        self.assertEqual(self.runtime.count('pool_busy',self.a),1)
        self.assertEqual(self.runtime.summary()['results'],[])
        self.assertEqual(self.runtime.summary()['jobs'][0]['completed'],0)
        self.runtime.finish(self.a)
        self.assertEqual(self.runtime.count('pool_free'),2)
        self.assertEqual(len(self.runtime.summary()['results']),1)

    def test_duplicate_admission_and_start_do_not_reserve_twice(self):
        self.prepare();before=self.runtime.marking()
        self.runtime.admit(self.a,{'sku':'one'});self.runtime.start(self.a)
        self.assertEqual(before,self.runtime.marking())
        self.assertEqual(len(self.runtime.summary()['jobs']),1)

    def test_conflicting_payload_is_rejected(self):
        self.prepare()
        with self.assertRaises(ValueError):self.runtime.admit(self.a,{'sku':'different'})

    def test_two_orders_and_swapped_receipt(self):
        self.prepare(self.a);self.prepare(self.b)
        receipt=self.runtime.send(self.b);before=self.runtime.marking()
        with self.assertRaises(ValueError):self.runtime.receive(self.a,receipt)
        self.assertEqual(before,self.runtime.marking())
        self.runtime.receive(self.b,receipt);self.runtime.settle(self.b)
        self.assertEqual(self.runtime.count('registrations',self.a),1)
        self.assertEqual(self.runtime.count('registrations',self.b),0)
        self.runtime.receive(self.a,self.runtime.send(self.a));self.runtime.settle(self.a)
        self.assertEqual(len(self.runtime.summary()['results']),2)
        self.assertEqual(self.runtime.count('pool_free'),2)

    def test_late_receipt_updates_ledger_but_does_not_unfence_worker(self):
        self.prepare();receipt=self.runtime.send(self.a);self.runtime.cancel(self.a)
        self.reopen()
        with self.assertRaises(ValueError):self.runtime.settle(self.a,generation=1)
        self.runtime.receive(self.a,receipt);self.runtime.settle(self.a,generation=self.runtime.generation(self.a))
        self.assertEqual(self.runtime.generation(self.a),2)
        self.assertEqual(self.runtime.count('sold',self.a),1)

    def test_duplicate_receipt_and_completion_are_idempotent(self):
        self.prepare();receipt=self.runtime.send(self.a)
        for _ in range(2):self.runtime.receive(self.a,receipt);self.runtime.settle(self.a)
        self.assertEqual(len(self.runtime.summary()['results']),1)
        self.assertEqual(self.runtime.count('pool_free'),2)

    def test_not_found_never_releases_stock(self):
        self.prepare();self.runtime.reconcile(self.a);self.runtime.reconcile(self.a)
        self.assertEqual(self.runtime.count('manual',self.a),1)
        self.assertEqual(self.runtime.count('registrations',self.a),1)
        self.assertEqual(self.runtime.count('released',self.a),0)

    def test_contradictory_final_evidence_is_quarantined_as_error(self):
        self.prepare();receipt=self.runtime.send(self.a);self.runtime.receive(self.a,receipt)
        bad=dict(receipt,state='Rejected');before=self.runtime.marking()
        with self.assertRaises(ValueError):self.runtime.receive(self.a,bad)
        self.assertEqual(before,self.runtime.marking())

    def test_weaker_status_does_not_erase_paid_evidence(self):
        self.prepare();receipt=self.runtime.send(self.a);self.runtime.receive(self.a,receipt)
        self.runtime.receive(self.a,dict(receipt,state='NotFound'));self.runtime.settle(self.a)
        self.assertEqual(self.runtime.count('sold',self.a),1)

    def test_rejection_releases_and_consumes_request(self):
        self.prepare();self.runtime.receive(self.a,self.runtime.send(self.a,'Rejected'));self.runtime.settle(self.a)
        self.assertEqual(self.runtime.count('released',self.a),1)
        self.assertEqual(self.runtime.count('registrations',self.a),0)
        self.assertEqual(self.runtime.count('charge_requests',self.a),0)

    def test_recovery_budget_guard_is_enforced_by_model_runtime(self):
        self.prepare();self.runtime.receive(self.a,self.runtime.send(self.a,'Pending'));self.runtime.settle(self.a)
        with self.assertRaises(ValueError):
            with self.runtime.transaction():self.runtime.fire('escalate',self.a)

    def test_late_success_resolves_escalated_order(self):
        self.prepare();self.runtime.receive(self.a,self.runtime.send(self.a,'Pending'));self.runtime.settle(self.a)
        self.runtime.reconcile(self.a);self.runtime.reconcile(self.a)
        self.assertEqual(self.runtime.count('manual',self.a),1)
        self.runtime.provider.resolve(self.a,'Paid');self.reopen();self.runtime.reconcile(self.a)
        self.assertEqual(self.runtime.count('sold',self.a),1)
        self.assertEqual(self.runtime.count('registrations',self.a),0)
        self.assertEqual(self.runtime.summary()['results'][0]['state'],'Ok')
        self.assertEqual(self.runtime.count('pool_free'),2)

    def test_reopen_refuses_silent_net_revision_change(self):
        source=self.runtime.net.source+'\n# new revision\n'
        with self.assertRaises(ValueError):Runtime(self.path,source=source)


if __name__=='__main__':unittest.main()
