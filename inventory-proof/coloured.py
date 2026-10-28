#!/usr/bin/env python3
"""Restricted coloured nets: symbolic invariant families and finite unfolding.

Two positional colour sorts (tenant, order), variable-only inscriptions, no
arbitrary ML expressions. The old parser validates the explicitly erased view;
proofs and execution below retain every inscription.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import re
from collections import Counter, deque
from dataclasses import dataclass
from pathlib import Path

from checker import CheckError, Net, check_flow, leaf, linear_expression, parse_net, prove, tree


@dataclass
class ColouredNet:
    source: str
    base: Net
    places: dict[str, tuple[str, ...]]
    bindings: dict[str, tuple[str, ...]]
    arcs: dict[str, dict[str, dict[str, tuple[str, ...]]]]
    families: dict[str, tuple[str, tuple[str, ...], int]]
    orders: int
    correlation_property: str


def keys(text):
    return tuple(x.strip() for x in text.split(',')) if text else ()


def parse_coloured(source: str) -> ColouredNet:
    roots = tree(source)
    if len(roots) != 1:
        raise CheckError('E400', 'Expected one coloured net.')
    places, bindings, arcs, families = {}, {}, {}, {}
    projection = [roots[0].text]
    order_count, correlation = None, None
    for node in roots[0].children:
        text = node.text
        if m := re.fullmatch(r'place (\w+)(?:\[([\w, ]+)\])?( = .+)', text):
            leaf(node)
            if m[1] in places:
                raise CheckError('E400', 'Duplicate coloured place.', node.line)
            places[m[1]] = keys(m[2])
            if places[m[1]] and (len(places[m[1]]) != 2 or len(set(places[m[1]])) != 2):
                raise CheckError('E400', 'Places use two distinct tenant/order indices.', node.line)
            projection.append('    place ' + m[1] + m[3])
        elif m := re.fullmatch(r'transition (\w+)\[([\w, ]+)\]:', text):
            name, primary = m[1], keys(m[2])
            if name in bindings or len(primary) != 2 or len(set(primary)) != 2:
                raise CheckError('E400', 'Transition needs unique name and tenant/order binding.', node.line)
            bindings[name], arcs[name] = primary, {'take': {}, 'put': {}, 'read': {}}
            projection.append(f'    transition {name}:')
            for child in node.children:
                leaf(child)
                if a := re.fullmatch(r'(take|put|read) ([1-9]\d*) (\w+)(?:\[([\w, ]+)\])?', child.text):
                    if a[3] in arcs[name][a[1]]:
                        raise CheckError('E400', 'Duplicate arc.', child.line)
                    arcs[name][a[1]][a[3]] = keys(a[4])
                    projection.append(f'        {a[1]} {a[2]} {a[3]}')
                else:
                    projection.append('        ' + child.text)
        elif m := re.fullmatch(r'invariant (\w+)\[([\w, ]+)\]:', text):
            if len(node.children) != 1 or m[1] in families:
                raise CheckError('E400', 'Invalid or duplicate invariant family.', node.line)
            leaf(node.children[0])
            families[m[1]] = (node.children[0].text, keys(m[2]), node.line)
        elif m := re.fullmatch(r'check (\w+) for orders ([1-9]\d*):', text):
            if order_count is not None:
                raise CheckError('E400', 'Duplicate exploration declaration.', node.line)
            order_count = int(m[2])
            projection.append(f'    check {m[1]} for one_order:')
            for child in node.children:
                leaf(child)
                if p := re.fullmatch(r'property (\w+): tokens match firing', child.text):
                    if correlation:
                        raise CheckError('E400', 'Duplicate token correlation property.', child.line)
                    correlation = p[1]
                else:
                    projection.append('        ' + child.text)
        else:
            for child in node.children:
                leaf(child)
            projection.append('    ' + text)
            projection.extend('        ' + child.text for child in node.children)
    base = parse_net('\n'.join(projection) + '\n')
    for node in roots[0].children:
        if m := re.fullmatch(r'transition (\w+)\[([\w, ]+)\]:', node.text):
            base.transitions[m[1]].line = node.line
    if order_count is None or correlation is None or not families:
        raise CheckError('E400', 'Coloured source needs a bound, token correlation property, and invariant families.')
    if set(bindings) != set(base.transitions):
        raise CheckError('E400', 'Every transition requires an explicit firing colour.')
    if set(families) & base.invariants.keys():
        raise CheckError('E400', 'Aggregate and family invariant names must be distinct.')
    for name, primary in bindings.items():
        sorts = {symbol: i for i, symbol in enumerate(primary)}
        for kind, inscriptions in arcs[name].items():
            for place, inscription in inscriptions.items():
                if len(inscription) != len(places[place]):
                    raise CheckError('E400', f'{name}: missing or wrong colour arity on {kind} {place}.')
                for i, variable in enumerate(inscription):
                    if variable in sorts and sorts[variable] != i:
                        raise CheckError('E400', f'{name}: colour variable {variable} mixes tenant and order sorts.')
                    sorts[variable] = i
    return ColouredNet(source, base, places, bindings, arcs, families, order_count, correlation)


def prove_colours(net: ColouredNet) -> dict:
    aggregate = prove(net.base)
    # Erased counts are valid aggregate initial values only when initially
    # nonzero coloured places have zero weight (otherwise cardinality matters).
    for invariant in aggregate['invariants']:
        for place, weight in zip(aggregate['places'], invariant['weights']):
            if net.places[place] and weight and net.base.places[place].initial != '0':
                raise CheckError('E411', 'Aggregate initial marking depends on colour cardinality; use an invariant family.')
    results = []
    for name, (expression, binder, line) in net.families.items():
        if len(binder) != 2 or len(set(binder)) != 2:
            raise CheckError('E411', 'Invariant families require two distinct indices.', line)
        def erase(m):
            if keys(m[2]) != binder or not net.places.get(m[1]):
                raise CheckError('E411', 'Family terms must use the declared colour on indexed places.', line)
            return m[1]
        erased = re.sub(r'(\w+)\[([\w, ]+)\]', erase, expression)
        bare = re.sub(r'(\w+)\[([\w, ]+)\]', '0', expression).split('==')[0]
        if linear_expression(bare)[0]:
            raise CheckError('E411', 'Unindexed terms cannot occur in a per-colour invariant.', line)
        parts = erased.split('==')
        if len(parts) != 2:
            raise CheckError('E411', 'Family requires an equality.', line)
        lhs, lc = linear_expression(parts[0]); rhs, rc = linear_expression(parts[1])
        # Reject bare place terms: their meaning would be a sum, not a colour.
        occurrences = set(re.findall(r'(\w+)\[', expression))
        if rhs or not lhs or set(lhs) - occurrences or set(lhs) - net.places.keys():
            raise CheckError('E411', 'Family left terms must be indexed places; right side must be constant.', line)
        initial = 0
        for p, w in lhs.items():
            value = net.base.places[p].initial
            if not value.isdigit():
                raise CheckError('E411', 'Family initial values must be constant per colour.', line)
            initial += w * int(value)
        if initial + lc != rc:
            raise CheckError('E411', f'{name}: per-colour initial marking fails.', line)
        columns = {}
        for t in net.base.transitions.values():
            residual = Counter()
            for kind, sign in [('take', -1), ('put', 1)]:
                for p, n in getattr(t, kind).items():
                    residual[net.arcs[t.name][kind][p]] += sign * n * lhs.get(p, 0)
            residual = {str(k): v for k, v in residual.items() if v}
            if residual:
                raise CheckError('E412', f'{name} is NOT PROVED for every colour: {t.name} has symbolic colour residual {residual}.', t.line)
            columns[t.name] = residual
        results.append({'name': name, 'status': 'PROVED', 'expression': expression,
                        'initial_per_colour': initial, 'target': rc-lc,
                        'weights': lhs, 'symbolic_columns': columns})
    return {'format': 'weave-colour-invariant-v1', 'source_sha256': hashlib.sha256(net.source.encode()).hexdigest(),
            'aggregate': aggregate['invariants'], 'families': results,
            'transition_inscriptions': net.arcs, 'finite_unfolding': Unfolding(net).matrix(),
            'scope': 'All colours and variable bindings in this inscription fragment; guard-independent accounting only.'}


@dataclass
class Mode:
    transition: str
    colour: tuple[str, str]
    binding: dict[str, str]
    take: dict[int, int]
    put: dict[int, int]
    read: dict[int, int]

    def label(self):
        return self.transition + '[' + ','.join(f'{k}={v}' for k, v in self.binding.items()) + ']'


class Unfolding:
    def __init__(self, net: ColouredNet, colours=None, stock=None):
        self.net = net
        self.colours = tuple(colours or [('tenant', f'order{i+1}') for i in range(net.orders)])
        if len(set(self.colours)) != len(self.colours) or any(len(c) != 2 for c in self.colours):
            raise ValueError('Colours must be unique tenant/order pairs')
        self.stock = len(self.colours) if stock is None else stock
        self.rows = [(p, c) for p in net.base.places for c in (self.colours if net.places[p] else (None,))]
        self.index = {row: i for i, row in enumerate(self.rows)}
        self.initial = tuple(self.stock if net.base.places[p].initial == net.base.parameter else int(net.base.places[p].initial)
                             for p, _ in self.rows)
        self.modes = []
        domains = [sorted({c[i] for c in self.colours}) for i in (0, 1)]
        for t in net.base.transitions.values():
            sorts = {s: i for i, s in enumerate(net.bindings[t.name])}
            for inscriptions in net.arcs[t.name].values():
                for inscription in inscriptions.values():
                    sorts.update({s: i for i, s in enumerate(inscription)})
            symbols = list(sorts)
            for values in itertools.product(*(domains[sorts[s]] for s in symbols)):
                binding = dict(zip(symbols, values))
                colour = tuple(binding[s] for s in net.bindings[t.name])
                if colour not in self.colours:
                    continue
                mapped = {}
                valid = True
                for kind in ('take', 'put', 'read'):
                    mapped[kind] = {}
                    for p, count in getattr(t, kind).items():
                        inscription = net.arcs[t.name][kind][p]
                        c = tuple(binding[s] for s in inscription) if inscription else None
                        if (p, c) not in self.index:
                            valid = False
                            break
                        mapped[kind][self.index[p, c]] = count
                if valid:
                    self.modes.append(Mode(t.name, colour, binding, **mapped))

    def enabled(self, marking, mode):
        return all(marking[i] >= n for arcs in (mode.take, mode.read) for i, n in arcs.items())

    def fire(self, marking, mode):
        if not self.enabled(marking, mode):
            raise CheckError('E421', f'Disabled coloured firing: {mode.label()}')
        result = list(marking)
        for i, n in mode.take.items(): result[i] -= n
        for i, n in mode.put.items(): result[i] += n
        return tuple(result)

    def select(self, name, colour):
        found = [m for m in self.modes if m.transition == name and m.colour == colour]
        if len(found) != 1:
            raise CheckError('E421', 'Execution requires one unambiguous colour binding.')
        return found[0]

    def snapshot(self, marking):
        return {p + (f'[{c[0]},{c[1]}]' if c else ''): marking[i]
                for i, (p, c) in enumerate(self.rows) if marking[i]}

    def matrix(self):
        return {'rows': [p + (f'[{c[0]},{c[1]}]' if c else '') for p, c in self.rows],
                'columns': [m.label() for m in self.modes], 'initial': self.initial,
                'incidence': [[m.put.get(i, 0)-m.take.get(i, 0) for m in self.modes]
                              for i in range(len(self.rows))]}


def explore_colours(net, max_states=100000, colours=None):
    if max_states < 1:
        raise CheckError('E422', 'NOT ESTABLISHED: state budget must be positive.')
    unfolding = Unfolding(net, colours)
    model = net.base.order_check
    start = (unfolding.initial, (0,) * len(unfolding.colours))
    parents, pending = {start: None}, deque([start])
    triggers = dict.fromkeys(model.properties, 0)
    edges, used = 0, set()

    def path(state, mode):
        trace = [mode.label()]
        while parents[state] is not None:
            state, before = parents[state]
            trace.append(before)
        return ' -> '.join(reversed(trace))

    def fail(name, state, mode, detail):
        raise CheckError('E420', f'VIOLATED {name} with orders={len(unfolding.colours)}.\nTrace: {path(state, mode)}\n{detail}', net.base.transitions[mode.transition].line)

    for i, (p, c) in enumerate(unfolding.rows):
        if c is not None and unfolding.initial[i] > model.bound:
            raise CheckError('E422', 'NOT ESTABLISHED: initial token bound exceeded.')
    for colour in unfolding.colours:
        for name, (kind, place, requirement) in model.properties.items():
            if (place, colour) not in unfolding.index:
                raise CheckError('E400', f'Per-order property must refer to indexed place {place}.')
            present = unfolding.initial[unfolding.index[place, colour]] > 0
            if kind != 'requires' or not present: continue
            valid = requirement.startswith('marked ') and unfolding.initial[unfolding.index[requirement.removeprefix('marked '), colour]] > 0
            if not valid:
                raise CheckError('E420', f'VIOLATED {name} for {colour} in the initial marking.')

    while pending:
        state = pending.popleft(); marking, flags = state
        for ci, colour in enumerate(unfolding.colours):
            for name, (kind, place, requirement) in model.properties.items():
                if (place, colour) not in unfolding.index:
                    raise CheckError('E400', f'Per-order property must refer to indexed place {place}.')
                present = marking[unfolding.index[place, colour]] > 0
                premise = bool(flags[ci] & 4) if kind == 'forbid' else present
                if kind == 'after_dispatch': premise = bool(flags[ci] & 2) and present
                triggers[name] += int(premise)
        for mode in unfolding.modes:
            if not unfolding.enabled(marking, mode): continue
            for kind in ('take', 'read', 'put'):
                for row in getattr(mode, kind):
                    p, c = unfolding.rows[row]
                    if c is not None and c != mode.colour:
                        fail(net.correlation_property, state, mode,
                             f'{kind} {p}[{",".join(c)}] belongs to another order; firing belongs to {mode.colour}.')
            ci = unfolding.colours.index(mode.colour)
            if mode.transition == model.admission and flags[ci] & 1:
                fail('unique_admission', state, mode, 'A second reservation for the same identity is enabled.')
            after = unfolding.fire(marking, mode)
            updated = list(flags)
            if mode.transition == model.admission: updated[ci] |= 1
            if mode.transition == model.dispatch: updated[ci] |= 2
            guard_classes = {model.guards[g] for g in net.base.transitions[mode.transition].guards}
            if 'establishes_paid' in guard_classes: updated[ci] |= 4
            if 'establishes_rejected' in guard_classes: updated[ci] |= 8
            for cj, colour in enumerate(unfolding.colours):
                for name, (kind, place, requirement) in model.properties.items():
                    present = after[unfolding.index[place, colour]] > 0
                    premise = bool(updated[cj] & 4) if kind == 'forbid' else present
                    if kind == 'after_dispatch': premise = bool(updated[cj] & 2) and present
                    if kind == 'forbid': valid = not present
                    elif requirement == 'paid_evidence': valid = bool(updated[cj] & 4)
                    elif requirement == 'rejected_evidence': valid = bool(updated[cj] & 8)
                    else: valid = after[unfolding.index[requirement.removeprefix('marked '), colour]] > 0
                    if premise and not valid:
                        fail(name, state, mode, f'Order {colour}: {unfolding.snapshot(after)}')
            for i, (p, c) in enumerate(unfolding.rows):
                # Shared places retain their initial capacity; stock and pool
                # are separate resources and can have different capacities.
                limit = model.bound if c else max(unfolding.stock, unfolding.initial[i])
                if after[i] > limit:
                    raise CheckError('E422', f'NOT ESTABLISHED: token bound exceeded at {p}, {c}.')
            next_state = (after, tuple(updated)); edges += 1; used.add(mode.transition)
            if next_state not in parents:
                if len(parents) >= max_states:
                    raise CheckError('E422', 'NOT ESTABLISHED: coloured state budget exhausted.')
                parents[next_state] = (state, mode.label()); pending.append(next_state)
    return {'format': 'weave-colour-exploration-v1', 'source_sha256': hashlib.sha256(net.source.encode()).hexdigest(),
            'orders': len(unfolding.colours), 'colours': unfolding.colours, 'stock': unfolding.stock,
            'states': len(parents), 'edges': edges, 'complete': True, 'max_states': max_states,
            'token_bound_per_colour': model.bound, 'unreached_transitions': sorted(net.base.transitions.keys()-used),
            'properties': list(model.properties) + [net.correlation_property, 'unique_admission'],
            'premise_states': triggers,
            'scope': 'Exhaustive at the stated colours, stock, and bounds; no arbitrary-order cutoff theorem.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prove', 'explore', 'analyze', 'check'])
    parser.add_argument('source', type=Path)
    parser.add_argument('program', type=Path, nargs='?')
    args = parser.parse_args()
    try:
        net = parse_coloured(args.source.read_text())
        proof = prove_colours(net) if args.command != 'explore' else None
        result = explore_colours(net) if args.command != 'prove' else None
        checked = []
        if args.command == 'check':
            if args.program is None: parser.error('check requires a flow source')
            checked = check_flow(net.base, args.program.read_text())
        if proof:
            for item in proof['aggregate']: print('PROVED aggregate ' + item['name'])
            for item in proof['families']: print('PROVED per-colour ' + item['name'])
        if result:
            print(f"CHECKED WITHIN BOUNDS orders={result['orders']}, states={result['states']}, edges={result['edges']}")
            print('Properties: ' + ', '.join(result['properties']))
        for name in checked: print(f'CHECKED flow {name} against coloured protocol API')
        print(f'NOT ESTABLISHED orders>{net.orders} exploration, arbitrary-order ordering, provider truthfulness/consistency, or distributed runtime refinement.')
    except CheckError as e:
        print(e.render(str(args.source)))
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
