// SPDX-FileCopyrightText: 2026 Thomas F. Hagelien
// SPDX-License-Identifier: MIT

//! A small arbitrary-precision integer (decision 1A of `core-decisions.rst`:
//! `Int` is the mathematical integers; the integer-size budget, not the host,
//! bounds them). Sign and magnitude, with 32-bit limbs, least significant
//! first. Standard library only, so the workspace keeps building offline
//! (ADR 0009, option 6B: no third-party crate is needed).
//!
//! Operations: decimal parsing and printing, comparison, negation, addition,
//! subtraction, multiplication (schoolbook), Euclidean division and remainder
//! (Knuth's algorithm D), and bit length. None of them panics.

use std::cmp::Ordering;

#[derive(Clone, Debug, PartialEq, Eq, Hash, Default)]
pub struct BigInt {
    /// True only for a nonzero negative value.
    negative: bool,
    /// Magnitude, least significant limb first, without trailing zero limbs.
    magnitude: Vec<u32>,
}

const BASE: u64 = 1 << 32;

fn trim(mut v: Vec<u32>) -> Vec<u32> {
    while v.last() == Some(&0) {
        v.pop();
    }
    v
}

fn cmp_mag(a: &[u32], b: &[u32]) -> Ordering {
    if a.len() != b.len() {
        return a.len().cmp(&b.len());
    }
    for (x, y) in a.iter().rev().zip(b.iter().rev()) {
        match x.cmp(y) {
            Ordering::Equal => {}
            other => return other,
        }
    }
    Ordering::Equal
}

fn add_mag(a: &[u32], b: &[u32]) -> Vec<u32> {
    let (long, short) = if a.len() >= b.len() { (a, b) } else { (b, a) };
    let mut out = Vec::with_capacity(long.len() + 1);
    let mut carry = 0u64;
    for (i, &x) in long.iter().enumerate() {
        let s = u64::from(x) + u64::from(short.get(i).copied().unwrap_or(0)) + carry;
        out.push(s as u32);
        carry = s >> 32;
    }
    if carry > 0 {
        out.push(carry as u32);
    }
    trim(out)
}

/// `a - b` for `a >= b`.
fn sub_mag(a: &[u32], b: &[u32]) -> Vec<u32> {
    let mut out = Vec::with_capacity(a.len());
    let mut borrow = 0i64;
    for (i, &x) in a.iter().enumerate() {
        let mut d = i64::from(x) - i64::from(b.get(i).copied().unwrap_or(0)) - borrow;
        if d < 0 {
            d += BASE as i64;
            borrow = 1;
        } else {
            borrow = 0;
        }
        out.push(d as u32);
    }
    trim(out)
}

fn mul_mag(a: &[u32], b: &[u32]) -> Vec<u32> {
    if a.is_empty() || b.is_empty() {
        return Vec::new();
    }
    let mut out = vec![0u32; a.len() + b.len()];
    for (i, &x) in a.iter().enumerate() {
        let mut carry = 0u64;
        for (j, &y) in b.iter().enumerate() {
            if let Some(slot) = out.get_mut(i + j) {
                let t = u64::from(x) * u64::from(y) + u64::from(*slot) + carry;
                *slot = t as u32;
                carry = t >> 32;
            }
        }
        let mut k = i + b.len();
        while carry > 0 {
            if let Some(slot) = out.get_mut(k) {
                let t = u64::from(*slot) + carry;
                *slot = t as u32;
                carry = t >> 32;
                k += 1;
            } else {
                break;
            }
        }
    }
    trim(out)
}

/// `(a / d, a % d)` for a one-limb divisor `d > 0`.
fn divrem_small(a: &[u32], d: u32) -> (Vec<u32>, u32) {
    let mut q = vec![0u32; a.len()];
    let mut r = 0u64;
    for i in (0..a.len()).rev() {
        let cur = (r << 32) | u64::from(a.get(i).copied().unwrap_or(0));
        if let Some(slot) = q.get_mut(i) {
            *slot = (cur / u64::from(d)) as u32;
        }
        r = cur % u64::from(d);
    }
    (trim(q), r as u32)
}

fn shl_bits(a: &[u32], s: u32, extra: bool) -> Vec<u32> {
    let mut out = Vec::with_capacity(a.len() + 1);
    let mut carry = 0u32;
    for &x in a {
        if s == 0 {
            out.push(x);
        } else {
            out.push((x << s) | carry);
            carry = x >> (32 - s);
        }
    }
    if extra {
        out.push(carry);
    }
    out
}

