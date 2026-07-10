---
name: smart-pointers
description: Rust smart pointers — Box, Rc, Arc, Cow, RefCell, Cell, Mutex/RwLock, Pin/Unpin, and when to reach for each
---

# Smart Pointers in Rust

Smart pointers own data on the heap (or add behavior to it) and implement `Deref`, `Drop`, or both. They are how Rust expresses "more than one owner," interior mutability, and recursive/lifetime-defying structures.

## Box<T> — Heap Allocation

`Box` moves a value to the heap. Use it for large stack values, trait objects, and recursive types.

```rust
// Recursive type needs indirection so its size is known at compile time.
enum List {
    Cons(i32, Box<List>),
    Nil,
}

fn main() {
    let b = Box::new(5);            // 5 now lives on the heap
    println!("{}", b);              // derefs automatically
    let dyn_err: Box<dyn std::error::Error> = Box::from("oops");
}
```

## Rc<T> — Single-Threaded Shared Ownership

`Rc` (reference count) lets multiple owners share immutable data on one thread. Cheap clone (bumps the count, no deep copy).

```rust
use std::rc::Rc;

let a = Rc::new(String::from("shared"));
let b = Rc::clone(&a);   // strong count -> 2
let c = Rc::clone(&a);   // strong count -> 3
println!("{} strong refs", Rc::strong_count(&a));
```

`Rc` is `!Send`/`!Sync` — do not move it across threads. Use `Arc` for that.

## Arc<T> — Multi-Threaded Shared Ownership

`Arc` (atomic reference count) is the thread-safe sibling of `Rc`. Cloning atomically bumps the count.

```rust
use std::sync::Arc;
use std::thread;

let data = Arc::new(vec![1, 2, 3]);
let handles: Vec<_> = (0..3)
    .map(|_| {
        let data = Arc::clone(&data);
        thread::spawn(move || data.len())
    })
    .collect();
for h in handles { h.join().unwrap(); }
```

## Cow<T> — Clone-on-Write

`Cow` holds either a borrowed (`&T`) or owned (`T::Owned`) value, cloning only when mutation is required.

```rust
use std::borrow::Cow;

fn sanitize(input: &str) -> Cow<'_, str> {
    if input.contains('\t') {
        Cow::Owned(input.replace('\t', "    ")) // allocate only if needed
    } else {
        Cow::Borrowed(input)                     // zero allocation
    }
}
```

## Interior Mutability

### Cell<T> — Copy Types

`Cell` gives interior mutability for `Copy` types by copying values in/out. No borrowing, no references.

```rust
use std::cell::Cell;

let c = Cell::new(5);
let five = c.get();   // copies out
c.set(10);
```

### RefCell<T> — Runtime Borrow Checking

`RefCell` moves borrow checking to runtime (`borrow()`/`borrow_mut()`). Use when the borrow structure can't be proven statically (e.g., graphs, mocks).

```rust
use std::cell::RefCell;

let cell = RefCell::new(vec![1, 2, 3]);
cell.borrow_mut().push(4);          // mutable borrow ends here
println!("{:?}", cell.borrow());
```

Two overlapping `borrow_mut()` (or `borrow_mut` + `borrow`) at runtime panics instead of compiling.

### Rc<RefCell<T>> / Arc<Mutex<T>> — Shared Mutability

- Single-threaded shared mutable state: `Rc<RefCell<T>>`
- Multi-threaded shared mutable state: `Arc<Mutex<T>>` (or `Arc<RwLock<T>>`)

## Mutex<T> / RwLock<T> — Locking

```rust
use std::sync::{Arc, Mutex};

let counter = Arc::new(Mutex::new(0));
let c2 = Arc::clone(&counter);
std::thread::spawn(move || {
    *c2.lock().unwrap() += 1;   // lock() -> MutexGuard; dropped at end of stmt
}).join().unwrap();
```

`RwLock` allows many concurrent readers or one writer. Prefer it when reads dominate.

## Pin / Unpin — Pinning for Async & Self-Referential Types

`Pin<P>` prevents a value from being moved. Required for self-referential `async` state machines.

```rust
use std::pin::Pin;

let boxed: Pin<Box<dyn std::future::Future<Output = ()>>> = Box::pin(async {
    println!("pinned future");
});
```

Most `T: Unpin` (movers) are freely usable through `Pin`. Self-referential futures are `!Unpin` and must stay pinned once polled.

## When to Reach for What

| Need | Use |
|------|-----|
| Heap allocate / trait object / recursion | `Box<T>` |
| Share immutable data, one thread | `Rc<T>` |
| Share data across threads | `Arc<T>` |
| Mutate shared state, one thread | `Rc<RefCell<T>>` |
| Mutate shared state, many threads | `Arc<Mutex<T>>` / `Arc<RwLock<T>>` |
| Borrow unless you must own | `Cow<T>` |
| Cheap interior mut for `Copy` types | `Cell<T>` |
| Runtime-checked interior mut | `RefCell<T>` |
| Self-referential / async pinned data | `Pin<P>` |

## Common Pitfalls

### Reference Cycles Leak Memory
`Rc`-pointing-to-`Rc` never frees. Break cycles with `Weak<T>`:

```rust
use std::rc::{Rc, Weak};
let strong = Rc::new(1);
let weak: Weak<i32> = Rc::downgrade(&strong);   // does not keep it alive
assert!(weak.upgrade().is_some());
drop(strong);
assert!(weak.upgrade().is_none());
```

### `RefCell` Borrow Panics at Runtime
```rust
let cell = RefCell::new(1);
let b = cell.borrow();
let m = cell.borrow_mut(); // PANICS: already immutably borrowed
```
Keep borrow scopes tight; drop guards before taking conflicting borrows.

### Deadlocks with `Mutex`
Locking two mutexes in inconsistent order across threads, or re-locking a non-reentrant `std::sync::Mutex` you already hold, deadlocks. Acquire in a fixed global order; never hold a guard across an `.await` (use `tokio::sync::Mutex` if you must).

### Poisoned Mutex
A panic while a `Mutex` is held "poisons" it; the next `lock()` returns `Err`. Decide explicitly: recover via `err.into_inner()` or propagate the failure.

### Using `Rc` Where `Arc` Is Needed
`Rc` is `!Send`, so `thread::spawn(move || rc)` fails to compile. Reach for `Arc` the moment threads are involved.

## Links

- [The Rust Book — Smart Pointers](https://doc.rust-lang.org/book/ch15-00-smart-pointers.html)
- [std::boxed::Box](https://doc.rust-lang.org/std/boxed/struct.Box.html)
- [std::rc::Rc](https://doc.rust-lang.org/std/rc/struct.Rc.html)
- [std::sync::Arc](https://doc.rust-lang.org/std/sync/struct.Arc.html)
- [std::cell::RefCell](https://doc.rust-lang.org/std/cell/struct.RefCell.html)
- [std::borrow::Cow](https://doc.rust-lang.org/std/borrow/enum.Cow.html)
- [std::pin::Pin](https://doc.rust-lang.org/std/pin/struct.Pin.html)
