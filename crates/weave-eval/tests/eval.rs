// SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
// SPDX-License-Identifier: MIT

//! Dynamic semantics of P0 (`pure.rst`): values, evaluation order, faults,
//! budgets, the P0 corpus, and behaviour that follows the source.

#![allow(clippy::unwrap_used, clippy::expect_used, clippy::panic)]

use std::path::{Path, PathBuf};
use weave_eval::{
    BigInt, Budgets, DEFAULT_BUDGETS, Exhaustion, Fault, Outcome, Run, RunError, Usage,
    budgets_json, outcome_diagnostic, run,
};
use weave_syntax::json::{self, Value as Json};

fn examples() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("../../specification/examples")
}

fn read(rel: &str) -> String {
    std::fs::read_to_string(examples().join(rel)).unwrap_or_else(|e| panic!("{rel}: {e}"))
}

fn go(src: &str, entry: &str, args: &str, budgets: Budgets) -> Run {
    let program = weave_check::check(src).unwrap_or_else(|d| panic!("{} {}", d.code, d.message));
    match run(&program, entry, &json::parse(args).unwrap(), budgets) {
        Ok(r) => r,
        Err(e) => panic!("{e:?}"),
    }
}

fn value(src: &str, entry: &str, args: &str) -> String {
    let program = weave_check::check(src).unwrap();
    let r = run(
        &program,
        entry,
        &json::parse(args).unwrap(),
        DEFAULT_BUDGETS,
    )
    .unwrap();
    match &r.outcome {
        Outcome::Value(v) => weave_eval::value::to_json(v, &program).to_json(),
        other => panic!("{other:?}"),
    }
}

/// (kind name, code, rule, spanned text) of a fault or exhaustion.
fn stopped(
    src: &str,
    entry: &str,
    args: &str,
    budgets: Budgets,
) -> (String, String, String, String) {
    let r = go(src, entry, args, budgets);
    let d = outcome_diagnostic(&r).unwrap_or_else(|| panic!("value: {:?}", r.outcome));
    let kind = match r.outcome {
        Outcome::Fault(f, _) => f.name(),
        Outcome::Exhausted(x, _) => x.name(),
        Outcome::Value(_) => unreachable!(),
    };
    let text = src.get(d.span.start..d.span.end).unwrap().to_string();
    (kind.into(), d.code.into(), d.rule().unwrap(), text)
}

fn budgets(fuel: u64, depth: u64, int_bits: u64) -> Budgets {
    Budgets {
        fuel,
        depth,
        int_bits,
    }
}

const ARITH: &str = "fn q(a: Int, d: Int) -> Int:\n    return div(a, d)\n\nfn r(a: Int, d: Int) -> Int:\n    return mod(a, d)\n";

#[test]
fn euclidean_division_for_every_sign() {
    for a in -9i64..=9 {
        for d in [-4i64, -3, -1, 1, 2, 5] {
            let r = a.rem_euclid(d);
            let q = (a - r) / d;
            assert_eq!(a, d * q + r);
            let args = format!("[{a}, {d}]");
            assert_eq!(value(ARITH, "q", &args), q.to_string(), "div({a}, {d})");
            assert_eq!(value(ARITH, "r", &args), r.to_string(), "mod({a}, {d})");
        }
        for f in ["q", "r"] {
            let (kind, code, rule, text) = stopped(ARITH, f, &format!("[{a}, 0]"), DEFAULT_BUDGETS);
            assert_eq!(kind, "division-by-zero");
            assert_eq!((code.as_str(), rule.as_str()), ("E520", "P0-ARITH-2"));
            assert!(text.starts_with(if f == "q" { "div(" } else { "mod(" }));
        }
    }
    // Arguments far beyond 64 bits.
    let big = "-340282366920938463463374607431768211457";
    assert_eq!(
        value(ARITH, "q", &format!("[{big}, 7]")),
        "-48611766702991209066196372490252601637"
    );
    assert_eq!(value(ARITH, "r", &format!("[{big}, 7]")), "2");
}

