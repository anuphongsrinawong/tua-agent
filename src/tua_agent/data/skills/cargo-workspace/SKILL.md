---
name: cargo-workspace
description: Cargo workspaces — shared Cargo.lock, [workspace.dependencies], feature flags, [patch]/[replace], build-dependencies, target-specific deps, and publishing workflow
---

# Cargo Workspaces

A workspace lets multiple crates share one `Cargo.lock`, one `target/` directory, and a common dependency set. Use it for any multi-crate repository.

## Workspace Layout

```
my-workspace/
├── Cargo.toml          # workspace root (virtual or with [workspace])
├── Cargo.lock          # shared, single source of truth
├── crates/
│   ├── core/
│   │   └── Cargo.toml
│   ├── cli/
│   │   └── Cargo.toml
│   └── utils/
│       └── Cargo.toml
└── target/             # shared build output
```

```toml
# Root Cargo.toml
[workspace]
resolver = "2"
members = ["crates/core", "crates/cli", "crates/utils"]
```

`resolver = "2"` (the edition-2021 default) enables feature unification that respects per-crate usage instead of merging across the workspace.

## [workspace.dependencies] — Central Version Management

Define a dependency once at the workspace root and reference it by name in each member:

```toml
# Root Cargo.toml
[workspace.dependencies]
serde = { version = "1.0", features = ["derive"] }
tokio = "1"
anyhow = "1"
```

```toml
# crates/core/Cargo.toml
[dependencies]
serde = { workspace = true }
anyhow = { workspace = true }

[dev-dependencies]
tokio = { workspace = true }
```

This pins every member to one version and makes upgrades a single edit.

## Local Crates

```toml
[dependencies]
my-utils = { path = "../utils", version = "0.1.0" }
```

Always specify a `version` even for `path` deps if you intend to publish — `path` is used locally, `version` is what the registry resolves when published.

## Feature Flags

```toml
[features]
default = ["json"]
json = ["dep:serde_json"]
async-runtime = ["dep:tokio"]

[dependencies]
serde_json = { version = "1", optional = true }
tokio = { version = "1", optional = true }
```

- `dep:serde_json` (`dep:` syntax) refers to the optional dependency without exposing it as an implicit feature named `serde_json`.
- `default-features = false` opts a dependency out of its defaults so you only enable what you use.

```toml
[dependencies]
serde = { version = "1", default-features = false, features = ["derive", "alloc"] }
```

### Optional / Build Dependencies

```toml
[build-dependencies]      # used by build.rs only
prost-build = "0.12"

[dependencies]
rand = { version = "0.8", optional = true }   # only compiled behind a feature
```

## Target-Specific Dependencies

```toml
[target.'cfg(windows)'.dependencies]
winapi = { version = "0.3", features = ["winuser"] }

[target.'cfg(unix)'.dependencies]
nix = "0.27"
```

## [patch.crates-io] & [replace]

Override a dependency's source — essential for local development against an upstream fix:

```toml
[patch.crates-io]
serde = { git = "https://github.com/serde-rs/serde", branch = "main" }
# or a local checkout:
# foo = { path = "../my-fork-of-foo" }
```

`[patch]` (preferred) replaces a crate; `[replace]` is deprecated.

## Publishing Workflow

```bash
cargo publish --dry-run     # validate packaging without uploading
cargo publish               # upload to crates.io
cargo yank --vers 1.0.2     # prevent new dependents from picking a bad version
                            # (yanked versions still work for existing lock files)
```

### Version Bump Workflow (SemVer)

- **PATCH** (`1.2.3 -> 1.2.4`): bug fixes, no API change.
- **MINOR** (`1.2.4 -> 1.3.0`): backwards-compatible additions.
- **MAJOR** (`1.3.0 -> 2.0.0`): breaking change.

After a breaking change, publish all affected crates in dependency order (deps before dependents) and bump `version = "x.y.z"` in every `[dependencies]` reference.

```bash
cargo workspaces version minor    # cargo-workspaces plugin automates multi-crate bumps
cargo workspaces publish
```

## Common Pitfalls

### Feature Unification Across the Workspace
With `resolver = "1"`, enabling a feature in one crate turns it on for every crate in the build. `resolver = "2"` fixes this by resolving features per-target and per-crate — always use it on edition 2021+.

### Circular Dependencies
`core` depending on `cli` while `cli` depends on `core` is a hard error. Extract the shared code into a third crate (e.g., `shared`/`types`) that both depend on.

### Forgetting to Bump Dependents After a Breaking Change
If `utils` goes `0.1 -> 0.2` with a breaking change but `core` still pins `utils = "0.1"`, `cargo publish` rejects it. Bump and update all in-crate references in one commit.

### Publishing Without `version` on a `path` Dep
A `path`-only dependency with no `version` works locally but fails `cargo publish` ("no version specified"). Always pair `path` with the published `version`.

### `default-features = false` Surprises
Disabling defaults on a crate you depend on transitively doesn't propagate. If you need a feature off everywhere, each crate in the chain must disable it.

### Shared `target/` Disk Blow-Up
Large workspaces share one `target/`; `cargo clean` occasionally, and use `cargo build --timings` to find slow crates.

## Links

- [Cargo Book — Workspaces](https://doc.rust-lang.org/cargo/reference/workspaces.html)
- [Cargo Book — Specifying Dependencies](https://doc.rust-lang.org/cargo/reference/specifying-dependencies.html)
- [Cargo Book — Features](https://doc.rust-lang.org/cargo/reference/features.html)
- [Cargo Book — [patch]](https://doc.rust-lang.org/cargo/reference/overriding-dependencies.html)
- [Cargo Book — Publishing](https://doc.rust-lang.org/cargo/reference/publishing.html)
- [cargo-workspaces](https://docs.rs/cargo-workspaces)
- [Resolver v2](https://doc.rust-lang.org/cargo/reference/resolver.html#feature-resolver-version-2)
