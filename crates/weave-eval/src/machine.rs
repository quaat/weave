// SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
// SPDX-License-Identifier: MIT

//! Lowering of the typed program to instructions, and the evaluator.
//!
//! Each function body becomes a flat instruction list; every instruction
//! carries the span of the typed expression it implements, so faults and
//! exhaustion are reported at source (source mapping). The evaluator keeps
//! an explicit stack of call frames: a Weave call pushes a frame and never
//! recurses on the host stack. Within a frame, operands are on a value stack.
//!
//! Semantics (`pure.rst`): operands and arguments are evaluated left to right
//! (`P0-EVAL-1`); `and` and `or` skip their right operand when the left one
//! decides (`P0-EVAL-2`); each user-function call, the entry call included,
//! first takes one unit of fuel, then a depth slot (`P0-EVAL-3`,
//! `P0-BUDGET-2`, `P0-BUDGET-3`); every integer produced is checked against
//! the size budget (`P0-BUDGET-4`).

use crate::bigint::BigInt;
use crate::value::{List, RecordValue, Value, integers};
use std::rc::Rc;
use weave_check::typed::{ArithOp, Block, CmpOp, Expr, ExprK, Terminal};
use weave_check::{Prim, Program};
use weave_syntax::Span;

/// Run parameters (`P0-BUDGET-1`). The defaults are this tool's; a run always
/// reports the budgets it used.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Budgets {
    /// Maximum number of user-function calls, the entry call included.
    pub fuel: u64,
    /// Maximum number of simultaneously active calls.
    pub depth: u64,
    /// Maximum bit length of the magnitude of any integer.
    pub int_bits: u64,
}

pub const DEFAULT_BUDGETS: Budgets = Budgets {
    fuel: 1_000_000,
    depth: 10_000,
    int_bits: 65_536,
};

impl Default for Budgets {
    fn default() -> Budgets {
        DEFAULT_BUDGETS
    }
}

/// What a run used, within its budgets.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Usage {
    /// Calls admitted.
    pub fuel: u64,
    /// Largest number of simultaneously active calls.
    pub depth: u64,
    /// Largest bit length of an admitted integer.
    pub int_bits: u64,
}

/// The closed set of pure faults (`P0-FAULT-1`).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Fault {
    /// `div` or `mod` with a zero divisor (`P0-ARITH-2`, E520).
    DivisionByZero,
    /// `head` or `tail` of an empty list (`P0-LIST-1`, E521).
    EmptyList,
}

impl Fault {
    pub fn name(self) -> &'static str {
        match self {
            Fault::DivisionByZero => "division-by-zero",
            Fault::EmptyList => "empty-list",
        }
    }
    pub fn code(self) -> &'static str {
        match self {
            Fault::DivisionByZero => "E520",
            Fault::EmptyList => "E521",
        }
    }
}

/// The closed set of exhausted budgets (`P0-BUDGET-1`); never a fault.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Exhaustion {
    Fuel,
    Depth,
    IntSize,
}

impl Exhaustion {
    pub fn name(self) -> &'static str {
        match self {
            Exhaustion::Fuel => "fuel",
            Exhaustion::Depth => "depth",
            Exhaustion::IntSize => "int-size",
        }
    }
    pub fn code(self) -> &'static str {
        match self {
            Exhaustion::Fuel => "E530",
            Exhaustion::Depth => "E531",
            Exhaustion::IntSize => "E532",
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub enum Outcome {
    Value(Value),
    Fault(Fault, Span),
    Exhausted(Exhaustion, Span),
}

#[derive(Clone, Debug, PartialEq)]
pub struct Run {
    pub outcome: Outcome,
    pub usage: Usage,
    pub budgets: Budgets,
}

/// An inconsistency between the checker and the evaluator: a defect, never a
/// Weave outcome.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct InternalError(pub String);

#[derive(Clone, Debug)]
enum Op {
    Int(BigInt),
    Bool(bool),
    Load(usize),
    Store(usize),
    Neg,
    Arith(ArithOp),
    Cmp(CmpOp),
    Field(usize),
    /// Pop one value per written field, in written order; `order[i]` is the
    /// declared index of the i-th written field.
    Construct {
        record: usize,
        order: Vec<usize>,
    },
    List(usize),
    Prim(Prim),
    Call {
        function: usize,
        argc: usize,
    },
    JumpIfFalse(usize),
    Jump(usize),
    Return,
}

#[derive(Clone, Debug)]
struct Instr {
    op: Op,
    span: Span,
}

/// A program lowered to instructions, ready to run any number of times.
#[derive(Clone, Debug)]
pub struct Machine<'p> {
    program: &'p Program,
    code: Vec<Vec<Instr>>,
}

