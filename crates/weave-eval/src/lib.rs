// SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
// SPDX-License-Identifier: MIT

//! The P0 evaluator (`specification/docs/chapters/pure.rst`, "Dynamic
//! semantics" and "Budgets").
//!
//! A run takes a checked [`Program`], an entry function, its arguments as
//! JSON and the [`Budgets`]. Its outcome is exactly one of a value, a pure
//! [`Fault`] or an [`Exhaustion`]; both enums are closed, and the evaluator
//! never panics or unwinds for a Weave outcome. Every run reports what it
//! used of each budget ([`Usage`]).

pub mod bigint;
pub mod machine;
pub mod value;

pub use bigint::BigInt;
pub use machine::{
    Budgets, DEFAULT_BUDGETS, Exhaustion, Fault, InternalError, Machine, Outcome, Run, Usage,
};
pub use value::Value;
use weave_check::Program;
use weave_syntax::json::Value as Json;
use weave_syntax::{Diagnostic, Span};

/// Code of an invalid run request (`P0-RUN-1`).
pub const RUN_REQUEST_CODE: &str = "E540";

/// Why a run did not start or did not finish as a Weave outcome.
#[derive(Clone, Debug, PartialEq)]
pub enum RunError {
    /// Unknown entry function or arguments that do not match it (E540).
    Request(Diagnostic),
    /// A defect of this implementation.
    Internal(InternalError),
}

/// Decode `args` (a JSON array, one element per parameter) and call `entry`.
pub fn run(program: &Program, entry: &str, args: &Json, budgets: Budgets) -> Result<Run, RunError> {
    let request = |message: String, span: Span| {
        RunError::Request(Diagnostic::new(RUN_REQUEST_CODE, "run", message, span))
    };
    let Some(index) = program.function(entry) else {
        return Err(request(
            format!("No function named '{entry}' in this file."),
            Span::at(0),
        ));
    };
    let Some(function) = program.functions.get(index) else {
        return Err(request("No such function.".into(), Span::at(0)));
    };
    let Json::Array(items) = args else {
        return Err(request(
            "Arguments are a JSON array with one element per parameter.".into(),
            function.name_span,
        ));
    };
    if items.len() != function.params.len() {
        return Err(request(
            format!(
                "'{entry}' takes {} argument(s), not {}.",
                function.params.len(),
                items.len()
            ),
            function.name_span,
        ));
    }
    let mut values = Vec::with_capacity(items.len());
    for (item, (name, ty)) in items.iter().zip(&function.params) {
        match value::from_json(item, ty, program, name) {
            Ok(v) => values.push(v),
            Err(e) => {
                return Err(request(
                    format!("Argument {}: {}.", e.path, e.message),
                    function.name_span,
                ));
            }
        }
    }
    let machine = Machine::new(program).map_err(RunError::Internal)?;
    machine
        .run(index, values, budgets)
        .map_err(RunError::Internal)
}

/// The diagnostic of a fault or an exhaustion, with its code, rule and span;
/// `None` for a value.
pub fn outcome_diagnostic(run: &Run) -> Option<Diagnostic> {
    let b = run.budgets;
    match &run.outcome {
        Outcome::Value(_) => None,
        Outcome::Fault(fault, span) => Some(Diagnostic::new(
            fault.code(),
            "runtime",
            match fault {
                Fault::DivisionByZero => "Division or remainder by zero (pure fault).".to_string(),
                Fault::EmptyList => "head or tail of an empty list (pure fault).".to_string(),
            },
            *span,
        )),
        Outcome::Exhausted(kind, span) => Some(Diagnostic::new(
            kind.code(),
            "runtime",
            match kind {
                Exhaustion::Fuel => format!(
                    "Fuel budget of {} call(s) exhausted (budget exhaustion, not a fault; fuel is not a termination proof).",
                    b.fuel
                ),
                Exhaustion::Depth => format!(
                    "Depth budget of {} active call(s) exhausted (budget exhaustion, not a fault).",
                    b.depth
                ),
                Exhaustion::IntSize => format!(
                    "Integer size budget of {} bit(s) exhausted (budget exhaustion, not a fault).",
                    b.int_bits
                ),
            },
            *span,
        )),
    }
}

/// The run's budgets and usage as JSON (`P0-BUDGET-1`).
pub fn budgets_json(run: &Run) -> Json {
    let pair = |limit: u64, used: u64, key: &str| {
        Json::Object(vec![
            ("limit".into(), Json::Number(limit.to_string())),
            (key.into(), Json::Number(used.to_string())),
        ])
    };
    Json::Object(vec![
        (
            "fuel".into(),
            pair(run.budgets.fuel, run.usage.fuel, "used"),
        ),
        (
            "depth".into(),
            pair(run.budgets.depth, run.usage.depth, "max"),
        ),
        (
            "int_bits".into(),
            pair(run.budgets.int_bits, run.usage.int_bits, "max"),
        ),
    ])
}
