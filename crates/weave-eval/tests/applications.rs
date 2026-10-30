// SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
// SPDX-License-Identifier: MIT

//! Conformance applications (quaat/weave#11) in process: merge sort and its
//! stability on every short list, and the routing rule on a boundary grid and
//! on generated route lists. The oracles are written here, from the rules the
//! programs state; `specification/scripts/p0_applications.py` runs the same
//! programs through the `weave` command against Python oracles.

#![allow(clippy::unwrap_used, clippy::expect_used, clippy::panic)]

use std::path::Path;
use weave_eval::{DEFAULT_BUDGETS, Outcome, RunError, run};
use weave_syntax::json;

fn read(rel: &str) -> String {
    let path = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../specification/examples/pure");
    std::fs::read_to_string(path.join(rel)).unwrap_or_else(|e| panic!("{rel}: {e}"))
}

fn value(program: &weave_check::Program, entry: &str, args: &str) -> String {
    let r = run(program, entry, &json::parse(args).unwrap(), DEFAULT_BUDGETS)
        .unwrap_or_else(|e| panic!("{entry}{args}: {e:?}"));
    match &r.outcome {
        Outcome::Value(v) => weave_eval::value::to_json(v, program).to_json(),
        other => panic!("{entry}{args}: {other:?}"),
    }
}

/// Every list of length 0 to `max` over {0, 1, 2}.
fn short_lists(max: usize) -> Vec<Vec<i64>> {
    let mut all = vec![Vec::new()];
    let mut frontier = vec![Vec::new()];
    for _ in 0..max {
        frontier = frontier
            .iter()
            .flat_map(|xs: &Vec<i64>| {
                (0..3).map(move |v| {
                    let mut ys = xs.clone();
                    ys.push(v);
                    ys
                })
            })
            .collect();
        all.extend(frontier.iter().cloned());
    }
    all
}

fn ints(xs: &[i64]) -> String {
    let parts: Vec<String> = xs.iter().map(i64::to_string).collect();
    format!("[{}]", parts.join(","))
}

fn items(xs: &[(i64, i64)]) -> String {
    let parts: Vec<String> = xs
        .iter()
        .map(|(k, i)| format!("{{\"key\":{k},\"id\":{i}}}"))
        .collect();
    format!("[{}]", parts.join(","))
}

#[test]
fn merge_sort_sorts_every_short_list() {
    let program = weave_check::check(&read("valid/merge_sort.weave")).unwrap();
    let lists = short_lists(6);
    assert_eq!(lists.len(), 1093);
    for xs in &lists {
        let mut want = xs.clone();
        want.sort();
        assert_eq!(
            value(&program, "merge_sort", &format!("[{}]", ints(xs))),
            ints(&want),
            "{xs:?}"
        );
    }
}

#[test]
fn sort_items_is_stable_on_every_short_key_sequence() {
    let program = weave_check::check(&read("valid/merge_sort.weave")).unwrap();
    let mut with_equal_keys = 0;
    for keys in short_lists(6) {
        // Ids are positions, so the output ids show the order of equal keys.
        let input: Vec<(i64, i64)> = keys.iter().copied().zip(0..).collect();
        let mut want = input.clone();
        want.sort_by_key(|&(k, _)| k); // stable
        let mut distinct = keys.clone();
        distinct.sort();
        distinct.dedup();
        with_equal_keys += usize::from(distinct.len() < keys.len());
        assert_eq!(
            value(&program, "sort_items", &format!("[{}]", items(&input))),
            items(&want),
            "{keys:?}"
        );
    }
    assert!(with_equal_keys > 1000);
}

#[test]
fn an_unstable_merge_is_seen_on_the_ids() {
    let src = read("valid/merge_sort.weave").replacen("if x.key <= y.key:", "if x.key < y.key:", 1);
    let program = weave_check::check(&src).unwrap();
    let input = [(1, 0), (0, 1), (1, 2)];
    let got = value(&program, "sort_items", &format!("[{}]", items(&input)));
    assert_eq!(got, items(&[(0, 1), (1, 2), (1, 0)]));
    assert_ne!(got, items(&[(0, 1), (1, 0), (1, 2)]));
}

