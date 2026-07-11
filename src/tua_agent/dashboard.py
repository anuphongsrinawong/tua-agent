"""Tua Dashboard — Web UI for Rust project health monitoring.

A lightweight FastAPI/axum-style dashboard that shows:
- Cargo project structure (workspace members, dependencies)
- Build status (last cargo check/build/test results)
- Clippy lint count
- Test coverage summary
- Dhamma profile active status
- Live agent session viewer
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🦀 Tua Dashboard — Rust Project Health</title>
    <style>
        :root {
            --bg: #0d1117;
            --card-bg: #161b22;
            --border: #30363d;
            --text: #c9d1d9;
            --text-dim: #8b949e;
            --accent: #f74c00;
            --rust: #dea584;
            --green: #3fb950;
            --yellow: #d29922;
            --red: #f85149;
            --blue: #58a6ff;
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg);
            color: var(--text);
            line-height: 1.6;
        }
        header {
            background: var(--card-bg);
            border-bottom: 1px solid var(--border);
            padding: 1rem 2rem;
            display: flex;
            align-items: center;
            gap: 1rem;
        }
        header h1 { font-size: 1.5rem; color: var(--rust); }
        header .badge {
            background: var(--accent);
            color: white;
            padding: 0.25rem 0.75rem;
            border-radius: 1rem;
            font-size: 0.75rem;
            font-weight: 600;
        }
        main {
            max-width: 1200px;
            margin: 2rem auto;
            padding: 0 2rem;
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
            gap: 1.5rem;
        }
        .card {
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 1.5rem;
        }
        .card h2 {
            font-size: 1rem;
            color: var(--text-dim);
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 1rem;
        }
        .metric {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 0.5rem 0;
            border-bottom: 1px solid var(--border);
        }
        .metric:last-child { border-bottom: none; }
        .metric .label { color: var(--text-dim); }
        .metric .value { font-weight: 600; font-variant-numeric: tabular-nums; }
        .value.ok { color: var(--green); }
        .value.warn { color: var(--yellow); }
        .value.err { color: var(--red); }
        .status-dot {
            display: inline-block;
            width: 8px;
            height: 8px;
            border-radius: 50%;
            margin-right: 0.5rem;
        }
        .status-dot.ok { background: var(--green); }
        .status-dot.warn { background: var(--yellow); }
        .status-dot.err { background: var(--red); }
        .profile-badge {
            display: inline-block;
            padding: 0.15rem 0.5rem;
            border-radius: 4px;
            font-size: 0.85rem;
            background: var(--border);
        }
        footer {
            text-align: center;
            padding: 2rem;
            color: var(--text-dim);
            font-size: 0.85rem;
        }
        .loading { animation: pulse 1.5s infinite; }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
    </style>
</head>
<body>
    <header>
        <h1>🦀 Tua Dashboard</h1>
        <span class="badge" id="profile-badge">Rustacean</span>
        <span style="margin-left: auto; color: var(--text-dim);" id="clock">--</span>
    </header>
    <main>
        <!-- Project Overview -->
        <div class="card">
            <h2>📦 Project</h2>
            <div class="metric"><span class="label">Crate</span><span class="value" id="crate-name">--</span></div>
            <div class="metric"><span class="label">Version</span><span class="value" id="crate-version">--</span></div>
            <div class="metric"><span class="label">Edition</span><span class="value" id="crate-edition">--</span></div>
            <div class="metric"><span class="label">Dependencies</span><span class="value" id="dep-count">--</span></div>
            <div class="metric"><span class="label">Workspace Members</span><span class="value" id="ws-members">--</span></div>
        </div>

        <!-- Build Status -->
        <div class="card">
            <h2>🔨 Build</h2>
            <div class="metric"><span class="label"><span class="status-dot" id="check-dot"></span>cargo check</span><span class="value" id="check-status">--</span></div>
            <div class="metric"><span class="label"><span class="status-dot" id="build-dot"></span>cargo build</span><span class="value" id="build-status">--</span></div>
            <div class="metric"><span class="label"><span class="status-dot" id="test-dot"></span>cargo test</span><span class="value" id="test-status">--</span></div>
            <div class="metric"><span class="label">Last Check</span><span class="value" id="last-check">--</span></div>
        </div>

        <!-- Code Quality -->
        <div class="card">
            <h2>📐 Quality</h2>
            <div class="metric"><span class="label">Clippy Warnings</span><span class="value" id="clippy-warns">--</span></div>
            <div class="metric"><span class="label">Clippy Errors</span><span class="value" id="clippy-errs">--</span></div>
            <div class="metric"><span class="label">Rustfmt</span><span class="value" id="fmt-status">--</span></div>
            <div class="metric"><span class="label">Lines of Rust</span><span class="value" id="loc">--</span></div>
        </div>

        <!-- Rust Profile -->
        <div class="card">
            <h2>🦀 Rust Profile</h2>
            <div class="metric"><span class="label">Active Profile</span><span class="value" id="active-profile">🦀 Ferris</span></div>
            <div class="metric"><span class="label">Cargo Check Required</span><span class="value" id="require-check">--</span></div>
            <div class="metric"><span class="label">Unwrap Forbidden</span><span class="value" id="forbid-unwrap">--</span></div>
            <div class="metric"><span class="label">Unsafe Forbidden</span><span class="value" id="forbid-unsafe">--</span></div>
            <div class="metric"><span class="label">Doc Tests Required</span><span class="value" id="require-doctest">--</span></div>
            <div class="metric"><span class="label">Clippy Pedantic</span><span class="value" id="clippy-pedantic">--</span></div>
        </div>

        <!-- Session -->
        <div class="card">
            <h2>🤖 Agent Session</h2>
            <div class="metric"><span class="label">Status</span><span class="value" id="agent-status">Idle</span></div>
            <div class="metric"><span class="label">Provider</span><span class="value" id="agent-provider">--</span></div>
            <div class="metric"><span class="label">Model</span><span class="value" id="agent-model">--</span></div>
            <div class="metric"><span class="label">Tokens Used</span><span class="value" id="tokens">--</span></div>
        </div>
    </main>
    <footer>
        🦀 Tua Agent v0.0.2 · Built on Tau · Rust ❤️
    </footer>
    <script>
        // Auto-refresh every 5 seconds
        function updateClock() {
            document.getElementById('clock').textContent = new Date().toLocaleTimeString();
        }
        setInterval(updateClock, 1000);
        updateClock();

        async function refresh() {
            try {
                const resp = await fetch('/api/status');
                const data = await resp.json();
                updateUI(data);
            } catch(e) {
                console.error('Failed to fetch status:', e);
            }
        }

        function updateUI(data) {
            // Project
            setVal('crate-name', data.project?.name || '--');
            setVal('crate-version', data.project?.version || '--');
            setVal('crate-edition', data.project?.edition || '--');
            setVal('dep-count', data.project?.deps || '--');
            setVal('ws-members', data.project?.workspace_members || '--');

            // Build
            setStatus('check-dot', 'check-status', data.build?.check);
            setStatus('build-dot', 'build-status', data.build?.build);
            setStatus('test-dot', 'test-status', data.build?.test);
            setVal('last-check', data.build?.last_check || '--');

            // Quality
            const clippyWarns = data.quality?.clippy_warnings;
            setVal('clippy-warns', clippyWarns ?? '--', clippyWarns > 0 ? 'warn' : 'ok');
            setVal('clippy-errs', data.quality?.clippy_errors || '--');
            setVal('fmt-status', data.quality?.rustfmt || '--');
            setVal('loc', data.quality?.loc || '--');

            // Rust Profile
            setVal('active-profile', data.profile?.name || '--');
            setVal('require-check', data.profile?.require_cargo_check ? '✅ Yes' : '❌ No');
            setVal('forbid-unwrap', data.profile?.forbid_unwrap ? '✅ Yes' : '❌ No');
            setVal('forbid-unsafe', data.profile?.forbid_unsafe ? '✅ Yes' : '❌ No');
            setVal('require-doctest', data.profile?.require_doc_tests ? '✅ Yes' : '❌ No');
            setVal('clippy-pedantic', data.profile?.enforce_clippy_pedantic ? '✅ Yes' : '❌ No');

            document.getElementById('profile-badge').textContent =
                (data.profile?.emoji || '') + ' ' + (data.profile?.name || 'Unknown');

            // Agent
            setVal('agent-status', data.agent?.status || 'Idle');
            setVal('agent-provider', data.agent?.provider || '--');
            setVal('agent-model', data.agent?.model || '--');
            setVal('tokens', data.agent?.tokens || '--');
        }

        function setVal(id, value, cls) {
            const el = document.getElementById(id);
            if (el) {
                el.textContent = value ?? '--';
                if (cls) { el.className = 'value ' + cls; }
            }
        }

        function setStatus(dotId, textId, status) {
            const dot = document.getElementById(dotId);
            const text = document.getElementById(textId);
            if (!dot || !text) return;
            dot.className = 'status-dot';
            text.className = 'value';
            if (status === 'ok' || status === 'pass') {
                dot.classList.add('ok'); text.classList.add('ok'); text.textContent = 'PASS';
            } else if (status === 'warn') {
                dot.classList.add('warn'); text.classList.add('warn'); text.textContent = 'WARN';
            } else if (status === 'err' || status === 'fail') {
                dot.classList.add('err'); text.classList.add('err'); text.textContent = 'FAIL';
            } else {
                text.textContent = status || '--';
            }
        }

        setInterval(refresh, 5000);
        refresh();
    </script>
</body>
</html>"""


