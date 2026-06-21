"""Always-on Claude brain for the NormaCore web UI.

Holds ONE persistent `ClaudeSDKClient` session (not a process-per-message) that:
  - authenticates with your **Claude subscription** (the `claude login` credential) — NOT an API key,
  - loads the project skill you wrote (`.claude/skills/robot-operator/`),
  - connects to the `station_mcp` MCP server so Claude can drive the arm,
  - streams every assistant text / tool-call / tool-result / thinking block back out, so the UI can
    render a live "watch it think" panel.

This is the SAME engine + SAME skill + SAME MCP that someone gets by running Claude Code with the
`normacore-station` MCP locally — just exposed to the web UI instead of a terminal.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, AsyncIterator

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient

# Repo root = the dir that contains `.claude/skills/` and `station_mcp/`.
REPO_ROOT = Path(__file__).resolve().parent.parent
STATION_MCP_DIR = REPO_ROOT / "station_mcp"

# The MCP server key here becomes the tool prefix `mcp__normacore-station__<tool>`,
# matching what the robot-operator skill expects.
MCP_NAME = "normacore-station"


def _station_mcp_launch() -> dict[str, Any]:
    """Command/args to start the station MCP in ITS OWN venv.

    Using `uv run --directory station_mcp` inherits whatever venv is active in the parent process
    (the agent_service venv, which lacks Pillow) — so look() can't build a mock frame. Launching
    station_mcp/.venv's interpreter directly pins the right environment regardless of the launcher.
    Falls back to `uv run` if the venv hasn't been created yet.
    """
    venv_py = STATION_MCP_DIR / ".venv" / "bin" / "python"          # Linux / WSL / macOS
    venv_py_win = STATION_MCP_DIR / ".venv" / "Scripts" / "python.exe"  # Windows
    if venv_py.exists():
        return {"command": str(venv_py), "args": [str(STATION_MCP_DIR / "server.py")]}
    if venv_py_win.exists():
        return {"command": str(venv_py_win), "args": [str(STATION_MCP_DIR / "server.py")]}
    # No venv yet — fall back to uv (works, but see the docstring caveat).
    return {"command": "uv", "args": ["run", "--directory", str(STATION_MCP_DIR), "python", "server.py"]}


def _assert_subscription_auth() -> None:
    """Fail loud if an API key is set — we want the Claude SUBSCRIPTION, not per-token billing.

    Auth precedence in the Agent SDK is ANTHROPIC_API_KEY first, then the `claude login` credential.
    A stray key silently flips billing to the API, which is exactly what the user does NOT want.
    """
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is set — this would bill the API instead of using your Claude "
            "subscription. Unset it (`unset ANTHROPIC_API_KEY`) and run `claude login` first.\n"
            "If you intentionally want API-key billing, set ALLOW_API_KEY=1 to bypass this check."
        )


def _build_options() -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        cwd=str(REPO_ROOT),                 # so the project skill in .claude/skills is discovered
        setting_sources=["project"],        # load .claude/settings.json + project skills
        permission_mode="bypassPermissions",  # headless: no human to approve each tool call
        allowed_tools=[f"mcp__{MCP_NAME}__*"],  # auto-approve only the robot's MCP tools
        mcp_servers={
            MCP_NAME: {
                "type": "stdio",
                # Launch in station_mcp's OWN venv (see _station_mcp_launch). MOCK by default
                # (STATION_HOST unset). server.py also loads its own .env next to itself.
                **_station_mcp_launch(),
                # Inherit the FULL parent environment (PATH, locale, HOME, …). Passing a filtered/empty
                # dict here REPLACES the subprocess env and makes the stdio MCP server fail to start.
                # STATION_*/NORMA_CORE_PATH come from station_mcp/.env (the server loads it via dotenv).
                "env": dict(os.environ),
            }
        },
        # Append a small framing note; the robot-operator SKILL.md carries the real policy.
        system_prompt={
            "type": "preset",
            "preset": "claude_code",
            "append": (
                "You are the always-on operator brain behind the NormaCore web UI. The person is "
                "talking to you through a chat box (voice later). Follow the robot-operator skill. "
                "Acknowledge instantly, then act through the normacore-station MCP tools."
            ),
        },
    )


def _normalize(message: Any) -> list[dict[str, Any]]:
    """Turn an SDK message into JSON-serializable UI events (the 'watch it think' feed)."""
    # Import lazily so a missing SDK gives a clean error at startup, not import time.
    from claude_agent_sdk.types import (  # type: ignore
        AssistantMessage,
        ResultMessage,
        TextBlock,
        ThinkingBlock,
        ToolResultBlock,
        ToolUseBlock,
    )

    events: list[dict[str, Any]] = []
    if isinstance(message, AssistantMessage):
        for block in message.content:
            if isinstance(block, TextBlock):
                events.append({"kind": "text", "text": block.text})
            elif isinstance(block, ThinkingBlock):
                events.append({"kind": "thinking", "text": block.thinking})
            elif isinstance(block, ToolUseBlock):
                events.append({"kind": "tool_use", "tool": block.name, "input": block.input, "id": block.id})
            elif isinstance(block, ToolResultBlock):
                events.append({"kind": "tool_result", "tool_use_id": block.tool_use_id, "content": block.content})
    elif isinstance(message, ResultMessage):
        events.append({
            "kind": "result",
            "is_error": message.is_error,
            "result": message.result,
            "session_id": message.session_id,
        })
    elif type(message).__name__ == "SystemMessage":
        import sys as _sys
        d = getattr(message, "data", {}) or {}
        if getattr(message, "subtype", "") == "init":
            print(f"=== MCP INIT === mcp_servers={d.get('mcp_servers')} | "
                  f"tools_n={len(d.get('tools', []))} | slash_n={len(d.get('slash_commands', []))}",
                  file=_sys.stderr, flush=True)
    return events


class RobotBrain:
    """Wraps the single long-lived ClaudeSDKClient. One physical arm → one serialized session."""

    def __init__(self) -> None:
        self._client: ClaudeSDKClient | None = None

    async def start(self) -> None:
        if not os.environ.get("ALLOW_API_KEY"):
            _assert_subscription_auth()
        self._client = ClaudeSDKClient(options=_build_options())
        await self._client.connect()

    async def stop(self) -> None:
        if self._client is not None:
            await self._client.disconnect()
            self._client = None

    async def ask(self, prompt: str) -> AsyncIterator[dict[str, Any]]:
        """Send one user turn into the persistent session and stream normalized UI events."""
        if self._client is None:
            raise RuntimeError("RobotBrain not started")
        await self._client.query(prompt)
        async for message in self._client.receive_response():
            for event in _normalize(message):
                yield event