#[derive(Clone, Copy, Debug)]
struct Route {
    dest: i64,
    cost: i64,
    hops: i64,
}

/// The routing rule: valid when 0 <= cost <= limit and 1 <= hops <= 16; the
/// least cost wins, ties going to the lower destination; no valid route is
/// the rejection.
fn oracle(routes: &[Route], limit: i64) -> String {
    let best = routes
        .iter()
        .filter(|r| r.cost >= 0 && r.cost <= limit && (1..=16).contains(&r.hops))
        .min_by_key(|r| (r.cost, r.dest));
    match best {
        Some(r) => format!(
            "{{\"accepted\":true,\"dest\":{},\"cost\":{}}}",
            r.dest, r.cost
        ),
        None => "{\"accepted\":false,\"dest\":0,\"cost\":0}".into(),
    }
}

fn route_args(routes: &[Route], limit: i64) -> String {
    let parts: Vec<String> = routes
        .iter()
        .map(|r| {
            format!(
                "{{\"dest\":{},\"cost\":{},\"hops\":{}}}",
                r.dest, r.cost, r.hops
            )
        })
        .collect();
    format!("[[{}],{limit}]", parts.join(","))
}

#[test]
fn route_follows_the_rule_on_valid_and_invalid_records() {
    let program = weave_check::check(&read("valid/routing.weave")).unwrap();
    let mut cases: Vec<(Vec<Route>, i64)> = vec![(Vec::new(), 10)];
    for cost in [-1, 0, 1, 2, 3] {
        for hops in [-1, 0, 1, 16, 17] {
            for limit in [-1, 0, 2] {
                cases.push((
                    vec![Route {
                        dest: 1,
                        cost,
                        hops,
                    }],
                    limit,
                ));
            }
        }
    }
    // A small linear congruential generator: fixed, platform-independent inputs.
    let mut state: u64 = 20_261_111;
    let mut next = |n: i64| -> i64 {
        state = state
            .wrapping_mul(6_364_136_223_846_793_005)
            .wrapping_add(1_442_695_040_888_963_407);
        ((state >> 33) % n as u64) as i64
    };
    for _ in 0..300 {
        let limit = next(23) - 2;
        let len = next(12) as usize;
        let routes = (0..len)
            .map(|_| Route {
                dest: next(11) - 5,
                cost: next(29) - 3,
                hops: next(20) - 1,
            })
            .collect();
        cases.push((routes, limit));
    }
    let (mut accepted, mut rejected, mut invalid) = (0, 0, 0);
    for (routes, limit) in &cases {
        let want = oracle(routes, *limit);
        if want.contains("true") {
            accepted += 1;
        } else {
            rejected += 1;
        }
        invalid += routes
            .iter()
            .filter(|r| r.cost < 0 || r.cost > *limit || !(1..=16).contains(&r.hops))
            .count();
        assert_eq!(
            value(&program, "route", &route_args(routes, *limit)),
            want,
            "{routes:?} limit {limit}"
        );
    }
    assert!(accepted > 50 && rejected > 50 && invalid > 300);
}

#[test]
fn malformed_route_requests_are_invalid_run_requests() {
    let program = weave_check::check(&read("valid/routing.weave")).unwrap();
    for args in [
        "[[{\"dest\": 1, \"cost\": 2}], 10]",
        "[[{\"dest\": 1, \"cost\": 2, \"hops\": 1, \"via\": 3}], 10]",
        "[[{\"dest\": 1, \"cost\": \"2\", \"hops\": 1}], 10]",
        "[[{\"dest\": 1, \"cost\": 2, \"hops\": true}], 10]",
        "[[], \"10\"]",
        "[[]]",
    ] {
        match run(
            &program,
            "route",
            &json::parse(args).unwrap(),
            DEFAULT_BUDGETS,
        ) {
            Err(RunError::Request(d)) => assert_eq!(d.code, "E540", "{args}"),
            other => panic!("{args}: {other:?}"),
        }
    }
    assert_eq!(
        value(
            &program,
            "route",
            "[[{\"dest\": 1, \"cost\": 2, \"hops\": 1}], 10]"
        ),
        "{\"accepted\":true,\"dest\":1,\"cost\":2}"
    );
}
