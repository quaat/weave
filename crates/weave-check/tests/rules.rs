// SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
// SPDX-License-Identifier: MIT

//! Static rules of P0 (`pure.rst`): one accepted and at least one rejected
//! program per rule, with the code, the code's principal rule and the text
//! under the primary span.

#![allow(clippy::unwrap_used, clippy::expect_used, clippy::panic)]

use weave_check::{Ty, check};

/// (code, principal rule, spanned text) of the first diagnostic.
fn reject(src: &str) -> (&'static str, String, String) {
    match check(src) {
        Ok(_) => panic!("accepted:\n{src}"),
        Err(d) => {
            assert!(d.span.end <= src.len(), "span inside the source");
            let text = src.get(d.span.start..d.span.end).unwrap().to_string();
            (d.code, d.rule().unwrap_or_default(), text)
        }
    }
}

fn accept(src: &str) -> weave_check::Program {
    match check(src) {
        Ok(p) => p,
        Err(d) => panic!(
            "{} {} at {:?} ({:?}):\n{src}",
            d.code,
            d.message,
            d.span,
            src.get(d.span.start..d.span.end)
        ),
    }
}

fn assert_rejects(src: &str, code: &str, rule: &str, spanned: &str) {
    let (c, r, t) = reject(src);
    assert_eq!(
        (c, r.as_str(), t.as_str()),
        (code, rule, spanned),
        "\n{src}"
    );
}

#[test]
fn p0_file_1_syntax_and_prefix_words() {
    accept("fn f(x: Int) -> Int:\n    return x\n");
    assert_rejects(
        "fn f(x: Int) -> Bool:\n    return 1 < x < 3\n",
        "E500",
        "P0-FILE-1",
        "<",
    );
    // The grammar derives a word before a qualified name; only await survives lowering.
    assert_rejects(
        "fn f(x: Int) -> Int:\n    return wait Payments.charge(x)\n",
        "E500",
        "P0-FILE-1",
        "wait",
    );
    assert_rejects("flow f():\n    return\n", "E500", "P0-FILE-1", "flow");
}

#[test]
fn p0_decl_1_top_level_names() {
    accept("record R:\n    a: Int\n\nfn r(x: R) -> Int:\n    return x.a\n");
    assert_rejects(
        "fn f() -> Int:\n    return 1\n\nfn f() -> Int:\n    return 2\n",
        "E501",
        "P0-DECL-1",
        "f",
    );
    assert_rejects(
        "record R:\n    a: Int\n\nfn R() -> Int:\n    return 1\n",
        "E501",
        "P0-DECL-1",
        "R",
    );
    for builtin in ["head", "div", "not", "true", "Int", "List"] {
        let (code, _, text) = reject(&format!("fn {builtin}() -> Int:\n    return 1\n"));
        assert_eq!((code, text.as_str()), ("E501", builtin));
    }
}

#[test]
fn p0_decl_2_and_3_records() {
    accept("record P:\n    a: Int\n    b: List[Int]\n\nrecord Q:\n    p: P\n    ps: List[P]\n");
    assert_rejects(
        "record P:\n    a: Int\n    a: Bool\n",
        "E502",
        "P0-DECL-2",
        "a",
    );
    assert_rejects("record T:\n    kids: List[T]\n", "E503", "P0-DECL-3", "T");
    assert_rejects(
        "record A:\n    b: B\n\nrecord B:\n    a: List[A]\n",
        "E503",
        "P0-DECL-3",
        "A",
    );
}

#[test]
fn p0_decl_4_signatures_first_and_every_body_checked() {
    // A call to a function declared later, and a record declared after its use.
    accept(
        "fn first() -> P:\n    return second(1)\n\nfn second(x: Int) -> P:\n    return P(a: x)\n\nrecord P:\n    a: Int\n",
    );
    // A body nothing calls is still checked.
    assert_rejects(
        "fn used() -> Int:\n    return 1\n\nfn unused() -> Int:\n    return true\n",
        "E510",
        "P0-TYPE-2",
        "true",
    );
}

#[test]
fn p0_type_1_handles_and_unknown_types_are_rejected() {
    accept("fn f(xs: List[List[Bool]]) -> List[Int]:\n    return []\n");
    // AC-2: a handle in a parameter, a result or a field, with span and rule.
    assert_rejects(
        "fn peek(hold: Hold[t, o]) -> Int:\n    return 0\n",
        "E504",
        "P0-TYPE-1",
        "Hold[t, o]",
    );
    assert_rejects(
        "fn make() -> Escrow[t, o]:\n    return make()\n",
        "E504",
        "P0-TYPE-1",
        "Escrow[t, o]",
    );
    assert_rejects(
        "record R:\n    h: Hold[t, o]\n",
        "E504",
        "P0-TYPE-1",
        "Hold[t, o]",
    );
    assert_rejects(
        "fn f(xs: List[Hold[t, o]]) -> Int:\n    return 0\n",
        "E504",
        "P0-TYPE-1",
        "Hold[t, o]",
    );
    for bad in ["Nat", "Unit", "Money", "List", "List[Int, Int]", "Int[x]"] {
        let (code, rule, text) = reject(&format!("fn f(x: {bad}) -> Int:\n    return 0\n"));
        assert_eq!(
            (code, rule.as_str(), text.as_str()),
            ("E504", "P0-TYPE-1", bad)
        );
    }
}

