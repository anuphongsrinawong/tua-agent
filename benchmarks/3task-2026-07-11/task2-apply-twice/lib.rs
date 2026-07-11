/// Applies a closure `f` twice to the input value `x`.
///
/// This is equivalent to computing `f(f(x))`.
///
/// The function accepts any closure that implements [`FnMut`], which is the most
/// flexible trait bound that allows calling the closure multiple times. This
/// supports:
///
/// - **Pure functions** (`Fn`) — closures that only read their captures.
/// - **Stateful closures** (`FnMut`) — closures that mutate captured variables
///   between calls.
/// - **Move-capture closures** — closures that take ownership of captured values
///   via the `move` keyword, as long as the body does not consume them
///   (which would make them [`FnOnce`]-only).
///
/// # Examples
///
/// ## Pure function — doubling an integer
///
/// ```
/// use apply_twice::apply_twice;
///
/// let result = apply_twice(3, |x| x * 2);
/// assert_eq!(result, 12);
/// ```
///
/// ## String concatenation (mutable binding)
///
/// ```
/// use apply_twice::apply_twice;
///
/// let result = apply_twice("hello".to_string(), |mut s| {
///     s.push_str("!");
///     s
/// });
/// assert_eq!(result, "hello!!");
/// ```
///
/// ## Stateful counter (`FnMut`)
///
/// ```
/// use apply_twice::apply_twice;
///
/// let mut counter = 0i32;
/// let result = apply_twice(10, |x| {
///     counter += 1;
///     x + counter
/// });
/// assert_eq!(result, 13); // 10+1=11, 11+2=13
/// assert_eq!(counter, 2);
/// ```
///
/// ## Move-capture closure
///
/// ```
/// use apply_twice::apply_twice;
///
/// let prefix = ">>".to_string();
/// let result = apply_twice("hello".to_string(), move |s| {
///     format!("{prefix}{s}")
/// });
/// assert_eq!(result, ">>>>hello");
/// ```
pub fn apply_twice<T>(x: T, mut f: impl FnMut(T) -> T) -> T {
    let intermediate = f(x);
    f(intermediate)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn int_doubling() {
        // Pure function — `|x| x * 2` implements `Fn`, which satisfies `FnMut`.
        let result = apply_twice(3, |x| x * 2);
        assert_eq!(result, 12);
    }

    #[test]
    fn string_concatenation() {
        let result = apply_twice("hello".to_string(), |mut s| {
            s.push_str("!");
            s
        });
        assert_eq!(result, "hello!!");
    }

    #[test]
    fn int_doubling_verify_more() {
        assert_eq!(apply_twice(0, |x| x * 2), 0);
        assert_eq!(apply_twice(1, |x| x * 2), 4);
        assert_eq!(apply_twice(-3, |x| x * 2), -12);
        assert_eq!(apply_twice(5, |x| x + 1), 7);
    }

    #[test]
    fn stateful_counter() {
        // Closure that mutates a captured variable between calls.
        let mut counter = 0i32;
        let result = apply_twice(10, |x| {
            counter += 1;
            x + counter
        });
        assert_eq!(result, 13); // first call: 10+1=11, second: 11+2=13
        assert_eq!(counter, 2);
    }

    #[test]
    fn stateful_accumulator() {
        // Another stateful example: accumulating values.
        let mut acc = Vec::new();
        let result = apply_twice(0u32, |x| {
            acc.push(x);
            x + 1
        });
        assert_eq!(result, 2); // 0→1, 1→2
        assert_eq!(acc, vec![0, 1]);
    }

    #[test]
    fn move_capture_closure() {
        // A `move` closure that captures `prefix` by value but does not consume
        // it on each call (format! borrows it), so it still implements `FnMut`.
        let prefix = ">>".to_string();
        let result = apply_twice("hello".to_string(), move |s| format!("{prefix}{s}"));
        assert_eq!(result, ">>>>hello");
    }

    #[test]
    fn move_capture_with_state() {
        // A `move` closure that captures a mutable counter by value.
        // `move` moves `counter` into the closure, but since it's `i32`
        // (Copy), and the closure only mutates it in place, this still
        // implements `FnMut`.
        let result = apply_twice(0i32, move |mut x| {
            x += 1;
            x
        });
        assert_eq!(result, 2);
    }

    #[test]
    fn mapped_through_string_slice() {
        // Test with a more complex transform: append then prepend.
        let result = apply_twice(String::new(), |mut s| {
            s.push_str("ab");
            s
        });
        assert_eq!(result, "abab");
    }

    #[test]
    fn generic_over_different_types() {
        // f64
        assert!((apply_twice(1.5f64, |x| x * 2.0) - 6.0).abs() < 1e-10);
        // i64
        assert_eq!(apply_twice(7i64, |x| x * 3), 63);
        // bool — XOR with true
        assert_eq!(apply_twice(false, |x| x ^ true), false);
    }
}