struct Frame {
    function: usize,
    pc: usize,
    locals: Vec<Option<Value>>,
    stack: Vec<Value>,
}

fn internal(what: &str) -> InternalError {
    InternalError(format!("internal evaluator error: {what}"))
}

impl<'p> Machine<'p> {
    pub fn new(program: &'p Program) -> Result<Machine<'p>, InternalError> {
        let mut code = Vec::new();
        for f in &program.functions {
            let mut out = Vec::new();
            lower_block(&f.body, &mut out)?;
            code.push(out);
        }
        Ok(Machine { program, code })
    }

    pub fn program(&self) -> &'p Program {
        self.program
    }

    /// Call `function` with `args` under `budgets`. `entry_span` locates the
    /// entry call (and over-budget arguments) in reports.
    pub fn run(
        &self,
        function: usize,
        args: Vec<Value>,
        budgets: Budgets,
    ) -> Result<Run, InternalError> {
        let mut usage = Usage::default();
        let entry_span = self
            .program
            .functions
            .get(function)
            .map_or(Span::at(0), |f| f.name_span);
        let done = |outcome, usage| {
            Ok(Run {
                outcome,
                usage,
                budgets,
            })
        };
        // Arguments are checked against the size budget before the entry call.
        let mut ints = Vec::new();
        args.iter().for_each(|v| integers(v, &mut ints));
        for n in ints {
            if n.bits() > budgets.int_bits {
                return done(Outcome::Exhausted(Exhaustion::IntSize, entry_span), usage);
            }
            usage.int_bits = usage.int_bits.max(n.bits());
        }
        let mut frames: Vec<Frame> = Vec::new();
        if let Some(stop) =
            self.enter(function, args, entry_span, &mut frames, &mut usage, budgets)?
        {
            return done(stop, usage);
        }
        loop {
            let Some(frame) = frames.last_mut() else {
                return Err(internal("no frame"));
            };
            let Some(instr) = self.code.get(frame.function).and_then(|c| c.get(frame.pc)) else {
                return Err(internal("pc out of range"));
            };
            frame.pc += 1;
            let span = instr.span;
            let pop =
                |frame: &mut Frame| frame.stack.pop().ok_or_else(|| internal("stack underflow"));
            match &instr.op {
                Op::Int(n) => {
                    if let Some(stop) = admit(n, span, &mut usage, budgets) {
                        return done(stop, usage);
                    }
                    frame.stack.push(Value::Int(n.clone()));
                }
                Op::Bool(b) => frame.stack.push(Value::Bool(*b)),
                Op::Load(slot) => {
                    let v = frame
                        .locals
                        .get(*slot)
                        .and_then(Option::clone)
                        .ok_or_else(|| internal("unset local"))?;
                    frame.stack.push(v);
                }
                Op::Store(slot) => {
                    let v = pop(frame)?;
                    let cell = frame
                        .locals
                        .get_mut(*slot)
                        .ok_or_else(|| internal("bad slot"))?;
                    *cell = Some(v);
                }
                Op::Neg => {
                    let Value::Int(a) = pop(frame)? else {
                        return Err(internal("neg"));
                    };
                    let r = a.neg();
                    if let Some(stop) = admit(&r, span, &mut usage, budgets) {
                        return done(stop, usage);
                    }
                    frame.stack.push(Value::Int(r));
                }
                Op::Arith(op) => {
                    let (Value::Int(b), Value::Int(a)) = (pop(frame)?, pop(frame)?) else {
                        return Err(internal("arith"));
                    };
                    let r = match op {
                        ArithOp::Add => a.add(&b),
                        ArithOp::Sub => a.sub(&b),
                        ArithOp::Mul => a.mul(&b),
                    };
                    if let Some(stop) = admit(&r, span, &mut usage, budgets) {
                        return done(stop, usage);
                    }
                    frame.stack.push(Value::Int(r));
                }
                Op::Cmp(op) => {
                    let (b, a) = (pop(frame)?, pop(frame)?);
                    let r = match (op, &a, &b) {
                        (CmpOp::Eq, _, _) => a == b,
                        (CmpOp::Ne, _, _) => a != b,
                        (_, Value::Int(x), Value::Int(y)) => match op {
                            CmpOp::Lt => x < y,
                            CmpOp::Le => x <= y,
                            CmpOp::Gt => x > y,
                            _ => x >= y,
                        },
                        _ => return Err(internal("compare")),
                    };
                    frame.stack.push(Value::Bool(r));
                }
                Op::Field(i) => {
                    let Value::Record(r) = pop(frame)? else {
                        return Err(internal("field"));
                    };
                    let v = r
                        .fields
                        .get(*i)
                        .cloned()
                        .ok_or_else(|| internal("field index"))?;
                    frame.stack.push(v);
                }
                Op::Construct { record, order } => {
                    let at = frame
                        .stack
                        .len()
                        .checked_sub(order.len())
                        .ok_or_else(|| internal("construct"))?;
                    let written = frame.stack.split_off(at);
                    let mut fields: Vec<Option<Value>> = vec![None; order.len()];
                    for (index, v) in order.iter().zip(written) {
                        let cell = fields
                            .get_mut(*index)
                            .ok_or_else(|| internal("construct index"))?;
                        *cell = Some(v);
                    }
                    let fields = fields
                        .into_iter()
                        .collect::<Option<Vec<_>>>()
                        .ok_or_else(|| internal("missing field"))?;
                    frame.stack.push(Value::Record(Rc::new(RecordValue {
                        record: *record,
                        fields,
                    })));
                }
                Op::List(n) => {
                    let at = frame
                        .stack
                        .len()
                        .checked_sub(*n)
                        .ok_or_else(|| internal("list"))?;
                    let items = frame.stack.split_off(at);
                    frame.stack.push(Value::List(List::from_values(items)));
                }
                Op::Prim(p) => match self.primitive(*p, frame, span, &mut usage, budgets)? {
                    Ok(v) => frame.stack.push(v),
                    Err(stop) => return done(stop, usage),
                },
                Op::Call { function, argc } => {
                    let at = frame
                        .stack
                        .len()
                        .checked_sub(*argc)
                        .ok_or_else(|| internal("call"))?;
                    let args = frame.stack.split_off(at);
                    if let Some(stop) =
                        self.enter(*function, args, span, &mut frames, &mut usage, budgets)?
                    {
                        return done(stop, usage);
                    }
                }
                Op::JumpIfFalse(target) => match pop(frame)? {
                    Value::Bool(false) => frame.pc = *target,
                    Value::Bool(true) => {}
                    _ => return Err(internal("condition")),
                },
                Op::Jump(target) => frame.pc = *target,
                Op::Return => {
                    let v = pop(frame)?;
                    frames.pop();
                    match frames.last_mut() {
                        Some(caller) => caller.stack.push(v),
                        None => return done(Outcome::Value(v), usage),
                    }
                }
            }
        }
    }

