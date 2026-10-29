#!/usr/bin/env python3
"""Merge-sort demo: run the checked Weave program merge_sort.weave on a JSON list of integers.

The sort, recursion, comparisons, fork/join, and merge are Weave source executed by the kit
runner's `run-pure` command. This script only validates input, invokes the runner, and renders
the runner's actual JSON result. It never sorts in Python.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

DEMO_DIR = Path(__file__).resolve().parent
KIT_ROOT = DEMO_DIR.parents[1]
RUNNER = KIT_ROOT / 'scripts' / 'weave.py'
SOURCE = DEMO_DIR / 'merge_sort.weave'
ENTRY = 'merge_sort'
MAX_VALUES = 1000
# Unindented text lines that are not claims, besides the runner's (weave_labels.NON_CLAIM_PREFIXES).
# Claims are 'LABEL statement' lines; tests/test_result_labels.py lints the output with these.
TEXT_PREFIXES = ('Input: ', 'Sorted: ', 'Mode: ', 'Work: ', 'Trace:')


def positive_int(text):
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError('must be a positive integer')
    return value


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description='Sort a JSON list of integers with the recursive fork/join merge sort written in Weave. '
                    'Concurrent mode uses a cooperative scheduler on one OS thread (not CPU parallelism).')
    parser.add_argument('--values', required=True, help="JSON list of integers, e.g. '[3,1,2]'")
    parser.add_argument('--mode', choices=('sequential', 'concurrent'), default='concurrent')
    parser.add_argument('--trace', action='store_true', help='show scheduler events from the actual run')
    parser.add_argument('--json', action='store_true', help='emit one JSON document on stdout')
    parser.add_argument('--max-values', type=positive_int, default=MAX_VALUES,
                        help=f'reject longer inputs (default {MAX_VALUES})')
    parser.add_argument('--schedule', choices=('fifo', 'lifo', 'random'), default='fifo')
    parser.add_argument('--seed', type=int, default=0)
    for name in ('workers', 'quantum', 'fuel', 'max-tasks', 'max-depth'):
        parser.add_argument('--' + name, type=positive_int, help='runner resource limit (default: runner default)')
    parser.add_argument('--source', type=Path, default=SOURCE, help='Weave source (default: merge_sort.weave)')
    return parser.parse_args(argv)


def parse_values(text, limit):
    try:
        values = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f'--values is not valid JSON: {error}') from None
    if not isinstance(values, list):
        raise ValueError('--values must be a JSON list of integers')
    for index, value in enumerate(values):
        if type(value) is not int:  # rejects bool, float, str, list, dict, null
            raise ValueError(f'--values[{index}] must be an integer, got {json.dumps(value)}')
    if len(values) > limit:
        raise ValueError(f'--values has {len(values)} items; the demo limit is {limit} (--max-values)')
    return values


def run(args, values):
    cmd = [sys.executable, '-B', str(RUNNER), '--json', 'run-pure', str(args.source), '--entry', ENTRY,
           '--args', json.dumps([values]), '--mode', args.mode, '--schedule', args.schedule, '--seed', str(args.seed)]
    for name in ('workers', 'quantum', 'fuel', 'max_tasks', 'max_depth'):
        if getattr(args, name) is not None:
            cmd += ['--' + name.replace('_', '-'), str(getattr(args, name))]
    if args.trace:
        cmd.append('--trace')
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        data = {'ok': False, 'diagnostic': {'code': 'RUNNER_OUTPUT', 'stage': 'demo', 'line': 0,
                                            'message': 'Runner did not return JSON. ' + proc.stderr.strip()}}
    return proc.returncode, data


def describe(event):
    fields = ' '.join(f'{k}={v}' for k, v in event.items() if k not in ('seq', 'event') and v is not None)
    return f"{event['seq']:>5} {event['event']:<18} {fields}"


def main(argv=None):
    args = parse_args(argv)
    try:
        values = parse_values(args.values, args.max_values)
    except ValueError as error:
        if args.json:
            print(json.dumps({'demo': 'merge_sort', 'ok': False,
                              'diagnostic': {'code': 'INPUT', 'stage': 'demo', 'message': str(error)}}))
        else:
            print(f'error: {error}', file=sys.stderr)
        return 2
    code, data = run(args, values)
    ok = code == 0 and data.get('ok') is True
    report = {'demo': 'merge_sort', 'ok': ok, 'source': str(args.source), 'entry': ENTRY,
              'input': values, 'runner_exit': code}
    if ok:
        # The runner's NOT ESTABLISHED claim for the pure program and the run's runtime status.
        report.update(output=data['result'], check=data['check'], runtime_status=data['runtime_status'],
                      execution=data['execution'], stats=data['stats'], scope=data['scope'])
        if args.trace:
            report['events'] = data['events']
    else:
        report['diagnostic'] = data.get('diagnostic', {'code': 'RUNNER_FAILED', 'message': 'no diagnostic'})
    if args.json:
        print(json.dumps(report))
    elif ok:
        stats, ex = report['stats'], report['execution']
        print(f"Input:  {json.dumps(values)}")
        print(f"Sorted: {json.dumps(report['output'])}")
        print(f"Mode:   {ex['mode']} ({ex['scheduler']}; schedule={ex['schedule']}, "
              f"workers={ex['limits']['workers']}, quantum={ex['limits']['quantum']})")
        print(f"Work:   {stats['steps']} instructions, {stats['tasks_created']} activations, "
              f"{stats['forks']} forks, {stats['joins']} joins, max live {stats['max_live_tasks']}, "
              f"max frames {stats['max_frames']}")
        print(f"{report['check']['claim_label']} for this pure fn program: no specified guarantee (kit extension "
              "outside F0); accepted by the kit's pure checker, termination not checked")
        print(f"runtime status: {report['runtime_status']} (executed by the Weave runner)")
        if args.trace:
            print('Trace:')
            for event in report['events']:
                print('  ' + describe(event))
    else:
        d = report['diagnostic']
        span = d.get('span') or {}
        loc = f"{span['file']}:{span['start']['line']}" if span else (f"{d.get('file')}:{d.get('line')}" if d.get('file') else '')
        print(f"error: {d.get('code')} [{d.get('stage')}] {loc}: {d.get('message')}", file=sys.stderr)
    if ok:
        return 0
    return code if code not in (0, None) else 1


if __name__ == '__main__':
    sys.exit(main())
