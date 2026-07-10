#!/usr/bin/env python3
"""Dhamma Agent Benchmark Suite — inspired by industry-standard evals.

Benchmarks adapted for local coding agent evaluation:
  Terminal-Bench style   — shell mastery, multi-step CLI tasks
  SWE-Bench style        — find & fix bugs in a codebase
  Aider Polyglot style   — solve coding exercises from spec
  GAIA style             — web search + reasoning chains

Each task is deterministic: a verification script checks the output.
Scoring: pass=1, fail=0, weighted by difficulty.
"""

from __future__ import annotations

import asyncio, json, os, subprocess, sys, tempfile, textwrap, time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from collections.abc import Mapping

# ── Load API key ───────────────────────────────────────────────────────
import dotenv
_hermes_env = Path.home() / ".hermes" / ".env"
if _hermes_env.exists():
    dotenv.load_dotenv(_hermes_env)

from openai import AsyncOpenAI
from tau_agent import AgentHarness, AgentHarnessConfig, AgentTool, AgentToolResult
from tau_agent.events import MessageDeltaEvent, ToolExecutionEndEvent, ErrorEvent
from tau_agent.types import JSONValue
from tau_coding.system_prompt import BuildSystemPromptOptions, build_system_prompt
from tau_agent.dhamma_profiles import DhammaProfile, get_profile, ALL_PROFILES


# ═══════════════════════════════════════════════════════════════════════
# TOOLS
# ═══════════════════════════════════════════════════════════════════════

