---
name: concurrency
description: Rust concurrency — Send/Sync, Arc<Mutex<T>>, channels (mpsc/oneshot/broadcast/watch), tokio::spawn, Rayon, atomics, and the pitfalls that bite
---

# Concurrency in Rust

Rust's ownership model makes "fearless concurrency" real: data races are compile-time errors, not 3am debugging sessions. The mechanism is two auto-traits — `Send` and `Sync`.

## Send & Sync (Auto-Traits)

- **`Send`** — a type can be moved across thread boundaries (`T` is safe to give to another thread).
- **`Sync`** — `&T` can be shared across threads (it's safe for multiple threads to hold a shared reference).

Both are auto-derived from a type's fields. `Rc<T>` is `!Send`/`!Sync` (non-atomic refcount); `Arc<T>` is both. Raw pointers are `!Send`/`!Sync`.

```rust
// Compiler rejects this:
use std::rc::Rc;
// let r = Rc::new(1);
// std::thread::spawn(move || println!("{r}")); // ERROR: `Rc` cannot be sent between threads
```

## Arc<Mutex<T>> — The Shared Mutable State Pattern

The canonical thread-safe shared-state primitive:

```rust
use std::sync::{Arc, Mutex};
use std::thread;

let counter = Arc::new(Mutex::new(0));
let mut handles = vec![];
for _ in 0..10 {
    let counter = Arc::clone(&counter);
    handles.push(thread::spawn(move || {
        let mut num = counter.lock().unwrap();
        *num += 1;
    }));
}
for h in handles { h.join().unwrap(); }
println!("result = {}", *counter.lock().unwrap());
```

For read-heavy workloads, `Arc<RwLock<T>>` allows many readers or one writer.

## Channels — Message Passing

### std mpsc (single-producer, multi-consumer input)

```rust
use std::sync::mpsc;
use std::thread;

let (tx, rx) = mpsc::channel();
thread::spawn(move || {
    tx.send(42).unwrap();
});
println!("got {}", rx.recv().unwrap());
```

Clone `tx` for multiple producers: `let tx2 = tx.clone();`.

### tokio channels

| Channel | Use case |
|---------|----------|
| `mpsc` | many senders, one receiver, backpressured |
| `oneshot` | one value, one-shot (request/response) |
| `broadcast` | one sender, many receivers each get every value |
| `watch` | many readers of the latest single value (config/state) |

```rust
#[tokio::main]
async fn main() {
    let (tx, mut rx) = tokio::sync::mpsc::channel::<u32>(8);
    tokio::spawn(async move {
        tx.send(1).await.unwrap();
    });
    while let Some(v) = rx.recv().await {
        println!("received {v}");
    }
}
```

## tokio::spawn — Async Tasks

```rust
#[tokio::main]
async fn main() {
    let handle = tokio::spawn(async {
        tokio::time::sleep(std::time::Duration::from_millis(10)).await;
        7
    });
    println!("task returned {}", handle.await.unwrap());
}
```

`tokio::spawn` requires the future to be `Send + 'static` — it owns its data and can be moved between worker threads.

## Rayon — Data Parallelism

Rayon turns sequential iterators into parallel ones with `par_iter()`:

```rust
use rayon::prelude::*;

let sum: i32 = (1..=1_000_000).into_par_iter().sum();
let doubled: Vec<i32> = vec![1, 2, 3].par_iter().map(|x| x * 2).collect();
```

Great for CPU-bound fan-out over collections; backed by a work-stealing thread pool.

## std::thread::scope — Scoped Threads

`scope` lets spawned threads borrow non-`'static` data, because the scope guarantees all threads are joined before it returns:

```rust
use std::thread;

let data = vec![1, 2, 3];
thread::scope(|s| {
    for chunk in data.chunks(1) {
        s.spawn(move || {
            println!("sum = {}", chunk.iter().sum::<i32>());
        });
    }
}); // all scoped threads joined here — `data` can be used again after
```

No `Arc`/`clone` needed for borrowed inputs.

## Atomics

Lock-free primitives when a full `Mutex` is overkill:

```rust
use std::sync::atomic::{AtomicUsize, Ordering};

static COUNTER: AtomicUsize = AtomicUsize::new(0);
COUNTER.fetch_add(1, Ordering::SeqCst);
let now = COUNTER.load(Ordering::SeqCst);
```

- `AtomicBool`, `AtomicUsize`, `AtomicI64`, … plus `AtomicPtr<T>`.
- **Ordering** — `Relaxed` (no ordering guarantees), `Acquire`/`Release` (publish/consume), `SeqCst` (sequentially consistent, strongest). Default to `SeqCst` until you've measured and understood `Acquire`/`Release`.

## Common Pitfalls

### Async Block Not `Send` ("future cannot be sent between threads safely")
Usually a `!Send` value (`Rc`, `RefCell`, `std::sync::MutexGuard`) is held across an `.await`. Drop it before the await, switch to `Arc`/`tokio::sync::Mutex`, or scope the guard in a block.

```rust
// PROBLEM
let g = mutex.lock().unwrap();
do_async().await;        // guard held across await -> !Send
```
```rust
// FIX
{ let g = mutex.lock().unwrap(); /* use g */ }   // guard dropped here
do_async().await;
```

### Holding a `std::sync::MutexGuard` Across `.await`
Beyond the `Send` error, holding a blocking guard across a suspension point can stall a whole worker thread (or deadlock). Use the synchronous guard synchronously, or `tokio::sync::Mutex`.

### Deadlocks From Inconsistent Lock Ordering
Two threads each grabbing locks A then B vs B then A deadlock. Always acquire locks in one globally agreed order.

### Confusing `Sync` with `Send`
`&T` crossing a thread requires `T: Sync`; the owned value crossing requires `T: Send`. A `Cell<T>` is `Send` (you can move it) but `!Sync` (you can't share `&Cell` across threads).

### Blocking the Async Runtime
`std::thread::sleep`, busy loops, and synchronous I/O inside an async task stall the worker. Use async equivalents or `tokio::task::spawn_blocking`.

### Spawning Without Joining
An ignored `JoinHandle` is silently dropped on panic. `.await`/`.join()` handles (or propagate errors) so panics surface and shutdowns are orderly.

## Links

- [The Rust Book — Fearless Concurrency](https://doc.rust-lang.org/book/ch16-00-concurrency.html)
- [std::sync](https://doc.rust-lang.org/std/sync/index.html)
- [Nomicon — Send and Sync](https://doc.rust-lang.org/nomicon/send-and-sync.html)
- [tokio tutorial — Spawning](https://tokio.rs/tokio/tutorial/spawning)
- [Rayon](https://docs.rs/rayon)
- [std::sync::atomic — Orderings](https://doc.rust-lang.org/std/sync/atomic/index.html#memory-orderings)
