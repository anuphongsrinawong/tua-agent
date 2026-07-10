---
name: wasm
description: Compiling Rust to WebAssembly — wasm-pack, wasm-bindgen for JS interop, wasm32-unknown-unknown target, web-sys/js-sys, smaller binaries, and wasm testing
---

# Rust + WebAssembly

Rust compiles to `wasm32-unknown-unknown`, producing small, fast WebAssembly modules that interoperate with JavaScript. The toolchain of choice is `wasm-pack`.

## Setup

```bash
rustup target add wasm32-unknown-unknown
cargo install wasm-pack        # the primary build/test/pack tool
```

## wasm-bindgen — JS Interop

`wasm-bindgen` is the bridge: it exposes Rust functions/structs to JS and imports JS functions into Rust.

```rust
use wasm_bindgen::prelude::*;

/// Greet someone from JavaScript.
#[wasm_bindgen]
pub fn greet(name: &str) -> String {
    format!("Hello, {}!", name)
}
```

After `wasm-pack build`, JS can call `greet("world")` directly.

### Importing JS Functions

```rust
#[wasm_bindgen]
extern "C" {
    #[wasm_bindgen(js_namespace = console)]
    fn log(s: &str);
}

#[wasm_bindgen]
pub fn shout(msg: &str) {
    log(msg);
}
```

## The Build Command

```bash
wasm-pack build --target web       # output for native ES modules + <script type="module">
wasm-pack build --target nodejs    # for Node.js / bundlers
wasm-pack build --target bundler   # for webpack/rollup/vite
wasm-pack build --release          # optimized (default for publish)
```

`--target web` needs no bundler — import the generated JS directly in the browser.

## Consuming in the Browser (target web)

```html
<script type="module">
  import init, { greet } from './pkg/my_crate.js';
  await init();                    // must await before calling exports
  console.log(greet('world'));
</script>
```

## web-sys & js-sys — DOM & JS Standard Types

- **js-sys** — bindings to JS built-ins (`Array`, `Object`, `Date`, `Promise`, `Reflect`).
- **web-sys** — bindings to the full Web API (`Document`, `Element`, `Window`, `Canvas`, `fetch`).

```rust
use wasm_bindgen::JsCast;
use web_sys::{Document, HtmlCanvasElement};

fn canvas() -> Option<HtmlCanvasElement> {
    let doc = web_sys::window()?.document()?;
    let el = doc.get_element_by_id("canvas")?;
    el.dyn_into::<HtmlCanvasElement>().ok()
}
```

Enable only the `web-sys` features you use to keep the bundle small:

```toml
[dependencies.web-sys]
version = "0.3"
features = ["Document", "Window", "HtmlCanvasElement", "CanvasRenderingContext2d"]
```

## Smaller Binaries

```toml
[profile.release]
opt-level = "z"      # or "s" — optimize for size
lto = true
codegen-units = 1
strip = true
```

```rust
// console_error_panic_hook — readable panics in the browser console
#[cfg(feature = "console_error_panic_hook")]
console_error_panic_hook::set_once();
```

`wee_alloc` (a smaller allocator) was historically popular; it is now largely unmaintained — prefer default allocator tuning and check final `.wasm` size with `wasm-opt -Oz` from binaryen.

## Passing Data Across the Boundary

- **Numbers, `bool`, `char`, `&str`/`String`** — direct.
- **Complex/owned data** — serialize with `serde` + `serde-wasm-bindgen` (or `gloo` helpers):

```rust
#[derive(serde::Serialize, serde::Deserialize)]
pub struct Point { pub x: f64, pub y: f64 }

#[wasm_bindgen]
pub fn parse_point(val: JsValue) -> Result<JsValue, JsValue> {
    let p: Point = serde_wasm_bindgen::from_value(val).map_err(|e| e.to_string())?;
    serde_wasm_bindgen::to_value(&Point { x: p.x + 1.0, y: p.y + 1.0 })
        .map_err(|e| e.to_string().into())
}
```

Avoid frequent cross-boundary calls (each has overhead) — batch work in Rust.

## Testing WebAssembly

```bash
wasm-pack test --node        # run tests in Node.js
wasm-pack test --headless    # run tests in a headless browser (needs geckodriver)
wasm-pack test --firefox     # specific browser
```

```rust
use wasm_bindgen_test::*;

#[wasm_bindgen_test]
fn adds_in_wasm() {
    assert_eq!(2 + 2, 4);
}
```

Configure the test runner in `Cargo.toml`:

```toml
[dev-dependencies]
wasm-bindgen-test = "0.3"
```

## Project Layout

```
my-wasm-crate/
├── Cargo.toml
├── src/lib.rs
├── tests/web.rs          # wasm-bindgen-test tests
└── www/                  # static site / bundler frontend
    └── index.html
```

## Common Pitfalls

### Forgetting `#[wasm_bindgen]`
A public `pub fn` without `#[wasm_bindgen]` is not exported — JS won't see it. Every boundary function/struct needs the attribute (or `#[wasm_bindgen]` on an `extern "C"` block for imports).

### Calling Exports Before `init()`
With `--target web`, you must `await init()` (or `init().then(...)`) before calling any exported function, otherwise the wasm module isn't ready.

### Panics Are Silent by Default
A Rust panic in wasm aborts with an opaque "unreachable" trap. Wire up `console_error_panic_hook::set_once()` early in `main`/init so panics print a stack trace to the console.

### Heavy web-sys Features Inflate the Bundle
`features = [...]` pulls in codegen per API. Enable only what you call, and run `wasm-opt -Oz` + `twiggy top` to inspect what's bloating the module.

### Treating wasm Threads Like OS Threads
`std::thread` is unavailable on `wasm32-unknown-unknown`. Use `wasm-bindgen-futures` + async, or compile to `wasm32-unknown-eme`/`wasm32-wasip1` if you need threads/WASI.

### Blocking in Async wasm
There is no preemption; a long synchronous computation blocks the browser UI. Chunk long work with `await` yielding (e.g., `wasm_bindgen_futures::spawn_local`) or move it to a Web Worker.

## Links

- [wasm-pack book](https://rustwasm.github.io/docs/wasm-pack/)
- [wasm-bindgen guide](https://rustwasm.github.io/docs/wasm-bindgen/)
- [Rust 🦀 and WebAssembly book](https://rustwasm.github.io/book/)
- [web-sys API docs](https://docs.rs/web-sys)
- [js-sys API docs](https://docs.rs/js-sys)
- [serde-wasm-bindgen](https://docs.rs/serde-wasm-bindgen)
- [wasm-bindgen-test](https://docs.rs/wasm-bindgen-test)
- [wasm-opt / binaryen](https://github.com/WebAssembly/binaryen)
