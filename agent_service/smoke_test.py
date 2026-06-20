"""Smoke-test the running agent_service WebSocket — no UI needed.

Run server.py in one terminal, then in another:
    cd agent_service && uv run python smoke_test.py
    cd agent_service && uv run python smoke_test.py "pick up the red block and put it in the tray"

Proves the full chain: this client → Claude (subscription) → robot-operator skill → station_mcp → mock arm.
Expect to see tool_use (look / run_vla_task) → tool_result → text events, then turn_end.
"""
from __future__ import annotations

import asyncio
import json
import sys

import websockets  # ships with uvicorn[standard]

URL = "ws://localhost:8770/chat"
DEFAULT_PROMPT = "Call look on the top camera and tell me what you see."


def _render(event: dict) -> None:
    kind = event.get("kind")
    if kind == "text":
        print(f"\n💬 {event['text']}")
    elif kind == "thinking":
        print(f"\n🧠 (thinking) {event['text'][:200]}")
    elif kind == "tool_use":
        print(f"\n🔧 tool_use → {event['tool']}  input={json.dumps(event['input'])[:200]}")
    elif kind == "tool_result":
        body = json.dumps(event.get("content"))[:200]
        print(f"   ↳ result: {body}")
    elif kind == "result":
        flag = "ERROR" if event.get("is_error") else "ok"
        print(f"\n✅ loop done ({flag}) session={event.get('session_id')}")
    elif kind == "error":
        print(f"\n❌ error: {event['message']}")
    elif kind == "turn_end":
        print("\n— turn end —")


async def main() -> None:
    prompt = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PROMPT
    print(f"→ connecting to {URL}")
    async with websockets.connect(URL) as ws:
        print(f"→ sending: {prompt!r}\n" + "-" * 60)
        await ws.send(json.dumps({"text": prompt}))
        async for raw in ws:
            event = json.loads(raw)
            _render(event)
            if event.get("kind") == "turn_end":
                break


if __name__ == "__main__":
    asyncio.run(main())
