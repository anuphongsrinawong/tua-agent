---
name: error-handling
description: Rust error handling with Result/Option, the ? operator, thiserror, anyhow, and error design patterns
---

# Error Handling

Rust has no exceptions. Errors are values, returned via `Result<T, E>`. There are no nulls — absence is represented with `Option<T>`.

## Result and Option

```rust
enum Result<T, E> {
    Ok(T),
    Err(E),
}

enum Option<T> {
    Some(T),
    None,
}
```

```rust
use std::fs::File;

fn open_file(path: &str) -> Result<File, std::io::Error> {
    File::open(path)
}

fn main() {
    match open_file("data.txt") {
        Ok(file) => println!("opened"),
        Err(e) => eprintln!("error: {}", e),
    }
}
```

## The `?` Operator

`?` returns early on `Err`, propagating it. On `Ok`, unwraps the value.

```rust
use std::fs::File;
use std::io::{self, Read};

fn read_config(path: &str) -> io::Result<String> {
    let mut file = File::open(path)?;
    let mut contents = String::new();
    file.read_to_string(&mut contents)?;
    Ok(contents)
}
```

`?` also converts error types via `From`, so you can use it across mismatched error types:

```rust
fn load() -> Result<String, Box<dyn std::error::Error>> {
    let s = std::fs::read_to_string("config.toml")?; // io::Error → boxed
    Ok(s)
}
```

## Option Combinators

```rust
let nums = vec![1, 2, 3];
let first = nums.first().copied().unwrap_or(0);
let doubled = nums.first().map(|x| x * 2).unwrap_or(0);
let name: String = std::env::var("USER").ok().unwrap_or_else(|| "anon".to_string());
```

## Result Combinators

```rust
let parsed: i32 = "42"
    .parse::<i32>()
    .map(|n| n * 2)
    .unwrap_or(0);

let result: Result<i32, _> = "abc"
    .parse::<i32>()
    .map_err(|e| format!("parse failed: {}", e));
```

## Defining Your Own Error Type

### Minimal — using `thiserror`

```toml
# Cargo.toml
[dependencies]
thiserror = "1"
```

```rust
use thiserror::Error;

#[derive(Debug, Error)]
pub enum AppError {
    #[error("io error: {0}")]
    Io(#[from] std::io::Error),

    #[error("config missing key: {key}")]
    MissingKey { key: String },

    #[error("invalid value {value} for {field}")]
    InvalidValue { field: String, value: String },

    #[error("unauthorized")]
    Unauthorized,
}
```

`#[from]` generates a `From` impl so `?` works seamlessly.

### Application Errors — using `anyhow`

```toml
# Cargo.toml
[dependencies]
anyhow = "1"
```

```rust
use anyhow::{Context, Result};

fn load_config(path: &str) -> Result<String> {
    let contents = std::fs::read_to_string(path)
        .with_context(|| format!("failed to read config at {}", path))?;
    Ok(contents)
}

fn main() -> Result<()> {
    let cfg = load_config("config.toml")?;
    println!("{}", cfg);
    Ok(())
}
```

`anyhow::Error` is essentially `Box<dyn Error + Send + Sync + 'static>` with attached context. Great for application boundaries.

## When to Use What

| Use case | Library | Application |
|----------|---------|-------------|
| Error type | `thiserror` — typed, structured | `anyhow` — opaque, with context |
| Public API | Always return concrete, `Error`-implementing types | N/A |
| Internal code | Typed if you handle them; else `anyhow` | `anyhow` |
| `main()` | N/A | `fn main() -> anyhow::Result<()>` |

**Rule of thumb:** libraries define their own error enums with `thiserror`. Applications use `anyhow` for plumbing and convert at boundaries.

```rust
// Library code
pub fn parse(input: &str) -> Result<Foo, ParseError> { ... }

// Application code wrapping it
use anyhow::Context;
let foo = my_lib::parse(input).context("parsing user input")?;
```

## Pattern: Context-Aware Errors

```rust
#[derive(Debug, thiserror::Error)]
pub enum DbError {
    #[error("connection failed to {url}: {source}")]
    Connection {
        url: String,
        #[source]
        source: std::io::Error,
    },
}

fn connect(url: &str) -> Result<Conn, DbError> {
    let conn = Conn::new(url).map_err(|e| DbError::Connection {
        url: url.to_string(),
        source: e,
    })?;
    Ok(conn)
}
```

## Pattern: Downcasting `anyhow::Error`

```rust
use anyhow::Result;

fn work() -> Result<()> {
    Err(anyhow::anyhow!("specific failure"))
}

fn main() {
    if let Err(e) = work() {
        if let Some(io_err) = e.downcast_ref::<std::io::Error>() {
            println!("it was an io error: {}", io_err);
        } else {
            println!("other error: {}", e);
        }
    }
}
```

## Pattern: Converting Between Errors

```rust
#[derive(Debug, thiserror::Error)]
pub enum AppError {
    #[error(transparent)]
    Io(#[from] std::io::Error),
    #[error(transparent)]
    Parse(#[from] std::num::ParseIntError),
}

fn parse_count(s: &str) -> Result<i32, AppError> {
    let n: i32 = s.parse()?; // ParseIntError → AppError::Parse
    Ok(n)
}
```

## Common Pitfalls & Errors

### Using `unwrap()`/`expect()` in Production

```rust
let port: u16 = std::env::var("PORT")
    .unwrap() // panics on missing
    .parse()
    .unwrap(); // panics on non-numeric
```

Better:

```rust
let port: u16 = std::env::var("PORT")
    .ok()
    .and_then(|s| s.parse().ok())
    .unwrap_or(8080);
```

### Swallowing Errors Silently

```rust
let _ = send_email(); // ignores Err — bug
```

At least log:

```rust
if let Err(e) = send_email() {
    log::warn!("failed to send email: {}", e);
}
```

### `Box<dyn Error>` Instead of a Real Type

```rust
// Quick & dirty, but loses type info
fn work() -> Result<(), Box<dyn std::error::Error>> { ... }
```

Acceptable for prototyping; use `anyhow` or `thiserror` for real code.

### Forgetting `#[from]` Breaks `?`

```rust
#[derive(Debug, thiserror::Error)]
pub enum AppError {
    #[error("io: {0}")]
    Io(std::io::Error), // NO #[from] — `?` won't convert io::Error → AppError
}
```

Fix: add `#[from]`:

```rust
#[error("io: {0}")]
Io(#[from] std::io::Error),
```

### Confusing `?` on `Option`

`?` works on `Option` too, but only inside functions returning `Option`:

```rust
fn first_char(s: &str) -> Option<char> {
    let c = s.chars().next()?; // returns None early if empty
    Some(c)
}
```

### Not Implementing `std::error::Error` for Custom Errors

If your error type doesn't implement `Error`, it won't compose with `?`, `anyhow`, or downcasting. `thiserror::Error` derives it automatically — use it.

## References

- [The Rust Book — Error Handling](https://doc.rust-lang.org/book/ch09-00-error-handling.html)
- [std::error::Error](https://doc.rust-lang.org/std/error/trait.Error.html)
- [std::result::Result](https://doc.rust-lang.org/std/result/enum.Result.html)
- [thiserror crate](https://docs.rs/thiserror)
- [anyhow crate](https://docs.rs/anyhow)
- [Rust Blog — Error Handling Survey](https://nick.groenen.me/posts/rust-error-handling/)