#[test]
fn p0_name_1_values_are_bindings() {
    accept("fn f(x: Int) -> Bool:\n    let y = x\n    return y == x and true or false\n");
    assert_rejects(
        "fn f(x: Int) -> Int:\n    return y\n",
        "E505",
        "P0-NAME-1",
        "y",
    );
    assert_rejects(
        "fn f(x: Int) -> Int:\n    return f\n",
        "E505",
        "P0-NAME-1",
        "f",
    );
    assert_rejects(
        "fn f(x: Int) -> Int:\n    return head\n",
        "E505",
        "P0-NAME-1",
        "head",
    );
    // A dotted name whose root is not a binding names an operation, not a value.
    assert_rejects(
        "fn f(x: Int) -> Int:\n    return Inventory.stock\n",
        "E505",
        "P0-NAME-1",
        "Inventory",
    );
    // A binding is in scope only after its let.
    assert_rejects(
        "fn f(x: Int) -> Int:\n    let y = y\n    return x\n",
        "E505",
        "P0-NAME-1",
        "y",
    );
}

#[test]
fn p0_name_2_no_shadowing() {
    // The same name in sibling branches is not shadowing.
    accept(
        "fn f(x: Int) -> Int:\n    if x > 0:\n        let y = 1\n        return y\n    else:\n        let y = 2\n        return y\n",
    );
    assert_rejects(
        "fn f(x: Int) -> Int:\n    let x = 1\n    return x\n",
        "E506",
        "P0-NAME-2",
        "x",
    );
    assert_rejects(
        "fn f(x: Int, x: Int) -> Int:\n    return x\n",
        "E506",
        "P0-NAME-2",
        "x",
    );
    assert_rejects(
        "fn f(x: Int) -> Int:\n    let y = 1\n    if x > 0:\n        let y = 2\n        return y\n    else:\n        return y\n",
        "E506",
        "P0-NAME-2",
        "y",
    );
    assert_rejects(
        "fn g() -> Int:\n    return 1\n\nfn f(g: Int) -> Int:\n    return g\n",
        "E506",
        "P0-NAME-2",
        "g",
    );
    assert_rejects(
        "fn f(x: Int) -> Int:\n    let length = 1\n    return x\n",
        "E506",
        "P0-NAME-2",
        "length",
    );
    assert_rejects(
        "fn f(true: Int) -> Int:\n    return 1\n",
        "E506",
        "P0-NAME-2",
        "true",
    );
}

#[test]
fn p0_call_1_targets_and_argument_forms() {
    accept(
        "record P:\n    a: Bool\n\nfn f(x: Int) -> P:\n    return P(a: is_empty(cons(x, [x])) or not(true) and div(x, mod(x, 2)) > length([x]))\n",
    )
    .functions
    .len();
    let base = "record P:\n    a: Int\n\nfn g(x: Int) -> Int:\n    return x\n\n";
    for (body, spanned) in [
        ("return g(1, 2)", "g(1, 2)"),
        ("return g()", "g()"),
        ("return g(x: 1)", "x: 1"),
        ("return head(xs: [1])", "xs: [1]"),
        ("return div(1)", "div(1)"),
        ("return nothing(1)", "nothing"),
    ] {
        let src = format!("{base}fn f(x: Int) -> Int:\n    {body}\n");
        assert_rejects(&src, "E507", "P0-CALL-1", spanned);
    }
    assert_rejects(
        &format!("{base}fn f(x: Int) -> P:\n    return P(x)\n"),
        "E507",
        "P0-CALL-1",
        "x",
    );
    assert_rejects(
        &format!("{base}fn f(x: Int) -> P:\n    return P(1 + 1: x)\n"),
        "E507",
        "P0-CALL-1",
        "1 + 1",
    );
    assert_rejects(
        &format!("{base}fn f(x: Int) -> Int:\n    return x(1)\n"),
        "E507",
        "P0-CALL-1",
        "x",
    );
}

