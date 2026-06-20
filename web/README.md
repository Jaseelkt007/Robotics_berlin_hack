# NormaCore web UI (Door B)

The operator dashboard — a clean, ElevenLabs-style (white + Inter) React app. Its chat box talks to
the always-on Claude brain (`agent_service`), and the "watch it think" feed renders Claude's text,
reasoning, robot tool calls, and camera frames live.

- **Stack:** Vite 7 + React 19 + TypeScript + Tailwind v4 + lucide-react (same stack as norma-core's
  station-viewer, so its components/iframe embed cleanly).
- **Brain:** WebSocket to `agent_service` (`ws://localhost:8770/chat`).
- **Cameras + calibration:** reuses norma-core's `station-viewer` via an embedded iframe — set
  `VITE_VIEWER_URL` to the running viewer (e.g. `http://localhost:5173`). Until then, `look()` frames
  still show inline in the conversation.

## Run

```bash
cd web
npm install
cp .env.example .env        # optional: set VITE_VIEWER_URL to embed the live viewer
npm run dev                 # http://localhost:5174
```

Make sure the brain is up first (`cd agent_service && uv run python server.py`).

## Layout

- Left grouped sidebar · top pill-button bar · "Good evening" greeting + tabs (matches the ElevenLabs
  dashboard you referenced).
- Main: **Conversation / watch-it-think** panel (left) + **Cameras & calibration** card (right).

## Config

| Var | Meaning |
|---|---|
| `VITE_AGENT_WS` | brain WebSocket (default `ws://localhost:8770/chat`) |
| `VITE_VIEWER_URL` | station-viewer URL to embed for live cameras/calibration (blank = placeholder) |
