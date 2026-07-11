/// Splits a string slice at the first space character, returning the two halves.
///
/// This is a zero-copy operation — no heap allocation is performed. The returned
/// string slices borrow from the original input and live as long as it does.
///
/// # Behaviour
///
/// * If a space is found, returns `(before_space, after_space)` where the
///   second element includes everything after (and not including) the space.
/// * If **no** space is found, returns `(input, "")` — the original string in
///   the first element and an empty slice in the second.
/// * If the string is empty, returns `("", "")`.
///
/// # Examples
///
/// ```
/// use split_pair::split_pair;
///
/// let (first, rest) = split_pair("hello world");
/// assert_eq!(first, "hello");
/// assert_eq!(rest, "world");
///
/// // No space → full string in first position
/// let (first, rest) = split_pair("hello");
/// assert_eq!(first, "hello");
/// assert_eq!(rest, "");
///
/// // Multiple spaces → splits at the first space only
/// let (first, rest) = split_pair("a  b  c");
/// assert_eq!(first, "a");
/// assert_eq!(rest, " b  c");
///
/// // Empty string
/// let (first, rest) = split_pair("");
/// assert_eq!(first, "");
/// assert_eq!(rest, "");
/// ```
#[allow(clippy::needless_lifetimes)]
pub fn split_pair<'a>(s: &'a str) -> (&'a str, &'a str) {
    match s.find(' ') {
        Some(idx) => (&s[..idx], &s[idx + 1..]),
        None => (s, ""),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn basic_split() {
        let (first, rest) = split_pair("hello world");
        assert_eq!(first, "hello");
        assert_eq!(rest, "world");
    }

    #[test]
    fn no_space_returns_full_and_empty() {
        let (first, rest) = split_pair("hello");
        assert_eq!(first, "hello");
        assert_eq!(rest, "");
    }

    #[test]
    fn multiple_spaces_splits_at_first_only() {
        let (first, rest) = split_pair("a  b  c");
        assert_eq!(first, "a");
        assert_eq!(rest, " b  c");
    }

    #[test]
    fn empty_string_returns_two_empty_slices() {
        let (first, rest) = split_pair("");
        assert_eq!(first, "");
        assert_eq!(rest, "");
    }

    #[test]
    fn leading_space() {
        let (first, rest) = split_pair(" hello");
        assert_eq!(first, "");
        assert_eq!(rest, "hello");
    }

    #[test]
    fn trailing_space() {
        let (first, rest) = split_pair("hello ");
        assert_eq!(first, "hello");
        assert_eq!(rest, "");
    }

    #[test]
    fn only_spaces() {
        let (first, rest) = split_pair("   ");
        assert_eq!(first, "");
        assert_eq!(rest, "  ");
    }

    #[test]
    fn return_lifetime_matches_input() {
        let s = String::from("hello world");
        let (first, rest) = split_pair(&s);
        assert_eq!(first, "hello");
        assert_eq!(rest, "world");
    }
}
