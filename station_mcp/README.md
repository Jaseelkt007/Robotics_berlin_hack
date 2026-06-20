# Station-MCP server

The bridge that lets **Claude (or Codex) drive the NormaCore Station** — the literal track deliverable
("integrate the Station API into Claude"). It wraps `station_py` and exposes the robot as MCP tools.

See [`../docs/11-claude-integration.md`](../docs/11-claude-integration.md) for the full design and
[`../docs/10-implementation-strategy.md`](../docs/10-implementation-strategy.md) for the two-stage plan.

## Status

Scaffold. **Mock mode works today** (no hardware) — use it to prove the MCP↔Claude wiring, especially
that `look()` returns an image Claude can *see*. Live-mode methods that need hardware / NormaCore
confirmation are stubbed and clearly marked `TODO` in `backend.py`.

## Tools

| Tool | Stage | Status |
|---|---|---|
| `look(camera="top"\|"wrist")` | both | ✅ mock · 🔧 live TODO (parse `usbvideo`) |
| `get_state()` | both | ✅ mock · 🔧 live TODO (parse `st3215/inference`) |
| `run_vla_task(instruction, max_tries)` | 1 (primary) | ✅ mock · 🔧 live TODO (confirm NormaCore SmolVLA run API) |
| `locate(target)` | 2 (fallback) | 🔧 TODO (ArUco + 2D→3D) |
| `move_to(x,y,z)` | 2 (fallback) | 🔧 TODO (IK) |
| `grasp()` / `release()` | 2 | ✅ mock · 🔧 live via gripper write (clamped) |
| `home()` | — | ✅ mock · 🔧 live TODO |

Every motor command passes through `safety.clamp_targets()` (calibrated-range clamp).

## Run

```bash
cd station_mcp
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# MOCK (no hardware) — default when STATION_HOST is unset:
python server.py

# LIVE — point at the (possibly remote) calibrated Station:
STATION_HOST=192.168.x.y NORMA_CORE_PATH=../norma-core python server.py
```

Config via env (see `.env.example`): `STATION_HOST`, `STATION_PORT`, `NORMA_CORE_PATH`, `MOCK`,
`MOCK_FRAME_PATH`, `VLA_MAX_TRIES`.

## Connect to Claude Code

```bash
claude mcp add normacore-station -- python /abs/path/to/station_mcp/server.py
```

Then in a Claude Code session, ask it to call `look` — the **hour-1 linchpin** is confirming Claude
actually *sees* the returned frame and can describe it. Once that works, everything else builds on it.

## What's left to wire (LIVE)
- `look` / `get_state`: parse the `usbvideo` and `st3215/inference` protobufs (on hardware).
- `run_vla_task`: confirm with NormaCore exactly how the finetuned SmolVLA is triggered.
- `locate` (ArUco + 2D→3D) and `move_to` (IK via `ikpy`/PyBullet + URDF).
- Camera selection for `top` vs `wrist` (by serial/unique_id).
