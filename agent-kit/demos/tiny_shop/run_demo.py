#!/usr/bin/env python3
"""Tiny Shop terminal demo: buy the last item in a stock-one Inventory simulation.

This is presentation plumbing only. Reservation, payment-outcome branching, and
settlement live in shop.weave and are executed by the kit's existing Weave runner
(scripts/weave.py simulate). This script selects the scripted outcome, invokes the
runner, and renders the runner's actual JSON results.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

DEMO_DIR = Path(__file__).resolve().parent
KIT_ROOT = DEMO_DIR.parents[1]
RUNNER = KIT_ROOT / 'scripts' / 'weave.py'
SOURCE = DEMO_DIR / 'shop.weave'
ENTRY = 'checkout'
OUTCOMES = ('Ok', 'Err', 'Unknown', 'all')

STOCK_PLACES = ('available', 'sold', 'recovery_queue', 'registrations')
TRANSIENT_PLACES = ('held', 'escrow', 'inflight', 'paid', 'unpaid', 'uncertain', 'manual')

# Labels keyed by the settling NET transition the runner actually executed.
SETTLEMENT = {
    'sell': ('Purchase completed',
             'Payment succeeded; Paid evidence was consumed by Inventory.sell.'),
    'release': ('Payment rejected; item released',
                'Final rejection; Unpaid was consumed by Inventory.release and the item is available again.'),
    'handoff': ('Payment unresolved; item held for recovery',
                'Outcome unknown; Uncertain was handed off to the recovery queue with its '
                'registration intact. Recovery itself is not run by this demo.'),
}


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description='Tiny Shop: simulate buying the last item with a scripted payment outcome. '
                    'Each invocation is a fresh, independent stock-one simulation; tenant, order, '
                    'and amount are symbolic inputs, and no payment is made.')
    parser.add_argument('--outcome', choices=OUTCOMES, default='all',
                        help='scripted Payments.charge outcome (default: all)')
    parser.add_argument('--trace', action='store_true',
                        help='also show the recorded marking after each event')
    parser.add_argument('--json', action='store_true',
                        help='emit one JSON document on stdout')
    parser.add_argument('--source', type=Path, default=SOURCE,
                        help='Weave flow file to execute (default: shop.weave next to this script)')
    return parser.parse_args(argv)


def run_runner(source, outcome):
    """Invoke the existing runner; return (exit code, parsed JSON or None, stderr text)."""
    cmd = [sys.executable, '-B', str(RUNNER), '--json', 'simulate', str(source),
           '--entry', ENTRY, '--outcome', outcome, '--trace']
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        data = None
    return proc.returncode, data, proc.stderr.strip()


def summarize_run(run, with_trace):
    events = run.get('events', [])
    transitions = [e['name'] for e in events if e['kind'] == 'NET']
    settled_by = transitions[-1] if transitions else None
    label, explanation = SETTLEMENT.get(settled_by, ('Unexpected result', 'No recognized settlement transition was executed.'))
    scenario = {
        # The runner's claim for this run and the run's own status, relayed unchanged.
        'claim_label': run['claim_label'],
        'runtime_status': run['runtime_status'],
        'outcome': run['outcome'],
        'result': label,
        'explanation': explanation,
        'return_type': run.get('return_type'),
        'return_tag': run.get('return_tag'),
        'net_transitions': transitions,
        'final_marking': run['marking'],
    }
    if with_trace:
        scenario['events'] = events
    return scenario


def build_report(args):
    code, data, stderr = run_runner(args.source, args.outcome)
    report = {'demo': 'tiny_shop', 'source': str(args.source), 'entry': ENTRY,
              'requested_outcome': args.outcome, 'runner_exit': code}
    if data is None:
        report.update(ok=False, diagnostic={'code': 'RUNNER_OUTPUT', 'stage': 'demo',
                                            'message': 'Runner did not return JSON. ' + stderr})
        return report
    report['ok'] = bool(code == 0 and data.get('ok'))
    for key in ('accounting', 'ordering', 'diagnostic'):
        if key in data:
            report[key] = data[key]
    if report['ok']:
        report['scenarios'] = [summarize_run(r, args.trace) for r in data['runs']]
    elif 'diagnostic' not in report:
        report['diagnostic'] = {'code': 'RUNNER_FAILED', 'stage': 'demo',
                                'message': stderr or 'Runner reported failure without a diagnostic.'}
    return report


def fmt_marking(marking, places):
    return ' '.join(f'{p}={marking[p]}' for p in places)


def render_text(report):
    acc, order = report['accounting'], report['ordering']
    print('Tiny Shop - buy the last item (stock = 1, fresh simulation per run)')
    # Claims are printed as 'LABEL statement' lines with the runner's labels; other lines are not claims.
    print(f"{acc['claim_label']} net accounting ({', '.join(acc['invariants'])})")
    print(f"{order['claim_label']} order model ({order['states']} states/{order['edges']} edges, "
          f"orders={order['orders']}, stock={order['stock']}, tokens/place<={order['place_bound']})")
    for s in report['scenarios']:
        m = s['final_marking']
        print()
        print(f"== Payment outcome: {s['outcome']} -> {s['result']}")
        print(f"{s['claim_label']} flow execution with chosen payment outcome {s['outcome']} "
              "(no real payment I/O)")
        print(f"   runtime status: {s['runtime_status']}")
        print(f"   NET transitions: {' -> '.join(s['net_transitions'])}")
        if 'events' in s:
            print('   Trace:')
            for e in s['events']:
                tag = f"[{e['tag']}]" if e['tag'] else ''
                print(f"     {e['kind']:<6} {e['name'] + tag:<22} {fmt_marking(e['marking'], e['marking'])}")
        print(f"   Final: {fmt_marking(m, STOCK_PLACES)}")
        print(f"          {fmt_marking(m, TRANSIENT_PLACES)}  charge_requests={m['charge_requests']}")
        print(f"   {s['explanation']}")
    print()
    print('charge_requests=1 remains because the simulator does not drain the adapter queue.')


def main(argv=None):
    args = parse_args(argv)
    report = build_report(args)
    if args.json:
        print(json.dumps(report, indent=2))
    elif report['ok']:
        render_text(report)
    else:
        d = report['diagnostic']
        span = d.get('span') or {}
        loc = f" {span['file']}:{span['start']['line']}" if span else (f" {d.get('file')}:{d.get('line')}" if d.get('file') else '')
        print(f"error: {d.get('code')} [{d.get('stage')}]{loc}: {d.get('message')}", file=sys.stderr)
    if report['ok']:
        return 0
    return report['runner_exit'] if report['runner_exit'] not in (0, None) else 1


if __name__ == '__main__':
    sys.exit(main())
