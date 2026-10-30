// SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
// SPDX-License-Identifier: MIT

//! Reader for the ISO-style EBNF of `specification/grammar/*.ebnf`.
//!
//! Notation (grammar chapter): quoted strings are terminals, `,` concatenates,
//! `|` separates alternatives, `[ ]` is optional, `{ }` repeats zero or more
//! times, `( )` groups, `;` ends a production, `? ... ?` is a special sequence
//! (a lexical class) and `(* ... *)` is a comment.

/// Nesting limit for brackets in an EBNF text.
pub const MAX_DEPTH: usize = 200;

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Expr {
    /// A quoted terminal.
    Terminal(String),
    /// A reference to a production.
    Ref(String),
    /// A special sequence; only the whole body of a lexical production.
    Special(String),
    Optional(Box<Expr>),
    Repeat(Box<Expr>),
    Seq(Vec<Expr>),
    Alt(Vec<Expr>),
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Production {
    pub name: String,
    pub expr: Expr,
    /// 1-based line of the production name.
    pub line: usize,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct EbnfError {
    pub line: usize,
    pub message: String,
}

impl std::fmt::Display for EbnfError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "EBNF line {}: {}", self.line, self.message)
    }
}

impl std::error::Error for EbnfError {}

#[derive(Clone, Debug, PartialEq, Eq)]
enum Tok {
    Name(String),
    Str(String),
    Special(String),
    Punct(char),
}

fn tokenize(text: &str) -> Result<Vec<(Tok, usize)>, EbnfError> {
    let mut out = Vec::new();
    let mut line = 1;
    let mut chars = text.char_indices().peekable();
    while let Some((i, c)) = chars.next() {
        match c {
            '\n' => line += 1,
            c if c.is_whitespace() => {}
            '(' if text.get(i + 1..i + 2) == Some("*") => {
                chars.next();
                let start = line;
                let mut closed = false;
                while let Some((j, d)) = chars.next() {
                    if d == '\n' {
                        line += 1;
                    } else if d == '*' && text.get(j + 1..j + 2) == Some(")") {
                        chars.next();
                        closed = true;
                        break;
                    }
                }
                if !closed {
                    return Err(EbnfError {
                        line: start,
                        message: "unterminated comment".into(),
                    });
                }
            }
            '"' | '?' => {
                let start = line;
                let mut body = String::new();
                let mut closed = false;
                for (_, d) in chars.by_ref() {
                    if d == c {
                        closed = true;
                        break;
                    }
                    if d == '\n' {
                        line += 1;
                    }
                    body.push(d);
                }
                if !closed {
                    return Err(EbnfError {
                        line: start,
                        message: format!(
                            "unterminated {}",
                            if c == '"' {
                                "terminal"
                            } else {
                                "special sequence"
                            }
                        ),
                    });
                }
                if c == '"' && body.is_empty() {
                    return Err(EbnfError {
                        line: start,
                        message: "empty terminal".into(),
                    });
                }
                out.push((
                    if c == '"' {
                        Tok::Str(body)
                    } else {
                        Tok::Special(body.trim().to_string())
                    },
                    start,
                ));
            }
            '=' | ',' | ';' | '|' | '[' | ']' | '{' | '}' | '(' | ')' => {
                out.push((Tok::Punct(c), line))
            }
            c if c.is_ascii_alphabetic() => {
                let mut name = c.to_string();
                while let Some(&(_, d)) = chars.peek() {
                    if d.is_ascii_alphanumeric() || d == '-' || d == '_' {
                        name.push(d);
                        chars.next();
                    } else {
                        break;
                    }
                }
                out.push((Tok::Name(name), line));
            }
            other => {
                return Err(EbnfError {
                    line,
                    message: format!("unexpected character {other:?}"),
                });
            }
        }
    }
    Ok(out)
}

struct Reader {
    toks: Vec<(Tok, usize)>,
    pos: usize,
}

impl Reader {
    fn line(&self) -> usize {
        self.toks
            .get(self.pos)
            .or_else(|| self.toks.last())
            .map_or(1, |(_, l)| *l)
    }

    fn error<T>(&self, message: impl Into<String>) -> Result<T, EbnfError> {
        Err(EbnfError {
            line: self.line(),
            message: message.into(),
        })
    }

    fn peek(&self) -> Option<&Tok> {
        self.toks.get(self.pos).map(|(t, _)| t)
    }

    fn eat(&mut self, c: char) -> bool {
        if self.peek() == Some(&Tok::Punct(c)) {
            self.pos += 1;
            true
        } else {
            false
        }
    }

