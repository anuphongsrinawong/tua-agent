//! Parallel vector summation using scoped threads.
//!
//! This module provides `run_parallel`, which sums a vector of integers
//! using 3 parallel threads via `std::thread::scope`.

use std::thread;

/// Sums a vector of i32 using 3 parallel threads.
///
/// Uses `std::thread::scope` to create scoped threads that can safely
/// borrow from the parent scope without Arc/Mutex. The vector is split
/// into 3 chunks, each processed by a separate thread.
///
/// # Arguments
///
/// * `v` - Vector of i32 values to sum
///
/// # Returns
///
/// The sum of all elements as i64
///
/// # Examples
///
/// ```ignore
/// // Doc example — crate name varies by setup
/// let result = run_parallel_claude::run_parallel(vec![1, 2, 3, 4, 5, 6]);
/// assert_eq!(result, 21);
/// ```
pub fn run_parallel(v: Vec<i32>) -> i64 {
    let len = v.len();

    // Handle empty vector early
    if len == 0 {
        return 0;
    }

    // Handle single element without threading
    if len == 1 {
        return v[0] as i64;
    }

    // Calculate chunk sizes for 3 threads
    let chunk_size = len / 3;
    let rem = len % 3;

    let mut sums = [0i64; 3];

    thread::scope(|s| {
        // Thread 1: first chunk
        let t1 = s.spawn(|| {
            let end = chunk_size + if rem > 0 { 1 } else { 0 };
            v[..end].iter().map(|&x| x as i64).sum::<i64>()
        });

        // Thread 2: second chunk
        let t2 = s.spawn(|| {
            let start = chunk_size + if rem > 0 { 1 } else { 0 };
            let end = start + chunk_size + if rem > 1 { 1 } else { 0 };
            v[start..end].iter().map(|&x| x as i64).sum::<i64>()
        });

        // Thread 3: third chunk (remainder)
        let t3 = s.spawn(|| {
            let start = chunk_size + chunk_size + if rem > 0 { 1 } else { 0 } + if rem > 1 { 1 } else { 0 };
            v[start..].iter().map(|&x| x as i64).sum::<i64>()
        });

        sums[0] = t1.join().unwrap();
        sums[1] = t2.join().unwrap();
        sums[2] = t3.join().unwrap();
    });

    sums.iter().sum()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_small_vector() {
        let result = run_parallel(vec![1, 2, 3, 4, 5, 6]);
        assert_eq!(result, 21);
    }

    #[test]
    fn test_large_vector() {
        let v: Vec<i32> = (1..=1000).collect();
        let result = run_parallel(v);
        assert_eq!(result, 500500);
    }

    #[test]
    fn test_empty_vector() {
        let result = run_parallel(vec![]);
        assert_eq!(result, 0);
    }

    #[test]
    fn test_single_element() {
        let result = run_parallel(vec![42]);
        assert_eq!(result, 42);
    }
}
