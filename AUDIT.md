# Tua Agent — Codebase Audit

Audit of `src/tua_agent/` (8 modules) and `tests/` (shared suite for the 4-package Tau monorepo).
All claims below were verified by reading the source, running the CLI, hitting the dashboard, and running the test suite on 2026-07-10.

## Repo shape (context for every finding)

`pyproject.toml` ships **four** packages from one repo:

```
src/tau_agent/   ← portable agent harness (loop, tools, session, types)  — 17 modules
src/tau_ai/      ← provider/model streaming (openai, anthropic, …)       — 13 modules
src/tau_coding/  ← CLI/TUI, sessions, skills, system prompt, providers    — 40 modules
src/tua_agent/   ← the Rust specialization under audit                     —  8 modules
```

`tua_agent` is a thin Rust-focused layer that depends on the other three. Note `tau_agent` (t-a-u, the harness) ≠ `tua_agent` (t-u-a, this package).

---

## Test & smoke-test results

| Check | Result |
|---|---|
| `pytest` (full suite, all 4 packages) | **765 passed, 1 failed** of 766 (76s) |
| Failed test | `tests/test_package_metadata.py::test_current_version_has_release_notes` |
| `tua --help` / `--list-profiles` / `profiles` | ✅ work |
| `tua -p "say hi" --model glm/glm-5.2` | ✅ returns `"Hi"` (full agent loop, provider streaming, session) |
| `tua -p "…"` (no `--model`, defaults) | ❌ fails — `Model is not configured for provider 9router: gpt-5.4` |
| `tua` (no `-p`) | ⚠️ prints "Interactive TUI coming in next release" and exits |
| Dashboard `/api/health`, `/api/status`, `/` | ✅ respond; `/api/status` returns mostly hardcoded data |
| `ruff check src/tua_agent/` | ❌ 85 errors (28 auto-fixable), incl. 20 unused-import F401s |

