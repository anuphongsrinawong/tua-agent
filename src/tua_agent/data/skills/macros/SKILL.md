---
name: macros
description: Rust declarative macros (macro_rules!), procedural macros (derive, attribute, function-like), and common macro patterns
---

# Rust Macros

Rust has two macro systems:

1. **Declarative macros** (`macro_rules!`) — pattern-matching template expansion.
2. **Procedural macros** — actual Rust code that generates code at compile time.

Unlike C preprocessor macros, Rust macros are **hygienic** and operate on the AST, not text.

## Declarative Macros — `macro_rules!`

```rust
macro_rules! vec_of_strings {
    ($($x:expr),*) => {
        {
            let mut v = Vec::new();
            $(
                v.push(String::from($x));
            )*
            v
        }
    };
}

fn main() {
    let names = vec_of_strings!("alice", "bob", "carol");
    println!("{:?}", names);
}
```

### Fragment Specifiers

| Specifier | Matches | Example |
|-----------|---------|---------|
| `expr` | Expression | `1 + 2`, `foo()` |
| `ident` | Identifier | `x`, `MyStruct` |
| `tt` | Token tree | anything inside `()`/`[]`/`{}` |
| `ty` | Type | `Vec<i32>`, `&str` |
| `pat` | Pattern | `Some(x)`, `_` |
| `stmt` | Statement | `let x = 1;` |
| `block` | Block | `{ ... }` |
| `literal` | Literal | `42`, `"hi"` |
| `meta` | Attribute meta | `derive(Debug)` |
| `lifetime` | Lifetime | `'a`, `'static` |
| `vis` | Visibility | `pub`, `pub(crate)` |

### Repetition

```rust
macro_rules! sum {
    ($($x:expr),*) => {
        0 $(+ $x)*
    };
}

fn main() {
    assert_eq!(sum!(1, 2, 3, 4), 10);
}
```

The `$(...)*` repeats, and you can use a separator:

- `$(...)*` — zero or more, no separator
- `$(...),*` — zero or more, comma-separated
- `$(...),+` — one or more, comma-separated
- `$(...)?` — zero or one

```rust
macro_rules! hashmap {
    ($($key:expr => $value:expr),* $(,)?) => {{
        let mut m = std::collections::HashMap::new();
        $(
            m.insert($key, $value);
        )*
        m
    }};
}

let h = hashmap!("a" => 1, "b" => 2,);
```

### Recursive Macros

```rust
macro_rules! count {
    () => (0);
    ($head:tt $($tail:tt)*) => (1 + count!($($tail)*));
}

fn main() {
    println!("{}", count!(a b c d)); // 4
}
```

### Hygiene

Variables introduced inside the macro are distinct from those outside, preventing accidental capture:

```rust
macro_rules! swap {
    ($a:expr, $b:expr) => {
        let tmp = $a;
        $a = $b;
        $b = tmp;
    };
}

fn main() {
    let mut x = 1;
    let mut y = 2;
    swap!(x, y);
    // Even if caller had a variable named `tmp`, it wouldn't conflict.
}
```

To export a macro for use in other crates:

```rust
// In lib.rs
#[macro_export]
macro_rules! my_macro { ... }
```

## Procedural Macros

Procedural macros are functions that take `TokenStream` as input and return `TokenStream` as output. They must live in a **separate crate** with `proc-macro = true` in `Cargo.toml`.

```toml
# Cargo.toml (proc macro crate)
[lib]
proc-macro = true

[dependencies]
syn = "2"
quote = "1"
proc-macro2 = "1"
```

There are three kinds:

### 1. Derive Macros

```rust
use proc_macro::TokenStream;
use quote::quote;
use syn::{parse_macro_input, DeriveInput};

#[proc_macro_derive(HelloMacro)]
pub fn hello_macro_derive(input: TokenStream) -> TokenStream {
    let ast = parse_macro_input!(input as DeriveInput);
    let name = &ast.ident;
    let expanded = quote! {
        impl #name {
            fn hello_macro() {
                println!("Hello from {}!", stringify!(#name));
            }
        }
    };
    expanded.into()
}
```

Usage:

```rust
#[derive(HelloMacro)]
struct Pancakes;

fn main() {
    Pancakes::hello_macro(); // "Hello from Pancakes!"
}
```

### 2. Attribute Macros

Attribute macros can be applied to any item, possibly transforming it entirely.