    /// Admit a call: one unit of fuel, then one depth slot (`P0-EVAL-3`).
    fn enter(
        &self,
        function: usize,
        args: Vec<Value>,
        span: Span,
        frames: &mut Vec<Frame>,
        usage: &mut Usage,
        budgets: Budgets,
    ) -> Result<Option<Outcome>, InternalError> {
        if usage.fuel >= budgets.fuel {
            return Ok(Some(Outcome::Exhausted(Exhaustion::Fuel, span)));
        }
        usage.fuel += 1;
        if frames.len() as u64 >= budgets.depth {
            return Ok(Some(Outcome::Exhausted(Exhaustion::Depth, span)));
        }
        let f = self
            .program
            .functions
            .get(function)
            .ok_or_else(|| internal("function"))?;
        if args.len() != f.params.len() {
            return Err(internal("argument count"));
        }
        let mut locals: Vec<Option<Value>> = args.into_iter().map(Some).collect();
        locals.resize(f.locals.max(locals.len()), None);
        frames.push(Frame {
            function,
            pc: 0,
            locals,
            stack: Vec::new(),
        });
        usage.depth = usage.depth.max(frames.len() as u64);
        Ok(None)
    }

    fn primitive(
        &self,
        p: Prim,
        frame: &mut Frame,
        span: Span,
        usage: &mut Usage,
        budgets: Budgets,
    ) -> Result<Result<Value, Outcome>, InternalError> {
        let mut pop = || frame.stack.pop().ok_or_else(|| internal("stack underflow"));
        Ok(match p {
            Prim::Not => match pop()? {
                Value::Bool(b) => Ok(Value::Bool(!b)),
                _ => return Err(internal("not")),
            },
            Prim::Div | Prim::Mod => {
                let (Value::Int(d), Value::Int(a)) = (pop()?, pop()?) else {
                    return Err(internal("div"));
                };
                match a.div_rem_euclid(&d) {
                    None => Err(Outcome::Fault(Fault::DivisionByZero, span)),
                    Some((q, r)) => {
                        let v = if p == Prim::Div { q } else { r };
                        match admit(&v, span, usage, budgets) {
                            Some(stop) => Err(stop),
                            None => Ok(Value::Int(v)),
                        }
                    }
                }
            }
            Prim::Cons => {
                let (Value::List(xs), x) = (pop()?, pop()?) else {
                    return Err(internal("cons"));
                };
                Ok(Value::List(List::cons(x, xs)))
            }
            Prim::Length | Prim::IsEmpty | Prim::Head | Prim::Tail => {
                let Value::List(xs) = pop()? else {
                    return Err(internal("list primitive"));
                };
                match p {
                    Prim::Length => {
                        let n = BigInt::from_u64(xs.len() as u64);
                        match admit(&n, span, usage, budgets) {
                            Some(stop) => Err(stop),
                            None => Ok(Value::Int(n)),
                        }
                    }
                    Prim::IsEmpty => Ok(Value::Bool(xs.is_empty())),
                    Prim::Head => match xs.head() {
                        Some(v) => Ok(v.clone()),
                        None => Err(Outcome::Fault(Fault::EmptyList, span)),
                    },
                    _ => match xs.tail() {
                        Some(t) => Ok(Value::List(t)),
                        None => Err(Outcome::Fault(Fault::EmptyList, span)),
                    },
                }
            }
        })
    }
}