#[test]
fn p0_record_1_and_2_construction_and_access() {
    let rec = "record R:\n    dest: Int\n    cost: Int\n\n";
    accept(&format!(
        "{rec}fn f(r: R) -> R:\n    return R(cost: r.dest, dest: r.cost)\n"
    ));
    assert_rejects(
        &format!("{rec}fn f(d: Int) -> R:\n    return R(dest: d)\n"),
        "E508",
        "P0-RECORD-1",
        "R(dest: d)",
    );
    assert_rejects(
        &format!("{rec}fn f(d: Int) -> R:\n    return R(dest: d, dest: d, cost: d)\n"),
        "E508",
        "P0-RECORD-1",
        "dest",
    );
    assert_rejects(
        &format!("{rec}fn f(d: Int) -> R:\n    return R(dest: d, cost: d, price: d)\n"),
        "E508",
        "P0-RECORD-1",
        "price",
    );
    // AC: a wrong record field.
    assert_rejects(
        &format!("{rec}fn f(r: R) -> Int:\n    return r.price\n"),
        "E509",
        "P0-RECORD-2",
        "price",
    );
    assert_rejects(
        &format!("{rec}fn f(r: R) -> Int:\n    return r.dest.cost\n"),
        "E509",
        "P0-RECORD-2",
        "cost",
    );
}

#[test]
fn p0_type_2_mismatches() {
    accept("fn f(b: Bool, x: Int) -> Bool:\n    return b == (x != 0) and -x < x * 2\n");
    for (body, spanned) in [
        ("return b + 1", "b"),
        ("return x", "x"),
        ("return x and b", "x"),
        ("return [1] == [1]", "[1]"),
        ("return x == b", "b"),
        ("return not(x)", "x"),
        ("return head([true]) < 1", "head([true])"),
        ("return [1, true] == []", "true"),
        ("return length(x) > 0", "x"),
    ] {
        let src = format!("fn f(b: Bool, x: Int) -> Bool:\n    {body}\n");
        assert_rejects(&src, "E510", "P0-TYPE-2", spanned);
    }
    assert_rejects(
        "fn f(x: Int) -> Int:\n    if x:\n        return 1\n    else:\n        return 2\n",
        "E510",
        "P0-TYPE-2",
        "x",
    );
    assert_rejects(
        "fn f(x: Int) -> Int:\n    return []\n",
        "E510",
        "P0-TYPE-2",
        "[]",
    );
}

#[test]
fn p0_type_3_empty_lists_need_an_expected_type() {
    let p = accept(
        "record R:\n    xs: List[Int]\n\nfn g(xs: List[Bool]) -> Int:\n    return 0\n\nfn f() -> List[List[Int]]:\n    let r = R(xs: [])\n    let n = g([])\n    let ys = cons(1, [])\n    return [[], cons(n, r.xs), ys]\n",
    );
    let f = p.functions.iter().find(|f| f.name == "f").unwrap();
    assert_eq!(f.ret, Ty::list(Ty::list(Ty::Int)));
    for body in [
        "let xs = []\n    return 0",
        "return length([])",
        "return head([])",
        "return cons([], [[]]) == []",
    ] {
        let src = format!("fn f() -> Int:\n    {body}\n");
        assert_rejects(&src, "E511", "P0-TYPE-3", "[]");
    }
}

#[test]
fn p0_effect_and_fork_rules_reject_with_span() {
    // AC-2: operations and waiting are rejected with span and rule.
    assert_rejects(
        "fn pay(amount: Int) -> Int:\n    return Payments.charge(amount)\n",
        "E512",
        "P0-EFFECT-1",
        "Payments.charge(amount)",
    );
    assert_rejects(
        "fn pay(amount: Int) -> Int:\n    let x = 1 + Inventory.reserve(amount, amount)\n    return x\n",
        "E512",
        "P0-EFFECT-1",
        "Inventory.reserve(amount, amount)",
    );
    assert_rejects(
        "fn reserve(n: Int) -> Int:\n    let hold = await Inventory.reserve(n)\n    return n\n",
        "E513",
        "P0-EFFECT-2",
        "await Inventory.reserve(n)",
    );
    assert_rejects(
        "fn f(n: Int) -> Int:\n    return await Inventory.stock\n",
        "E513",
        "P0-EFFECT-2",
        "await Inventory.stock",
    );
    assert_rejects(
        "fn f(n: Int) -> Int:\n    fork:\n        let a = f(n)\n    return n\n",
        "E514",
        "P0-FORK-1",
        "fork",
    );
}

