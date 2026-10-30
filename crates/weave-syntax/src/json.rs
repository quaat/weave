// SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
// SPDX-License-Identifier: MIT

//! A small JSON value, reader and writer (standard library only).
//!
//! The reader is used for the embedded `diagnostics.json` and for the shared
//! conformance manifest in tests; the writer emits CSTs and diagnostics. Numbers
//! keep their source text, so no host numeric type is imposed on them.

use std::fmt::Write as _;

/// Nesting limit of the reader; deeper documents are rejected, never overflowed.
pub const MAX_DEPTH: usize = 512;

#[derive(Clone, Debug, PartialEq)]
pub enum Value {
    Null,
    Bool(bool),
    /// A number, kept as its JSON text.
    Number(String),
    String(String),
    Array(Vec<Value>),
    /// Members in document order.
    Object(Vec<(String, Value)>),
}

impl Value {
    pub fn get(&self, key: &str) -> Option<&Value> {
        match self {
            Value::Object(members) => members.iter().find(|(k, _)| k == key).map(|(_, v)| v),
            _ => None,
        }
    }

    pub fn as_str(&self) -> Option<&str> {
        match self {
            Value::String(s) => Some(s),
            _ => None,
        }
    }

    pub fn as_array(&self) -> Option<&[Value]> {
        match self {
            Value::Array(items) => Some(items),
            _ => None,
        }
    }

    pub fn as_object(&self) -> Option<&[(String, Value)]> {
        match self {
            Value::Object(members) => Some(members),
            _ => None,
        }
    }

    pub fn from_usize(n: usize) -> Value {
        Value::Number(n.to_string())
    }

    pub fn str(s: impl Into<String>) -> Value {
        Value::String(s.into())
    }

    /// Compact JSON text.
    pub fn to_json(&self) -> String {
        let mut out = String::new();
        write_value(self, &mut out, None, 0);
        out
    }

    /// JSON text indented by two spaces per level, with a final newline.
    pub fn to_json_pretty(&self) -> String {
        let mut out = String::new();
        write_value(self, &mut out, Some(2), 0);
        out.push('\n');
        out
    }
}

fn write_string(s: &str, out: &mut String) {
    out.push('"');
    for c in s.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if (c as u32) < 0x20 || c == '\u{7f}' => {
                let _ = write!(out, "\\u{:04x}", c as u32);
            }
            c => out.push(c),
        }
    }
    out.push('"');
}

fn newline(out: &mut String, indent: Option<usize>, level: usize) {
    if let Some(width) = indent {
        out.push('\n');
        out.extend(std::iter::repeat_n(' ', width * level));
    }
}

fn write_value(value: &Value, out: &mut String, indent: Option<usize>, level: usize) {
    match value {
        Value::Null => out.push_str("null"),
        Value::Bool(b) => out.push_str(if *b { "true" } else { "false" }),
        Value::Number(n) => out.push_str(n),
        Value::String(s) => write_string(s, out),
        Value::Array(items) => {
            if items.is_empty() {
                out.push_str("[]");
                return;
            }
            out.push('[');
            for (i, item) in items.iter().enumerate() {
                if i > 0 {
                    out.push(',');
                }
                newline(out, indent, level + 1);
                write_value(item, out, indent, level + 1);
            }
            newline(out, indent, level);
            out.push(']');
        }
        Value::Object(members) => {
            if members.is_empty() {
                out.push_str("{}");
                return;
            }
            out.push('{');
            for (i, (key, item)) in members.iter().enumerate() {
                if i > 0 {
                    out.push(',');
                }
                newline(out, indent, level + 1);
                write_string(key, out);
                out.push(':');
                if indent.is_some() {
                    out.push(' ');
                }
                write_value(item, out, indent, level + 1);
            }
            newline(out, indent, level);
            out.push('}');
        }
    }
}

/// A JSON reading error with its byte offset.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct JsonError {
    pub offset: usize,
    pub message: String,
}

impl std::fmt::Display for JsonError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "JSON error at byte {}: {}", self.offset, self.message)
    }
}

