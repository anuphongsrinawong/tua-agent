# 05 — Core Types and Events

Phase 1 defines the provider-neutral objects that later Tau phases share.

## Why these types exist

The provider layer, agent loop, harness, tools, sessions, and UI should not exchange provider-specific objects.
Instead, they use Tau's own message, tool, result, and event models.

## Messages

Messages live in `tau_agent.messages`:

- `UserMessage` records user input.
- `AssistantMessage` records assistant text and optional tool calls.
- `ToolResultMessage` records the result of a specific tool call.
- `AgentMessage` is the union of all transcript message types.

These are the objects that will eventually be passed to model providers and persisted in sessions.

## Tools

Tools live in `tau_agent.tools`:

- `ToolCall` is the assistant's request to execute a named tool with JSON-like arguments.
- `AgentTool` describes an executable tool: name, description, input schema, and async executor.
- `AgentToolResult` is the structured response from running a tool.

The core types do not implement coding tools yet. Built-in tools such as `read`, `write`, `edit`, and `bash`
will come in a later phase under the coding-agent application layer.

## Events

Events live in `tau_agent.events`. They describe progress from the portable agent layer:

- `agent_start`
- `agent_end`
- `turn_start`
- `turn_end`
- `message_start`
- `message_delta`
- `message_end`
- `tool_execution_start`
- `tool_execution_update`
- `tool_execution_end`
- `error`

Print mode, Rich renderers, and the future Textual TUI can all consume the same event stream.

## Design boundary

These models are intentionally small and provider-neutral. Provider adapters will translate Anthropic,
OpenAI, or other API payloads into Tau types in a later phase.