/// Truncating magnitude division `(a / b, a % b)` for nonzero `b`
/// (Knuth, TAOCP vol. 2, 4.3.1, algorithm D).
fn divrem_mag(a: &[u32], b: &[u32]) -> (Vec<u32>, Vec<u32>) {
    if cmp_mag(a, b) == Ordering::Less {
        return (Vec::new(), a.to_vec());
    }
    let n = b.len();
    if n == 1 {
        let (q, r) = divrem_small(a, b.first().copied().unwrap_or(1));
        return (q, trim(vec![r]));
    }
    let m = a.len() - n;
    let s = b.last().copied().unwrap_or(1).leading_zeros();
    let vn = shl_bits(b, s, false);
    let mut un = shl_bits(a, s, true);
    let mut q = vec![0u32; m + 1];
    let at = |v: &[u32], i: usize| u64::from(v.get(i).copied().unwrap_or(0));
    let v1 = at(&vn, n - 1);
    let v2 = at(&vn, n - 2);
    for j in (0..=m).rev() {
        let num = (at(&un, j + n) << 32) | at(&un, j + n - 1);
        let mut qhat = num / v1;
        let mut rhat = num % v1;
        while qhat >= BASE
            || u128::from(qhat) * u128::from(v2)
                > (u128::from(rhat) << 32) + u128::from(at(&un, j + n - 2))
        {
            qhat -= 1;
            rhat += v1;
            if rhat >= BASE {
                break;
            }
        }
        // Multiply and subtract.
        let mut k: i64 = 0;
        for i in 0..n {
            let p = qhat * at(&vn, i);
            let t = at(&un, i + j) as i64 - k - (p & 0xFFFF_FFFF) as i64;
            if let Some(slot) = un.get_mut(i + j) {
                *slot = t as u32;
            }
            k = (p >> 32) as i64 - (t >> 32);
        }
        let t = at(&un, j + n) as i64 - k;
        if let Some(slot) = un.get_mut(j + n) {
            *slot = t as u32;
        }
        if t < 0 {
            // Add back.
            qhat -= 1;
            let mut c = 0u64;
            for i in 0..n {
                let s2 = at(&un, i + j) + at(&vn, i) + c;
                if let Some(slot) = un.get_mut(i + j) {
                    *slot = s2 as u32;
                }
                c = s2 >> 32;
            }
            if let Some(slot) = un.get_mut(j + n) {
                *slot = slot.wrapping_add(c as u32);
            }
        }
        if let Some(slot) = q.get_mut(j) {
            *slot = qhat as u32;
        }
    }
    // Unnormalise the remainder.
    let mut r = vec![0u32; n];
    for i in 0..n {
        let lo = at(&un, i) >> s;
        let hi = if s == 0 {
            0
        } else {
            (at(&un, i + 1) << (32 - s)) & 0xFFFF_FFFF
        };
        if let Some(slot) = r.get_mut(i) {
            *slot = (lo | hi) as u32;
        }
    }
    (trim(q), trim(r))
}

impl BigInt {
    pub fn zero() -> BigInt {
        BigInt::default()
    }

    fn from_parts(negative: bool, magnitude: Vec<u32>) -> BigInt {
        let magnitude = trim(magnitude);
        BigInt {
            negative: negative && !magnitude.is_empty(),
            magnitude,
        }
    }

    pub fn from_i64(v: i64) -> BigInt {
        let m = v.unsigned_abs();
        BigInt::from_parts(v < 0, vec![m as u32, (m >> 32) as u32])
    }

    pub fn from_u64(v: u64) -> BigInt {
        BigInt::from_parts(false, vec![v as u32, (v >> 32) as u32])
    }

    /// The value as an `i128` when it fits.
    pub fn to_i128(&self) -> Option<i128> {
        if self.magnitude.len() > 4 {
            return None;
        }
        let mut m: u128 = 0;
        for &limb in self.magnitude.iter().rev() {
            m = (m << 32) | u128::from(limb);
        }
        if self.negative {
            if m <= i128::MAX as u128 + 1 {
                Some((m as i128).wrapping_neg())
            } else {
                None
            }
        } else {
            i128::try_from(m).ok()
        }
    }

    /// Parse `-?[0-9]+`; `None` for anything else, including an empty string.
    pub fn parse(text: &str) -> Option<BigInt> {
        let (negative, digits) = match text.strip_prefix('-') {
            Some(rest) => (true, rest),
            None => (false, text),
        };
        if digits.is_empty() || !digits.bytes().all(|b| b.is_ascii_digit()) {
            return None;
        }
        let mut mag: Vec<u32> = Vec::new();
        for chunk in digits.as_bytes().chunks(9) {
            let mut value = 0u64;
            let mut scale = 1u64;
            for &b in chunk {
                value = value * 10 + u64::from(b - b'0');
                scale *= 10;
            }
            // mag = mag * scale + value
            let mut carry = value;
            for limb in mag.iter_mut() {
                let t = u64::from(*limb) * scale + carry;
                *limb = t as u32;
                carry = t >> 32;
            }
            while carry > 0 {
                mag.push(carry as u32);
                carry >>= 32;
            }
        }
        Some(BigInt::from_parts(negative, mag))
    }

