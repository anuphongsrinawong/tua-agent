/// Applies a function `f` twice to a value `x`, returning `f(f(x))`.
///
/// This function uses `FnMut` because:
/// - `FnMut` is the most flexible trait that can be called multiple times
/// - `FnOnce` consumes its closure, so it can only be called once
/// - `FnMut` allows mutable state (e.g., counters) while supporting repeated calls
/// - `Fn` is a subtype of `FnMut`, so pure functions also work
pub fn apply_twice<T>(x: T, mut f: impl FnMut(T) -> T) -> T {
    let intermediate = f(x);
    f(intermediate)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_fn_doubling() {
        // Fn: pure function that captures by reference (or nothing)
        let double = |x: i32| x * 2;
        assert_eq!(apply_twice(3, double), 12);
    }

    #[test]
    fn test_fn_square() {
        // Fn: another pure function (square then square = fourth power)
        let square = |x: i32| x * x;
        assert_eq!(apply_twice(3, square), 81); // (3^2)^2 = 81
    }

    #[test]
    fn test_fn_string_concat() {
        // Fn: working with different types
        let exclaim = |s: String| s + "!";
        assert_eq!(apply_twice("hello".to_string(), exclaim), "hello!!");
    }

    #[test]
    fn test_fnmut_counter() {
        // FnMut: captures mutable variable (counter)
        let mut count = 0;
        let add_and_count = |x: i32| {
            count += 1;
            x + 1
        };

        // After two calls, count should be 2
        assert_eq!(apply_twice(5, add_and_count), 7);
        assert_eq!(count, 2);
    }

    #[test]
    fn test_fnmut_stateful_accumulator() {
        // FnMut: stateful closure that accumulates values
        let mut accumulator = 0;
        let accumulate = |x: i32| {
            accumulator += x;
            accumulator
        };

        // First call: accumulator = 0 + 10 = 10
        // Second call: accumulator = 10 + 10 = 20
        assert_eq!(apply_twice(10, accumulate), 20);
        assert_eq!(accumulator, 20);
    }

    #[test]
    fn test_move_closure() {
        // Move closure: captures ownership
        let multiplier = 5;
        let multiply = move |x: i32| x * multiplier;

        // multiply(multiply(2)) = multiply(2 * 5) = multiply(10) = 10 * 5 = 50
        assert_eq!(apply_twice(2, multiply), 50);
    }

    #[test]
    fn test_move_closure_string() {
        // Move closure with owned data
        let suffix = String::from(" world");
        let append = move |s: String| s + &suffix;

        let result = apply_twice("Hello".to_string(), append);
        assert_eq!(result, "Hello world world");
    }

    #[test]
    fn test_complex_type() {
        // Test with a more complex type
        // f((5,3)) = (8,2); f((8,2)) = (10,6)
        let transform = |(a, b): (i32, i32)| (a + b, a - b);
        assert_eq!(apply_twice((5, 3), transform), (10, 6));
    }
}