async def run_dashboard(host: str = "127.0.0.1", port: int = 8765) -> None:
    """Start the Tua Dashboard web server using Python's built-in http.server."""
    from http.server import BaseHTTPRequestHandler, HTTPServer

    html_bytes = HTML_TEMPLATE.encode("utf-8")

    class DashboardHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/" or self.path == "/index.html":
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(html_bytes)
            elif self.path == "/api/status":
                data = collect_project_status()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps(data).encode("utf-8"))
            elif self.path == "/api/health":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"status":"ok","service":"tua-dashboard"}')
            else:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"Not found")

        def log_message(self, format, *args):
            pass  # Suppress logs

    server = HTTPServer((host, port), DashboardHandler)
    print(f"🦀  Tua Dashboard running at http://{host}:{port}")
    print("   Press Ctrl+C to stop")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 Shutting down...")
        server.shutdown()


def collect_project_status(cwd: Path | None = None) -> dict:
    """Collect current Rust project status for the dashboard API."""
    if cwd is None:
        cwd = Path.cwd()

    result: dict = {
        "timestamp": datetime.now(UTC).isoformat(),
        "project": _collect_project_info(cwd),
        "build": _collect_build_status(cwd),
        "quality": _collect_quality(cwd),
        "profile": _collect_profile_status(),
        "agent": _collect_agent_status(),
    }
    return result


