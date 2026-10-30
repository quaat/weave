// SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
// SPDX-License-Identifier: MIT

//! Lexer and layout pass (lexical chapter, LEX-REQ-1 and LEX-REQ-2).
//!
//! Every byte of the source belongs to exactly one token or one trivia piece,
//! so printing the tokens with their trivia reproduces the source.
//!
//! * Lines end at LF or CRLF. A carriage return elsewhere is rejected.
//! * `#` starts a comment through the end of the line; there are no strings.
//! * Tabs are rejected everywhere, including comments and blank lines (E001).
//! * Blank and comment-only lines are trivia and do not affect layout.
//! * Trailing spaces and comments are trivia of the line's `NL` token.
//! * Each indentation level is four spaces; the first logical line is at level
//!   zero; a deeper line is exactly one level deeper and follows a line ending
//!   in `:` (E001). `INDENT` and `DEDENT` are zero-width tokens placed directly
//!   after the preceding `NL`, before any blank lines or comments.
//! * Words are maximal runs of ASCII letters, digits and `_`. A word that
//!   starts with a digit must be all digits (an integer token). Words are not
//!   reserved: the grammar matches keywords by text (LEX-REQ-2).
//! * Any other character outside a comment, including non-ASCII characters
//!   and control characters, is a lexical error.

use crate::diagnostic::{Diagnostic, LAYOUT_CODE};
use crate::span::Span;

/// Lexical class of a token.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum TokenClass {
    /// `[A-Za-z_][A-Za-z0-9_]*`: an identifier or a contextual word.
    Word,
    /// `[0-9]+`; the grammar decides whether it is `"0"` or `POSINT`.
    Int,
    /// Punctuation, including `->` and `==`.
    Punct,
    /// End of a nonblank logical line; empty at the end of a file without a final newline.
    Newline,
    /// Zero-width block opening.
    Indent,
    /// Zero-width block closing.
    Dedent,
    /// Zero-width end of input; carries trailing trivia.
    Eof,
}