impl std::error::Error for JsonError {}

/// Read one JSON document (RFC 8259); trailing non-whitespace is an error.
pub fn parse(text: &str) -> Result<Value, JsonError> {
    let mut reader = Reader {
        bytes: text.as_bytes(),
        text,
        pos: 0,
    };
    reader.ws();
    let value = reader.value(0)?;
    reader.ws();
    if reader.pos != reader.bytes.len() {
        return Err(reader.error("trailing characters after the document"));
    }
    Ok(value)
}

struct Reader<'a> {
    bytes: &'a [u8],
    text: &'a str,
    pos: usize,
}

impl Reader<'_> {
    fn error(&self, message: &str) -> JsonError {
        JsonError {
            offset: self.pos,
            message: message.to_string(),
        }
    }

    fn peek(&self) -> Option<u8> {
        self.bytes.get(self.pos).copied()
    }

    fn ws(&mut self) {
        while matches!(self.peek(), Some(b' ' | b'\t' | b'\n' | b'\r')) {
            self.pos += 1;
        }
    }

    fn literal(&mut self, word: &str, value: Value) -> Result<Value, JsonError> {
        if self.bytes.get(self.pos..self.pos + word.len()) == Some(word.as_bytes()) {
            self.pos += word.len();
            Ok(value)
        } else {
            Err(self.error("invalid literal"))
        }
    }

    fn value(&mut self, depth: usize) -> Result<Value, JsonError> {
        if depth > MAX_DEPTH {
            return Err(self.error("nesting too deep"));
        }
        match self.peek() {
            Some(b'n') => self.literal("null", Value::Null),
            Some(b't') => self.literal("true", Value::Bool(true)),
            Some(b'f') => self.literal("false", Value::Bool(false)),
            Some(b'"') => self.string().map(Value::String),
            Some(b'[') => {
                self.pos += 1;
                let mut items = Vec::new();
                self.ws();
                if self.peek() == Some(b']') {
                    self.pos += 1;
                    return Ok(Value::Array(items));
                }
                loop {
                    self.ws();
                    items.push(self.value(depth + 1)?);
                    self.ws();
                    match self.peek() {
                        Some(b',') => self.pos += 1,
                        Some(b']') => {
                            self.pos += 1;
                            return Ok(Value::Array(items));
                        }
                        _ => return Err(self.error("expected ',' or ']'")),
                    }
                }
            }
            Some(b'{') => {
                self.pos += 1;
                let mut members = Vec::new();
                self.ws();
                if self.peek() == Some(b'}') {
                    self.pos += 1;
                    return Ok(Value::Object(members));
                }
                loop {
                    self.ws();
                    if self.peek() != Some(b'"') {
                        return Err(self.error("expected a member name"));
                    }
                    let key = self.string()?;
                    self.ws();
                    if self.peek() != Some(b':') {
                        return Err(self.error("expected ':'"));
                    }
                    self.pos += 1;
                    self.ws();
                    let value = self.value(depth + 1)?;
                    members.push((key, value));
                    self.ws();
                    match self.peek() {
                        Some(b',') => self.pos += 1,
                        Some(b'}') => {
                            self.pos += 1;
                            return Ok(Value::Object(members));
                        }
                        _ => return Err(self.error("expected ',' or '}'")),
                    }
                }
            }
            Some(b'-' | b'0'..=b'9') => self.number(),
            _ => Err(self.error("expected a value")),
        }
    }

    fn number(&mut self) -> Result<Value, JsonError> {
        let start = self.pos;
        if self.peek() == Some(b'-') {
            self.pos += 1;
        }
        match self.peek() {
            Some(b'0') => self.pos += 1,
            Some(b'1'..=b'9') => {
                while matches!(self.peek(), Some(b'0'..=b'9')) {
                    self.pos += 1;
                }
            }
            _ => return Err(self.error("invalid number")),
        }
        if self.peek() == Some(b'.') {
            self.pos += 1;
            if !matches!(self.peek(), Some(b'0'..=b'9')) {
                return Err(self.error("invalid fraction"));
            }
            while matches!(self.peek(), Some(b'0'..=b'9')) {
                self.pos += 1;
            }
        }
        if matches!(self.peek(), Some(b'e' | b'E')) {
            self.pos += 1;
            if matches!(self.peek(), Some(b'+' | b'-')) {
                self.pos += 1;
            }
            if !matches!(self.peek(), Some(b'0'..=b'9')) {
                return Err(self.error("invalid exponent"));
            }
            while matches!(self.peek(), Some(b'0'..=b'9')) {
                self.pos += 1;
            }
        }
        let text = self.text.get(start..self.pos).unwrap_or_default();
        Ok(Value::Number(text.to_string()))
    }

    fn hex4(&mut self) -> Result<u32, JsonError> {
        let digits = self
            .text
            .get(self.pos..self.pos + 4)
            .ok_or_else(|| self.error("truncated \\u escape"))?;
        let value =
            u32::from_str_radix(digits, 16).map_err(|_| self.error("invalid \\u escape"))?;
        self.pos += 4;
        Ok(value)
    }

    fn string(&mut self) -> Result<String, JsonError> {
        self.pos += 1; // opening quote
        let mut out = String::new();
        loop {
            let rest = self
                .text
                .get(self.pos..)
                .ok_or_else(|| self.error("invalid position"))?;
            let Some(c) = rest.chars().next() else {
                return Err(self.error("unterminated string"));
            };
            self.pos += c.len_utf8();
            match c {
                '"' => return Ok(out),
                '\\' => {
                    let escape = self.peek().ok_or_else(|| self.error("truncated escape"))?;
                    self.pos += 1;
                    match escape {
                        b'"' => out.push('"'),
                        b'\\' => out.push('\\'),
                        b'/' => out.push('/'),
                        b'b' => out.push('\u{8}'),
                        b'f' => out.push('\u{c}'),
                        b'n' => out.push('\n'),
                        b'r' => out.push('\r'),
                        b't' => out.push('\t'),
                        b'u' => {
                            let high = self.hex4()?;
                            let code = if (0xD800..0xDC00).contains(&high) {
                                if self.bytes.get(self.pos..self.pos + 2) != Some(b"\\u") {
                                    return Err(self.error("unpaired surrogate"));
                                }
                                self.pos += 2;
                                let low = self.hex4()?;
                                if !(0xDC00..0xE000).contains(&low) {
                                    return Err(self.error("unpaired surrogate"));
                                }
                                0x10000 + ((high - 0xD800) << 10) + (low - 0xDC00)
                            } else {
                                high
                            };
                            out.push(
                                char::from_u32(code)
                                    .ok_or_else(|| self.error("invalid code point"))?,
                            );
                        }
                        _ => return Err(self.error("invalid escape")),
                    }
                }
                c if (c as u32) < 0x20 => return Err(self.error("control character in string")),
                c => out.push(c),
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn round_trips_values() {
        let text =
            r#"{"a": [1, -2.5e3, true, false, null], "b": "x\"\\\n\u00e9\ud83d\ude00", "c": {}}"#;
        let value = parse(text).unwrap_or(Value::Null);
        assert_eq!(
            value.get("b").and_then(Value::as_str),
            Some("x\"\\\n\u{e9}\u{1f600}")
        );
        assert_eq!(parse(&value.to_json()), Ok(value.clone()));
        assert_eq!(parse(&value.to_json_pretty()), Ok(value));
    }

    #[test]
    fn rejects_malformed_documents() {
        for bad in [
            "",
            "{",
            "[1,]",
            "{\"a\" 1}",
            "01",
            "\"\\x\"",
            "\"\u{1}\"",
            "1 2",
            "[\"\\ud800\"]",
        ] {
            assert!(parse(bad).is_err(), "{bad:?}");
        }
        let deep = "[".repeat(MAX_DEPTH + 10);
        assert!(parse(&deep).is_err());
    }

    #[test]
    fn escapes_control_characters() {
        assert_eq!(Value::str("\u{0}\u{7f}").to_json(), "\"\\u0000\\u007f\"");
    }
}