    pub fn is_zero(&self) -> bool {
        self.magnitude.is_empty()
    }

    pub fn is_negative(&self) -> bool {
        self.negative
    }

    /// Bit length of the magnitude: 0 for zero, otherwise the number of bits
    /// of `abs(self)` (`P0-BUDGET-4`).
    pub fn bits(&self) -> u64 {
        match self.magnitude.last() {
            None => 0,
            Some(top) => {
                (self.magnitude.len() as u64 - 1) * 32 + u64::from(32 - top.leading_zeros())
            }
        }
    }

    pub fn neg(&self) -> BigInt {
        BigInt::from_parts(!self.negative, self.magnitude.clone())
    }

    pub fn add(&self, other: &BigInt) -> BigInt {
        if self.negative == other.negative {
            return BigInt::from_parts(self.negative, add_mag(&self.magnitude, &other.magnitude));
        }
        match cmp_mag(&self.magnitude, &other.magnitude) {
            Ordering::Equal => BigInt::zero(),
            Ordering::Greater => {
                BigInt::from_parts(self.negative, sub_mag(&self.magnitude, &other.magnitude))
            }
            Ordering::Less => {
                BigInt::from_parts(other.negative, sub_mag(&other.magnitude, &self.magnitude))
            }
        }
    }

    pub fn sub(&self, other: &BigInt) -> BigInt {
        self.add(&other.neg())
    }

    pub fn mul(&self, other: &BigInt) -> BigInt {
        BigInt::from_parts(
            self.negative != other.negative,
            mul_mag(&self.magnitude, &other.magnitude),
        )
    }

    /// Euclidean division (decision D3): `self = d * q + r` with
    /// `0 <= r < abs(d)`. `None` when `d` is zero.
    pub fn div_rem_euclid(&self, d: &BigInt) -> Option<(BigInt, BigInt)> {
        if d.is_zero() {
            return None;
        }
        let (qm, rm) = divrem_mag(&self.magnitude, &d.magnitude);
        if !self.negative {
            return Some((
                BigInt::from_parts(d.negative, qm),
                BigInt::from_parts(false, rm),
            ));
        }
        if rm.is_empty() {
            return Some((BigInt::from_parts(!d.negative, qm), BigInt::zero()));
        }
        // a < 0, r != 0: q = -sign(d) * (qm + 1), r = abs(d) - rm.
        let q = BigInt::from_parts(!d.negative, add_mag(&qm, &[1]));
        let r = BigInt::from_parts(false, sub_mag(&d.magnitude, &rm));
        Some((q, r))
    }

    /// Decimal text, with a leading `-` for negative values.
    pub fn to_decimal(&self) -> String {
        if self.is_zero() {
            return "0".into();
        }
        let mut chunks = Vec::new();
        let mut mag = self.magnitude.clone();
        while !mag.is_empty() {
            let (q, r) = divrem_small(&mag, 1_000_000_000);
            chunks.push(r);
            mag = q;
        }
        let mut out = String::new();
        if self.negative {
            out.push('-');
        }
        for (i, chunk) in chunks.iter().rev().enumerate() {
            if i == 0 {
                out.push_str(&chunk.to_string());
            } else {
                out.push_str(&format!("{chunk:09}"));
            }
        }
        out
    }
}

impl Ord for BigInt {
    fn cmp(&self, other: &BigInt) -> Ordering {
        match (self.negative, other.negative) {
            (false, true) => Ordering::Greater,
            (true, false) => Ordering::Less,
            (false, false) => cmp_mag(&self.magnitude, &other.magnitude),
            (true, true) => cmp_mag(&other.magnitude, &self.magnitude),
        }
    }
}

impl PartialOrd for BigInt {
    fn partial_cmp(&self, other: &BigInt) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}

