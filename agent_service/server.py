"""FastAPI WebSocket bridge between the web UI chat box and the always-on RobotBrain.

The browser opens ws://<host>/chat, sends `{"text": "..."}`, and receives a stream of UI events:
  {"kind": "text"|"thinking"|"tool_use"|"tool_result"|"result", ...}  then  {"kind": "turn_end"}.

The arm is a single physical resource, so turns are serialized with one lock — a second message
queues behind the first instead of racing it onto the hardware.
"""
from __future__ import annotations

import asyncio
import contextlib
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from agent import RobotBrain

brain = RobotBrain()
turn_lock = asyncio.Lock()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await brain.start()
    yield
    await brain.stop()


app = FastAPI(title="NormaCore Robot Brain", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.websocket("/chat")
async def chat(ws: WebSocket) -> None:
    await ws.accept()
    try:
        while True:
            data = await ws.receive_json()
            text = (data or {}).get("text", "").strip()
            if not text:
                continue
            # Serialize: only one turn drives the arm at a time.
            async with turn_lock:
                try:
                    async for event in brain.ask(text):
                        await ws.send_json(event)
                except Exception as exc:  # surface brain/MCP errors to the UI instead of dropping
                    await ws.send_json({"kind": "error", "message": str(exc)})
                await ws.send_json({"kind": "turn_end"})
    except WebSocketDisconnect:
        pass
    finally:
        with contextlib.suppress(Exception):
            await ws.close()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8770)
