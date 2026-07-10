---
name: lifetimes
description: Rust lifetime elision rules, named lifetimes, higher-ranked trait bounds (HRTB), 'static lifetime, and common lifetime errors
---

# Lifetimes

Lifetimes are the compiler's way of ensuring that references are valid as long as they need to be. They are mostly inferred, but sometimes you must annotate them.

## Core Idea

Every reference has a **lifetime** — the scope during which it's valid.

```rust
// The compiler needs to know: which input does the output borrow from?
fn longest<'a>(x: &'a str, y: &'a str) -> &'a str {
    if x.len() > y.len() {
        x
    } else {
        y
    }
}
```

The generic lifetime `'a` says: the returned reference lives as long as the **shortest** of the two input lifetimes.

## Lifetime Elision Rules

The compiler applies three rules so you rarely need to annotate:

1. **Each reference parameter gets its own lifetime.**
   `fn foo(x: &str, y: &str)` → `fn foo<'a, 'b>(x: &'a str, y: &'b str)`

2. **If exactly one input lifetime, it's assigned to all outputs.**
   `fn foo(x: &str) -> &str` → `fn foo<'a>(x: &'a str) -> &'a str`

3. **If multiple inputs but one is `&self`/`&mut self`, that lifetime is assigned to all outputs.**

If after applying these rules there are still ambiguous output lifetimes, the compiler errors and you must annotate.

```rust
// Elision works — single input
fn first_word(s: &str) -> &str {
    // ...
    s
}
```

## Named Lifetimes

```rust
struct Excerpt<'a> {
    part: &'a str,
}

impl<'a> Excerpt<'a> {
    fn announce(&self, msg: &str) -> &str {
        println!("{}: {}", msg, self.part);
        self.part
    }
    // Elided: returns &'a str (rule 3 — &self)
}
```

A struct holding a reference must declare the lifetime; the struct cannot outlive the reference.

## `'static` Lifetime

`'static` means the reference lives for the entire program. All string literals are `&'static str`.

```rust
let s: &'static str = "I live forever";
```

Be careful — don't use `'static` as a band-aid to silence borrow checker errors. It often signals a design issue (e.g., leaking data, storing references when you should own).

```rust
// Often a smell:
fn get_config() -> &'static Config { ... }
// Prefer returning owned data:
fn get_config() -> Config { ... }
```

## Higher-Ranked Trait Bounds (HRTB)

For functions that take a reference and the lifetime isn't tied to anything else, use `for<'a>`.

```rust
fn apply<F>(f: F)
where
    F: for<'a> Fn(&'a str) -> &'a str,
{
    let s = String::from("hi");
    println!("{}", f(&s));
}
```

`for<'a> Fn(&'a str) -> &'a str` means "works for any lifetime `'a`."

The short form `fn(&str) -> &str` is sugar for this HRTB.

```rust
// These two are equivalent:
fn map1(f: fn(&str) -> &str) {}
fn map2(f: for<'a> Fn(&'a str) -> &'a str) {}
```

## Common Patterns

### Storing References in Structs

```rust
struct Parser<'a> {
    input: &'a str,
    pos: usize,
}

impl<'a> Parser<'a> {
    fn new(input: &'a str) -> Self {
        Parser { input, pos: 0 }
    }
    fn rest(&self) -> &'a str {
        &self.input[self.pos..]
    }
}
```

### Multiple Distinct Lifetimes

When two references have different relationships:

```rust
struct Context<'a, 'b> {
    config: &'a Config,  // lives longer
    cache: &'b mut Cache, // shorter, mutable
}
```

### Lifetime vs Ownership — Prefer Owning

```rust
// Often harder to use — callers must keep data alive
struct Logger<'a> { target: &'a str }

// Easier — owns its data
struct Logger { target: String }
```

## Common Pitfalls & Errors

### Returning a Reference to a Local

```rust
fn dangling() -> &str { // ERROR: missing lifetime specifier
    let s = String::from("temp");
    &s[..]
} // s dropped — dangling reference
```

Fix: return owned data.

```rust
fn owned() -> String {
    String::from("temp")
}
```

### Lifetime Mismatch in Structs

```rust
struct App<'a> {
    name: &'a str,
}

fn main() {
    let name = String::from("app");
    let app = App { name: &name }; // borrows name
    // If app outlives name, this is an error.
    drop(name); // ERROR: borrowed as immutable
    println!("{}", app.name);
}
```

### Confused by Elision Rule 3

```rust
struct Excerpt<'a> { part: &'a str }

impl<'a> Excerpt<'a> {
    fn level(&self) -> i32 { 3 }
    fn announce_and_return(&self, x: &str) -> &str {
        // Rule 3 ties output to &self, NOT to x
        x // Compiles only because 'a outlives the call;
          // if x must outlive self, you need to tie them.
    }
}
```

### `'_` — the Placeholder Lifetime

Use `'_` to silence warnings about unused lifetime names.

```rust
// Warning: lifetime parameter 'a never used
struct Foo<'a> { data: String }

// Silenced:
struct Foo<'_> { data: String }
```

Also used in `&'_ str` when elision doesn't apply but you want the compiler to infer:

```rust
fn printer(msg: &'_ str) { println!("{}", msg); }
```

## References

- [The Rust Book — Validating References with Lifetimes](https://doc.rust-lang.org/book/ch10-03-lifetime-syntax.html)
- [Rust Reference — Lifetimes](https://doc.rust-lang.org/reference/lifetimes.html)
- [Rustonomicon — Lifetimes](https://doc.rust-lang.org/nomicon/lifetimes.html)
- [std::pin](https://doc.rust-lang.org/std/pin/index.html) (for self-referential structs — related)
- [Higher-Ranked Trait Bounds](https://doc.rust-lang.org/nomicon/hrtb.html)