#[test]
fn empty_list_faults_have_their_span() {
    let src = "fn h(xs: List[Int]) -> Int:\n    return 1 + head(xs)\n\nfn t(xs: List[Int]) -> List[Int]:\n    return tail(tail(xs))\n";
    let (kind, code, rule, text) = stopped(src, "h", "[[]]", DEFAULT_BUDGETS);
    assert_eq!(
        (kind.as_str(), code.as_str(), rule.as_str(), text.as_str()),
        ("empty-list", "E521", "P0-LIST-1", "head(xs)")
    );
    let (_, _, _, text) = stopped(src, "t", "[[1]]", DEFAULT_BUDGETS);
    assert_eq!(text, "tail(tail(xs))");
    assert_eq!(value(src, "t", "[[1, 2, 3]]"), "[3]");
}

#[test]
fn evaluation_is_left_to_right_and_the_first_fault_wins() {
    let src = "record R:\n    a: Int\n    b: Int\n\nfn ab(xs: List[Int]) -> Int:\n    return div(1, 0) + head(xs)\n\nfn ba(xs: List[Int]) -> Int:\n    return head(xs) + div(1, 0)\n\nfn rec(xs: List[Int]) -> R:\n    return R(b: head(xs), a: div(1, 0))\n\nfn lst(xs: List[Int]) -> List[Int]:\n    return [div(1, 0), head(xs)]\n\nfn args(xs: List[Int]) -> Int:\n    return two(head(xs), div(1, 0))\n\nfn two(a: Int, b: Int) -> Int:\n    return a\n";
    let kind = |f: &str| stopped(src, f, "[[]]", DEFAULT_BUDGETS).0;
    assert_eq!(kind("ab"), "division-by-zero");
    assert_eq!(kind("ba"), "empty-list");
    // Record fields run in written order, not declaration order.
    assert_eq!(kind("rec"), "empty-list");
    assert_eq!(kind("lst"), "division-by-zero");
    assert_eq!(kind("args"), "empty-list");
}

#[test]
fn short_circuit_skips_faults_and_calls() {
    let src = read("pure/valid/short_circuit.weave");
    assert_eq!(value(&src, "safe_ratio_above", "[0, 1]"), "false");
    assert_eq!(value(&src, "zero_or_divides", "[0]"), "true");
    assert_eq!(value(&src, "guarded_head", "[[]]"), "true");
    let skipped = go(&src, "skips_calls", "[true, 100000]", DEFAULT_BUDGETS);
    assert_eq!(skipped.usage.fuel, 1);
    let taken = go(&src, "skips_calls", "[false, 10]", DEFAULT_BUDGETS);
    assert_eq!((taken.usage.fuel, taken.usage.depth), (12, 12));
}

#[test]
fn a_non_terminating_function_fails_cleanly_at_its_fuel_budget() {
    // AC-1: the run stops at its budget with a diagnostic, code, rule and span.
    let src = read("pure/valid/budgets.weave");
    for fuel in [0, 1, 1000, 100_000] {
        let r = go(&src, "spin", "[0]", budgets(fuel, u64::MAX, 64));
        assert!(matches!(r.outcome, Outcome::Exhausted(Exhaustion::Fuel, _)));
        assert_eq!(r.usage.fuel, fuel);
        let d = outcome_diagnostic(&r).unwrap();
        assert_eq!((d.code, d.rule().as_deref()), ("E530", Some("P0-BUDGET-2")));
        let text = src.get(d.span.start..d.span.end).unwrap();
        assert_eq!(text, if fuel == 0 { "spin" } else { "spin(n + 1)" });
        assert!(d.message.contains("not a termination proof"));
    }
    // Without enough depth, the same function stops at its depth budget instead.
    let r = go(&src, "spin", "[0]", budgets(1_000_000, 500, 64));
    assert!(matches!(
        r.outcome,
        Outcome::Exhausted(Exhaustion::Depth, _)
    ));
    assert_eq!((r.usage.fuel, r.usage.depth), (501, 500));
}