    fn alt(&mut self, depth: usize) -> Result<Expr, EbnfError> {
        if depth > MAX_DEPTH {
            return self.error("nesting too deep");
        }
        let mut alts = vec![self.seq(depth)?];
        while self.eat('|') {
            alts.push(self.seq(depth)?);
        }
        Ok(if alts.len() == 1 {
            alts.remove(0)
        } else {
            Expr::Alt(alts)
        })
    }

    fn seq(&mut self, depth: usize) -> Result<Expr, EbnfError> {
        let mut items = vec![self.term(depth)?];
        while self.eat(',') {
            items.push(self.term(depth)?);
        }
        Ok(if items.len() == 1 {
            items.remove(0)
        } else {
            Expr::Seq(items)
        })
    }

    fn term(&mut self, depth: usize) -> Result<Expr, EbnfError> {
        let Some(tok) = self.peek().cloned() else {
            return self.error("unexpected end of grammar");
        };
        self.pos += 1;
        match tok {
            Tok::Str(s) => Ok(Expr::Terminal(s)),
            Tok::Name(n) => Ok(Expr::Ref(n)),
            Tok::Special(s) => Ok(Expr::Special(s)),
            Tok::Punct(open @ ('[' | '{' | '(')) => {
                let inner = self.alt(depth + 1)?;
                let close = match open {
                    '[' => ']',
                    '{' => '}',
                    _ => ')',
                };
                if !self.eat(close) {
                    return self.error(format!("expected '{close}'"));
                }
                Ok(match open {
                    '[' => Expr::Optional(Box::new(inner)),
                    '{' => Expr::Repeat(Box::new(inner)),
                    _ => inner,
                })
            }
            Tok::Punct(c) => {
                self.pos -= 1;
                self.error(format!("unexpected '{c}'"))
            }
        }
    }
}

/// Read every production of an EBNF text, in order. Duplicates are kept; the
/// normalisation check reports them.
pub fn parse(text: &str) -> Result<Vec<Production>, EbnfError> {
    let mut reader = Reader {
        toks: tokenize(text)?,
        pos: 0,
    };
    let mut productions = Vec::new();
    while let Some(tok) = reader.peek().cloned() {
        let line = reader.line();
        let Tok::Name(name) = tok else {
            return reader.error("expected a production name");
        };
        reader.pos += 1;
        if !reader.eat('=') {
            return reader.error(format!("expected '=' after {name}"));
        }
        let expr = reader.alt(0)?;
        if !reader.eat(';') {
            return reader.error(format!("expected ';' to end {name}"));
        }
        productions.push(Production { name, expr, line });
    }
    Ok(productions)
}

impl Expr {
    /// Visit this expression and every sub-expression, outermost first.
    pub fn walk<'a>(&'a self, visit: &mut dyn FnMut(&'a Expr)) {
        visit(self);
        match self {
            Expr::Optional(e) | Expr::Repeat(e) => e.walk(visit),
            Expr::Seq(items) | Expr::Alt(items) => items.iter().for_each(|e| e.walk(visit)),
            Expr::Terminal(_) | Expr::Ref(_) | Expr::Special(_) => {}
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn reads_notation() {
        let p = parse("(* c *) a = \"x\", [ b ], { \"y\" | c } ; b = ? word ? ; c = ( \"p\" | \"q\" ), \"r\" ;")
            .unwrap_or_default();
        assert_eq!(p.len(), 3);
        assert_eq!(
            p.first().map(|p| &p.expr),
            Some(&Expr::Seq(vec![
                Expr::Terminal("x".into()),
                Expr::Optional(Box::new(Expr::Ref("b".into()))),
                Expr::Repeat(Box::new(Expr::Alt(vec![
                    Expr::Terminal("y".into()),
                    Expr::Ref("c".into())
                ]))),
            ]))
        );
        assert_eq!(
            p.get(1).map(|p| &p.expr),
            Some(&Expr::Special("word".into()))
        );
    }

    #[test]
    fn rejects_malformed_text() {
        for bad in [
            "a = \"x\"",
            "a \"x\";",
            "a = (\"x\" ;",
            "a = \"x ;",
            "(* x",
            "a = ;",
            "a = \"\" ;",
            "a = $ ;",
        ] {
            assert!(parse(bad).is_err(), "{bad}");
        }
        let deep = format!(
            "a = {}\"x\"{} ;",
            "(".repeat(MAX_DEPTH + 5),
            ")".repeat(MAX_DEPTH + 5)
        );
        assert!(parse(&deep).is_err());
    }
}