The single failing test is the version-consistency test (see ❌ #5): `pyproject.toml` declares `version = "0.0.1"`, but `src/tau_coding/data/release-notes/releases.json` has no `0.0.1` entry.

---

## ✅ What works (with evidence)

1. **Imports all resolve.** `tau_agent`, `tau_ai`, `tau_coding`, `tua_agent` import cleanly in the venv; `from tua_agent import cli` succeeds. (`rust_tools.py` correctly imports `AgentTool`/`AgentToolResult`/`ToolCancellationToken` from `tau_agent.tools`, `JSONValue` from `tau_agent.types`.)
2. **The agent loop runs end-to-end.** `tua -p "say hi in one word" --model glm/glm-5.2` → `Hi`, exit 0. Provider streaming, system prompt, session, and tool registration are all live.
3. **All 13 Rust tools are registered in the loop.** `cli.py:159-160` builds `tools = create_coding_tools(...)` then `tools.extend(get_rust_tools())` and passes them to `CodingSessionConfig(tools=tools)`. `rust_tools.py:979-993` defines exactly 13: `cargo, rustc, rustfmt, clippy, rustup, cargo_audit, cargo_outdated, cargo_udep, cargo_deny, cargo_bench, cargo_doc, cargo_test_doc, wasm_pack`. Each has an input schema + executor (`tests/test_tua_agent.py::TestRustTools` passes).
4. **Tool executors are real and robust.** `rust_tools.py` shells out via a shared async subprocess runner with PATH resolution, timeout/cancel handling, process-group kills, output truncation, and `ok`/`error`/`data` results. Optional tools (`cargo-audit/outdated/udeps/deny`, `wasm-pack`) return clear "not installed — `cargo install …`" messages when missing (`TestGracefulFallback` passes).
5. **Session persistence works.** `_run_print_mode` writes a real JSONL session via `jsonl_session_storage(record.path)`. `session-temp.jsonl` in the repo shows real recorded entries (`message`, `leaf`, `model_change`, `session_info`, `thinking_level_change`).
6. **8 Rust profiles** are defined (`rust_profiles.py:30-108`), validated, and rendered by `--list-profiles`. Guardrail flags differ per profile (`TestRustProfiles` passes).
7. **Profile selection measurably changes the system prompt.** `_run_print_mode` injects `build_profile_context()` into `full_system` (`cli.py:167-168`), so `--profile strict` vs `--profile cargo-cult` produce different guardrail text sent to the model.
8. **Config loader works.** `config.py` reads `.tua/config.toml` (project) merged over `~/.tua/config.toml` (user). `TestConfig` passes for defaults and overrides.
9. **9Router provider is configured and tested.** `~/.tau/providers.json` sets `default_provider = "9router"`, `~/.tau/credentials.json` has the `9router` credential, and a live `tua -p … --model glm/glm-5.2` call succeeded against it.
10. **Dashboard HTTP server runs.** `dashboard_command` serves `/` (styled HTML), `/api/status`, `/api/health` from Python's stdlib `http.server` (no extra deps). `TestDashboard` passes.
11. **10 skills exist with valid frontmatter.** `.tau/skills/` has 10 directories (async-rust, cargo-workspace, concurrency, error-handling, lifetimes, macros, ownership-borrowing, smart-pointers, testing, wasm), each with `SKILL.md` + `name:`/`description:`. `TestSkills` passes.

---

## ⚠️ What partially works (runs, but with gaps)

1. **`tua -p` does not work with zero flags — the default model is unservable.**
   `_detect_model()` (`cli.py:240-248`) only checks `DEEPSEEK/ANTHROPIC/OPENAI_API_KEY`; with none set it falls back to `DEFAULT_MODEL` = `gpt-5.4`. But the configured default provider is `9router`, whose catalog (`~/.tau/catalog.toml`) only serves `deepseek/deepseek-v4-flash`, `glm/glm-4.7`, `glm/glm-5.2`. Result: `❌ Error: Model is not configured for provider 9router: gpt-5.4`. The error message itself is good (lists valid models), but the headline command fails until you pass `--model`. `_detect_model()` is unaware of the 9router default.

2. **The system prompt omits the "Available tools" and "Guidelines" sections.**
   `cli.py:168` always sets `custom_system_prompt`, and `tau_coding/system_prompt.py:43-51` takes a shortcut when `custom_prompt` is set: it skips `format_available_tools()` and `format_guidelines()`. So the model gets the Rust identity prompt + profile guardrails + skills + date/cwd, but **no prose list of available tools and no standard guidelines**. The tools are still callable (they're registered on the harness and sent to the provider as tool schemas), so this is a quality gap, not a breakage. The *unused* `build_rust_system_prompt()` (`rust_system_prompt.py:92`) would have done this correctly.

3. **Skills load into the agent context only inside this dev checkout.**
   `TauResourcePaths()` defaults to `~/.tau` (`resources.py:46`), which has 0 Rust skills. They load only via the project-local path when `cwd` = this repo — confirmed: `load_skills(resource_paths_with_cwd(rp, repo))` → **10 skills**. But the skills live at **repo-root `.tau/skills/`**, which is **not under `src/`** and therefore **not included in the wheel** (`pyproject.toml` packages only `src/*`). An installed `tua` running in a real Rust project will see **0 Rust skills** unless they're manually copied. Tests pass only because they run against the dev tree.

4. **Dashboard: project/quality partly real; profile + agent fully hardcoded.**
   - `_collect_project_info` / `_collect_quality` parse `Cargo.toml` and count `.rs` LOC — real but shallow (deps counted by counting `[dependencies` headers).
   - `_collect_build_status` is a **proxy**: it only checks whether `target/debug` exists — it never runs `cargo`. Clippy warning/error counts are always `0`.
   - `_collect_profile_status` (`dashboard.py:393-402`) **hardcodes `Rustacean`** regardless of the `--profile` actually selected.
   - `_collect_agent_status` (`dashboard.py:405-411`) **hardcodes `provider: deepseek`, `model: deepseek-v4-pro`, `tokens: 0`** — never wired to any real session.

5. **Profile guardrail *guidelines* are computed then dropped.**
   `cli.py:147` computes `guidelines = session_config.build_guidelines()` but never passes it anywhere (not to the config, not to the prompt). Only the shorter `build_profile_context()` is used. So the richer per-profile rules in `rust_session.py` / `rust_profiles.profile_guidelines()` are dead.

---

## ❌ What's missing or broken

1. **No interactive TUI.** `tua` with no `-p` just prints `📟 Interactive TUI coming in next release.` and exits (`cli.py:104-106`). The module docstring (`cli.py:4`) and README both claim `tua` "Start interactive TUI (Rust mode)". Tau has a full Textual TUI at `src/tau_coding/tui/` that Tua does not wire up.

2. **README documents a TUI and slash-commands that do not exist.** `README.md:46-60` ("Rust-Specific Commands — Inside the Tua TUI") lists `/cargo build`, `/cargo test`, `/rustc explain E0502`, `/profile ferris`, etc. **None of these exist anywhere in the codebase** (grep for `/cargo`, `/profile`, `register_command` finds nothing in `tua_agent`). This entire section is fictional.

3. **Most promised CLI commands are absent.** Only `dashboard-command` and `profiles` exist. There is **no** `tua new`, `tua check`, `tua fix`, `tua audit`, or `tua bench`.

4. **Dashboard command name is wrong vs. docs.** The function is `dashboard_command` (`cli.py:110`), so Typer exposes it as **`tua dashboard-command`** — not `tua dashboard` as the docstring (`cli.py:8`) and README imply. `tua dashboard` is an unknown command.

5. **Version is inconsistent across the repo, and one test fails because of it.**
   - `src/tua_agent/__init__.py:10` → `__version__ = "0.0.1"`
   - `pyproject.toml` → `version = "0.0.1"`
   - `cli.py:81` → banner hardcodes **`v0.1.0`**
   - `dashboard.py:181` → footer hardcodes **`v0.1.0`**
   - Git history has a `Prepare 0.1.5 release` commit.
   - Commit `2ff9ca1` "Fix: use __version__ in CLI output instead of hardcoded v0.1.0" **only added the import `from tua_agent import __version__` (`cli.py:48`) and never used it** — line 81 still prints `v0.1.0`. The "fix" is incomplete.
   - Consequence: `test_current_version_has_release_notes` fails (no `0.0.1` entry in `releases.json`).

6. **Significant dead code / unused imports.** `ruff` reports **85 errors** in `src/tua_agent/`, including ~20 `F401` unused imports:
   - `build_rust_system_prompt` (imported `cli.py:44`, never called) and its helper `_detect_rust_project` (`rust_system_prompt.py:129`) — a whole, well-built prompt path that's never used.
   - `JsonlSessionStorage`, `ModelProvider`, `DEFAULT_OPENAI_COMPATIBLE_BASE_URL`, `FileCredentialStore`, `DEFAULT_PROVIDER_NAME`, `ProviderSettings`, `BuildSystemPromptOptions`, `build_system_prompt`, `__version__`, plus `subprocess`/`os`/`sys`/`Sequence`/`field`/`Path` across modules.
   - The `skills = load_skills(resource_paths)` call (`cli.py:164`) loads skills that are then **discarded** — `CodingSession` re-loads them itself.

7. **Dashboard has no live cargo output or session-history viewer.** It polls `/api/status` every 5s but never reads real agent session logs or streams build output — both explicitly called out as missing in the audit brief.

8. **No graceful credentials/config UX.** With no API key you get the raw provider error rather than a guided "run `tau login` / set X" message. The CLI doesn't validate provider/model compatibility before launching.

---

## 🔧 Quick wins (< 5 minutes each)

1. **Fix the version once, for real.** Replace `v0.1.0` in `cli.py:81` and `dashboard.py:181` with `v{__version__}`, set `__version__` (and `pyproject.toml`) to the real release value, and add that version to `releases.json`. → kills the failing test and the banner lie in one pass.
2. **Make `tua dashboard` work as documented.** Register the command with an explicit name: `@app.command(name="dashboard")` on `cli.py:109` (or rename the function).
3. **Auto-fix unused imports.** `ruff check --fix src/tua_agent/` clears 28 errors immediately (all the F401s, including the bogus `__version__` "fix").
4. **Make `tua -p` work with zero flags.** Have `_detect_model()` consult the resolved default provider's catalog (e.g. default to `glm/glm-5.2` when the default provider is `9router`) instead of unconditionally falling back to `gpt-5.4`.
5. **Stop dropping the guidelines.** Feed `session_config.build_guidelines()` into the prompt (e.g. via `BuildSystemPromptOptions(extra_guidelines=...)`), or switch `_run_print_mode` to use the already-written `build_rust_system_prompt()` so the system prompt includes Available Tools + guidelines + detected project info.
6. **Rename `contextlib_suppress`** (`rust_tools.py:1008`) to just use `contextlib.suppress`, or drop the `"contextlib_suppress"` quoted annotation (`UP037`) — clears the lint noise around it.

---

## 📋 Priority roadmap (build order)

1. **Make `tua -p "…"` work with no flags.** (⚠️ #1 / ❌ #8) Highest user-facing impact — the flagship command currently errors by default. Fix `_detect_model()` against the 9router catalog.
2. **Resolve version consistency + the failing test.** (❌ #5, quick win #1) Unblocks a green CI.
3. **Either wire the TUI or stop claiming it.** (❌ #1, #2) Reuse `tau_coding/tui/` with Rust defaults, or remove the TUI docstring/README/slash-command sections so docs match reality.
4. **Ship the skills with the package.** (⚠️ #3) Move `.tau/skills/` under `src/tua_agent/` (or add it as wheel package-data and point a `TauResourcePaths` at it) so installed users actually get the 10 Rust skills.
5. **Add the promised CLI commands** `new / check / fix / audit / bench` (❌ #3) — or document them explicitly as not-yet-implemented.
6. **Connect the dashboard to real data.** (⚠️ #4, ❌ #7) Drive profile from the selected `--profile`, agent stats from the active session, run real `cargo check`/`clippy` (or read the session log), and add a session-history viewer.
7. **Delete dead code.** (❌ #6) Remove or actually use `build_rust_system_prompt()`, `_detect_rust_project()`, and the unused imports; pick one Rust-project-detection path (there are currently two: `cli._detect_and_print_rust_project` and `rust_system_prompt._detect_rust_project`).

---

## Notes on test coverage

`tests/` is a **shared** suite for the whole 4-package monorepo. The only file that exercises `tua_agent` directly is `tests/test_tua_agent.py` (profiles, 13 tools, session config, system prompt, dashboard, config, skills) — **all of its tests pass**. The remaining ~34 files test `tau_coding`/`tau_agent`/`tau_ai` (the base layers); they pass too, which means the foundation `tua_agent` builds on is solid. There is **no test** that actually exercises the `_run_print_mode` wiring end-to-end, the system-prompt assembly, or skill-loading-from-cwd — the gaps above are precisely where coverage is thinnest.
