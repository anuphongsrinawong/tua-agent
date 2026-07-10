"""Integration tests for Tua Agent components."""

import pytest
from pathlib import Path


class TestRustProfiles:
    """Tests for Rust coding profiles."""

    def test_all_profiles_load(self):
        from tua_agent.rust_profiles import RUST_PROFILES, get_profile
        assert len(RUST_PROFILES) == 8
        for name in RUST_PROFILES:
            profile = get_profile(name)
            assert profile.name == name
            assert profile.emoji

    def test_strict_profile_guardrails(self):
        from tua_agent.rust_profiles import get_profile
        p = get_profile("strict")
        assert p.forbid_unwrap is True
        assert p.forbid_unsafe is True
        assert p.require_doc_tests is True
        assert p.enforce_clippy_pedantic is True

    def test_ferris_profile_forbids_unsafe(self):
        from tua_agent.rust_profiles import get_profile
        p = get_profile("ferris")
        assert p.forbid_unsafe is True

    def test_rustacean_forbids_unwrap(self):
        from tua_agent.rust_profiles import get_profile
        p = get_profile("rustacean")
        assert p.forbid_unwrap is True

    def test_cargo_cult_is_relaxed(self):
        from tua_agent.rust_profiles import get_profile
        p = get_profile("cargo-cult")
        assert p.forbid_unwrap is False
        assert p.forbid_unsafe is False


class TestRustTools:
    """Tests for Rust tool definitions."""

    def test_thirteen_tools_registered(self):
        from tua_agent.rust_tools import RUST_TOOLS
        assert len(RUST_TOOLS) == 13

    def test_core_tools_present(self):
        from tua_agent.rust_tools import RUST_TOOLS
        names = {t.name for t in RUST_TOOLS}
        assert "cargo" in names
        assert "rustc" in names
        assert "rustfmt" in names
        assert "clippy" in names
        assert "rustup" in names

    def test_extended_tools_present(self):
        from tua_agent.rust_tools import RUST_TOOLS
        names = {t.name for t in RUST_TOOLS}
        assert "cargo_audit" in names
        assert "cargo_outdated" in names
        assert "cargo_udep" in names
        assert "cargo_deny" in names

    def test_all_tools_have_schemas(self):
        from tua_agent.rust_tools import RUST_TOOLS
        for tool in RUST_TOOLS:
            assert tool.input_schema is not None
            assert "type" in tool.input_schema

    def test_all_tools_have_executors(self):
        from tua_agent.rust_tools import RUST_TOOLS
        for tool in RUST_TOOLS:
            assert tool.executor is not None


class TestRustSessionConfig:
    """Tests for RustSessionConfig."""

    def test_builds_guidelines(self):
        from tua_agent.rust_session import RustSessionConfig
        from tua_agent.rust_profiles import get_profile
        config = RustSessionConfig(profile=get_profile("strict"))
        guidelines = config.build_guidelines()
        assert len(guidelines) >= 4

    def test_ferris_guidelines_no_unwrap_mention(self):
        from tua_agent.rust_session import RustSessionConfig
        from tua_agent.rust_profiles import get_profile
        config = RustSessionConfig(profile=get_profile("ferris"))
        guidelines = config.build_guidelines()
        combined = " ".join(guidelines)
        assert "unsafe" in combined.lower()
        assert "unwrap" not in combined.lower()

    def test_profile_context_string(self):
        from tua_agent.rust_session import RustSessionConfig
        from tua_agent.rust_profiles import get_profile
        config = RustSessionConfig(profile=get_profile("strict"))
        ctx = config.build_profile_context()
        assert "strict" in ctx
        assert "FORBIDDEN" in ctx


class TestRustSystemPrompt:
    """Tests for the Rust system prompt."""

    def test_prompt_contains_rust_keywords(self):
        from tua_agent.rust_system_prompt import RUST_SYSTEM_PROMPT
        assert "ownership" in RUST_SYSTEM_PROMPT.lower()
        assert "lifetime" in RUST_SYSTEM_PROMPT.lower()
        assert "cargo" in RUST_SYSTEM_PROMPT.lower()
        assert "borrow" in RUST_SYSTEM_PROMPT.lower()
        assert "unsafe" in RUST_SYSTEM_PROMPT.lower()


class TestDashboard:
    """Tests for the dashboard."""

    def test_html_contains_title(self):
        from tua_agent.dashboard import HTML_TEMPLATE
        assert "Tua Dashboard" in HTML_TEMPLATE

    def test_html_contains_api_endpoints(self):
        from tua_agent.dashboard import HTML_TEMPLATE
        assert "/api/status" in HTML_TEMPLATE
        # /api/health appears in the Python handler code, not the HTML template
        assert "fetch('/api/" in HTML_TEMPLATE

    def test_collect_project_status_returns_dict(self):
        from tua_agent.dashboard import collect_project_status
        result = collect_project_status()
        assert isinstance(result, dict)
        assert "project" in result
        assert "build" in result
        assert "quality" in result
        assert "profile" in result
        assert "agent" in result


class TestNewTools:
    """Tests for the four newly added Rust tools."""

    def test_13_tools_total(self):
        from tua_agent.rust_tools import RUST_TOOLS
        assert len(RUST_TOOLS) == 13

    def test_cargo_bench_present(self):
        from tua_agent.rust_tools import get_rust_tool_names
        assert "cargo_bench" in get_rust_tool_names()

    def test_cargo_doc_present(self):
        from tua_agent.rust_tools import get_rust_tool_names
        assert "cargo_doc" in get_rust_tool_names()

    def test_cargo_test_doc_present(self):
        from tua_agent.rust_tools import get_rust_tool_names
        assert "cargo_test_doc" in get_rust_tool_names()

    def test_wasm_pack_present(self):
        from tua_agent.rust_tools import get_rust_tool_names
        assert "wasm_pack" in get_rust_tool_names()

    def test_new_tools_have_schemas_and_executors(self):
        from tua_agent.rust_tools import RUST_TOOLS
        new_names = {"cargo_bench", "cargo_doc", "cargo_test_doc", "wasm_pack"}
        new_tools = [t for t in RUST_TOOLS if t.name in new_names]
        assert len(new_tools) == 4
        for tool in new_tools:
            assert tool.input_schema is not None
            assert "type" in tool.input_schema
            assert tool.executor is not None


