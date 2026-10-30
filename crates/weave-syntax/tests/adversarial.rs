// SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
// SPDX-License-Identifier: MIT

//! Adversarial input: every case gives a diagnostic or a correct parse, never a panic.

#![allow(clippy::unwrap_used, clippy::expect_used, clippy::panic)]

use weave_syntax::parser::DEFAULT_MAX_DEPTH;
use weave_syntax::{Diagnostic, Options, Start, parse, parse_bytes, round_trips};

const FLOW: &str = "flow f(hold: Hold[t, o]) -> Hold[t, o]:\n    return hold\n";
const NET: &str = "net N(stock: Nat):\n    place p = stock owner domain\n    transition t:\n        take 1 p\n        put 1 p\n    invariant i:\n        p == stock\n";

fn err(src: &str, start: Start) -> Diagnostic {
    match parse(src, start) {
        Ok(_) => panic!("accepted: {src:?}"),
        Err(d) => {
            assert!(d.rule().is_some(), "{} has a rule", d.code);
            assert!(
                d.span.start <= d.span.end && d.span.end <= src.len(),
                "span inside the source"
            );
            d
        }
    }
}

fn ok(src: &str, start: Start) {
    match round_trips(src, start) {
        Ok(true) => {}
        Ok(false) => panic!("round trip failed: {src:?}"),
        Err(d) => panic!("{} {} at {:?}: {src:?}", d.code, d.message, d.span),
    }
}

#[test]
fn baselines_parse() {
    ok(FLOW, Start::FlowFile);
    ok(NET, Start::N0File);
}

#[test]
fn tabs_are_layout_errors_everywhere() {
    for src in [
        FLOW.replace("    return", "\treturn"),
        format!("#\tcomment\n{FLOW}"),
        format!("{FLOW}\t\n"),
        FLOW.replace("hold: Hold", "hold:\tHold"),
    ] {
        let d = err(&src, Start::FlowFile);
        assert_eq!((d.code, d.stage), ("E001", "layout"), "{src:?}");
        assert_eq!(src.get(d.span.start..d.span.end), Some("\t"));
    }
    assert_eq!(
        err(&NET.replace("    place", "\tplace"), Start::N0File).code,
        "E001"
    );
}

#[test]
fn indentation_errors_are_layout_errors() {
    for (src, start) in [
        (FLOW.replace("    return", "   return"), Start::FlowFile),
        (FLOW.replace("    return", "     return"), Start::FlowFile),
        (
            FLOW.replace("    return", "        return"),
            Start::FlowFile,
        ),
        (format!("    {FLOW}"), Start::FlowFile),
        (format!("# comment first\n    {FLOW}"), Start::FlowFile),
        (NET.replace("        take", "      take"), Start::N0File),
        (NET.replace("        put", "          put"), Start::N0File),
        (
            "net N(stock: Nat)\n    place p = 0 owner domain\n".to_string(),
            Start::N0File,
        ),
    ] {
        let d = err(&src, start);
        assert_eq!(d.code, "E001", "{src:?}: {}", d.message);
    }
}

#[test]
fn dedent_to_an_unknown_level_is_rejected() {
    // Six spaces after a block at eight: not a multiple of four, so never a level.
    let src = "flow f(r: R):\n    match r:\n        Ok(x):\n            return\n      Err(y):\n            return\n";
    assert_eq!(err(src, Start::FlowFile).code, "E001");
    // A dedent to an enclosing level that the grammar does not allow there.
    let src = "flow f(r: R):\n    match r:\n        Ok(x):\n            return\n    Err(y):\n            return\n";
    assert_eq!(err(src, Start::FlowFile).code, "E001");
    let src = "flow f(r: R):\n    match r:\n        Ok(x):\n            return\n    Err(y):\n        return\n";
    let d = err(src, Start::FlowFile);
    assert_eq!((d.code, d.stage), ("E200", "syntax"), "{}", d.message);
}

#[test]
fn comment_lines_do_not_affect_layout() {
    ok(
        "flow f(h: H) -> H:\n  # two\n     # five\n\n    return h  # trailing\n# end",
        Start::FlowFile,
    );
    ok(
        &FLOW.replace("    return hold\n", "    return hold   \n"),
        Start::FlowFile,
    );
    ok(
        &format!("{FLOW}\n\n   \n# trailing comment\n\n"),
        Start::FlowFile,
    );
}

