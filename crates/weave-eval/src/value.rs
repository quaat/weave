// SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
// SPDX-License-Identifier: MIT

//! P0 values (`P0-VALUE-1`): exact integers, Booleans, persistent lists and
//! records. Values are immutable; lists share suffixes, so `cons` and `tail`
//! take constant time. Dropping a list is iterative, so a long list never
//! overflows the host stack.

use crate::bigint::BigInt;
use std::rc::Rc;
use weave_check::{Program, Ty};
use weave_syntax::json::Value as Json;

#[derive(Clone, Debug, PartialEq)]
pub enum Value {
    Int(BigInt),
    Bool(bool),
    List(List),
    Record(Rc<RecordValue>),
}

#[derive(Clone, Debug, PartialEq)]
pub struct RecordValue {
    /// Index into [`Program::records`].
    pub record: usize,
    /// Field values in declaration order.
    pub fields: Vec<Value>,
}

/// A persistent singly linked list with its length cached in every node.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct List(Option<Rc<Cons>>);

#[derive(Debug, PartialEq)]
struct Cons {
    head: Value,
    tail: List,
    len: usize,
}

impl Drop for Cons {
    fn drop(&mut self) {
        let mut next = self.tail.0.take();
        while let Some(rc) = next {
            match Rc::try_unwrap(rc) {
                Ok(mut node) => next = node.tail.0.take(),
                Err(_) => break,
            }
        }
    }
}

impl List {
    pub fn empty() -> List {
        List(None)
    }

    pub fn len(&self) -> usize {
        self.0.as_ref().map_or(0, |c| c.len)
    }

    pub fn is_empty(&self) -> bool {
        self.0.is_none()
    }

    pub fn cons(head: Value, tail: List) -> List {
        let len = tail.len() + 1;
        List(Some(Rc::new(Cons { head, tail, len })))
    }

    pub fn head(&self) -> Option<&Value> {
        self.0.as_ref().map(|c| &c.head)
    }

    pub fn tail(&self) -> Option<List> {
        self.0.as_ref().map(|c| c.tail.clone())
    }

    /// The elements in order.
    pub fn iter(&self) -> ListIter<'_> {
        ListIter(self.0.as_deref())
    }

    pub fn from_values(values: Vec<Value>) -> List {
        let mut list = List::empty();
        for v in values.into_iter().rev() {
            list = List::cons(v, list);
        }
        list
    }
}

pub struct ListIter<'a>(Option<&'a Cons>);

impl<'a> Iterator for ListIter<'a> {
    type Item = &'a Value;
    fn next(&mut self) -> Option<&'a Value> {
        let node = self.0?;
        self.0 = node.tail.0.as_deref();
        Some(&node.head)
    }
}

/// A JSON argument that does not match its parameter type (`P0-RUN-1`).
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct DecodeError {
    /// Where in the argument, as in `xs[2].cost`.
    pub path: String,
    pub message: String,
}

/// Decode a JSON value as a P0 value of type `ty` (`P0-RUN-1`).
pub fn from_json(
    json: &Json,
    ty: &Ty,
    program: &Program,
    path: &str,
) -> Result<Value, DecodeError> {
    let fail = |message: String| DecodeError {
        path: path.to_string(),
        message,
    };
    match (ty, json) {
        (Ty::Int, Json::Number(text)) => {
            let integral = {
                let digits = text.strip_prefix('-').unwrap_or(text);
                !digits.is_empty()
                    && digits.bytes().all(|b| b.is_ascii_digit())
                    && (digits == "0" || !digits.starts_with('0'))
            };
            if !integral {
                return Err(fail(format!(
                    "{text} is not an integer: Int arguments are JSON integers without fraction or exponent"
                )));
            }
            BigInt::parse(text)
                .map(Value::Int)
                .ok_or_else(|| fail(format!("{text} is not an integer")))
        }
        (Ty::Bool, Json::Bool(b)) => Ok(Value::Bool(*b)),
        (Ty::List(element), Json::Array(items)) => {
            let mut values = Vec::with_capacity(items.len());
            for (i, item) in items.iter().enumerate() {
                values.push(from_json(item, element, program, &format!("{path}[{i}]"))?);
            }
            Ok(Value::List(List::from_values(values)))
        }
        (Ty::Record(r), Json::Object(members)) => {
            let Some(record) = program.records.get(*r) else {
                return Err(fail("unknown record".into()));
            };
            for (i, (key, _)) in members.iter().enumerate() {
                if !record.fields.iter().any(|(n, _)| n == key) {
                    return Err(fail(format!("record {} has no field {key}", record.name)));
                }
                if members.iter().take(i).any(|(k, _)| k == key) {
                    return Err(fail(format!("field {key} appears twice")));
                }
            }
            let mut fields = Vec::with_capacity(record.fields.len());
            for (name, fty) in &record.fields {
                let Some((_, v)) = members.iter().find(|(k, _)| k == name) else {
                    return Err(fail(format!(
                        "record {} needs the field {name}",
                        record.name
                    )));
                };
                fields.push(from_json(v, fty, program, &format!("{path}.{name}"))?);
            }
            Ok(Value::Record(Rc::new(RecordValue { record: *r, fields })))
        }
        (ty, _) => Err(fail(format!(
            "expected {}, found {}",
            ty.spell(&program.records),
            kind(json)
        ))),
    }
}

fn kind(json: &Json) -> &'static str {
    match json {
        Json::Null => "null",
        Json::Bool(_) => "a Boolean",
        Json::Number(_) => "a number",
        Json::String(_) => "a string",
        Json::Array(_) => "an array",
        Json::Object(_) => "an object",
    }
}

/// Encode a value as JSON (`P0-RUN-2`): integers as JSON integers, lists as
/// arrays, records as objects with fields in declaration order.
pub fn to_json(value: &Value, program: &Program) -> Json {
    match value {
        Value::Int(n) => Json::Number(n.to_decimal()),
        Value::Bool(b) => Json::Bool(*b),
        Value::List(list) => Json::Array(list.iter().map(|v| to_json(v, program)).collect()),
        Value::Record(r) => {
            let names = program.records.get(r.record).map(|rec| &rec.fields);
            Json::Object(
                r.fields
                    .iter()
                    .enumerate()
                    .map(|(i, v)| {
                        let name = names
                            .and_then(|f| f.get(i))
                            .map_or_else(|| format!("field{i}"), |(n, _)| n.clone());
                        (name, to_json(v, program))
                    })
                    .collect(),
            )
        }
    }
}

/// Every integer inside `value`, in order (for the integer-size budget).
pub fn integers<'a>(value: &'a Value, out: &mut Vec<&'a BigInt>) {
    match value {
        Value::Int(n) => out.push(n),
        Value::Bool(_) => {}
        Value::List(list) => list.iter().for_each(|v| integers(v, out)),
        Value::Record(r) => r.fields.iter().for_each(|v| integers(v, out)),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn long_lists_drop_without_recursion() {
        let mut list = List::empty();
        for i in 0..1_000_000 {
            list = List::cons(Value::Int(BigInt::from_i64(i)), list);
        }
        assert_eq!(list.len(), 1_000_000);
        let shared = list.tail().unwrap_or_default();
        drop(list);
        assert_eq!(shared.len(), 999_999);
        assert_eq!(shared.iter().count(), 999_999);
    }
}