#[test]
fn fuel_is_taken_before_depth_and_counts_calls_exactly() {
    let src = read("pure/valid/budgets.weave");
    // depth(n) makes n + 1 calls.
    let ok = go(&src, "depth", "[9]", budgets(10, 10, 64));
    assert!(matches!(ok.outcome, Outcome::Value(_)));
    assert_eq!(
        ok.usage,
        Usage {
            fuel: 10,
            depth: 10,
            int_bits: 4
        }
    );
    let short = go(&src, "depth", "[9]", budgets(9, 10, 64));
    assert!(matches!(
        short.outcome,
        Outcome::Exhausted(Exhaustion::Fuel, _)
    ));
    // Both budgets short at the entry call: fuel is checked first.
    let both = go(&src, "identity", "[1]", budgets(0, 0, 64));
    assert!(matches!(
        both.outcome,
        Outcome::Exhausted(Exhaustion::Fuel, _)
    ));
    let depth0 = go(&src, "identity", "[1]", budgets(1, 0, 64));
    assert!(matches!(
        depth0.outcome,
        Outcome::Exhausted(Exhaustion::Depth, _)
    ));
    assert_eq!(depth0.usage.fuel, 1);
}

#[test]
fn deep_recursion_within_the_depth_budget_uses_no_host_stack() {
    // Run on a small thread stack: each Weave call is a heap frame.
    let handle = std::thread::Builder::new()
        .stack_size(256 << 10)
        .spawn(|| {
            let src = read("pure/valid/budgets.weave");
            let program = weave_check::check(&src).unwrap();
            run(
                &program,
                "depth",
                &json::parse("[300000]").unwrap(),
                budgets(1_000_000, 400_000, 64),
            )
            .map(|r| (r.usage.depth, matches!(r.outcome, Outcome::Value(_))))
        })
        .unwrap();
    assert_eq!(handle.join().unwrap(), Ok((300_001, true)));
}

#[test]
fn integer_size_budget_covers_literals_arguments_and_intermediates() {
    let src = "fn lit() -> Int:\n    return 1000\n\nfn id(x: Int) -> Int:\n    return x\n\nfn sq(x: Int) -> Int:\n    return x * x\n\nfn neg(x: Int) -> Int:\n    return -x\n\nfn len(xs: List[Int]) -> Int:\n    return length(xs)\n\nfn zero() -> Int:\n    return 0 * 0\n";
    let b = |bits| budgets(100, 100, bits);
    let (kind, code, rule, text) = stopped(src, "lit", "[]", b(9));
    assert_eq!(
        (kind.as_str(), code.as_str(), rule.as_str(), text.as_str()),
        ("int-size", "E532", "P0-BUDGET-4", "1000")
    );
    assert_eq!(value(src, "lit", "[]"), "1000");
    let r = go(src, "id", "[1024]", b(10));
    assert!(matches!(
        r.outcome,
        Outcome::Exhausted(Exhaustion::IntSize, _)
    ));
    assert_eq!(
        r.usage,
        Usage::default(),
        "nothing runs before the arguments fit"
    );
    assert_eq!(stopped(src, "id", "[1024]", b(10)).3, "id");
    assert_eq!(stopped(src, "sq", "[65536]", b(32)).3, "x * x");
    assert!(matches!(
        go(src, "sq", "[65535]", b(32)).outcome,
        Outcome::Value(_)
    ));
    // -(2^k) needs k + 1 bits, like 2^k.
    assert!(matches!(
        go(src, "neg", "[-512]", b(10)).outcome,
        Outcome::Value(_)
    ));
    assert_eq!(stopped(src, "neg", "[-1024]", b(10)).0, "int-size");
    assert_eq!(stopped(src, "len", "[[1, 1, 1, 1]]", b(2)).3, "length(xs)");
    assert!(matches!(
        go(src, "zero", "[]", b(0)).outcome,
        Outcome::Value(_)
    ));
    // A huge argument is rejected at once, without computing with it.
    let huge = format!("[{}]", "9".repeat(20_000));
    let r = go(src, "sq", &huge, DEFAULT_BUDGETS);
    assert!(matches!(
        r.outcome,
        Outcome::Exhausted(Exhaustion::IntSize, _)
    ));
    // Within a large budget the same arithmetic is exact.
    let r = go(src, "sq", &huge, budgets(10, 10, 200_000));
    let Outcome::Value(weave_eval::Value::Int(n)) = r.outcome else {
        panic!("{:?}", r.outcome)
    };
    let x = BigInt::parse(&"9".repeat(20_000)).unwrap();
    assert_eq!(n, x.mul(&x));
    assert_eq!(r.usage.int_bits, n.bits());
}