```rust
#[proc_macro_attribute]
pub fn log_call(_attr: TokenStream, item: TokenStream) -> TokenStream {
    let input = parse_macro_input!(item as syn::ItemFn);
    let sig = input.sig.clone();
    let block = input.block.clone();
    let name = &sig.ident;

    quote! {
        #sig {
            println!("entering {}", stringify!(#name));
            #block
        }
    }.into()
}
```

Usage:

```rust
#[log_call]
fn do_thing() { /* ... */ }
```

### 3. Function-Like Macros

Called like `name!(...)`, just like `macro_rules!`, but with full code-generation power.

```rust
#[proc_macro]
pub fn make_answer(_input: TokenStream) -> TokenStream {
    quote!(42).into()
}
```

Usage:

```rust
let x: i32 = make_answer!();
```

A common example is `sqlx::query!`, which validates SQL at compile time.

## Common Patterns

### Derive with Helper Attributes

```rust
#[proc_macro_derive(Builder, attributes(builder))]
pub fn derive_builder(input: TokenStream) -> TokenStream {
    // allows #[builder(each = "name")] on fields
    ...
}
```

```rust
#[derive(Builder)]
struct Command {
    #[builder(each = "arg")]
    args: Vec<String>,
}
```

### The `quote!` Macro — Generating Code

`quote!` lets you write code that will be emitted, interpolating `#var`:

```rust
let name = format_ident!("MyType");
let tokens = quote! {
    struct #name;
};
// tokens: `struct MyType ;`
```

### Parsing Custom Syntax with `syn`

```rust
use syn::{parse::{Parse, ParseStream}, Token};

struct KeyValue {
    key: syn::Ident,
    value: syn::LitStr,
}

impl Parse for KeyValue {
    fn parse(input: ParseStream) -> syn::Result<Self> {
        let key: syn::Ident = input.parse()?;
        let _eq: Token![=] = input.parse()?;
        let value: syn::LitStr = input.parse()?;
        Ok(KeyValue { key, value })
    }
}
```

## Common Pitfalls & Errors

### `macro_rules!` Export Visibility

A `macro_rules!` macro defined inside a module isn't visible outside unless `#[macro_export]` is used.

```rust
// Invisible to other modules/crates
macro_rules! internal { () => {} };

// Visible crate-wide (and to other crates)
#[macro_export]
macro_rules! public { () => {} };
```

### Macro Expansion Order — Macro Before Type Check

Macros run before type checking, so they can't observe types or trait resolution. If your macro needs to know about types, consider a derive macro instead.

### Procedural Macros Must Be in a Separate Crate

```
error: procedural macro crates cannot export any items other than proc macros
```

Don't put proc macros and regular code in the same crate.

### `syn` 1.x vs 2.x

The `syn` crate has different APIs. Code written for `syn 1` won't compile under `syn 2`. Use `syn = "2"` for new code; the parsing API changed significantly (e.g., `DeriveInput`, `parse_macro_input!` usage).

### `expr` vs `tt` in Repetitions

```rust
macro_rules! bad {
    ($($e:expr),*) => { /* $e:expr in repetition is fine */ };
}

// But mixed types break:
macro_rules! take {
    ($($e:expr),*) => { }; // works
}

// For varargs where each arg may be a different token kind, use `tt`:
macro_rules! count {
    ($($t:tt)*) => { /* count tokens */ };
}
```

### Hygiene Bites

```rust
macro_rules! using_local {
    ($x:expr) => {
        let val = 10;
        println!("{}", $x + val);
    };
}
// If caller wrote `let val = 5; using_local!(val);`
// the `val` inside and outside are different — caller's `val` is used in $x
// which might surprise them.
```

To intentionally break hygiene (rare, usually a code smell), use `tt` and `$crate` carefully, or use proc macros where there's no hygiene.

## References

- [The Rust Book — Macros](https://doc.rust-lang.org/book/ch19-06-macros.html)
- [The Rust Reference — Macros](https://doc.rust-lang.org/reference/macros.html)
- [The Little Book of Rust Macros](https://danielkeep.github.io/tlborm/book/) (in-depth `macro_rules!`)
- [syn crate](https://docs.rs/syn)
- [quote crate](https://docs.rs/quote)
- [proc-macro2 crate](https://docs.rs/proc-macro2)
- [Proc macro workshop](https://github.com/dtolnay/proc-macro-workshop)