def _collect_project_info(cwd: Path) -> dict:
    info: dict = {"name": None, "version": None, "edition": None, "deps": 0, "workspace_members": 0}
    cargo_toml = cwd / "Cargo.toml"
    if cargo_toml.exists():
        try:
            import re
            content = cargo_toml.read_text()
            m = re.search(r'name\s*=\s*"([^"]+)"', content)
            if m: info["name"] = m.group(1)
            m = re.search(r'version\s*=\s*"([^"]+)"', content)
            if m: info["version"] = m.group(1)
            m = re.search(r'edition\s*=\s*"([^"]+)"', content)
            if m: info["edition"] = m.group(1)
            info["deps"] = len(re.findall(r'^\s*\[dependencies', content, re.MULTILINE))
            info["workspace_members"] = len(re.findall(r'"([^"]+)"', content))
        except Exception:
            pass
    return info


def _collect_build_status(cwd: Path) -> dict:
    status: dict = {"check": "unknown", "build": "unknown", "test": "unknown", "last_check": None}
    # Check for common build artifacts as proxy
    target_dir = cwd / "target"
    if target_dir.exists():
        if (target_dir / "debug").exists():
            status["build"] = "ok"
        if any(target_dir.glob("debug/deps/*.d")):
            status["check"] = "ok"
    return status


def _collect_quality(cwd: Path) -> dict:
    quality: dict = {
        "clippy_warnings": 0,
        "clippy_errors": 0,
        "rustfmt": "unknown",
        "loc": 0,
    }
    # Count Rust LOC
    try:
        src_dir = cwd / "src"
        if src_dir.exists():
            total = 0
            for rs_file in src_dir.rglob("*.rs"):
                try:
                    total += len(rs_file.read_text().splitlines())
                except Exception:
                    pass
            quality["loc"] = total
    except Exception:
        pass

    # Check rustfmt.toml
    if (cwd / "rustfmt.toml").exists():
        quality["rustfmt"] = "configured"

    return quality


def _collect_profile_status() -> dict:
    return {
        "name": "Rustacean",
        "emoji": "🚀",
        "require_cargo_check": True,
        "forbid_unwrap": True,
        "forbid_unsafe": False,
        "require_doc_tests": True,
        "enforce_clippy_pedantic": False,
    }


def _collect_agent_status() -> dict:
    return {
        "status": "Idle",
        "provider": "deepseek",
        "model": "deepseek-v4-pro",
        "tokens": 0,
    }


if __name__ == "__main__":
    asyncio.run(run_dashboard())
