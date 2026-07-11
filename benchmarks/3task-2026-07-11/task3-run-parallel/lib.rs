/// Sum all elements of a vector using 3 threads in parallel.
///
/// The vector is divided into 3 roughly equal slices, and each slice
/// is summed by a separate scoped thread. No `Arc` or `Mutex` is needed
/// because `std::thread::scope` guarantees all threads finish before
/// the borrowed vector goes out of scope.
///
/// # Safety
///
/// This function uses only safe Rust — scoped threads enforce that
/// the borrow of `v` lives as long as the threads need it, satisfying
/// `Send` + `Sync` without heap-allocated synchronization primitives.
///
/// # Returns
///
/// The sum as `i64` to avoid overflow when summing many `i32` values.
///
/// # Examples
///
/// ```
/// use run_parallel::run_parallel;
///
/// let v = vec![1, 2, 3, 4, 5];
/// assert_eq!(run_parallel(v), 15);
/// ```
pub fn run_parallel(v: Vec<i32>) -> i64 {
    let n = v.len();
    let third = n / 3;
    let rem = n % 3;

    // Pre-compute slice boundaries so each closure captures only its own `&[i32]`.
    let boundaries: Vec<usize> = {
        let mut b = vec![0];
        let mut pos = 0;
        for i in 0..3 {
            let chunk_size = third + if i < rem { 1 } else { 0 };
            pos += chunk_size;
            b.push(pos);
        }
        b
    };

    std::thread::scope(|s| {
        let mut handles = Vec::with_capacity(3);
        for i in 0..3 {
            let slice = &v[boundaries[i]..boundaries[i + 1]];
            // `move` is fine here: `&[i32]` is `Copy`, and scoped threads
            // ensure the borrow on `v` is still valid.
            handles.push(s.spawn(move || slice.iter().map(|&x| x as i64).sum::<i64>()));
        }
        handles.into_iter().map(|h| h.join().unwrap()).sum()
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn small_vector() {
        let v = vec![1, 2, 3, 4, 5];
        assert_eq!(run_parallel(v), 15);
    }

    #[test]
    fn large_vector() {
        let v = vec![1; 1000];
        assert_eq!(run_parallel(v), 1000);
    }

    #[test]
    fn empty_vector() {
        let v: Vec<i32> = vec![];
        assert_eq!(run_parallel(v), 0);
    }

    #[test]
    fn single_element() {
        let v = vec![42];
        assert_eq!(run_parallel(v), 42);
    }

    #[test]
    fn negative_numbers() {
        let v = vec![-5, 10, -3, 8, -1];
        assert_eq!(run_parallel(v), 9);
    }

    #[test]
    fn exactly_three_elements() {
        let v = vec![7, 11, 13];
        assert_eq!(run_parallel(v), 31);
    }
}