/// `P0-BUDGET-4`: an integer is admitted only within the size budget.
fn admit(n: &BigInt, span: Span, usage: &mut Usage, budgets: Budgets) -> Option<Outcome> {
    let bits = n.bits();
    if bits > budgets.int_bits {
        return Some(Outcome::Exhausted(Exhaustion::IntSize, span));
    }
    usage.int_bits = usage.int_bits.max(bits);
    None
}

fn emit(out: &mut Vec<Instr>, op: Op, span: Span) -> usize {
    out.push(Instr { op, span });
    out.len() - 1
}

fn patch(out: &mut [Instr], at: usize, target: usize) {
    if let Some(i) = out.get_mut(at) {
        match &mut i.op {
            Op::JumpIfFalse(t) | Op::Jump(t) => *t = target,
            _ => {}
        }
    }
}

fn lower_block(block: &Block, out: &mut Vec<Instr>) -> Result<(), InternalError> {
    for (slot, value) in &block.lets {
        lower_expr(value, out)?;
        emit(out, Op::Store(*slot), value.span);
    }
    match &*block.end {
        Terminal::Return(e) => {
            lower_expr(e, out)?;
            emit(out, Op::Return, e.span);
        }
        Terminal::If {
            cond,
            then,
            otherwise,
        } => {
            lower_expr(cond, out)?;
            let jump = emit(out, Op::JumpIfFalse(0), cond.span);
            lower_block(then, out)?;
            let target = out.len();
            patch(out, jump, target);
            lower_block(otherwise, out)?;
        }
    }
    Ok(())
}

