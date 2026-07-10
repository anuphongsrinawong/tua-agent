---
name: testing
description: Testing Rust code — unit tests, integration tests, doc-tests, property testing (proptest), fuzzing (cargo-fuzz), and mocking (mockall, wiremock)
---

# Testing in Rust

Rust's testing is built into the compiler and `cargo`. Tests live next to the code they verify, run with a single command, and are first-class members of the build.

## Unit Tests

Inline tests live in the same file, gated by `#[cfg(test)]` so they never ship in release binaries:

```rust
pub fn add(a: i32, b: i32) -> i32 {
    a + b
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn add_works() {
        assert_eq!(add(2, 2), 4);
    }

    #[test]
    #[should_panic(expected = "overflow")]
    fn panics_on_overflow() {
        // demonstrates the should_panic attribute
        panic!("overflow");
    }

    #[test]
    fn result_based_test() -> Result<(), String> {
        if add(1, 1) == 2 {
            Ok(())
        } else {
            Err(String::from("math is broken"))
        }
    }
}
```

Prefer `Result`-returning tests over `unwrap()` so a test failure reads as an `Err`, not a panic.

## Integration Tests

Integration tests live in `tests/` and exercise the crate as an external consumer (only the public API is visible):

```rust
// tests/api.rs
use my_crate::add;

#[test]
fn public_api_adds() {
    assert_eq!(add(3, 4), 7);
}
```

Run a single test or filter: `cargo test add_works`, `cargo test --test api`.

## Doc-Tests

Code blocks in `///` doc comments are compiled and executed by `cargo test`:

```rust
/// Add two integers.
///
/// # Examples
///
/// ```
/// use my_crate::add;
/// assert_eq!(add(2, 2), 4);
/// ```
pub fn add(a: i32, b: i32) -> i32 {
    a + b
}
```

Mark a non-runnable doc block with `ignore`, or `no_run` to compile-but-not-run, or `compile_fail` to assert it does not compile.

## Property Testing with proptest

Property tests assert invariants hold over generated inputs rather than hand-picked examples:

```rust
use proptest::prelude::*;

proptest! {
    #[test]
    fn add_doesnt_change_parity(a in -1000i32..1000, b in -1000i32..1000) {
        // parity is preserved when both operands are even
        prop_assume!(a % 2 == 0 && b % 2 == 0);
        assert_eq!((a + b) % 2, 0);
    }
}
```

When a case fails, proptest shrinks it to the minimal failing input and persists it in `proptest-regressions/`.

## Fuzzing with cargo-fuzz

Coverage-guided fuzzing finds panics in arbitrary input parsing. Fuzz targets live in `fuzz/`:

```rust
// fuzz/fuzz_targets/parse.rs
#![no_main]
use libfuzzer_sys::fuzz_target;

fuzz_target!(|data: &[u8]| {
    let _ = my_crate::parse(data); // must not panic/UB on any input
});
```

Run with: `cargo +nightly fuzz run parse`.

## Mocking

- **mockall** — generate mocks for traits:
  ```rust
  use mockall::*;
  #[automock]
  trait Database {
      fn get(&self, key: &str) -> Option<String>;
  }

  #[test]
  fn uses_mock() {
      let mut db = MockDatabase::new();
      db.expect_get().with(eq("k")).returning(|_| Some("v".into()));
      assert_eq!(db.get("k"), Some("v".to_string()));
  }
  ```
- **wiremock** — HTTP-level mocking for async clients:
  ```rust
  use wiremock::{MockServer, Mock, ResponseTemplate};
  use wiremock::matchers::method;

  #[tokio::test]
  async fn hits_mock_server() {
      let server = MockServer::start().await;
      Mock::given(method("GET"))
          .respond_with(ResponseTemplate::new(200))
          .mount(&server)
          .await;
      // point your client at server.uri()
  }
  ```

## Useful Commands

- `cargo test` — run all unit + integration + doc tests
- `cargo test --doc` — doc-tests only
- `cargo test -- --nocapture` — show `println!` output from tests
- `cargo nextest run` — faster, parallel test runner (separate install)
- `cargo tarpaulin` — line coverage (separate install)

## Common Pitfalls

### `unwrap()` in Tests Hides the Real Failure
A panic from `.unwrap()` reports the unwrap site, not the mismatch. Use `assert_eq!`, `assert!`, or return `Result` for clearer failures.

### Tests Relying on Execution Order
`cargo test` runs tests in parallel by default and in arbitrary order. Never have one test depend on another having run first; each test must be independent and order-independent.

### Shared Mutable State Across Tests
A `lazy_static`/`OnceLock` global mutated by tests will race under parallel execution. Make fixtures local to each test, or serialize with `#[serial]`.

### Flaky Time/Network Tests
Prefer injectable clocks (`std::time` behind a trait) and mocks over real sleeps/sockets. Real network calls make tests flaky and offline-hostile.

### Forgetting `#[cfg(test)]`
Without `#[cfg(test)]`, test code and `#[dev-dependencies]` compile into release builds — bloating binaries and slowing builds.

## Links

- [The Rust Book — Testing](https://doc.rust-lang.org/book/ch11-00-testing.html)
- [Rustdoc — Documentation tests](https://doc.rust-lang.org/rustdoc/documentation-tests.html)
- [proptest book](https://proptest-rs.github.io/proptest/intro.html)
- [cargo-fuzz](https://rust-fuzz.github.io/book/cargo-fuzz.html)
- [mockall](https://docs.rs/mockall)
- [wiremock](https://docs.rs/wiremock)
- [cargo-nextest](https://nexte.st/)