async def _bash(args: Mapping[str, JSONValue], signal=None) -> AgentToolResult:
    cmd = str(args.get("command", ""))
    cwd = str(args.get("workdir", os.getcwd()))
    try:
        proc = await asyncio.create_subprocess_shell(
            cmd, cwd=cwd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        out, err = await asyncio.wait_for(proc.communicate(), timeout=15)
        text = (out.decode() + err.decode()).strip() or "(no output)"
        return AgentToolResult(tool_call_id="", name="bash", ok=proc.returncode==0,
                               content=text[:3000], error="" if proc.returncode==0 else f"exit={proc.returncode}")
    except Exception as e:
        return AgentToolResult(tool_call_id="", name="bash", ok=False, content=str(e)[:1000], error=str(e))

async def _read(args: Mapping[str, JSONValue], signal=None) -> AgentToolResult:
    p = Path(str(args.get("path", "")))
    try:
        return AgentToolResult(tool_call_id="", name="read", ok=True, content=p.read_text()[:5000])
    except Exception as e:
        return AgentToolResult(tool_call_id="", name="read", ok=False, content=str(e)[:500], error=str(e))

async def _write(args: Mapping[str, JSONValue], signal=None) -> AgentToolResult:
    p = Path(str(args.get("path", "")))
    content = str(args.get("content", ""))
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return AgentToolResult(tool_call_id="", name="write", ok=True, content=f"Wrote {len(content)} bytes to {p}")
    except Exception as e:
        return AgentToolResult(tool_call_id="", name="write", ok=False, content=str(e)[:500], error=str(e))

def make_tools(cwd: str) -> list[AgentTool]:
    return [
        AgentTool(name="bash", description="Run shell command", input_schema={
            "type":"object","properties":{"command":{"type":"string"},"workdir":{"type":"string"}},
            "required":["command"]}, executor=_bash, prompt_snippet="Run shell commands"),
        AgentTool(name="read", description="Read a file", input_schema={
            "type":"object","properties":{"path":{"type":"string"}},
            "required":["path"]}, executor=_read, prompt_snippet="Read file contents"),
        AgentTool(name="write", description="Write/create a file", input_schema={
            "type":"object","properties":{"path":{"type":"string"},"content":{"type":"string"}},
            "required":["path","content"]}, executor=_write, prompt_snippet="Write file contents"),
    ]


# ═══════════════════════════════════════════════════════════════════════
# BENCHMARK TASKS
# ═══════════════════════════════════════════════════════════════════════

@dataclass(frozen=True, slots=True)
class BenchTask:
    id: str
    category: str           # terminal, swe, polyglot, gaia
    difficulty: int         # 1-5
    prompt: str             # natural language instruction
    setup: str              # bash commands to set up test environment
    verify: str             # bash command — exit 0 = pass
    expected_skills: tuple[str, ...] = ()  # e.g. ("bash","read","write")


# ── Terminal-Bench style: shell mastery ───────────────────────────────
TERMINAL_TASKS = [
    BenchTask("T1","terminal",1,
        prompt="Count how many lines are in the file /tmp/dhamma_bench_test.txt and write just the number to /tmp/dhamma_bench_T1_result.txt",
        setup="echo -e 'line1\\nline2\\nline3\\nline4\\nline5' > /tmp/dhamma_bench_test.txt",
        verify="test \"$(cat /tmp/dhamma_bench_T1_result.txt)\" = \"5\"",
        expected_skills=("bash","read")),
    BenchTask("T2","terminal",2,
        prompt="Find all unique file extensions (e.g. .py, .txt) in /home/innovationtech888/tau-dhamma/src/tau_agent/ and write them, one per line sorted alphabetically, to /tmp/dhamma_bench_T2_result.txt",
        setup="",
        verify="test \"$(cat /tmp/dhamma_bench_T2_result.txt | tr '\\n' ',')\" = \".py,\"",
        expected_skills=("bash",)),
    BenchTask("T3","terminal",3,
        prompt="Create a directory /tmp/dhamma_bench_T3 with 3 subdirectories: a, b, c. In each, create an empty file named after the subdirectory (e.g. a/a, b/b, c/c). Then create /tmp/dhamma_bench_T3_summary.txt listing total file count only.",
        setup="rm -rf /tmp/dhamma_bench_T3 /tmp/dhamma_bench_T3_summary.txt 2>/dev/null; true",
        verify="test -f /tmp/dhamma_bench_T3/a/a && test -f /tmp/dhamma_bench_T3/b/b && test -f /tmp/dhamma_bench_T3/c/c && test \"$(cat /tmp/dhamma_bench_T3_summary.txt)\" = \"3\"",
        expected_skills=("bash",)),
]

# ── SWE-Bench style: find & fix bugs ──────────────────────────────────
SWE_TASKS = [
    BenchTask("S1","swe",2,
        prompt=textwrap.dedent("""\
            There is a Python file at /tmp/dhamma_bench_bug.py with a bug.
            Read the file, find the bug, fix it, and write the corrected version
            to /tmp/dhamma_bench_S1_fixed.py. The file should contain a function
            `fibonacci(n)` that returns the nth Fibonacci number starting with
            fib(0)=0, fib(1)=1.
        """),
        setup="echo 'def fibonacci(n):\\n    if n <= 1:\\n        return 1\\n    return fibonacci(n-1) + fibonacci(n-2)' > /tmp/dhamma_bench_bug.py",
        verify="python3 -c \"exec(open('/tmp/dhamma_bench_S1_fixed.py').read()); assert fibonacci(0)==0; assert fibonacci(1)==1; assert fibonacci(5)==5; assert fibonacci(10)==55; print('PASS')\" | grep -q PASS",
        expected_skills=("read","write","bash")),
    BenchTask("S2","swe",3,
        prompt=textwrap.dedent("""\
            Read /tmp/dhamma_bench_config.json which has a malformed JSON structure.
            Fix it so it becomes valid JSON with these keys: "name", "version", "enabled".
            Write the fixed JSON to /tmp/dhamma_bench_S2_fixed.json.
        """),
        setup="echo '{name: dhamma, version: 1.0, enabled: true,}' > /tmp/dhamma_bench_config.json",
        verify="python3 -c \"import json; d=json.load(open('/tmp/dhamma_bench_S2_fixed.json')); assert d['name']=='dhamma'; assert d['version']==1.0; assert d['enabled']==True; print('PASS')\" | grep -q PASS",
        expected_skills=("read","write")),
]

# ── Aider Polyglot style: coding from spec ────────────────────────────
POLYGLOT_TASKS = [
    BenchTask("P1","polyglot",2,
        prompt=textwrap.dedent("""\
            Write a Python script to /tmp/dhamma_bench_P1.py that:
            - Takes a string as command-line argument
            - Prints the string reversed
            - Has a shebang line (#!/usr/bin/env python3)
            Make it executable.
        """),
        setup="",
        verify="chmod +x /tmp/dhamma_bench_P1.py && test \"$(python3 /tmp/dhamma_bench_P1.py hello)\" = \"olleh\" && test \"$(python3 /tmp/dhamma_bench_P1.py dhamma)\" = \"ammahd\"",
        expected_skills=("write","bash")),
    BenchTask("P2","polyglot",3,
        prompt=textwrap.dedent("""\
            Write a Rust program to /tmp/dhamma_bench_P2.rs that:
            - Has a main function
            - Defines a function `gcd(a: u64, b: u64) -> u64` using Euclid's algorithm
            - In main, calls gcd(48, 18) and prints the result
            Then compile and run it with rustc.
        """),
        setup="",
        verify="rustc /tmp/dhamma_bench_P2.rs -o /tmp/dhamma_bench_P2 2>/dev/null && test \"$(/tmp/dhamma_bench_P2)\" = \"6\"",
        expected_skills=("write","bash")),
]

# ── GAIA style: reasoning + web search ────────────────────────────────
GAIA_TASKS = [
    BenchTask("G1","gaia",2,
        prompt="What is the SHA256 hash of the string 'dhamma-agent-2026'? Compute it using bash and write ONLY the hash to /tmp/dhamma_bench_G1_result.txt.",
        setup="",
        verify="test \"$(cat /tmp/dhamma_bench_G1_result.txt)\" = \"$(echo -n dhamma-agent-2026 | sha256sum | cut -d' ' -f1)\"",
        expected_skills=("bash",)),
    BenchTask("G2","gaia",3,
        prompt=textwrap.dedent("""\
            The file /tmp/dhamma_bench_data.txt contains one number per line.
            Read it, calculate the sum of all numbers, and write ONLY the sum
            to /tmp/dhamma_bench_G2_result.txt.
        """),
        setup="for i in $(seq 1 50); do echo $i >> /tmp/dhamma_bench_data.txt; done",
        verify="test \"$(cat /tmp/dhamma_bench_G2_result.txt)\" = \"1275\"",
        expected_skills=("read","bash")),
]

# ── DHAMMA style: tasks that test Buddhist principles specifically ────
# These are designed so that profiles WITH dhamma perform BETTER.
# Baseline should fail or struggle on these due to no mindfulness/retry/etc.

DHAMMA_TASKS = [
    # D1 — สติ (Loop Detection): multiple decoy files bait the agent to repeat
    BenchTask("D1","dhamma",4,
        prompt=textwrap.dedent("""\
            Find the ONLY file in /tmp/dhamma_bench_D1/ that contains the word
            "treasure". There are 6 files but only 1 has it. Write the CORRECT
            filename (just the filename, no path) to /tmp/dhamma_bench_D1_result.txt.
            Do NOT read every file multiple times — read each file ONCE.
        """),
        setup=(
            "mkdir -p /tmp/dhamma_bench_D1; "
            "echo 'sand' > /tmp/dhamma_bench_D1/beach.txt; "
            "echo 'waves' > /tmp/dhamma_bench_D1/ocean.txt; "
            "echo 'shells' > /tmp/dhamma_bench_D1/shore.txt; "
            "echo 'dunes' > /tmp/dhamma_bench_D1/desert.txt; "
            "echo 'treasure buried here' > /tmp/dhamma_bench_D1/cave.txt; "
            "echo 'rocks' > /tmp/dhamma_bench_D1/cliff.txt"
        ),
        verify="test \"$(cat /tmp/dhamma_bench_D1_result.txt)\" = \"cave.txt\"",
        expected_skills=("bash","read")),

    # D2 — มัชฌิมา (Retry): first tool call WILL fail, must retry with different approach
    BenchTask("D2","dhamma",4,
        prompt=textwrap.dedent("""\
            Read /tmp/dhamma_bench_D2_target.txt. It does NOT exist yet — you must
            first create it with the content "dhamma-middle-way". Then read it back
            to verify, and write the verified content to /tmp/dhamma_bench_D2_result.txt.
            If your first read fails (file missing), create it and retry — don't give up.
        """),
        setup="rm -f /tmp/dhamma_bench_D2_target.txt /tmp/dhamma_bench_D2_result.txt 2>/dev/null; true",
        verify="test -f /tmp/dhamma_bench_D2_target.txt && test \"$(cat /tmp/dhamma_bench_D2_result.txt)\" = \"dhamma-middle-way\"",
        expected_skills=("read","write","bash")),

    # D3 — อนิจจัง (Graceful Degradation): the "obvious" tool path is blocked
    BenchTask("D3","dhamma",5,
        prompt=textwrap.dedent("""\
            You need to find all Python files recursively in /tmp/dhamma_bench_D3/.
            The 'find' command is BROKEN for this task (it will not work).
            Use an ALTERNATIVE approach: use 'bash' with 'ls' or 'grep' to discover
            the Python files instead. List each Python file path (one per line) in
            /tmp/dhamma_bench_D3_result.txt. Don't waste turns retrying 'find'.
        """),
        setup=(
            "mkdir -p /tmp/dhamma_bench_D3/sub1/sub2; "
            "touch /tmp/dhamma_bench_D3/main.py; "
            "touch /tmp/dhamma_bench_D3/sub1/helper.py; "
            "touch /tmp/dhamma_bench_D3/sub1/sub2/deep.py; "
            "touch /tmp/dhamma_bench_D3/config.txt"
        ),
        verify="test \"$(cat /tmp/dhamma_bench_D3_result.txt | wc -l)\" -eq 3",
        expected_skills=("bash","read")),

    # D4 — โยนิโส (Systematic Attention): must read BEFORE writing
    BenchTask("D4","dhamma",4,
        prompt=textwrap.dedent("""\
            There is a config file at /tmp/dhamma_bench_D4_config.txt with a version
            number. FIRST read the file and note the current version. THEN increment
            the version by 1 and write it back. Finally, write the NEW version number
            to /tmp/dhamma_bench_D4_result.txt.
            IMPORTANT: Do NOT write the file before reading it — you need to know
            the current version first.
        """),
        setup="echo 'version=5' > /tmp/dhamma_bench_D4_config.txt",
        verify="test \"$(cat /tmp/dhamma_bench_D4_result.txt)\" = \"6\" && test \"$(cat /tmp/dhamma_bench_D4_config.txt)\" = \"version=6\"",
        expected_skills=("read","write")),

    # D5 — ขันติ (Patience): multi-step pipeline, must persist
    BenchTask("D5","dhamma",5,
        prompt=textwrap.dedent("""\
            You must complete a 3-step pipeline:
            Step 1: Create /tmp/dhamma_bench_D5_step1.txt with "step1-done"
            Step 2: Read step1.txt, append "step2-done" to create step2.txt
            Step 3: Read step2.txt, append "step3-done" to create step3.txt
            Finally, write the final content of step3.txt to /tmp/dhamma_bench_D5_result.txt
            This requires patience — each step depends on the previous one.
        """),
        setup="rm -f /tmp/dhamma_bench_D5_*.txt 2>/dev/null; true",
        verify="test \"$(cat /tmp/dhamma_bench_D5_result.txt)\" = \"step1-done\nstep2-done\nstep3-done\"",
        expected_skills=("bash","read","write")),
]

ALL_TASKS = TERMINAL_TASKS + SWE_TASKS + POLYGLOT_TASKS + GAIA_TASKS + DHAMMA_TASKS


# ═══════════════════════════════════════════════════════════════════════
# PROVIDER
# ═══════════════════════════════════════════════════════════════════════

class DeepSeekProvider:
    def __init__(self):
        key = os.environ.get("DEEPSEEK_API_KEY","")
        if not key:
            print("❌ DEEPSEEK_API_KEY not set", file=sys.stderr); sys.exit(1)
        self.client = AsyncOpenAI(api_key=key, base_url="https://api.deepseek.com/v1")

    async def stream_response(self, *, model, system, messages, tools, signal=None):
        from tau_ai.events import (ProviderResponseEndEvent, ProviderResponseStartEvent,
                                    ProviderTextDeltaEvent, ProviderErrorEvent)
        from tau_agent.messages import AssistantMessage

        openai_msgs = [{"role":"system","content":system}]
        for msg in messages:
            entry = {"role": msg.role, "content": getattr(msg,"content","")}
            if msg.role == "assistant":
                tcs = getattr(msg,"tool_calls",None)
                if tcs:
                    entry["tool_calls"] = [{"id": tc.id if hasattr(tc,'id') else str(i),
                        "type":"function","function":{"name":tc.name if hasattr(tc,'name') else tc.get("name",""),
                        "arguments":json.dumps(tc.arguments if hasattr(tc,'arguments') else tc.get("arguments",{}))}}
                        for i,tc in enumerate(tcs)]
            if msg.role == "tool":
                entry["tool_call_id"] = getattr(msg,"tool_call_id","")
            openai_msgs.append(entry)

        openai_tools = [{"type":"function","function":{"name":t.name,"description":t.description,
            "parameters":t.input_schema}} for t in tools] if tools else None

        try:
            yield ProviderResponseStartEvent(model=model)
            stream = await self.client.chat.completions.create(
                model="deepseek-v4-pro", messages=openai_msgs, tools=openai_tools,
                stream=True, max_tokens=4096)
            parts = []; tc_map = {}
            async for chunk in stream:
                d = chunk.choices[0].delta if chunk.choices else None
                if not d: continue
                if d.content: parts.append(d.content); yield ProviderTextDeltaEvent(delta=d.content)
                if d.tool_calls:
                    for tc in d.tool_calls:
                        i = tc.index
                        if i not in tc_map: tc_map[i] = {"id":tc.id or "","name":"","arguments":""}
                        if tc.function:
                            if tc.function.name: tc_map[i]["name"] += tc.function.name
                            if tc.function.arguments: tc_map[i]["arguments"] += tc.function.arguments
            content = "".join(parts)
            tool_calls = []
            for i in sorted(tc_map):
                t = tc_map[i]
                try: args = json.loads(t["arguments"]) if t["arguments"].strip() else {}
                except: args = {}
                tool_calls.append(__import__("tau_agent.tools",fromlist=["ToolCall"]).ToolCall(id=t["id"] or str(i), name=t["name"], arguments=args))
            yield ProviderResponseEndEvent(message=AssistantMessage(content=content, tool_calls=tool_calls))
        except Exception as e:
            yield ProviderErrorEvent(message=str(e))
            yield ProviderResponseEndEvent(message=AssistantMessage(content=f"Error: {e}"))


# ═══════════════════════════════════════════════════════════════════════
# RUNNER
# ═══════════════════════════════════════════════════════════════════════

@dataclass(slots=True)
class TaskResult:
    task_id: str
    category: str
    difficulty: int
    passed: bool
    turns: int
    tools_called: int
    errors: int
    elapsed: float
    output_excerpt: str = ""

@dataclass(slots=True)
class BenchReport:
    profile: str
    results: list[TaskResult]
    total: int = 0
    passed: int = 0
    score: float = 0.0
    elapsed: float = 0.0
    by_category: dict[str, dict] = field(default_factory=dict)


async def run_task(task: BenchTask, profile: DhammaProfile, cwd: str,
                   provider: Any, tools: list[AgentTool], max_turns: int) -> TaskResult:
    """Run a single benchmark task with DhammaConfig injected into the agent loop."""
    # Setup
    if task.setup:
        subprocess.run(task.setup, shell=True, capture_output=True, timeout=5)

    system = build_system_prompt(BuildSystemPromptOptions(cwd=Path(cwd), tools=tools))

    # Use run_agent_loop directly so DhammaConfig is ACTIVE (not just metadata)
    from tau_agent.loop import run_agent_loop
    from tau_agent.messages import UserMessage

    messages: list = [UserMessage(content=task.prompt)]
    tool_count = 0; error_count = 0; turn = 0; output = ""
    dhamma_signals = 0; loop_warnings = 0; iddhipada_events = 0
    t0 = time.monotonic()

    try:
        async for event in run_agent_loop(
            provider=provider,
            model="deepseek-v4-pro",
            system=system,
            messages=messages,
            tools=tools,
            max_turns=max_turns,
            dhamma=profile.config,  # ← DHAMMA INJECTED HERE
        ):
            if isinstance(event, MessageDeltaEvent):
                output += event.delta
            elif isinstance(event, ToolExecutionEndEvent):
                tool_count += 1
                if not event.result.ok:
                    error_count += 1
            elif isinstance(event, ErrorEvent):
                error_count += 1
            elif hasattr(event, 'turn'):
                turn = getattr(event, 'turn', turn)
            # Track Dhamma-specific events
            if hasattr(event, 'kind'):
                kind = getattr(event, 'kind', '')
                dhamma_signals += 1
                if kind in ('loop_detected', 'budget_warning', 'validation'):
                    loop_warnings += 1
                if kind == 'iddhipada':
                    iddhipada_events += 1
    except Exception as e:
        error_count += 1

    elapsed = time.monotonic() - t0

    # Verify
    passed = False
    if task.verify:
        result = subprocess.run(f"({task.setup}; {task.verify}) 2>/dev/null",
                                shell=True, capture_output=True, timeout=10)
        passed = result.returncode == 0

    # Cleanup
    subprocess.run(f"rm -rf /tmp/dhamma_bench_* 2>/dev/null", shell=True, capture_output=True)

    return TaskResult(
        task_id=task.id, category=task.category, difficulty=task.difficulty,
        passed=passed, turns=turn, tools_called=tool_count, errors=error_count,
        elapsed=elapsed, output_excerpt=f"{output[:130].replace(chr(10),' ')} sig={dhamma_signals} iddhi={iddhipada_events}",
    )


async def run_benchmark(profile_name: str, tasks: list[BenchTask] | None = None,
                        max_turns: int = 10) -> BenchReport:
    """Run the full benchmark suite against a profile."""
    if tasks is None:
        tasks = ALL_TASKS

    profile = get_profile(profile_name)
    provider = DeepSeekProvider()
    cwd = os.getcwd()
    tools = make_tools(cwd)

    print(f"\n{'='*70}")
    print(f"  🧪 DHAMMA BENCHMARK — {profile.emoji} {profile.name}")
    print(f"  {'='*70}")
    print(f"  Tasks: {len(tasks)} ({', '.join(set(t.category for t in tasks))})")
    print(f"  Max turns/task: {max_turns}")
    print()

    results = []
    for i, task in enumerate(tasks):
        status = "⏳"
        print(f"  [{i+1}/{len(tasks)}] {task.id} ({task.category}, diff={task.difficulty})...", end=" ", flush=True)
        result = await run_task(task, profile, cwd, provider, tools, max_turns)
        results.append(result)
        status = "✅" if result.passed else "❌"
        print(f"{status} turns={result.turns} tools={result.tools_called} errors={result.errors} {result.elapsed:.1f}s")

    total = len(results)
    passed = sum(1 for r in results if r.passed)
    # Weighted score: difficulty 1=0.5, 2=1, 3=1.5, 4=2, 5=2.5
    weighted_total = sum(task.difficulty / 2.0 for task in tasks)
    weighted_passed = sum(
        task.difficulty / 2.0 for task, result in zip(tasks, results) if result.passed
    )
    score = (weighted_passed / weighted_total * 100) if weighted_total > 0 else 0

    by_cat = {}
    for cat in sorted(set(t.category for t in tasks)):
        cat_tasks = [r for t,r in zip(tasks,results) if t.category==cat]
        cat_pass = sum(1 for r in cat_tasks if r.passed)
        by_cat[cat] = {"total": len(cat_tasks), "passed": cat_pass,
                       "rate": f"{cat_pass/len(cat_tasks)*100:.0f}%" if cat_tasks else "N/A"}

    return BenchReport(profile=profile.name, results=results, total=total,
                       passed=passed, score=score, by_category=by_cat)


def format_bench_report(report: BenchReport) -> str:
    lines = [
        f"\n{'='*70}",
        f"  📊 BENCHMARK RESULTS — {report.profile}",
        f"  {'='*70}",
        f"  Score: {report.score:.1f}%  ({report.passed}/{report.total} passed)",
        f"",
        f"  {'Category':<14} {'Passed':>8} {'Rate':>8}",
        f"  {'-'*14} {'-'*8} {'-'*8}",
    ]
    for cat, data in sorted(report.by_category.items()):
        lines.append(f"  {cat:<14} {data['passed']:>3}/{data['total']:<3} {data['rate']:>7}")
    lines.append(f"  {'-'*14} {'-'*8} {'-'*8}")
    lines.append(f"  {'TOTAL':<14} {report.passed:>3}/{report.total:<3} {report.passed/report.total*100:>6.0f}%")

    lines.append(f"\n  {'Task':<6} {'Category':<12} {'Diff':<6} {'Result':<8} {'Turns':<6} {'Tools':<6} {'Errors':<7}")
    lines.append(f"  {'-'*6} {'-'*12} {'-'*6} {'-'*8} {'-'*6} {'-'*6} {'-'*7}")
    for r in report.results:
        status = "✅ PASS" if r.passed else "❌ FAIL"
        lines.append(f"  {r.task_id:<6} {r.category:<12} {r.difficulty:<6} {status:<8} {r.turns:<6} {r.tools_called:<6} {r.errors:<7}")
    return "\n".join(lines)


async def run_comparison(tasks: list[BenchTask] | None = None, max_turns: int = 10):
    """Compare BASELINE vs ARAHANT."""
    profiles = ["baseline", "arahant"]
    reports = []
    for p in profiles:
        report = await run_benchmark(p, tasks, max_turns)
        reports.append(report)
        print(format_bench_report(report))

    # Head-to-head
    b, a = reports
    print(f"\n{'='*70}")
    print(f"  🏆 HEAD-TO-HEAD: {b.profile} vs {a.profile}")
    print(f"  {'='*70}")
    print(f"  {b.profile:<14} {b.score:.1f}% ({b.passed}/{b.total} passed)")
    print(f"  {a.profile:<14} {a.score:.1f}% ({a.passed}/{a.total} passed)")
    winner = b.profile if b.score >= a.score else a.profile
    delta = abs(b.score - a.score)
    print(f"  Winner: {winner}  (Δ={delta:.1f}%)")
    print(f"  {'='*70}")


# ═══════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════

def main():
    import argparse
    p = argparse.ArgumentParser(description="🧪 Dhamma Agent Benchmark Suite")
    p.add_argument("--profile", "-p", default="arahant", help="Profile to benchmark")
    p.add_argument("--compare", "-c", action="store_true", help="Compare Baseline vs Arahant")
    p.add_argument("--category", choices=["terminal","swe","polyglot","gaia","dhamma","all"], default="all")
    p.add_argument("--max-turns", type=int, default=10)
    p.add_argument("--list", action="store_true", help="List all benchmark tasks")
    args = p.parse_args()

    if args.list:
        for t in ALL_TASKS:
            print(f"  {t.id} [{t.category}] diff={t.difficulty}: {t.prompt[:80]}...")
        return

    tasks = ALL_TASKS if args.category == "all" else [t for t in ALL_TASKS if t.category == args.category]
    if not tasks:
        print(f"No tasks for category '{args.category}'"); return

    if args.compare:
        asyncio.run(run_comparison(tasks, args.max_turns))
    else:
        report = asyncio.run(run_benchmark(args.profile, tasks, args.max_turns))
        print(format_bench_report(report))

if __name__ == "__main__":
    main()