class TestGracefulFallback:
    """Optional toolchain tools must report install instructions when missing."""

    def test_missing_tool_reports_install_instruction(self, monkeypatch):
        import asyncio
        import tua_agent.rust_tools as rt

        def _raise(*_argv, **_kwargs):
            raise FileNotFoundError("executable not found on PATH")

        # Force the shared subprocess runner to raise so the fallback path runs.
        monkeypatch.setattr(rt, "_run_subprocess", _raise)

        async def run_all():
            return await asyncio.gather(
                rt._cargo_audit_executor({}),
                rt._cargo_outdated_executor({}),
                rt._cargo_udep_executor({}),
                rt._cargo_deny_executor({}),
                rt._wasm_pack_executor({}),
            )

        results = asyncio.run(run_all())
        assert len(results) == 5
        for result in results:
            assert result.ok is False
            assert "not installed" in result.content
            assert "Install:" in result.content

        # Spot-check that each reports its own install command.
        assert "cargo install cargo-audit" in results[0].content
        assert "cargo install cargo-outdated" in results[1].content
        assert "cargo install cargo-udeps" in results[2].content
        assert "cargo install cargo-deny" in results[3].content
        assert "cargo install wasm-pack" in results[4].content

    def test_wasm_pack_rejects_unknown_subcommand(self):
        import asyncio
        from tua_agent.rust_tools import _wasm_pack_executor

        result = asyncio.run(_wasm_pack_executor({"subcommand": "teleport"}))
        assert result.ok is False
        assert "Unknown wasm-pack subcommand" in result.content


class TestConfig:
    """Tests for the Tua configuration loader."""

    def test_loads_default_values(self, tmp_path, monkeypatch):
        import tua_agent.config as cfg

        # Isolate from any real ~/.tua/config.toml on the host.
        monkeypatch.setattr(cfg.Path, "home", lambda: tmp_path)

        config = cfg.TuaConfig.load(project_dir=tmp_path)
        assert config.default_profile == "rustacean"
        assert config.tool_timeout == 600
        assert config.max_output_chars == 16000
        assert config.dashboard_host == "127.0.0.1"
        assert config.dashboard_port == 8765
        assert config.rust_edition == "2021"
        assert config.clippy_pedantic is False
        assert config.require_doc_tests is False

    def test_merges_project_config(self, tmp_path, monkeypatch):
        import tua_agent.config as cfg

        monkeypatch.setattr(cfg.Path, "home", lambda: tmp_path)

        (tmp_path / ".tua").mkdir()
        config_text = (
            "[profile]\n"
            'default = "strict"\n'
            "\n"
            "[tools]\n"
            "timeout = 120\n"
            "max_output_chars = 8000\n"
            "\n"
            "[dashboard]\n"
            'host = "0.0.0.0"\n'
            "port = 9000\n"
            "\n"
            "[rust]\n"
            'edition = "2024"\n'
            "clippy_pedantic = true\n"
            "require_doc_tests = true\n"
        )
        (tmp_path / ".tua" / "config.toml").write_text(config_text)

        config = cfg.TuaConfig.load(project_dir=tmp_path)
        assert config.default_profile == "strict"
        assert config.tool_timeout == 120
        assert config.max_output_chars == 8000
        assert config.dashboard_host == "0.0.0.0"
        assert config.dashboard_port == 9000
        assert config.rust_edition == "2024"
        assert config.clippy_pedantic is True
        assert config.require_doc_tests is True


class TestSkills:
    """Tests for the bundled Rust skills under .tau/skills/."""

    @staticmethod
    def _skills_dir() -> Path:
        # Skills live in the package: src/tua_agent/data/skills/
        return Path(__file__).resolve().parent.parent / "src" / "tua_agent" / "data" / "skills"

    def test_ten_skill_directories_exist(self):
        skills = self._skills_dir()
        assert skills.is_dir(), f"skills directory missing at {skills}"
        dirs = [p for p in skills.iterdir() if p.is_dir()]
        assert len(dirs) == 10

    def test_each_skill_has_frontmatter(self):
        skills = self._skills_dir()
        dirs = sorted(p for p in skills.iterdir() if p.is_dir())
        assert dirs, "no skill directories found"
        for sub in dirs:
            skill_md = sub / "SKILL.md"
            assert skill_md.is_file(), f"missing SKILL.md in {sub.name}"
            text = skill_md.read_text(encoding="utf-8")
            assert text.lstrip().startswith("---"), f"{sub.name}: missing YAML frontmatter"
            assert "name:" in text, f"{sub.name}: missing 'name:' field"
            assert "description:" in text, f"{sub.name}: missing 'description:' field"

    def test_skill_names_match_directories(self):
        import re

        skills = self._skills_dir()
        for sub in sorted(p for p in skills.iterdir() if p.is_dir()):
            text = (sub / "SKILL.md").read_text(encoding="utf-8")
            match = re.search(r"^name:\s*(\S+)", text, re.MULTILINE)
            assert match, f"{sub.name}: no 'name:' field in frontmatter"
            assert match.group(1) == sub.name, (
                f"{sub.name}: name field {match.group(1)!r} != directory {sub.name!r}"
            )
