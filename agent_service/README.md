# Agent service — the always-on Claude brain (Door B)

The web UI's chat box talks to **one persistent Claude session** that drives the robot. Same engine,
same `robot-operator` skill, and same `station_mcp` MCP that you'd get running Claude Code locally —
just exposed over a WebSocket so the browser (text now, voice later) can reach it.

- **Auth = your Claude subscription**, not an API key. Run `claude login` first. The service refuses
  to start if `ANTHROPIC_API_KEY` is set (that would bill the API) — override with `ALLOW_API_KEY=1`.
- **Mock mode by default** — `STATION_HOST` unset ⇒ no hardware needed (matches `station_mcp`).
- **Headless** — `permission_mode=bypassPermissions`, only `mcp__normacore-station__*` tools allowed.

## Prerequisites

- **The Claude Code CLI must be installed** (`claude`) — the Agent SDK drives it under the hood. Install
  it (e.g. `npm i -g @anthropic-ai/claude-code`) and verify `claude --version`.
- **A Claude subscription** (Pro/Max) logged in via `claude login`.
- `station_mcp` set up (its own venv) — this service launches it with `station_mcp/.venv`'s interpreter.

## Setup

```bash
cd agent_service
uv venv && uv pip install -r requirements.txt      # or: pip install -r requirements.txt
claude login                                        # subscription auth (once)
unset ANTHROPIC_API_KEY                             # ensure subscription, not API billing
```

## Run

```bash
cd agent_service
uv run python server.py        # serves ws://localhost:8770/chat  +  GET /health
```

## Protocol

Client → server: `{"text": "hand me the red block"}`

Server → client (streamed): one JSON per event, then a turn terminator:
| `kind` | fields | meaning |
|---|---|---|
| `text` | `text` | assistant message to show in chat |
| `thinking` | `text` | reasoning (drives the "watch it think" panel) |
| `tool_use` | `tool`, `input`, `id` | Claude called a robot MCP tool |
| `tool_result` | `tool_use_id`, `content` | the tool's result (incl. camera frames) |
| `result` | `is_error`, `result`, `session_id` | end of the agent's internal loop |
| `error` | `message` | brain/MCP failure |
| `turn_end` | — | this user turn is fully done |

## Where this fits

```
UI chat box ──ws──► server.py ──► agent.py (ClaudeSDKClient, persistent)
                                    ├─ skill: .claude/skills/robot-operator
                                    └─ MCP: ../station_mcp ──► the arm
```
Next: fork `norma-core`'s `station-viewer` and point its new chat panel at `ws://localhost:8770/chat`.