impl TokenClass {
    pub fn name(self) -> &'static str {
        match self {
            TokenClass::Word => "word",
            TokenClass::Int => "int",
            TokenClass::Punct => "punct",
            TokenClass::Newline => "newline",
            TokenClass::Indent => "indent",
            TokenClass::Dedent => "dedent",
            TokenClass::Eof => "eof",
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum TriviaKind {
    /// Spaces.
    Whitespace,
    /// `#` through the end of the line, without the line ending.
    Comment,
    /// The LF or CRLF ending of a blank or comment-only line.
    Newline,
}

impl TriviaKind {
    pub fn name(self) -> &'static str {
        match self {
            TriviaKind::Whitespace => "whitespace",
            TriviaKind::Comment => "comment",
            TriviaKind::Newline => "newline",
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub struct Trivia {
    pub kind: TriviaKind,
    pub span: Span,
}

#[derive(Clone, Debug, PartialEq, Eq, Hash)]
pub struct Token {
    pub class: TokenClass,
    pub span: Span,
    /// Trivia between the previous token and this one, in source order.
    pub trivia: Vec<Trivia>,
}

impl Token {
    /// The start of this token including its leading trivia.
    pub fn full_start(&self) -> usize {
        self.trivia
            .first()
            .map_or(self.span.start, |t| t.span.start)
    }
}

/// Which syntax code a lexical (non-layout) fault receives.
#[derive(Clone, Copy, Debug)]
pub struct LexCodes {
    pub syntax: &'static str,
}

const PUNCT2: [&str; 2] = ["->", "=="];
const PUNCT1: &[u8] = b"()[],:.=+-*?";

/// Split `source` into tokens with trivia, including layout tokens and a final `EOF`.
pub fn lex(source: &str, codes: LexCodes) -> Result<Vec<Token>, Diagnostic> {
    let mut lexer = Lexer {
        src: source,
        codes,
        tokens: Vec::new(),
        pending: Vec::new(),
        levels: vec![0],
        last_was_colon: false,
        seen_logical: false,
        region_start: 0,
    };
    lexer.run()?;
    Ok(lexer.tokens)
}

struct Lexer<'a> {
    src: &'a str,
    codes: LexCodes,
    tokens: Vec<Token>,
    pending: Vec<Trivia>,
    levels: Vec<usize>,
    last_was_colon: bool,
    seen_logical: bool,
    /// End of the previous logical line's `NL` token: where layout tokens go.
    region_start: usize,
}

impl Lexer<'_> {
    fn byte(&self, i: usize) -> Option<u8> {
        self.src.as_bytes().get(i).copied()
    }

    fn trivia(&mut self, kind: TriviaKind, start: usize, end: usize) {
        if end > start {
            self.pending.push(Trivia {
                kind,
                span: Span::new(start, end),
            });
        }
    }

    fn push(&mut self, class: TokenClass, span: Span) {
        let trivia = std::mem::take(&mut self.pending);
        self.tokens.push(Token {
            class,
            span,
            trivia,
        });
    }

    fn layout_token(&mut self, class: TokenClass) {
        self.tokens.push(Token {
            class,
            span: Span::at(self.region_start),
            trivia: Vec::new(),
        });
    }

    fn layout_error(&self, message: impl Into<String>, span: Span) -> Diagnostic {
        Diagnostic::new(LAYOUT_CODE, "layout", message, span)
    }

    fn lexical_error(&self, message: impl Into<String>, span: Span) -> Diagnostic {
        Diagnostic::new(self.codes.syntax, "lexical", message, span)
    }

    fn char_span(&self, i: usize) -> (char, Span) {
        let c = self
            .src
            .get(i..)
            .and_then(|s| s.chars().next())
            .unwrap_or('\u{fffd}');
        (c, Span::new(i, i + c.len_utf8()))
    }

    fn run(&mut self) -> Result<(), Diagnostic> {
        let len = self.src.len();
        let mut pos = 0;
        while pos < len {
            let newline = self
                .src
                .get(pos..)
                .and_then(|s| s.find('\n'))
                .map(|i| pos + i);
            let (content_end, terminator) = match newline {
                Some(nl) if nl > pos && self.byte(nl - 1) == Some(b'\r') => {
                    (nl - 1, Some(Span::new(nl - 1, nl + 1)))
                }
                Some(nl) => (nl, Some(Span::new(nl, nl + 1))),
                None => (len, None),
            };
            self.line(pos, content_end, terminator)?;
            pos = terminator.map_or(len, |t| t.end);
        }
        // Close open blocks directly after the last logical line.
        while self.levels.len() > 1 {
            self.levels.pop();
            self.layout_token(TokenClass::Dedent);
        }
        self.push(TokenClass::Eof, Span::at(len));
        Ok(())
    }

    fn line(
        &mut self,
        start: usize,
        content_end: usize,
        terminator: Option<Span>,
    ) -> Result<(), Diagnostic> {
        let content = self.src.get(start..content_end).unwrap_or_default();
        if let Some(i) = content.find('\t') {
            return Err(self.layout_error(
                "Tabs are not allowed; indent with four spaces per level.",
                Span::new(start + i, start + i + 1),
            ));
        }
        if let Some(i) = content.find('\r') {
            return Err(self.lexical_error(
                "A carriage return is allowed only as part of a CRLF line ending.",
                Span::new(start + i, start + i + 1),
            ));
        }
        let comment_start = content.find('#').map_or(content_end, |i| start + i);
        let code = self.src.get(start..comment_start).unwrap_or_default();
        let indent_end = start + (code.len() - code.trim_start_matches(' ').len());
        let code_end = start + code.trim_end_matches(' ').len();

        if indent_end >= comment_start {
            // Blank or comment-only line: trivia only.
            self.trivia(TriviaKind::Whitespace, start, comment_start);
            self.trivia(TriviaKind::Comment, comment_start, content_end);
            if let Some(t) = terminator {
                self.trivia(TriviaKind::Newline, t.start, t.end);
            }
            return Ok(());
        }

        self.layout(indent_end - start, Span::new(start, indent_end))?;
        self.trivia(TriviaKind::Whitespace, start, indent_end);
        self.tokens_of(indent_end, code_end)?;
        self.last_was_colon = self.tokens.last().is_some_and(|t| {
            t.class == TokenClass::Punct && self.src.get(t.span.start..t.span.end) == Some(":")
        });
        self.trivia(TriviaKind::Whitespace, code_end, comment_start);
        self.trivia(TriviaKind::Comment, comment_start, content_end);
        let nl = terminator.unwrap_or(Span::at(content_end));
        self.push(TokenClass::Newline, nl);
        self.region_start = nl.end;
        self.seen_logical = true;
        Ok(())
    }

    fn layout(&mut self, indent: usize, span: Span) -> Result<(), Diagnostic> {
        let current = self.levels.last().copied().unwrap_or(0);
        if indent % 4 != 0 {
            return Err(self.layout_error(
                format!("Indentation of {indent} spaces is not a multiple of four."),
                span,
            ));
        }
        if !self.seen_logical {
            if indent != 0 {
                return Err(
                    self.layout_error("The first nonblank line must not be indented.", span)
                );
            }
            return Ok(());
        }
        if indent > current {
            if indent != current + 4 {
                return Err(self.layout_error(
                    format!(
                        "Indentation skips a level: expected at most {} spaces.",
                        current + 4
                    ),
                    span,
                ));
            }
            if !self.last_was_colon {
                return Err(self.layout_error(
                    "Unexpected nested block: the previous line does not end with ':'.",
                    span,
                ));
            }
            self.levels.push(indent);
            self.layout_token(TokenClass::Indent);
        } else {
            while self.levels.last().is_some_and(|&level| level > indent) {
                self.levels.pop();
                self.layout_token(TokenClass::Dedent);
            }
            if self.levels.last().copied() != Some(indent) {
                return Err(
                    self.layout_error("Dedent does not return to an enclosing level.", span)
                );
            }
        }
        Ok(())
    }

    fn tokens_of(&mut self, start: usize, end: usize) -> Result<(), Diagnostic> {
        let mut i = start;
        while i < end {
            let Some(b) = self.byte(i) else { break };
            if b == b' ' {
                let run = self
                    .src
                    .get(i..end)
                    .map_or(0, |s| s.len() - s.trim_start_matches(' ').len());
                self.trivia(TriviaKind::Whitespace, i, i + run);
                i += run;
            } else if b.is_ascii_alphanumeric() || b == b'_' {
                let mut j = i;
                while j < end
                    && self
                        .byte(j)
                        .is_some_and(|c| c.is_ascii_alphanumeric() || c == b'_')
                {
                    j += 1;
                }
                let text = self.src.get(i..j).unwrap_or_default();
                let class = if b.is_ascii_digit() {
                    if !text.bytes().all(|c| c.is_ascii_digit()) {
                        return Err(self.lexical_error(
                            format!("'{text}' is neither an integer nor an identifier: identifiers start with a letter or '_'."),
                            Span::new(i, j),
                        ));
                    }
                    TokenClass::Int
                } else {
                    TokenClass::Word
                };
                self.push(class, Span::new(i, j));
                i = j;
            } else if PUNCT2.iter().any(|p| self.src.get(i..i + 2) == Some(*p)) {
                self.push(TokenClass::Punct, Span::new(i, i + 2));
                i += 2;
            } else if PUNCT1.contains(&b) {
                self.push(TokenClass::Punct, Span::new(i, i + 1));
                i += 1;
            } else {
                let (c, span) = self.char_span(i);
                let message = if !c.is_ascii() {
                    format!(
                        "Non-ASCII character U+{:04X} outside a comment; identifiers and punctuation are ASCII.",
                        c as u32
                    )
                } else if c.is_ascii_control() {
                    format!("Control character U+{:04X} outside a comment.", c as u32)
                } else {
                    format!("Unexpected character '{c}'.")
                };
                return Err(self.lexical_error(message, span));
            }
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const CODES: LexCodes = LexCodes { syntax: "E200" };

    fn classes(src: &str) -> Vec<TokenClass> {
        lex(src, CODES)
            .map(|t| t.iter().map(|t| t.class).collect())
            .unwrap_or_default()
    }

    #[test]
    fn layout_tokens() {
        use TokenClass::*;
        assert_eq!(
            classes("a:\n    b\n\n  # c\nd\n"),
            vec![
                Word, Punct, Newline, Indent, Word, Newline, Dedent, Word, Newline, Eof
            ]
        );
        assert_eq!(classes(""), vec![Eof]);
        assert_eq!(
            classes("a:\n    b"),
            vec![Word, Punct, Newline, Indent, Word, Newline, Dedent, Eof]
        );
    }

    #[test]
    fn every_byte_is_covered() {
        let src =
            "# head\r\nnet  A(x: Nat):  # c\r\n    place p = 0 owner domain\r\n\r\n   # odd\n";
        let tokens = lex(src, CODES).unwrap_or_default();
        let mut printed = String::new();
        for t in &tokens {
            for tr in &t.trivia {
                printed.push_str(src.get(tr.span.start..tr.span.end).unwrap_or_default());
            }
            printed.push_str(src.get(t.span.start..t.span.end).unwrap_or_default());
        }
        assert_eq!(printed, src);
    }

    #[test]
    fn layout_errors_are_e001() {
        for bad in [
            "\ta",
            "a:\n\tb",
            "# x\t\na",
            "a:\n   b",
            "a:\n        b",
            " a",
            "a\n    b",
        ] {
            let err = lex(bad, CODES).err();
            assert_eq!(err.map(|d| d.code), Some("E001"), "{bad:?}");
        }
    }

    #[test]
    fn lexical_errors_use_the_syntax_code() {
        for bad in ["a\rb", "é", "a\u{0}", "1abc", "a @ b", "a\u{a0}b"] {
            let err = lex(bad, CODES).err();
            assert_eq!(err.map(|d| d.code), Some("E200"), "{bad:?}");
        }
        assert!(lex("a # é \u{0} @\n", CODES).is_ok());
    }

    #[test]
    fn grammar_punctuation_lexes_as_single_tokens() {
        for p in crate::grammar::PUNCTUATION {
            let tokens = lex(p, CODES).unwrap_or_default();
            let first = tokens.first().map(|t| (t.class, t.span));
            assert_eq!(
                first,
                Some((TokenClass::Punct, Span::new(0, p.len()))),
                "{p}"
            );
            assert_eq!(tokens.len(), 3, "{p}");
        }
    }
}