#[test]
fn long_lists_are_persistent_and_cheap() {
    let src = "fn size(xs: List[Int]) -> Int:\n    return length(xs) + head(xs) + head(tail(xs))\n\nfn build(n: Int, acc: List[Int]) -> List[Int]:\n    if n == 0:\n        return acc\n    else:\n        return build(n - 1, cons(n, acc))\n\nfn last(xs: List[Int]) -> Int:\n    if is_empty(tail(xs)):\n        return head(xs)\n    else:\n        return last(tail(xs))\n";
    let items: Vec<String> = (0..1_000_000).map(|i| i.to_string()).collect();
    let args = format!("[[{}]]", items.join(","));
    assert_eq!(value(src, "size", &args), "1000001");
    let built = go(src, "build", "[200000, []]", budgets(300_000, 300_000, 64));
    let Outcome::Value(weave_eval::Value::List(list)) = &built.outcome else {
        panic!("{:?}", built.outcome)
    };
    assert_eq!(list.len(), 200_000);
    let r = go(src, "last", &args, budgets(2_000_000, 2_000_000, 64));
    assert!(matches!(r.outcome, Outcome::Value(_)));
    assert_eq!(r.usage.depth, 1_000_000);
}

#[test]
fn run_requests_are_validated() {
    let src =
        "record R:\n    a: Int\n\nfn f(r: R, b: Bool, xs: List[Int]) -> Int:\n    return r.a\n";
    let program = weave_check::check(src).unwrap();
    let bad = |args: &str| match run(&program, "f", &json::parse(args).unwrap(), DEFAULT_BUDGETS) {
        Err(RunError::Request(d)) => {
            assert_eq!((d.code, d.rule().as_deref()), ("E540", Some("P0-RUN-1")));
            d.message
        }
        other => panic!("{args}: {other:?}"),
    };
    bad("[]");
    bad("{}");
    bad("[{\"a\": 1}, true]");
    bad("[{\"a\": 1.0}, true, []]");
    bad("[{\"a\": 1e3}, true, []]");
    bad("[{\"a\": 1}, 1, []]");
    bad("[{\"a\": true}, true, []]");
    bad("[{\"a\": 1, \"b\": 2}, true, []]");
    bad("[{\"a\": 1, \"a\": 2}, true, []]");
    bad("[{}, true, []]");
    bad("[{\"a\": 1}, true, [1, true]]");
    bad("[{\"a\": 1}, true, null]");
    assert!(matches!(
        run(&program, "g", &json::parse("[]").unwrap(), DEFAULT_BUDGETS),
        Err(RunError::Request(_))
    ));
    let ok = run(
        &program,
        "f",
        &json::parse("[{\"a\": -0}, false, []]").unwrap(),
        DEFAULT_BUDGETS,
    )
    .unwrap();
    assert!(matches!(ok.outcome, Outcome::Value(_)));
    let report = budgets_json(&ok).to_json();
    assert!(
        report.contains("\"fuel\":{\"limit\":\"1000000\"")
            || report.contains("\"fuel\":{\"limit\":1000000")
    );
}

// ------------------------------------------------------------------ the P0 corpus