#[test]
fn truncated_files_are_rejected_without_panicking() {
    for source in [FLOW, NET] {
        let start = if source == FLOW {
            Start::FlowFile
        } else {
            Start::N0File
        };
        let mut boundaries: Vec<usize> = (0..source.len())
            .filter(|&i| source.is_char_boundary(i))
            .collect();
        boundaries.push(source.len());
        for &end in &boundaries {
            let prefix = &source[..end];
            match parse(prefix, start) {
                Ok(cst) => assert_eq!(cst.print(), prefix),
                Err(d) => {
                    assert!(d.rule().is_some());
                    assert!(d.span.end <= prefix.len());
                }
            }
        }
        // A file cut inside its header fails with the syntax code.
        let cut = &source[..source.find('(').unwrap() + 3];
        assert_eq!(err(cut, start).code, start.syntax_code());
    }
    // A file without a final newline is accepted.
    ok(FLOW.trim_end(), Start::FlowFile);
}

#[test]
fn deep_parenthesis_nesting_is_a_limit_diagnostic() {
    let depth = 10_000;
    let expr = format!("{}p{}", "(".repeat(depth), ")".repeat(depth));
    let net = NET.replace("        p == stock", &format!("        {expr} == stock"));
    let d = err(&net, Start::N0File);
    assert_eq!((d.code, d.stage), ("E003", "limit"));
    // The limit is a parser property, not a grammar property: modest nesting parses.
    let net = NET.replace(
        "        p == stock",
        &format!("        {}p{} == stock", "(".repeat(20), ")".repeat(20)),
    );
    ok(&net, Start::N0File);
    // Unbalanced deep nesting, and deep unary minus, are rejected, never overflowed.
    let net_open = NET.replace(
        "        p == stock",
        &format!("        {}p == stock", "(".repeat(depth)),
    );
    assert!(parse(&net_open, Start::N0File).is_err());
    let net_minus = NET.replace(
        "        p == stock",
        &format!("        {}p == stock", "- ".repeat(depth)),
    );
    assert_eq!(err(&net_minus, Start::N0File).stage, "limit");
    // A smaller limit applies to the same input.
    let small = NET.replace("        p == stock", "        ((p)) == stock");
    assert!(weave_syntax::parse_with(&small, Start::N0File, Options { max_depth: 12 }).is_err());
    assert!(
        weave_syntax::parse_with(
            &small,
            Start::N0File,
            Options {
                max_depth: DEFAULT_MAX_DEPTH
            }
        )
        .is_ok()
    );
}

#[test]
fn deep_parenthesis_nesting_runs_on_a_small_stack() {
    // Test threads have small stacks; the depth limit must keep well inside them.
    let handle = std::thread::Builder::new()
        .stack_size(1 << 20)
        .spawn(|| {
            let expr = format!("{}p{}", "(".repeat(10_000), ")".repeat(10_000));
            let net = NET.replace("        p == stock", &format!("        {expr} == stock"));
            parse(&net, Start::N0File).map(|_| ()).map_err(|d| d.stage)
        })
        .unwrap();
    assert_eq!(handle.join().unwrap(), Err("limit"));
}

#[test]
fn long_lines_parse() {
    let args: Vec<String> = (0..20_000).map(|i| format!("a{i}")).collect();
    let src = format!(
        "flow f():\n    await Op.call({})\n    return\n",
        args.join(", ")
    );
    ok(&src, Start::FlowFile);
    let src = format!("flow f():\n    return {}\n", "x".repeat(1_000_000));
    ok(&src, Start::FlowFile);
    let comment = format!("# {}\n{FLOW}", "é".repeat(100_000));
    ok(&comment, Start::FlowFile);
}

#[test]
fn non_ascii_identifiers_are_lexical_errors() {
    for (src, start) in [
        (FLOW.replace("hold:", "höld:"), Start::FlowFile),
        (FLOW.replace("flow f", "flow 名"), Start::FlowFile),
        (NET.replace("place p", "place p\u{0301}"), Start::N0File),
        (format!("\u{feff}{FLOW}"), Start::FlowFile),
        (
            FLOW.replace("return hold", "return\u{a0}hold"),
            Start::FlowFile,
        ),
    ] {
        let d = err(&src, start);
        assert_eq!(
            (d.code, d.stage),
            (start.syntax_code(), "lexical"),
            "{src:?}"
        );
        assert!(d.message.contains("Non-ASCII"));
    }
    // Non-ASCII text in comments is fine and keeps character columns.
    ok(&format!("# Ωmega — ünïcode ✓\n{FLOW}"), Start::FlowFile);
    let d = err(
        &FLOW.replace("return hold", "return hold ¬"),
        Start::FlowFile,
    );
    let doc = d.to_json("f.weave", &FLOW.replace("return hold", "return hold ¬"));
    let column = doc
        .get("span")
        .and_then(|s| s.get("start"))
        .and_then(|p| p.get("column"))
        .cloned();
    assert_eq!(column, Some(weave_syntax::json::Value::from_usize(17)));
}