#[test]
fn p0_path_1_terminal_blocks() {
    accept(
        "fn f(x: Int) -> Int:\n    let a = 1\n    if x > 0:\n        let b = 2\n        if x > 1:\n            return b\n        else:\n            return a\n    else:\n        return 0\n",
    );
    assert_rejects(
        "fn f(x: Int) -> Int:\n    if x < 0:\n        return -1\n    return 1\n",
        "E515",
        "P0-PATH-1",
        "if",
    );
    assert_rejects(
        "fn f(x: Int) -> Int:\n    return 1\n    return 2\n",
        "E515",
        "P0-PATH-1",
        "return 2",
    );
    assert_rejects(
        "fn f(x: Int) -> Int:\n    let y = 1\n",
        "E515",
        "P0-PATH-1",
        "let y = 1",
    );
    assert_rejects(
        "fn f(x: Int) -> Int:\n    if x < 0:\n        let z = 1\n    else:\n        return 1\n",
        "E515",
        "P0-PATH-1",
        "let z = 1",
    );
}

#[test]
fn p0_rec_1_direct_recursion_only() {
    accept(
        "fn f(n: Int) -> Int:\n    if n <= 0:\n        return 0\n    else:\n        return f(n - 1)\n",
    );
    assert_rejects(
        "fn even(n: Int) -> Bool:\n    return n == 0 or odd(n - 1)\n\nfn odd(n: Int) -> Bool:\n    return n != 0 and even(n - 1)\n",
        "E516",
        "P0-REC-1",
        "odd(n - 1)",
    );
    // A cycle through three functions, closed by a call that would never run.
    assert_rejects(
        "fn a(n: Int) -> Int:\n    return b(n)\n\nfn b(n: Int) -> Int:\n    return c(n)\n\nfn c(n: Int) -> Int:\n    if false:\n        return a(n)\n    else:\n        return n\n",
        "E516",
        "P0-REC-1",
        "b(n)",
    );
}

#[test]
fn spans_survive_lowering_for_every_expression() {
    // AC-10: every typed expression keeps a span whose text is that expression.
    let src = "record R:\n    a: Int\n\nfn f(r: R, xs: List[Int]) -> Int:\n    let y = -(r.a + 2) * div(length(xs), 3)\n    if (y >= 1) and not(is_empty(xs)):\n        return head(cons(y, xs)) - R(a: y).a\n    else:\n        return y\n";
    // The field access on a call is not derivable; drop it and check spans.
    let src = src.replace(" - R(a: y).a", "");
    let p = accept(&src);
    fn walk(e: &weave_check::typed::Expr, src: &str, out: &mut Vec<String>) {
        use weave_check::typed::ExprK::*;
        out.push(src.get(e.span.start..e.span.end).unwrap().to_string());
        match &e.kind {
            Field(x, _) | Neg(x) => walk(x, src, out),
            Call(_, a) | Prim(_, a) | List(a) => a.iter().for_each(|x| walk(x, src, out)),
            Construct(_, f) => f.iter().for_each(|(_, x)| walk(x, src, out)),
            Arith(_, l, r) | Compare(_, l, r) | And(l, r) | Or(l, r) => {
                walk(l, src, out);
                walk(r, src, out);
            }
            Int(_) | Bool(_) | Local(_) => {}
        }
    }
    let f = &p.functions[0];
    let mut texts = Vec::new();
    for (_, e) in &f.body.lets {
        walk(e, &src, &mut texts);
    }
    if let weave_check::typed::Terminal::If {
        cond,
        then,
        otherwise,
    } = &*f.body.end
    {
        walk(cond, &src, &mut texts);
        for b in [then, otherwise] {
            if let weave_check::typed::Terminal::Return(e) = &*b.end {
                walk(e, &src, &mut texts);
            }
        }
    }
    for expected in [
        "-(r.a + 2) * div(length(xs), 3)",
        "-(r.a + 2)",
        "r.a + 2",
        "r.a",
        "r",
        "div(length(xs), 3)",
        "length(xs)",
        "(y >= 1) and not(is_empty(xs))",
        "y >= 1",
        "not(is_empty(xs))",
        "head(cons(y, xs))",
        "cons(y, xs)",
    ] {
        assert!(
            texts.iter().any(|t| t == expected),
            "{expected} in {texts:?}"
        );
    }
}

#[test]
fn the_checker_does_not_panic_on_mangled_input() {
    let base = std::fs::read_to_string(
        std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../specification/examples/pure/valid/merge_sort.weave"),
    )
    .unwrap();
    accept(&base);
    // Delete each token-sized slice in turn: every result is accepted or diagnosed.
    let bytes: Vec<usize> = base.char_indices().map(|(i, _)| i).collect();
    for (k, &start) in bytes.iter().enumerate().step_by(7) {
        let end = bytes.get(k + 3).copied().unwrap_or(base.len());
        let mut s = base.clone();
        s.replace_range(start..end, "");
        if let Err(d) = check(&s) {
            assert!(d.code.starts_with('E'));
            assert!(d.rule().is_some(), "{} has a rule", d.code);
            assert!(d.span.end <= s.len());
        }
    }
}
