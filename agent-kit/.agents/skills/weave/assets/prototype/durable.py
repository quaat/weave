#!/usr/bin/env python3
"""SQLite crash-injection model over the actual coloured transition system.

Domain and provider use separate databases. No real payment, network, or service
is contacted. Process termination is real; disk/power-loss and distributed
consensus failures are outside this model.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

from checker import CheckError
from coloured import Unfolding, parse_coloured, prove_colours

ROOT = Path(__file__).resolve().parent
COLOURS = [('tenant', 'order1'), ('tenant', 'order2')]


def connect(path):
    db = sqlite3.connect(path, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('PRAGMA synchronous=FULL')
    db.execute('PRAGMA foreign_keys=ON')
    return db


def key(colour):
    return json.dumps(['Payments.charge', *colour], separators=(',', ':'))


class Provider:
    """Persisted keyed provider contract, deliberately outside domain commits."""
    def __init__(self, path):
        self.db = connect(path)
        self.db.execute('CREATE TABLE IF NOT EXISTS payments (key TEXT PRIMARY KEY, digest TEXT NOT NULL, state TEXT NOT NULL, attempts INTEGER NOT NULL, charges INTEGER NOT NULL)')

    def charge(self, colour, digest, outcome='Paid'):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            row = self.db.execute('SELECT * FROM payments WHERE key=?', (key(colour),)).fetchone()
            if row:
                if row['digest'] != digest: raise ValueError('Provider key reused with a different request')
                self.db.execute('UPDATE payments SET attempts=attempts+1 WHERE key=?', (key(colour),))
            else:
                if outcome not in {'Paid', 'Rejected', 'Pending'}: raise ValueError('Invalid scripted provider outcome')
                self.db.execute('INSERT INTO payments VALUES (?,?,?,?,?)', (key(colour), digest, outcome, 1, int(outcome == 'Paid')))
            self.db.commit()
        except BaseException:
            self.db.rollback(); raise
        return self.status(colour)

    def status(self, colour):
        row = self.db.execute('SELECT * FROM payments WHERE key=?', (key(colour),)).fetchone()
        return {'key': key(colour), 'colour': list(colour), 'state': row['state'] if row else 'NotFound'}

    def resolve(self, colour, state):
        if state not in {'Paid','Rejected'}: raise ValueError('Expected final provider state')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            row = self.db.execute('SELECT state FROM payments WHERE key=?', (key(colour),)).fetchone()
            if row is None: raise ValueError('Unknown provider operation')
            if row['state'] != 'Pending' and row['state'] != state: raise ValueError('Provider final outcome is immutable')
            if row['state'] == 'Pending':
                self.db.execute('UPDATE payments SET state=?,charges=? WHERE key=?', (state,int(state=='Paid'),key(colour)))
            self.db.commit()
        except BaseException:
            self.db.rollback(); raise
        return self.status(colour)

    def close(self): self.db.close()


class Runtime:
    def __init__(self, directory, crash_at=None, source=None):
        self.directory = Path(directory); self.directory.mkdir(parents=True, exist_ok=True)
        self.net = parse_coloured(source or (ROOT/'Inventory.coloured.weave').read_text())
        self.proof = prove_colours(self.net)
        self.unfolding = Unfolding(self.net, COLOURS)
        self.crash_at = crash_at
        self.db = connect(self.directory/'domain.sqlite')
        self.provider = Provider(self.directory/'provider.sqlite')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS marking (cell INTEGER PRIMARY KEY, count INTEGER NOT NULL CHECK(count >= 0));
            CREATE TABLE IF NOT EXISTS jobs (key TEXT PRIMARY KEY, payload TEXT NOT NULL, generation INTEGER NOT NULL, completed INTEGER NOT NULL DEFAULT 0, source_ack INTEGER NOT NULL DEFAULT 0, worker_ack INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS operations (key TEXT PRIMARY KEY REFERENCES jobs(key), state TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, recovery_attempts INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS results (key TEXT PRIMARY KEY REFERENCES jobs(key), state TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events (sequence INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, detail TEXT NOT NULL, marking TEXT NOT NULL);
        ''')
        digest = hashlib.sha256(self.net.source.encode()).hexdigest()
        try:
            with self.transaction():
                row = self.db.execute("SELECT value FROM metadata WHERE key='source'").fetchone()
                if row is None:
                    self.db.execute('INSERT INTO metadata VALUES (?,?)', ('source', digest))
                    self.db.executemany('INSERT INTO marking VALUES (?,?)', enumerate(self.unfolding.initial))
                elif row['value'] != digest:
                    raise ValueError('Persisted net revision differs; migration is required')
                self.check_accounting()
        except BaseException:
            self.close(); raise

    @contextmanager
    def transaction(self):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            yield
            self.db.commit()
        except BaseException:
            self.db.rollback(); raise

    def checkpoint(self, name):
        if self.crash_at == name: os._exit(91)

    def marking(self):
        return tuple(r['count'] for r in self.db.execute('SELECT count FROM marking ORDER BY cell'))

    def count(self, place, colour=None):
        return self.marking()[self.unfolding.index[place, colour]]

    def event(self, kind, **detail):
        self.db.execute('INSERT INTO events(kind,detail,marking) VALUES (?,?,?)',
                        (kind, json.dumps(detail, sort_keys=True), json.dumps(self.unfolding.snapshot(self.marking()), sort_keys=True)))

    def check_accounting(self):
        marking = self.marking()
        for family in self.proof['families']:
            for c in self.unfolding.colours:
                actual = sum(w * marking[self.unfolding.index[p, c]] for p, w in family['weights'].items())
                if actual != family['target']: raise AssertionError(f'Family accounting violated: {family["name"]}, {c}')
        for inv in self.proof['aggregate']:
            weights = dict(zip(self.net.base.places, inv['weights']))
            actual = sum(weights[p] * marking[i] for i, (p, _) in enumerate(self.unfolding.rows))
            coefficient, constant = inv['initial_target']
            if actual != coefficient*self.unfolding.stock+constant:
                raise AssertionError('Aggregate accounting violated')

    def fire(self, transition, colour):
        if not self.db.in_transaction: raise AssertionError('Net changes require a domain transaction')
        mode = self.unfolding.select(transition, tuple(colour))
        # Execute the source inscriptions, not hand-written marking deltas.
        for kind in ('take', 'read', 'put'):
            if any(c is not None and c != mode.colour for i in getattr(mode, kind) for _, c in [self.unfolding.rows[i]]):
                raise CheckError('E420', 'Cross-order firing rejected by runtime')
        classes = {self.net.base.order_check.guards[g] for g in self.net.base.transitions[transition].guards}
        operation = self.db.execute('SELECT * FROM operations WHERE key=?', (key(colour),)).fetchone()
        if 'establishes_paid' in classes and (not operation or operation['state'] != 'Paid'):
            raise ValueError('Paid evidence required')
        if 'establishes_rejected' in classes and (not operation or operation['state'] != 'Rejected'):
            raise ValueError('Final rejection evidence required')
        guards = self.net.base.transitions[transition].guards
        if 'outcome_unresolved' in guards and (not operation or operation['state'] not in {'Pending', 'Unknown'}):
            raise ValueError('Unresolved operation required')
        if 'recovery_budget_exhausted' in guards and (not operation or operation['recovery_attempts'] < 2):
            raise ValueError('Recovery attempt budget not exhausted')
        after = self.unfolding.fire(self.marking(), mode)
        self.db.executemany('UPDATE marking SET count=? WHERE cell=?', [(n, i) for i, n in enumerate(after)])
        self.check_accounting()
        self.event('fire', transition=transition, colour=colour)

    def admit(self, colour, payload):
        colour = tuple(colour)
        if colour not in self.unfolding.colours: raise ValueError('Identity outside scenario bounds')
        encoded = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        with self.transaction():
            previous = self.db.execute('SELECT payload FROM jobs WHERE key=?', (key(colour),)).fetchone()
            if previous and previous['payload'] != encoded: raise ValueError('Conflicting payload for admitted identity')
            if not previous:
                self.db.execute('INSERT INTO jobs(key,payload,generation) VALUES (?,?,1)', (key(colour), encoded))
            self.event('admission_duplicate' if previous else 'admitted', colour=colour)
            self.checkpoint('before_admission_commit')
        self.checkpoint('after_admission_commit')
        with self.transaction():
            self.db.execute('UPDATE jobs SET source_ack=1 WHERE key=?', (key(colour),))
            self.event('source_ack', colour=colour)

    def generation(self, colour):
        row = self.db.execute('SELECT generation FROM jobs WHERE key=?', (key(colour),)).fetchone()
        if row is None: raise ValueError('Unknown admitted identity')
        return row['generation']

    def require_owner(self, colour, generation):
        if self.generation(colour) != generation: raise ValueError('Stale activation generation')

    def start(self, colour, generation=1):
        colour = tuple(colour)
        with self.transaction():
            self.require_owner(colour, generation)
            if self.count('identities', colour): self.fire('reserve', colour)
            if self.count('held', colour): self.fire('arm', colour)
            if self.count('escrow', colour):
                self.db.execute('INSERT INTO operations(key,state) VALUES (?,?)', (key(colour), 'Pending'))
                self.fire('dispatch', colour)
            self.checkpoint('before_start_commit')
        self.checkpoint('after_start_commit')

    def send(self, colour, outcome='Paid'):
        colour = tuple(colour)
        with self.transaction():
            operation = self.db.execute('SELECT state FROM operations WHERE key=?', (key(colour),)).fetchone()
            if operation is None: raise ValueError('Operation was not durably dispatched')
            if operation['state'] in {'Paid', 'Rejected'}: return self.provider.status(colour)
            if self.count('charge_requests', colour): self.fire('adapter_dequeue', colour)
            self.db.execute('UPDATE operations SET attempts=attempts+1 WHERE key=?', (key(colour),))
            self.event('send_attempt', colour=colour)
        self.checkpoint('after_dequeue_commit')
        payload = self.db.execute('SELECT payload FROM jobs WHERE key=?', (key(colour),)).fetchone()['payload']
        receipt = self.provider.charge(colour, hashlib.sha256(payload.encode()).hexdigest(), outcome)
        self.checkpoint('after_provider_commit')
        return receipt

    def receive(self, colour, receipt):
        colour = tuple(colour)
        if receipt.get('key') != key(colour) or tuple(receipt.get('colour', ())) != colour:
            raise ValueError('Receipt identity does not match operation')
        incoming = receipt.get('state')
        if incoming not in {'Paid', 'Rejected', 'Pending', 'NotFound'}: raise ValueError('Invalid provider evidence')
        with self.transaction():
            old = self.db.execute('SELECT state FROM operations WHERE key=?', (key(colour),)).fetchone()
            if old is None: raise ValueError('Receipt has no admitted operation')
            if old['state'] in {'Paid', 'Rejected'} and incoming in {'Paid', 'Rejected'} and old['state'] != incoming:
                raise ValueError('Contradictory final evidence')
            if old['state'] in {'Paid', 'Rejected'} and incoming in {'Pending', 'NotFound'}:
                incoming = old['state']  # weaker evidence cannot erase a terminal fact
            state = incoming if incoming in {'Paid', 'Rejected'} else 'Unknown'
            self.db.execute('UPDATE operations SET state=? WHERE key=?', (state, key(colour)))
            self.event('evidence', colour=colour, state=state)
            if self.count('inflight', colour):
                self.fire({'Paid':'charge_ok', 'Rejected':'charge_err', 'Unknown':'charge_unknown'}[state], colour)
            elif state in {'Paid', 'Rejected'}:
                if self.count('recovery_queue', colour): self.fire('recover_paid' if state == 'Paid' else 'recover_rejected', colour)
                elif self.count('manual', colour): self.fire('manual_paid' if state == 'Paid' else 'manual_rejected', colour)
            self.checkpoint('before_receipt_commit')
        self.checkpoint('after_receipt_commit')

    def settle(self, colour, generation=1):
        colour = tuple(colour)
        with self.transaction():
            self.require_owner(colour, generation)
            if self.count('paid', colour): self.fire('sell', colour)
            if self.count('unpaid', colour): self.fire('release', colour)
            if self.count('uncertain', colour): self.fire('handoff', colour)
        self.finish(colour)

    def finish(self, colour):
        colour = tuple(colour)
        with self.transaction():
            if self.count('sold', colour): state, transition = 'Ok', 'finish_sold'
            elif self.count('released', colour): state, transition = 'Err', 'finish_released'
            elif self.count('recovery_queue', colour): state, transition = 'Unknown', 'finish_unknown'
            else: return
            if self.count('pool_busy', colour): self.fire(transition, colour)
            # Updating a previously Unknown result is an explicit status change;
            # the result identity and completion/credit token are not duplicated.
            self.db.execute('INSERT INTO results VALUES (?,?) ON CONFLICT(key) DO UPDATE SET state=excluded.state', (key(colour), state))
            self.db.execute('UPDATE jobs SET completed=1 WHERE key=?', (key(colour),))
            self.event('result_commit', colour=colour, state=state)
            self.checkpoint('before_result_commit')
        self.checkpoint('after_result_commit')
        with self.transaction():
            self.db.execute('UPDATE jobs SET worker_ack=1 WHERE key=?', (key(colour),))
            self.event('worker_ack', colour=colour)

    def cancel(self, colour):
        colour = tuple(colour)
        with self.transaction():
            self.db.execute('UPDATE jobs SET generation=generation+1 WHERE key=?', (key(colour),))
            for place in ('held','escrow','inflight','paid','unpaid','uncertain'):
                if self.count(place, colour):
                    self.fire('cancel_' + place, colour); break
            self.event('cancelled', colour=colour, generation=self.generation(colour))
        self.finish(colour)
        self.checkpoint('after_cancel_finish')

    def reconcile(self, colour):
        colour = tuple(colour)
        self.receive(colour, self.provider.status(colour))
        self.settle(colour, generation=self.generation(colour))
        with self.transaction():
            operation = self.db.execute('SELECT state FROM operations WHERE key=?', (key(colour),)).fetchone()
            if operation['state'] == 'Unknown' and self.count('recovery_queue', colour):
                self.db.execute('UPDATE operations SET recovery_attempts=recovery_attempts+1 WHERE key=?', (key(colour),))
                attempts = self.db.execute('SELECT recovery_attempts FROM operations WHERE key=?', (key(colour),)).fetchone()[0]
                if attempts >= 2: self.fire('escalate', colour)
                self.event('reconciliation_wait', colour=colour, attempts=attempts)

    def summary(self):
        return {'marking': self.unfolding.snapshot(self.marking()),
                'jobs': [dict(r) for r in self.db.execute('SELECT * FROM jobs ORDER BY key')],
                'operations': [dict(r) for r in self.db.execute('SELECT * FROM operations ORDER BY key')],
                'results': [dict(r) for r in self.db.execute('SELECT * FROM results ORDER BY key')],
                'provider': [dict(r) for r in self.provider.db.execute('SELECT * FROM payments ORDER BY key')],
                'events': [{'sequence':r['sequence'], 'kind':r['kind'], 'detail':json.loads(r['detail']), 'marking':json.loads(r['marking'])}
                           for r in self.db.execute('SELECT * FROM events ORDER BY sequence')]}

    def close(self): self.provider.close(); self.db.close()


def crash_child(directory, action, checkpoint):
    child = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--child', str(directory), action, checkpoint], capture_output=True, text=True)
    if child.returncode != 91:
        raise AssertionError(f'Expected process death at {checkpoint}; got {child.returncode}: {child.stderr}')
    return {'action': action, 'checkpoint': checkpoint, 'exit_code': child.returncode}


def perform_child(directory, action, checkpoint):
    runtime = Runtime(directory, checkpoint); colour = COLOURS[0]
    if action == 'admit': runtime.admit(colour, {'sku':'one'})
    elif action == 'start': runtime.start(colour)
    elif action == 'send': runtime.send(colour)
    elif action == 'receive': runtime.receive(colour, runtime.provider.status(colour))
    elif action == 'settle': runtime.settle(colour)
    elif action == 'cancel': runtime.cancel(colour)
    else: raise ValueError('Unknown child action')
    runtime.close()
    raise AssertionError('Crash checkpoint was not reached')


def run_crash_cases(directory):
    root = Path(directory); root.mkdir(parents=True, exist_ok=True)
    results = []
    scenarios = ('admission_before_ack','result_before_ack','lost_success_reply',
                 'cancel_after_paid','late_receipt_after_cancel','inconclusive_status')
    if any((root/name/'domain.sqlite').exists() for name in scenarios):
        raise ValueError('Use a fresh directory to preserve earlier crash evidence')
    for scenario in scenarios:
        path = root/scenario; colour = COLOURS[0]
        runtime = Runtime(path)
        # Keep another order unresolved throughout, so recovery must preserve
        # its distinct registration across process death and late evidence.
        other = COLOURS[1]
        runtime.admit(other, {'sku':'one'}); runtime.start(other)
        runtime.receive(other, runtime.send(other, 'Pending')); runtime.settle(other)
        if scenario == 'admission_before_ack':
            runtime.close(); crash = crash_child(path, 'admit', 'after_admission_commit')
            runtime = Runtime(path)
            assert len(runtime.summary()['jobs']) == 2 and runtime.summary()['jobs'][0]['source_ack'] == 0
            runtime.admit(colour, {'sku':'one'})
            assert len(runtime.summary()['jobs']) == 2
            runtime.start(colour); receipt = runtime.send(colour); runtime.receive(colour, receipt); runtime.settle(colour)
        else:
            runtime.admit(colour, {'sku':'one'}); runtime.start(colour)
            if scenario == 'lost_success_reply':
                runtime.close(); crash = crash_child(path, 'send', 'after_provider_commit'); runtime = Runtime(path)
                assert runtime.count('inflight', colour) == runtime.count('registrations', colour) == 1
                runtime.reconcile(colour)
            elif scenario == 'result_before_ack':
                runtime.receive(colour, runtime.send(colour)); runtime.close()
                crash = crash_child(path, 'settle', 'after_result_commit'); runtime = Runtime(path)
                assert runtime.summary()['jobs'][0]['completed'] == 1 and runtime.summary()['jobs'][0]['worker_ack'] == 0
                assert runtime.count('pool_free') == 2 and len(runtime.summary()['results']) == 2
                runtime.settle(colour)
            elif scenario == 'cancel_after_paid':
                runtime.send(colour); runtime.close(); crash = crash_child(path, 'receive', 'after_receipt_commit')
                runtime = Runtime(path); assert runtime.count('paid', colour) == 1
                runtime.cancel(colour)
            elif scenario == 'late_receipt_after_cancel':
                runtime.send(colour); runtime.close()
                crash = crash_child(path, 'cancel', 'after_cancel_finish')
                runtime = Runtime(path)
                try: runtime.settle(colour, generation=1)
                except ValueError: pass
                else: raise AssertionError('Old generation accepted')
                runtime.receive(colour, runtime.provider.status(colour)); runtime.settle(colour, generation=runtime.generation(colour))
                runtime.receive(colour, runtime.provider.status(colour)); runtime.settle(colour, generation=runtime.generation(colour))
            else:
                runtime.send(colour, 'Pending'); runtime.close()
                crash = crash_child(path, 'receive', 'after_receipt_commit')
                runtime = Runtime(path); runtime.settle(colour); runtime.reconcile(colour); runtime.reconcile(colour)
                assert runtime.count('manual', colour) == runtime.count('registrations', colour) == 1
                assert runtime.count('released', colour) == 0
        summary = runtime.summary()
        assert runtime.count('charge_requests', colour) == 0
        assert runtime.count('charge_requests', other) == 0
        assert runtime.count('recovery_queue', other) == runtime.count('registrations', other) == 1
        assert runtime.count('pool_free') == 2
        assert len(summary['results']) == 2
        if scenario != 'inconclusive_status':
            assert runtime.count('sold', colour) == 1 and runtime.count('registrations', colour) == 0
            assert sum(r['charges'] for r in summary['provider']) == 1
        results.append({'scenario': scenario, 'status': 'PASSED', 'crash': crash, **summary})
        runtime.close()
    return results


def main():
    if len(sys.argv) > 1 and sys.argv[1] == '--child':
        perform_child(*sys.argv[2:]); return
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, help='Keep SQLite databases in a new directory')
    args = parser.parse_args()
    def report(directory):
        results = run_crash_cases(directory)
        for result in results: print(f"PASSED {result['scenario']}: {result['marking']}")
        if args.directory: (args.directory/'scenarios.json').write_text(json.dumps(results,indent=2)+'\n')
    if args.directory: report(args.directory)
    else:
        with tempfile.TemporaryDirectory() as directory: report(directory)
    print('Process-crash model only; filesystem power loss, real providers, network authentication, and distributed consensus are not verified.')


if __name__ == '__main__': main()
