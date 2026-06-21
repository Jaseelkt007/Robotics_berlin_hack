"""Send one command to the running brain over its WebSocket and report whether it actually
invokes a normacore-station MCP tool (vs. failing to find the tools). Read-only ('look')."""
import asyncio
import json

import websockets


async def main():
    uri = "ws://localhost:8770/chat"
    async with websockets.connect(uri, max_size=None) as ws:
        await ws.send(json.dumps({"text": "Call look on the top camera and briefly describe what you see."}))
        station_tool = False
        loop = asyncio.get_event_loop()
        deadline = loop.time() + 120
        while loop.time() < deadline:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=120)
            except asyncio.TimeoutError:
                break
            ev = json.loads(msg)
            k = ev.get("kind")
            if k == "tool_use":
                t = str(ev.get("tool", ""))
                print("TOOL_USE:", t, flush=True)
                if "normacore-station" in t or t in ("look", "get_state"):
                    station_tool = True
            elif k == "tool_result":
                print("TOOL_RESULT received", flush=True)
            elif k == "text":
                print("TEXT:", (ev.get("text", "") or "")[:240], flush=True)
            elif k == "error":
                print("ERROR:", ev.get("message"), flush=True)
            elif k in ("turn_end", "result"):
                print("END:", k, flush=True)
                break
        print(f"=== STATION MCP TOOL INVOKED: {station_tool} ===", flush=True)


asyncio.run(main())
