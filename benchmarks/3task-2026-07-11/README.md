# Tua Agent v0.0.2 — 3-Task Benchmark

**Date:** 2026-07-11  
**Model:** deepseek/deepseek-v4-flash (via 9Router)  
**Profile:** rustacean  
**Agent:** Tua Agent v0.0.2

---

## Task 1: `split_pair` — Memory & Lifetimes

**โจทย์:** เขียนฟังก์ชัน `split_pair` ที่รับ `&str` และคืน `(&str, &str)` โดยแยกคำด้วยช่องว่างตัวแรก ห้าม allocate หน่วยความจำใหม่ ต้องระบุ Lifetime Annotation ให้ถูกต้อง

**สิ่งที่ Tua ทำ:**
- ใช้ `s.find(' ')` หาช่องว่างตำแหน่งแรก → slice `&s[..idx]` และ `&s[idx+1..]`
- Explicit lifetime `'a` บนฟังก์ชัน — `fn split_pair<'a>(s: &'a str) -> (&'a str, &'a str)`
- Zero heap allocation — ทำงานบน stack ทั้งหมด
- `#[allow(clippy::needless_lifetimes)]` เพราะ elision ก็พอ แต่โจทย์บังคับ explicit

**ผลลัพธ์:**
- ✅ 8 unit tests + 1 doc-test — all pass
- ✅ Clippy: zero warnings
- ✅ Edge cases: empty, leading space, trailing space, only spaces, lifetime linkage

```rust
pub fn split_pair<'a>(s: &'a str) -> (&'a str, &'a str) {
    match s.find(' ') {
        Some(idx) => (&s[..idx], &s[idx + 1..]),
        None => (s, ""),
    }
}
```

---

## Task 2: `apply_twice` — Advanced Traits & Closures

**โจทย์:** เขียนฟังก์ชัน Generic `apply_twice` ที่รับค่า `x` และ closure `f` แล้วเรียก `f(f(x))` เลือกใช้ Fn/FnMut/FnOnce ให้ยืดหยุ่นที่สุด

**สิ่งที่ Tua ทำ:**
- **เลือก `FnMut`** — ถูกต้องที่สุด! เพราะ:
  - `Fn` closures ทำงานได้ (Fn สืบทอด FnMut)
  - `FnMut` closures ทำงานได้ (แก้ไข captured variables ได้)
  - `move` closures ที่ไม่ consume captures ก็ทำงานได้
  - `FnOnce` ไม่สามารถเรียกซ้ำได้ — จึงไม่ใช่คำตอบ
- แก้ borrow-checker: `let intermediate = f(x); f(intermediate)` — แยกการเรียกสองครั้ง

**ผลลัพธ์:**
- ✅ 9 unit tests + 4 doc-tests — all pass
- ✅ Clippy: zero warnings
- ✅ ครอบคลุม: pure Fn, FnMut (stateful counter, accumulator), move capture, string mutation, generic types (f64, i64, bool)

```rust
pub fn apply_twice<T>(x: T, mut f: impl FnMut(T) -> T) -> T {
    let intermediate = f(x);
    f(intermediate)
}
```

---

## Task 3: `run_parallel` — Concurrency & Thread Safety

**โจทย์:** สร้างฟังก์ชัน `run_parallel` ที่รับ `Vec<i32>` แล้วให้ 3 threads ช่วยกันบวกเลข โดยห้ามใช้ Arc หรือ Mutex

**สิ่งที่ Tua ทำ:**
- **ใช้ `std::thread::scope`** — คำตอบที่ถูกต้อง! เพราะ:
  - Scoped threads borrow จาก stack — ไม่ต้องใช้ `Arc` (compiler รับประกันว่า threads จบก่อน `v` ถูก drop)
  - `thread::spawn` ธรรมดาต้องการ `'static` → ต้องใช้ `Arc` → ผิดโจทย์
- แบ่ง vector เป็น 3 ส่วนเท่าๆ กัน (remainder แจกให้ chunks แรก)
- แต่ละ thread จับ `&[i32]` slice (Copy type) — `move` closure จับ reference
- Return `i64` ป้องกัน overflow

**ผลลัพธ์:**
- ✅ 6 unit tests + 1 doc-test — all pass
- ✅ Clippy: zero warnings
- ✅ Thread-safe โดยไม่ใช้ Arc/Mutex

```rust
pub fn run_parallel(v: Vec<i32>) -> i64 {
    std::thread::scope(|s| {
        let n = v.len();
        let third = n / 3;
        let handles: Vec<_> = (0..3).map(|i| {
            let start = i * third + (if i < n % 3 { i } else { n % 3 });
            let end = (i + 1) * third + (if i < n % 3 { i + 1 } else { n % 3 });
            let slice = &v[start.min(n)..end.min(n)];
            s.spawn(move || slice.iter().map(|&x| x as i64).sum::<i64>())
        }).collect();
        handles.into_iter().map(|h| h.join().unwrap()).sum()
    })
}
```

---

## Summary

| Task | Difficulty | Key Concept | Tua's Answer | Tests | Clippy |
|---|---|---|---|---|---|
| `split_pair` | 🔥🔥 | Explicit Lifetimes, Zero-copy | `find(' ')` + slice | 9 | ✅ |
| `apply_twice` | 🔥🔥🔥 | Closure Traits | `FnMut` | 13 | ✅ |
| `run_parallel` | 🔥🔥🔥🔥🔥 | Scoped Threads | `thread::scope` | 7 | ✅ |
| **Total** | — | — | — | **29** | ✅ |

**Tua Agent v0.0.2 ผ่านทั้งหมด 3 โจทย์ระดับยาก — zero errors, zero clippy warnings, 29 tests ผ่านทุกตัว 🦀**