#[test]
fn the_p0_corpus_meets_its_manifest() {
    let manifest = json::parse(&read("pure/manifest.json")).unwrap();
    assert_eq!(
        manifest.get("format").and_then(Json::as_str),
        Some("weave-p0-conformance-v1")
    );
    let mut runs = 0;
    for case in manifest.get("cases").and_then(Json::as_array).unwrap() {
        let s = |k: &str| {
            case.get(k)
                .and_then(Json::as_str)
                .unwrap_or_default()
                .to_string()
        };
        let (id, file, expect) = (s("id"), s("file"), s("expect"));
        let source = read(&file);
        let checked = weave_check::check(&source);
        if s("kind") == "check" {
            let got = match &checked {
                Ok(_) => "ACCEPT",
                Err(d) => d.code,
            };
            assert_eq!(got, expect, "{id} {file}");
            continue;
        }
        runs += 1;
        let program = checked.unwrap_or_else(|d| panic!("{id}: {} {}", d.code, d.message));
        let mut b = DEFAULT_BUDGETS;
        if let Some(given) = case.get("budgets") {
            let n = |k: &str| given.get(k).map(|v| v.to_json().parse::<u64>().unwrap());
            b.fuel = n("fuel").unwrap_or(b.fuel);
            b.depth = n("depth").unwrap_or(b.depth);
            b.int_bits = n("int_bits").unwrap_or(b.int_bits);
        }
        let args = case.get("args").unwrap();
        let result = run(&program, &s("entry"), args, b);
        let r = match (result, expect.as_str()) {
            (Err(RunError::Request(d)), "E540") => {
                assert_eq!(d.code, "E540");
                continue;
            }
            (Ok(r), _) => r,
            (other, _) => panic!("{id}: {other:?}"),
        };
        match (&r.outcome, expect.as_str()) {
            (Outcome::Value(v), "VALUE") => {
                let got = weave_eval::value::to_json(v, &program);
                assert_eq!(
                    json::parse(&got.to_json()).unwrap(),
                    case.get("value").cloned().unwrap(),
                    "{id}"
                );
            }
            (Outcome::Fault(f, _), code) => assert_eq!(f.code(), code, "{id}"),
            (Outcome::Exhausted(x, _), code) => assert_eq!(x.code(), code, "{id}"),
            (other, code) => panic!("{id}: {other:?}, expected {code}"),
        }
        if let Some(usage) = case.get("usage") {
            let n = |k: &str| usage.get(k).unwrap().to_json().parse::<u64>().unwrap();
            assert_eq!(
                r.usage,
                Usage {
                    fuel: n("fuel"),
                    depth: n("depth"),
                    int_bits: n("int_bits")
                },
                "{id}"
            );
        }
    }
    assert!(runs >= 40);
}

// ------------------------------------------------------------------ AC-3

/// Replace whole identifiers.
fn rename(src: &str, pairs: &[(&str, &str)]) -> String {
    let mut out = String::new();
    let mut word = String::new();
    let flush = |word: &mut String, out: &mut String| {
        let w = std::mem::take(word);
        out.push_str(
            pairs
                .iter()
                .find(|(a, _)| *a == w)
                .map_or(w.as_str(), |(_, b)| b),
        );
    };
    for c in src.chars() {
        if c.is_ascii_alphanumeric() || c == '_' {
            word.push(c);
        } else {
            flush(&mut word, &mut out);
            out.push(c);
        }
    }
    flush(&mut word, &mut out);
    out
}

