---
name: async-rust
description: Async/await in Rust, the Future trait, Pin, tokio runtime, and common async patterns
---

# Async Rust

Rust's async is **zero-cost** — futures are state machines, not threads. An `async fn` returns a `Future` that does nothing until polled.

## async/await Basics

```rust
async fn fetch_data(url: &str) -> Result<String, std::io::Error> {
    // ...async work...
    Ok(format!("data from {}", url))
}

async fn main_logic() {
    let result = fetch_data("https://example.com").await;
    println!("{:?}", result);
}
```

`.await` suspends the current task until the future is ready, yielding control back to the executor.

## The Future Trait

```rust
pub trait Future {
    type Output;
    fn poll(self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<Self::Output>;
}

pub enum Poll<T> {
    Ready(T),
    Pending,
}
```

A future is **polled**. When polled:
- If ready → returns `Poll::Ready(value)`.
- If not → schedules a wake-up via `cx.waker()`, returns `Poll::Pending`.

You almost never implement `Future` by hand — use `async fn` or combinators.

## Pin

`Pin<P>` ensures a value can't be moved in memory. This is critical for **self-referential** async state machines (e.g., an `async fn` that borrows across `.await` points creates a struct that references itself).

```rust
use std::pin::Pin;

// Pin<Box<T>> — pinned on the heap
let boxed: Pin<Box<dyn Future<Output = ()>>> = Box::pin(async {
    println!("hello");
});
```

You don't usually interact with `Pin` directly when using `async`/`await`. It matters when:
- Implementing `Future` manually
- Storing futures in a struct (use `Pin<Box<...>>` or `Box::pin`)
- Working with self-referential data (e.g., `tokio::select!`)

```rust
struct Task {
    future: Pin<Box<dyn Future<Output = ()> + Send>>,
}
```

## Tokio Runtime

The most popular async runtime.

```toml
# Cargo.toml
[dependencies]
tokio = { version = "1", features = ["full"] }
```

```rust
#[tokio::main]
async fn main() {
    println!("hello from tokio");
    tokio::spawn(async {
        // runs concurrently on the runtime
        tokio::time::sleep(std::time::Duration::from_millis(50)).await;
        println!("background task done");
    }).await.unwrap();
}
```

### Spawning Tasks

```rust
#[tokio::main]
async fn main() {
    let handle = tokio::spawn(async {
        42
    });
    let result: i32 = handle.await.unwrap();
    println!("{}", result);
}
```

`tokio::spawn` requires the future to be `Send + 'static` (must be movable across threads and own all its data).

## Common Patterns

### Concurrent Execution with `tokio::join!`

```rust
async fn get_user() -> User { /* ... */ }
async fn get_posts() -> Vec<Post> { /* ... */ }

async fn profile_page() -> (User, Vec<Post>) {
    tokio::join!(get_user(), get_posts())
}
```

`join!` runs both to completion concurrently on the same task.

### Racing with `tokio::select!`

```rust
use tokio::time::{sleep, Duration};

async fn with_timeout<T, F: Future<Output = T>>(f: F) -> Option<T> {
    tokio::select! {
        result = f => Some(result),
        _ = sleep(Duration::from_secs(5)) => None,
    }
}
```

### Concurrent Fetching — `FuturesUnordered` or `join_all`

```rust
use futures::future::join_all;

async fn fetch_all(urls: Vec<String>) -> Vec<String> {
    let futs = urls.iter().map(|u| fetch_data(u));
    join_all(futs).await.into_iter().collect()
}
```

For unbounded work, prefer `FuturesUnordered`:

```rust
use futures::stream::{FuturesUnordered, StreamExt};

async fn process_all(urls: Vec<String>) {
    let mut futs = FuturesUnordered::new();
    for u in urls {
        futs.push(fetch_data(&u));
    }
    while let Some(result) = futs.next().await {
        // handle as each completes
    }
}
```

### Channels

```rust
use tokio::sync::mpsc;

#[tokio::main]
async fn main() {
    let (tx, mut rx) = mpsc::channel::<String>(32);

    tokio::spawn(async move {
        tx.send("hello".to_string()).await.unwrap();
    });

    while let Some(msg) = rx.recv().await {
        println!("{}", msg);
    }
}
```

### Cancellation via `select!` and Drop

A future is cancelled when dropped. `select!` drops branches that didn't win.

```rust
tokio::select! {
    _ = tokio::signal::ctrl_c() => println!("interrupted"),
    _ = run_server() => println!("server exited"),
}
```

## Async Traits

Stable since Rust 1.75:

```rust
trait Service {
    async fn fetch(&self, url: &str) -> Result<String, std::io::Error>;
}
```

For older compilers or `dyn` dispatch, use `async_trait` crate:

```rust
use async_trait::async_trait;

#[async_trait]
trait Service {
    async fn fetch(&self, url: &str) -> Result<String, std::io::Error>;
}
```

## Common Pitfalls & Errors

### Forgetting `.await` — Nothing Runs

```rust
async fn work() { /* ... */ }

fn main() {
    let fut = work(); // Future created but never polled — does nothing
}
```

You must drive the future to completion with `.await` or hand it to a runtime.

### Blocking the Runtime

```rust
async fn bad() {
    std::thread::sleep(std::time::Duration::from_secs(5)); // blocks the worker thread!
}
```

Use the async equivalent:

```rust
async fn good() {
    tokio::time::sleep(std::time::Duration::from_secs(5)).await;
}
```

For unavoidable blocking work, use `spawn_blocking`:

```rust
tokio::task::spawn_blocking(|| {
    std::thread::sleep(std::time::Duration::from_secs(5));
});
```

### Futures Are Lazy

```rust
let f = async { println!("hi"); };
// "hi" not printed yet
f.await; // now it runs
```

### Send Bound Errors When Spawning

```
error: future cannot be sent between threads safely
```

Common cause: holding a `!Send` value (like `Rc` or `RefCell`) across `.await`. Use `Arc`/`Mutex` instead, or restructure to drop the `!Send` value before the `.await`.

### Holding a `std::sync::Mutex` Guard Across `.await`

```rust
// PROBLEM
let guard = mutex.lock().unwrap();
something_async().await; // guard held across await — may deadlock or be !Send
```

```rust
// FIX
{
    let guard = mutex.lock().unwrap();
    /* use guard */
} // drop before await
something_async().await;
```

Or use `tokio::sync::Mutex` if you must hold it across await.

### `async fn` in a Trait Object

Plain `async fn` in traits is not yet `dyn`-compatible. Use the `async_trait` crate or box the future manually:

```rust
trait Service {
    fn fetch(&self, url: &str) -> Pin<Box<dyn Future<Output = Result<String, std::io::Error>> + Send + '_>>;
}
```

## References

- [Asynchronous Programming in Rust (Tokio Tutorial)](https://tokio.rs/tokio/tutorial)
- [The Rust Async Book](https://rust-lang.github.io/async-book/)
- [std::future::Future](https://doc.rust-lang.org/std/future/trait.Future.html)
- [std::pin::Pin](https://doc.rust-lang.org/std/pin/struct.Pin.html)
- [tokio docs](https://docs.rs/tokio)
- [futures crate](https://docs.rs/futures)
