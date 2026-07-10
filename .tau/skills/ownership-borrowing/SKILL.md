---
name: ownership-borrowing
description: Rust ownership and borrowing patterns, move semantics, references, slices, Copy/Clone traits
---

# Ownership & Borrowing

## Core Concepts

Every value has a single **owner**. When the owner goes out of scope, the value is dropped.

```rust
fn main() {
    let s1 = String::from("hello");
    let s2 = s1; // s1 moved into s2; s1 is no longer valid
    // println!("{}", s1); // ERROR: value borrowed here after move

    let x = 5;
    let y = x; // i32 implements Copy, so x is still valid
    println!("{} {}", x, y);
}
```

## Borrowing — References

```rust
fn calculate_length(s: &String) -> usize {
    s.len()
} // s goes out of scope but since it's a reference, nothing is dropped

fn main() {
    let s = String::from("hello");
    let len = calculate_length(&s); // borrow, don't move
    println!("'{}' is {} chars", s, len);
}
```

### Mutable References

```rust
fn main() {
    let mut s = String::from("hello");
    change(&mut s);
}

fn change(s: &mut String) {
    s.push_str(", world");
}
```

**Rules:**
- At any given time, you can have **either** one mutable reference **or** any number of immutable references.
- References must always be valid (no dangling pointers).

## Slices

```rust
fn first_word(s: &str) -> &str {
    let bytes = s.as_bytes();
    for (i, &byte) in bytes.iter().enumerate() {
        if byte == b' ' {
            return &s[..i];
        }
    }
    &s[..]
}

fn main() {
    let s = String::from("hello world");
    let word = first_word(&s); // borrows s immutably
    // s.clear(); // ERROR: cannot borrow `s` as mutable while `word` borrows it
    println!("{}", word);
}
```

String slices `&str` borrow from the underlying data; they don't own it.

## Copy vs Clone

```rust
#[derive(Debug, Clone, Copy)]
struct Point {
    x: i32,
    y: i32,
}

fn main() {
    let p1 = Point { x: 10, y: 20 };
    let p2 = p1; // Copy — p1 still valid
    println!("{:?} {:?}", p1, p2);
}
```

- **Copy**: bitwise duplicate; original stays valid. Only types where bit-for-bit copy is safe (no heap allocation, no Drop).
- **Clone**: explicit `.clone()`; can do expensive deep copies.

```rust
let s1 = String::from("hello");
let s2 = s1.clone(); // explicit deep copy; s1 still valid
```

## Move Semantics Patterns

### Transferring Ownership Explicitly

```rust
fn takes_ownership(s: String) {
    println!("{}", s);
} // s dropped here

fn makes_copy(x: i32) {
    println!("{}", x);
} // x goes out of scope, nothing special

fn main() {
    let s = String::from("hello");
    takes_ownership(s);
    // s no longer valid here

    let x = 5;
    makes_copy(x);
    println!("{}", x); // still valid — i32 is Copy
}
```

### Returning Ownership

```rust
fn gives_ownership() -> String {
    String::from("from the function")
}

fn takes_and_gives_back(s: String) -> String {
    s
}
```

## Common Patterns

### Using References to Avoid Clones

```rust
// Bad — unnecessary clone
fn bad(data: &Vec<i32>) -> Vec<i32> {
    data.clone().iter().map(|x| x * 2).collect()
}

// Good — return owned data, borrow input
fn good(data: &[i32]) -> Vec<i32> {
    data.iter().map(|x| x * 2).collect()
}
```

### `Cow` for Borrowed or Owned Data

```rust
use std::borrow::Cow;

fn process(input: &str) -> Cow<'_, str> {
    if input.contains("bad") {
        Cow::Owned(input.replace("bad", "good"))
    } else {
        Cow::Borrowed(input)
    }
}
```

## Common Pitfalls & Errors

### Borrow Checker Errors

```
error[E0502]: cannot borrow `s` as mutable because it is also borrowed as immutable
```

Fix: ensure the immutable borrow ends before the mutable one begins, or restructure.

```rust
// ERROR
let mut s = String::from("hello");
let r = &s;
let r2 = &mut s; // can't borrow mutably while r is alive
```

```rust
// FIX — scopes end borrows
let mut s = String::from("hello");
{
    let r = &s;
    println!("{}", r);
} // r out of scope
let r2 = &mut s;
```

### Moving into a Struct and Still Using It

```rust
struct Config { name: String }

fn main() {
    let name = String::from("app");
    let cfg = Config { name }; // moved
    // println!("{}", name); // ERROR
}
```

Fix: `Config { name: name.clone() }` or restructure to pass a reference.

### Forgetting `&` When You Meant to Borrow

```rust
fn len(s: String) -> usize { s.len() } // takes ownership

let s = String::from("hi");
len(s);
// println!("{}", s); // moved — ERROR
```

Fix: `fn len(s: &String) -> usize` or `fn len(s: &str) -> usize`.

## References

- [The Rust Book — Ownership](https://doc.rust-lang.org/book/ch04-00-understanding-ownership.html)
- [The Rust Book — References and Borrowing](https://doc.rust-lang.org/book/ch04-02-references-and-borrowing.html)
- [The Rust Book — The Slice Type](https://doc.rust-lang.org/book/ch04-03-slices.html)
- [Rust Reference — Ownership](https://doc.rust-lang.org/reference/ownership.html)
- [std::borrow::Cow](https://doc.rust-lang.org/std/borrow/enum.Cow.html)
