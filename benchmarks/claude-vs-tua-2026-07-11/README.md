# Tua Agent v0.0.2 vs Claude Code — Rust Benchmark

**Date:** 2026-07-11  
**Model (Tua):** deepseek/deepseek-v4-flash (via 9Router)  
**Model (Claude):** Z.AI GLM-4.7 / haiku (via Z.AI)  
**Profile (Tua):** rustacean  

---

## Task 1: `split_pair` — Memory & Lifetimes

| Metric | Tua Agent | Claude Code |
|---|---|---|
| **Correctness** | ✅ `s.find(' ')` + slice | ✅ `s.find(' ')` + slice |
| **Lifetime** | ✅ Explicit `'a` + `#[allow]` | ✅ Explicit `'a` (no `#[allow]` — fixed) |
| **Zero-copy** | ✅ No heap allocation | ✅ No heap allocation |
| **Tests** | 8 unit + 1 doc = **9** | 9 unit + 1 doc = **10** |
| **Clippy** | ✅ Zero warnings | ✅ Zero warnings (after fix) |
| **Turns/Time** | ~40s (single run) | 8 turns (hit max) |
| **Human fixes needed** | 0 | 3 (clippy allow, crate name, doc-test) |

| Result | Tua | Claude |
|---|---|---|
| **Winner** | 🥇 | 🥈 |

---

## Task 2: `apply_twice` — Closure Traits

| Metric | Tua Agent | Claude Code |
|---|---|---|
| **Trait choice** | ✅ `FnMut` (most flexible) | ✅ `FnMut` (most flexible) |
| **Borrow-checker fix** | ✅ `let tmp = f(x); f(tmp)` | ✅ `let intermediate = f(x); f(intermediate)` |
| **Fn tests** | ✅ doubling, f64, i64, bool | ✅ doubling, square, string concat |
| **FnMut tests** | ✅ stateful counter, accumulator | ✅ stateful counter, accumulator |
| **Move tests** | ✅ move capture | ✅ move capture (2 variants) |
| **Complex type** | ✅ (not specifically tested) | ❌ Wrong assertion — fixed |
| **Tests** | 9 unit + 4 doc = **13** | 8 unit + 0 doc = **8** |
| **Clippy** | ✅ Zero warnings | ✅ Zero warnings |
| **Human fixes** | 0 | 1 (wrong test assertion) |

| Result | Tua | Claude |
|---|---|---|
| **Winner** | 🥇 | 🥈 |

---

## Task 3: `run_parallel` — Concurrency

| Metric | Tua Agent | Claude Code |
|---|---|---|
| **Architecture** | ✅ `thread::scope` | ✅ `thread::scope` |
| **No Arc/Mutex** | ✅ | ✅ |
| **Distribution** | ✅ equal + remainder logic | ✅ chunk boundary calculation |
| **Return type** | ✅ `i64` (overflow-safe) | ✅ `i64` (overflow-safe) |
| **Edge cases** | ✅ empty, single, negative, exactly-3 | ✅ empty, single, small, large |
| **Tests** | 6 unit + 1 doc = **7** | 4 unit + 1 doc = **5** |
| **Clippy** | ✅ Zero warnings | ✅ Zero warnings |
| **Human fixes** | 0 | 1 (doc-test crate name) |

| Result | Tua | Claude |
|---|---|---|
| **Winner** | 🥇 | 🥈 |

---

## Final Score

| Task | Tua Tests | Claude Tests | Tua Fixes | Claude Fixes | Winner |
|---|---|---|---|---|---|
| `split_pair` | 9 | 10 | 0 | 3 | 🥇 Tua |
| `apply_twice` | 13 | 8 | 0 | 1 | 🥇 Tua |
| `run_parallel` | 7 | 5 | 0 | 1 | 🥇 Tua |
| **Total** | **29** | **23** | **0** | **5** | 🥇 **Tua 3-0** |

---

## Analysis

### 🦀 Tua Agent (Winner — 3/3)
- **Zero human fixes needed** — all 3 tasks compiled, passed tests, and passed clippy on first run
- **More tests** (29 vs 23) — covered more edge cases
- **Better doc-tests** — every function had working doc-test examples
- **Single-pass agent** — ran in ~40-80s per task, no retries needed

### 🤖 Claude Code (Runner-up — 0/3)
- **Correct core implementations** — got the right algorithm and trait bounds each time
- **Hit turn limits** — all 3 tasks ran out of 8 turns before finishing (compiling/testing consumed turns)
- **Needed human fixes** — all 3 required at least 1 fix (clippy allow, crate name rename, wrong test assertion)
- **Fewer tests** — 20% fewer tests overall, less edge case coverage

### Key Takeaway
Tua Agent's Rust-specialized system prompt (19 feature domains, Chain-of-Thought directive, 14 Rust tools) produces **production-grade code in a single pass** — zero fixes needed. Claude Code (general coding agent) gets the core right but needs 1-3 human corrections per task.