fn lower_expr(e: &Expr, out: &mut Vec<Instr>) -> Result<(), InternalError> {
    let span = e.span;
    match &e.kind {
        ExprK::Int(text) => {
            let n = BigInt::parse(text).ok_or_else(|| internal("literal"))?;
            emit(out, Op::Int(n), span);
        }
        ExprK::Bool(b) => {
            emit(out, Op::Bool(*b), span);
        }
        ExprK::Local(slot) => {
            emit(out, Op::Load(*slot), span);
        }
        ExprK::Field(x, i) => {
            lower_expr(x, out)?;
            emit(out, Op::Field(*i), span);
        }
        ExprK::Call(f, args) => {
            for a in args {
                lower_expr(a, out)?;
            }
            emit(
                out,
                Op::Call {
                    function: *f,
                    argc: args.len(),
                },
                span,
            );
        }
        ExprK::Prim(p, args) => {
            for a in args {
                lower_expr(a, out)?;
            }
            emit(out, Op::Prim(*p), span);
        }
        ExprK::Construct(record, fields) => {
            for (_, v) in fields {
                lower_expr(v, out)?;
            }
            let order = fields.iter().map(|(i, _)| *i).collect();
            emit(
                out,
                Op::Construct {
                    record: *record,
                    order,
                },
                span,
            );
        }
        ExprK::List(items) => {
            for i in items {
                lower_expr(i, out)?;
            }
            emit(out, Op::List(items.len()), span);
        }
        ExprK::Neg(x) => {
            lower_expr(x, out)?;
            emit(out, Op::Neg, span);
        }
        ExprK::Arith(op, l, r) => {
            lower_expr(l, out)?;
            lower_expr(r, out)?;
            emit(out, Op::Arith(*op), span);
        }
        ExprK::Compare(op, l, r) => {
            lower_expr(l, out)?;
            lower_expr(r, out)?;
            emit(out, Op::Cmp(*op), span);
        }
        ExprK::And(l, r) => {
            lower_expr(l, out)?;
            let skip = emit(out, Op::JumpIfFalse(0), span);
            lower_expr(r, out)?;
            let end = emit(out, Op::Jump(0), span);
            let target = out.len();
            patch(out, skip, target);
            emit(out, Op::Bool(false), span);
            let target = out.len();
            patch(out, end, target);
        }
        ExprK::Or(l, r) => {
            lower_expr(l, out)?;
            let right = emit(out, Op::JumpIfFalse(0), span);
            emit(out, Op::Bool(true), span);
            let end = emit(out, Op::Jump(0), span);
            let target = out.len();
            patch(out, right, target);
            lower_expr(r, out)?;
            let target = out.len();
            patch(out, end, target);
        }
    }
    Ok(())
}