#[test]
fn renaming_changes_nothing_but_the_names() {
    let src = read("pure/valid/merge_sort.weave");
    let renamed = rename(
        &src,
        &[
            ("merge_sort", "ordenar"),
            ("merge", "combine"),
            ("split", "divide"),
            ("Halves", "Parts"),
            ("left", "front"),
            ("right", "back"),
            ("key", "rank"),
            ("id", "tag"),
            ("Item", "Entry"),
            ("xs", "values"),
        ],
    );
    assert_ne!(src, renamed);
    let input = "[[9, -3, 4, 4, 0, 12, -3, 7]]";
    assert_eq!(value(&renamed, "ordenar", input), "[-3,-3,0,4,4,7,9,12]");
    assert_eq!(
        value(&src, "merge_sort", input),
        value(&renamed, "ordenar", input)
    );
    let items = "[[{\"rank\": 2, \"tag\": 1}, {\"rank\": 1, \"tag\": 2}]]";
    assert_eq!(
        value(&renamed, "sort_items", items),
        "[{\"rank\":1,\"tag\":2},{\"rank\":2,\"tag\":1}]"
    );
    // The old names are gone: calling them is an invalid request, not a hidden alias.
    let program = weave_check::check(&renamed).unwrap();
    assert!(matches!(
        run(
            &program,
            "merge_sort",
            &json::parse(input).unwrap(),
            DEFAULT_BUDGETS
        ),
        Err(RunError::Request(_))
    ));
    // A partial rename is a static error at the stale use.
    let partial = src.replacen("fn merge(", "fn combine(", 1);
    let d = weave_check::check(&partial).unwrap_err();
    assert_eq!(
        (d.code, partial.get(d.span.start..d.span.end)),
        ("E507", Some("merge"))
    );
    let field = src.replacen("    left: List[Int]", "    front: List[Int]", 1);
    let d = weave_check::check(&field).unwrap_err();
    assert_eq!(d.code, "E508");
}

#[test]
fn source_edits_change_behaviour_as_written() {
    let src = read("pure/valid/merge_sort.weave");
    let input = "[[3, 1, 2, 3, 0]]";
    assert_eq!(value(&src, "merge_sort", input), "[0,1,2,3,3]");
    // Flip the comparison in merge: the same algorithm now sorts descending.
    let flipped = src.replacen("if head(a) <= head(b):", "if head(a) >= head(b):", 1);
    assert_eq!(value(&flipped, "merge_sort", input), "[3,3,2,1,0]");
    // Take from the right on equal keys: equal items change order (stability is in the source).
    let items = "[[{\"key\": 1, \"id\": 1}, {\"key\": 1, \"id\": 2}]]";
    assert_eq!(
        value(&src, "sort_items", items),
        "[{\"key\":1,\"id\":1},{\"key\":1,\"id\":2}]"
    );
    let unstable = src.replacen("if x.key <= y.key:", "if x.key < y.key:", 1);
    assert_eq!(
        value(&unstable, "sort_items", items),
        "[{\"key\":1,\"id\":2},{\"key\":1,\"id\":1}]"
    );
    // Another split point gives the same sorted result by another route: no
    // hidden coupling to one algorithm.
    let lopsided = src.replacen("split(xs, div(length(xs), 2))", "split(xs, 1)", 1);
    assert_ne!(lopsided, src);
    assert_eq!(value(&lopsided, "merge_sort", input), "[0,1,2,3,3]");
    let before = go(
        &src,
        "merge_sort",
        "[[5, 4, 3, 2, 1, 0, 9, 8]]",
        DEFAULT_BUDGETS,
    );
    let after = go(
        &lopsided,
        "merge_sort",
        "[[5, 4, 3, 2, 1, 0, 9, 8]]",
        DEFAULT_BUDGETS,
    );
    assert_ne!(
        before.usage, after.usage,
        "the work done follows the source"
    );
    // Break the base case: the run no longer terminates and stops at its budget.
    let broken = src.replacen("if length(xs) <= 1:", "if length(xs) <= 0:", 1);
    let r = go(&broken, "merge_sort", input, budgets(10_000, 10_000, 64));
    assert!(matches!(r.outcome, Outcome::Exhausted(_, _)));
    // Routing: a changed limit in the source changes the decision.
    let routing = read("pure/valid/routing.weave");
    let routes = "[[{\"dest\": 4, \"cost\": 3, \"hops\": 17}], 10]";
    assert_eq!(
        value(&routing, "route", routes),
        "{\"accepted\":false,\"dest\":0,\"cost\":0}"
    );
    let relaxed = routing.replacen("r.hops <= 16", "r.hops <= 32", 1);
    assert_eq!(
        value(&relaxed, "route", routes),
        "{\"accepted\":true,\"dest\":4,\"cost\":3}"
    );
}