impl std::fmt::Display for BigInt {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.to_decimal())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A deterministic generator (xorshift64*), so the tests need no crate.
    struct Rng(u64);
    impl Rng {
        fn next(&mut self) -> u64 {
            self.0 ^= self.0 >> 12;
            self.0 ^= self.0 << 25;
            self.0 ^= self.0 >> 27;
            self.0.wrapping_mul(0x2545_F491_4F6C_DD1D)
        }
        fn i128(&mut self) -> i128 {
            let bits = self.next() % 120;
            let v = (i128::from(self.next()) << 64 | i128::from(self.next())) >> (127 - bits);
            if self.next() % 2 == 0 { v } else { -v }
        }
        fn big(&mut self, limbs: usize) -> BigInt {
            let mag = (0..limbs).map(|_| self.next() as u32).collect();
            BigInt::from_parts(self.next() % 2 == 0, mag)
        }
    }

    fn b(v: i128) -> BigInt {
        BigInt::parse(&v.to_string()).unwrap_or_default()
    }

    /// Euclidean division over i128, written from D3 independently of the code above.
    fn euclid(a: i128, d: i128) -> (i128, i128) {
        let mut r = a % d;
        if r < 0 {
            r += d.abs();
        }
        ((a - r) / d, r)
    }

    #[test]
    fn decimal_round_trip_and_canonical_zero() {
        for text in [
            "0",
            "1",
            "-1",
            "4294967296",
            "-18446744073709551616",
            "123456789012345678901234567890",
        ] {
            assert_eq!(
                BigInt::parse(text).map(|v| v.to_decimal()).as_deref(),
                Some(text)
            );
        }
        assert_eq!(BigInt::parse("-0"), Some(BigInt::zero()));
        assert_eq!(
            BigInt::parse("007").map(|v| v.to_decimal()).as_deref(),
            Some("7")
        );
        for bad in ["", "-", "1.0", "1e3", "+1", " 1", "٣"] {
            assert_eq!(BigInt::parse(bad), None, "{bad:?}");
        }
    }

    #[test]
    fn arithmetic_agrees_with_i128() {
        let mut rng = Rng(0x9E37_79B9_7F4A_7C15);
        for _ in 0..20_000 {
            let (x, y) = (rng.i128() >> 2, rng.i128() >> 2);
            assert_eq!(b(x).add(&b(y)), b(x + y), "{x} + {y}");
            assert_eq!(b(x).sub(&b(y)), b(x - y), "{x} - {y}");
            assert_eq!(b(x).cmp(&b(y)), x.cmp(&y));
            assert_eq!(b(x).to_i128(), Some(x));
            let (sx, sy) = (x >> 60, y >> 60);
            assert_eq!(b(sx).mul(&b(sy)), b(sx * sy), "{sx} * {sy}");
            if y != 0 {
                let (q, r) = euclid(x, y);
                assert_eq!(
                    b(x).div_rem_euclid(&b(y)),
                    Some((b(q), b(r))),
                    "{x} divmod {y}"
                );
            }
        }
    }

    #[test]
    fn euclidean_signs_and_zero_divisor() {
        for (a, d, q, r) in [
            (7, 2, 3, 1),
            (-7, 2, -4, 1),
            (7, -2, -3, 1),
            (-7, -2, 4, 1),
            (6, 3, 2, 0),
            (-6, 3, -2, 0),
            (0, -5, 0, 0),
        ] {
            assert_eq!(b(a).div_rem_euclid(&b(d)), Some((b(q), b(r))), "{a} {d}");
        }
        assert_eq!(b(5).div_rem_euclid(&BigInt::zero()), None);
        assert_eq!(BigInt::zero().div_rem_euclid(&BigInt::zero()), None);
    }

    #[test]
    fn large_division_satisfies_the_identity() {
        let mut rng = Rng(42);
        for round in 0..2_000 {
            let a = rng.big(1 + (round % 9));
            let d = rng.big(1 + (round % 5));
            let Some((q, r)) = a.div_rem_euclid(&d) else {
                assert!(d.is_zero());
                continue;
            };
            assert_eq!(d.mul(&q).add(&r), a, "a = d*q + r");
            assert!(!r.is_negative());
            assert!(r < BigInt::from_parts(false, d.magnitude.clone()));
        }
        // Knuth D corner: a divisor whose top limbs force the add-back step.
        let a = BigInt::parse("340282366920938463444927863358058659840").unwrap_or_default();
        let d = BigInt::parse("18446744073709551615").unwrap_or_default();
        let (q, r) = a.div_rem_euclid(&d).unwrap_or_default();
        assert_eq!(d.mul(&q).add(&r), a);
    }

    #[test]
    fn bit_lengths() {
        assert_eq!(BigInt::zero().bits(), 0);
        assert_eq!(b(1).bits(), 1);
        assert_eq!(b(-1).bits(), 1);
        assert_eq!(b(255).bits(), 8);
        assert_eq!(b(256).bits(), 9);
        assert_eq!(b(-(1 << 40)).bits(), 41);
        assert_eq!(BigInt::from_u64(u64::MAX).bits(), 64);
        assert_eq!(BigInt::from_i64(i64::MIN).bits(), 64);
    }
}