#[test]
fn nul_bytes_and_control_characters() {
    for src in [
        FLOW.replace("hold:", "ho\0ld:"),
        format!("{FLOW}\0"),
        FLOW.replace(' ', "\u{c}"),
    ] {
        let d = err(&src, Start::FlowFile);
        assert_eq!(d.stage, "lexical", "{src:?}");
    }
    // Inside a comment a NUL is comment text.
    ok(&format!("# nul \0 here\n{FLOW}"), Start::FlowFile);
    // Invalid UTF-8 is a diagnostic, not a panic.
    let mut bytes = FLOW.as_bytes().to_vec();
    bytes.insert(5, 0xff);
    let d = parse_bytes(&bytes, Start::FlowFile, Options::default()).unwrap_err();
    assert_eq!((d.code, d.span.start), ("E200", 5));
}

#[test]
fn crlf_line_endings_are_accepted_and_preserved() {
    // Lexical chapter: LF or CRLF line endings.
    let crlf = FLOW.replace('\n', "\r\n");
    ok(&crlf, Start::FlowFile);
    let cst = parse(&crlf, Start::FlowFile).unwrap();
    assert_eq!(cst.print(), crlf);
    ok(&NET.replace('\n', "\r\n"), Start::N0File);
    // Mixed endings and CRLF blank and comment lines.
    ok(
        "flow f(h: H) -> H:\r\n\r\n    # c\r\n    return h\n",
        Start::FlowFile,
    );
    // A carriage return that does not end a line is rejected.
    for src in [
        FLOW.replace('\n', "\r"),
        FLOW.replace("return hold", "return\rhold"),
        format!("# a\rflow\n{FLOW}"),
    ] {
        let d = err(&src, Start::FlowFile);
        assert_eq!(d.stage, "lexical", "{src:?}");
    }
}

#[test]
fn empty_and_blank_files_are_syntax_errors() {
    for src in ["", "\n\n", "# only a comment\n", "   \n"] {
        assert_eq!(err(src, Start::FlowFile).code, "E200");
        assert_eq!(err(src, Start::N0File).code, "E003");
        assert_eq!(err(src, Start::N1File).code, "E003");
    }
}

#[test]
fn numerals_and_words() {
    let net = |arc: &str| NET.replace("take 1 p", arc);
    for bad in [
        "take 1p",
        "take 01 p",
        "take 0 p",
        "take p",
        "take 1 2",
        "take -1 p",
    ] {
        assert_eq!(err(&net(bad), Start::N0File).code, "E003", "{bad}");
    }
    ok(&net("take   1   p"), Start::N0File);
    // Words are maximal: `placep` is one identifier, not `place p`.
    assert!(parse(&NET.replace("place p", "placep"), Start::N0File).is_err());
    // Contextual words are identifiers where the grammar expects one (LEX-REQ-2).
    ok(
        "net net(net: Nat):\n    place place = net owner domain\n    transition take:\n        take 1 place\n        put 1 place\n    invariant invariant:\n        place == net\n",
        Start::N0File,
    );
    for src in [
        "flow f():\n    let x = await()\n    return\n",
        "flow f():\n    let x = await.op(a)\n    return\n",
        "flow f():\n    let x = await await()\n    return\n",
        "flow f():\n    let await = await A.b(await)\n    return await\n",
    ] {
        ok(src, Start::FlowFile);
    }
    // Spacing between tokens is not significant in the grammar.
    ok(
        "flow f(h:Hold[t,o])->Hold[t,o]:\n    return h\n",
        Start::FlowFile,
    );
}

#[test]
fn unexpected_characters_and_trailing_content() {
    for (src, stage) in [
        (format!("{FLOW}flow"), "syntax"),
        (FLOW.replace("return hold", "return hold;"), "lexical"),
        (FLOW.replace("return hold", "return \"hold\""), "lexical"),
        (format!("{FLOW}  }}\n"), "layout"),
        (FLOW.replace("-> Hold[t, o]", "-> Hold[t, o]]"), "syntax"),
    ] {
        assert_eq!(err(&src, Start::FlowFile).stage, stage, "{src:?}");
    }
}

#[test]
fn the_other_start_symbols_reject_flows_and_nets() {
    assert_eq!(err(FLOW, Start::N0File).code, "E003");
    assert_eq!(err(NET, Start::FlowFile).code, "E200");
}

