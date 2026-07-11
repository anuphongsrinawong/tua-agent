"""Prompt caching layout helper for Tua Agent (#18).

Rearrange conversation messages so that the static prefix (system prompt,
tool definitions, project context) sits first—enabling provider-side prompt
caching on the prefix—and the dynamic conversation tail follows.

Reference:
  Anthropic: https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching
  OpenAI:    https://platform.openai.com/docs/guides/prompt-caching
"""

from __future__ import annotations

from collections.abc import Sequence

from tau_agent.messages import AgentMessage


def compute_cache_layout(
    messages: Sequence[AgentMessage],
    *,
    system_content: str = "",
    static_context: Sequence[AgentMessage] = (),
) -> list[AgentMessage]:
    """Return messages reordered for optimal prompt caching.

    Layout (Anthropic/OpenAI cache breakpoint convention):

    1. **system** block (cached) — tool definitions + system prompt
    2. **static context** (cached)  — project info, workspace tree
    3. **dynamic conversation**     — user/assistant turns, tool results

    The first two blocks are cacheable; the third changes every turn and
    won't benefit from caching.
    """
    result: list[AgentMessage] = []

    # 1. System prompt (first cache breakpoint)
    if system_content:
        # We wrap system content as a UserMessage for the cacheable prefix
        from tau_agent.messages import UserMessage
        result.append(UserMessage(content=f"<system>\n{system_content}\n</system>"))

    # 2. Static context (second cache breakpoint)
    result.extend(static_context)

    # 3. Dynamic conversation
    # Filter: anything not already in the static prefix
    static_ids = {id(m) for m in static_context}
    for msg in messages:
        if id(msg) not in static_ids:
            result.append(msg)

    return result


def partition_cacheable(
    messages: Sequence[AgentMessage],
    *,
    count: int = 3,
) -> tuple[list[AgentMessage], list[AgentMessage]]:
    """Split messages into cacheable prefix and dynamic tail.

    The first ``count`` messages are treated as the cacheable prefix;
    the remainder is dynamic conversation. Callers can adjust ``count``
    based on their specific layout.
    """
    prefix = list(messages[:count])
    tail = list(messages[count:])
    return prefix, tail