#[test]
fn every_corpus_function_runs_without_panicking() {
    // Arguments of the right shape from the signature, under small budgets: any
    // outcome is acceptable, an internal error or a panic is not.
    fn arg(ty: &weave_check::Ty, program: &weave_check::Program, seed: u64) -> String {
        use weave_check::Ty;
        match ty {
            Ty::Int => {
                ["0", "-1", "7", "123456789012345678901234567890"][(seed % 4) as usize].into()
            }
            Ty::Bool => if seed % 2 == 0 { "true" } else { "false" }.into(),
            Ty::List(t) => {
                let n = seed % 4;
                let items: Vec<String> = (0..n).map(|i| arg(t, program, seed / 3 + i)).collect();
                format!("[{}]", items.join(","))
            }
            Ty::Record(r) => {
                let rec = &program.records[*r];
                let fields: Vec<String> = rec
                    .fields
                    .iter()
                    .enumerate()
                    .map(|(i, (n, t))| format!("\"{n}\":{}", arg(t, program, seed + i as u64)))
                    .collect();
                format!("{{{}}}", fields.join(","))
            }
        }
    }
    for entry in std::fs::read_dir(examples().join("pure/valid")).unwrap() {
        let path = entry.unwrap().path();
        let src = std::fs::read_to_string(&path).unwrap();
        let program = weave_check::check(&src).unwrap();
        for f in &program.functions {
            for seed in 0..6 {
                let args: Vec<String> = f
                    .params
                    .iter()
                    .map(|(_, t)| arg(t, &program, seed))
                    .collect();
                let args = json::parse(&format!("[{}]", args.join(","))).unwrap();
                let r = run(&program, &f.name, &args, budgets(500, 100, 256));
                assert!(r.is_ok(), "{}::{}: {r:?}", path.display(), f.name);
            }
        }
    }
}

#[test]
fn outcomes_are_closed_and_distinct() {
    // Faults and exhaustion are separate enums with distinct codes.
    let faults = [Fault::DivisionByZero, Fault::EmptyList];
    let exhausted = [Exhaustion::Fuel, Exhaustion::Depth, Exhaustion::IntSize];
    let mut codes: Vec<&str> = faults.iter().map(|f| f.code()).collect();
    codes.extend(exhausted.iter().map(|x| x.code()));
    let mut unique = codes.clone();
    unique.sort();
    unique.dedup();
    assert_eq!(unique.len(), codes.len());
    for code in codes {
        let info = weave_syntax::diagnostic::code_info(code).unwrap();
        assert_eq!(info.category, "specification");
        assert!(info.rule.unwrap().starts_with("P0-"));
    }
}

#[test]
fn expressions_at_the_depth_limit_evaluate_on_a_small_stack() {
    // The evaluator's setup recursion (lowering to instructions, dropping the
    // typed tree) follows the expression depth, which the checker bounds.
    let limit = weave_check::EXPR_DEPTH_LIMIT;
    let handle = std::thread::Builder::new()
        .stack_size(1 << 20)
        .spawn(move || {
            let chain = vec!["x"; limit].join(" * ");
            let minus = format!("{}x", "-".repeat(limit - 1));
            let src = format!(
                "fn p(x: Int) -> Int:\n    return {chain}\n\nfn m(x: Int) -> Int:\n    return {minus}\n"
            );
            let program = weave_check::check(&src).map_err(|d| d.message)?;
            let mut out = Vec::new();
            for f in ["p", "m"] {
                let r = run(&program, f, &json::parse("[1]").unwrap(), DEFAULT_BUDGETS)
                    .map_err(|e| format!("{e:?}"))?;
                out.push(matches!(r.outcome, Outcome::Value(_)));
            }
            Ok::<_, String>(out)
        })
        .unwrap();
    assert_eq!(handle.join().unwrap(), Ok(vec![true, true]));
}
