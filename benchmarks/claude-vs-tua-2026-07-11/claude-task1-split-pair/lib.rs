/// Splits a string slice at the first space character, returning a tuple of (before, after).
///
/// This function performs zero-copy splitting using slice indexing and explicit lifetime annotation.
/// No heap allocation occurs - the returned slices are views into the original string.
///
/// # Arguments
///
/// * `s` - A string slice to split
///
/// # Returns
///
/// A tuple of two string slices:
/// - The first element is everything before (and not including) the first space
/// - The second element is everything after (and not including) the first space
///
/// # Examples
///
/// ```
/// use split_pair_claude::split_pair;
/// let (first, second) = split_pair("hello world");
/// assert_eq!(first, "hello");
/// assert_eq!(second, "world");
/// ```
///
/// # Panics
///
/// This function does not panic. If there is no space character, the first element
/// will be the entire string and the second element will be an empty string.
#[allow(clippy::needless_lifetimes)]
pub fn split_pair<'a>(s: &'a str) -> (&'a str, &'a str) {
    // Find the first space character using zero-copy slice indexing
    if let Some(pos) = s.find(' ') {
        (&s[..pos], &s[pos + 1..])
    } else {
        (s, "")
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_basic_split() {
        let (first, second) = split_pair("hello world");
        assert_eq!(first, "hello");
        assert_eq!(second, "world");
    }

    #[test]
    fn test_no_space() {
        let (first, second) = split_pair("helloworld");
        assert_eq!(first, "helloworld");
        assert_eq!(second, "");
    }

    #[test]
    fn test_multiple_spaces_only_splits_first() {
        let (first, second) = split_pair("one two three");
        assert_eq!(first, "one");
        assert_eq!(second, "two three");
    }

    #[test]
    fn test_leading_space() {
        let (first, second) = split_pair(" hello");
        assert_eq!(first, "");
        assert_eq!(second, "hello");
    }

    #[test]
    fn test_trailing_space() {
        let (first, second) = split_pair("hello ");
        assert_eq!(first, "hello");
        assert_eq!(second, "");
    }

    #[test]
    fn test_empty_string() {
        let (first, second) = split_pair("");
        assert_eq!(first, "");
        assert_eq!(second, "");
    }

    #[test]
    fn test_single_space() {
        let (first, second) = split_pair(" ");
        assert_eq!(first, "");
        assert_eq!(second, "");
    }

    #[test]
    fn test_unicode_content() {
        let (first, second) = split_pair("café résumé");
        assert_eq!(first, "café");
        assert_eq!(second, "résumé");
    }

    #[test]
    fn test_zero_copy_slices_reference_original() {
        let original = "test data";
        let (first, second) = split_pair(original);
        // Verify that slices are referencing the original data
        assert!(std::ptr::eq(first.as_ptr(), original.as_ptr()));
        assert_eq!(second.as_ptr(), unsafe { original.as_ptr().add(5) });
    }
}