#[test]
fn the_depth_cap_fits_the_parser_stack() {
    use weave_syntax::parser::MAX_DEPTH_CAP;
    // Four productions per parenthesis level: this input nests close to the cap
    // and must parse, from a caller with a small stack, without overflowing.
    let levels = MAX_DEPTH_CAP / 4 - 10;
    let net = NET.replace(
        "        p == stock",
        &format!(
            "        {}p{} == stock",
            "(".repeat(levels),
            ")".repeat(levels)
        ),
    );
    let handle = std::thread::Builder::new()
        .stack_size(256 << 10)
        .spawn(move || {
            let deep = weave_syntax::parse_with(
                &net,
                Start::N0File,
                Options {
                    max_depth: usize::MAX,
                },
            );
            let shallow = weave_syntax::parse_with(&net, Start::N0File, Options::default());
            (
                deep.map(|cst| cst.print() == net).ok(),
                shallow.err().map(|d| d.stage),
            )
        })
        .unwrap();
    assert_eq!(handle.join().unwrap(), (Some(true), Some("limit")));
}

// ------------------------------------------------------------------ P0 pure files

const PURE: &str = "fn f(x: Int) -> Int:\n    return x\n";

#[test]
fn p0_files_round_trip_and_reject_with_e500() {
    ok(PURE, Start::PureFile);
    ok(
        "record R:\n    a: Int\n\nfn g(r: R, xs: List[List[Int]]) -> Bool:\n    if r.a <= 1 and not(r.a != 2) or r.a >= -3:\n        return length(xs) > 0\n    else:\n        let s = R(a: div(1, 2))\n        return s.a == mod(3, -4)\n",
        Start::PureFile,
    );
    for bad in [
        "fn f() -> Int:\n    return 1 < 2 < 3\n",
        "fn f() -> Int:\n    return 007\n",
        "fn f() -> Int:\n    return 1 !\n",
        "fn f() -> Int:\n    return a.b(c).d\n",
        "fn f() -> Int:\n    return await f(1)\n",
        "flow f():\n    return\n",
        "fn f() -> Int\n",
        "fn f(x: Int) -> Int:\n    return xé\n",
        "",
    ] {
        let d = err(bad, Start::PureFile);
        assert_eq!(d.code, "E500", "{bad:?}: {}", d.message);
        assert_eq!(d.rule().as_deref(), Some("P0-FILE-1"));
    }
    assert_eq!(
        err(&PURE.replace("    return", "\treturn"), Start::PureFile).code,
        "E001"
    );
}

#[test]
fn p0_punctuation_lexes_but_f0_and_n0_still_reject_it() {
    // Before P0 these characters were lexical errors; now they are tokens the
    // flow and net grammars do not derive. The code is the same either way.
    for op in ["<", "<=", ">", ">=", "!="] {
        let flow = FLOW.replace("return hold", &format!("return hold {op} hold"));
        let d = err(&flow, Start::FlowFile);
        assert_eq!((d.code, d.stage), ("E200", "syntax"), "{op}");
        let net = NET.replace("p == stock", &format!("p {op} stock"));
        assert_eq!(err(&net, Start::N0File).code, "E003", "{op}");
    }
    // A lone '!' stays a lexical error; '=>' is not a token, and '<-' is '<' '-'.
    assert_eq!(
        err(
            &FLOW.replace("return hold", "return !hold"),
            Start::FlowFile
        )
        .stage,
        "lexical"
    );
    assert_eq!(
        err(
            &format!("{PURE}fn g() -> Int:\n    return 1 => 2\n"),
            Start::PureFile
        )
        .code,
        "E500"
    );
    ok(
        &format!("{PURE}fn g() -> Bool:\n    return 1 <- 2\n"),
        Start::PureFile,
    );
}

#[test]
fn p0_nesting_at_the_parser_limit_is_a_limit_diagnostic() {
    let nested = |n: usize| {
        format!(
            "fn f() -> Int:\n    return {}1{}\n",
            "(".repeat(n),
            ")".repeat(n)
        )
    };
    // Each parenthesised level costs one pass through the seven expression productions.
    let mut deepest_ok = 0;
    for n in [1, 10, 30, 50, 54] {
        if parse(&nested(n), Start::PureFile).is_ok() {
            deepest_ok = n;
        }
    }
    assert!(deepest_ok >= 50, "{deepest_ok}");
    let d = err(&nested(60), Start::PureFile);
    assert_eq!((d.code, d.stage), ("E500", "limit"));
    let minus = format!("fn f() -> Int:\n    return {}1\n", "-".repeat(1000));
    assert_eq!(err(&minus, Start::PureFile).stage, "limit");
    let ok_minus = format!("fn f() -> Int:\n    return {}1\n", "-".repeat(300));
    assert!(parse(&ok_minus, Start::PureFile).is_ok());
}

#[test]
fn p0_long_lists_and_wide_expressions_parse() {
    let items: Vec<String> = (0..20_000).map(|i| i.to_string()).collect();
    ok(
        &format!("fn f() -> List[Int]:\n    return [{}]\n", items.join(", ")),
        Start::PureFile,
    );
    ok(
        &format!("fn f() -> Int:\n    return {}\n", items.join(" + ")),
        Start::PureFile,
    );
}
