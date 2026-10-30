// SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
// SPDX-License-Identifier: MIT

//! Byte spans and their 1-based line/column positions.

/// A half-open byte range `[start, end)` into the source text.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, Default)]
pub struct Span {
    pub start: usize,
    pub end: usize,
}

impl Span {
    pub fn new(start: usize, end: usize) -> Span {
        Span { start, end }
    }

    /// A zero-width span at `offset`.
    pub fn at(offset: usize) -> Span {
        Span {
            start: offset,
            end: offset,
        }
    }

    pub fn len(&self) -> usize {
        self.end.saturating_sub(self.start)
    }

    pub fn is_empty(&self) -> bool {
        self.end <= self.start
    }

    /// True when `other` lies inside this span.
    pub fn contains(&self, other: Span) -> bool {
        self.start <= other.start && other.end <= self.end
    }
}

/// A 1-based line and column. Columns count Unicode scalar values, as in
/// `weave-diagnostic-v1`; an end column is one past the last character.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Position {
    pub line: usize,
    pub column: usize,
}

/// Maps byte offsets of one source text to lines and columns. Lines end at `\n`;
/// the `\r` of a CRLF ending is the last character of its line.
#[derive(Clone, Debug)]
pub struct LineIndex<'a> {
    text: &'a str,
    starts: Vec<usize>,
}

impl<'a> LineIndex<'a> {
    pub fn new(text: &'a str) -> LineIndex<'a> {
        let mut starts = vec![0];
        starts.extend(text.match_indices('\n').map(|(i, _)| i + 1));
        LineIndex { text, starts }
    }

    /// The position of byte `offset`; offsets past the end, or inside a
    /// multi-byte character, are clamped to the nearest preceding boundary.
    pub fn position(&self, offset: usize) -> Position {
        let mut offset = offset.min(self.text.len());
        while offset > 0 && !self.text.is_char_boundary(offset) {
            offset -= 1;
        }
        let line = match self.starts.binary_search(&offset) {
            Ok(i) => i,
            Err(i) => i.saturating_sub(1),
        };
        let start = self.starts.get(line).copied().unwrap_or(0);
        let column = self
            .text
            .get(start..offset)
            .map_or(0, |s| s.chars().count())
            + 1;
        Position {
            line: line + 1,
            column,
        }
    }
}
