# Station-MCP server

The bridge that lets **Claude (or Codex) drive the NormaCore Station** — the literal track deliverable
("integrate the Station API into Claude"). It wraps `station_py` and exposes the robot to Claude as
**MCP tools**. Connects to a **local or remote** Station over TCP (so the arm can be on another laptop).

Design: [`../docs/11-claude-integration.md`](../docs/11-claude-integration.md) ·
two-stage plan: [`../docs/10-implementation-strategy.md`](../docs/10-implementation-strategy.md).

## Status

- ✅ **Mock mode works** (no hardware) — proves the MCP↔Claude wiring, incl. `look()` returning an
  image Claude can *see*. **Linchpin verified.**
- ✅ **Live `look()` + `get_state()` implemented** (background `follow` of `usbvideo` +
  `st3215/inference`, Gremlin reader parsing). Verified against the real protobufs — **pending an
  end-to-end run on the arm.**
- 🔧 **Next milestone:** `run_vla_task` (NormaCore SmolVLA trigger), `locate`/`move_to` (ArUco + IK),
  `send_joint_targets` (for live `grasp`/`release`/`home`).

## Tools

| Tool | Stage | Status |
|---|---|---|
| `look(camera="top"\|"wrist")` | both | ✅ mock · ✅ live (parses `usbvideo`; untested on real cam) |
| `get_state()` | both | ✅ mock · ✅ live (parses `st3215/inference`; untested on real arm) |
| `run_vla_task(instruction, max_tries)` | 1 (primary) | ✅ mock · 🔧 live TODO (confirm NormaCore SmolVLA run API) |
| `locate(target)` | 2 (fallback) | 🔧 TODO (ArUco + 2D→3D) |
| `move_to(x,y,z)` | 2 (fallback) | 🔧 TODO (IK) |
| `grasp()` / `release()` | 2 | ✅ mock · 🔧 live TODO (needs `send_joint_targets`) |
| `home()` | — | ✅ mock · 🔧 live TODO |

Every motor command passes through `safety.clamp_targets()` (calibrated-range clamp) — the LLM never
writes raw values to the arm.

## Setup (uv — fast, and avoids the `/mnt/d` venv/pip issue)

```bash
cd station_mcp
uv venv
uv pip install -r requirements.txt
```
*(No `uv`? `curl -LsSf https://astral.sh/uv/install.sh | sh`)*

## Run

```bash
# MOCK (no hardware) — default when STATION_HOST is unset:
uv run python server.py

# LIVE — point at a local or REMOTE Station (e.g. the robot laptop):
STATION_HOST=192.168.x.y NORMA_CORE_PATH=/mnt/d/normacore/norma-core uv run python server.py
```

### Config (env or a `.env` file next to `server.py`)
| Var | Meaning |
|---|---|
| `STATION_HOST` | Station host/IP. **Unset ⇒ MOCK mode.** |
| `STATION_PORT` | default `8888` |
| `NORMA_CORE_PATH` | path to the cloned `norma-core` repo (for `station_py` + protobufs) — LIVE only |
| `CAMERA_TOP` / `CAMERA_WRIST` | camera serial/unique_id substring to map names (else discovery order: top=1st, wrist=2nd) |
| `MOCK` | force mock even if `STATION_HOST` is set |
| `MOCK_FRAME_PATH` | image served by `look()` in mock mode |
| `VLA_MAX_TRIES` | Stage-1 retry count (default 3) |

See `.env.example`. A `.env` here is git-ignored (safe for the robot laptop's IP).

## Connect to Claude Code

```bash
claude mcp add normacore-station -- uv run --directory /mnt/d/normacore/station_mcp python server.py
claude mcp list      # should show: normacore-station … ✔ Connected
```
In a Claude Code session: `call look and describe what you see` (allow the tool if prompted; `/mcp`
shows status / reconnects). Config from `.env` is picked up — edit `.env`, then `/mcp` reconnect to
switch between mock and live.

## 🔌 Live test against the real arm (arm is on another laptop)

The arm/cameras + calibration live on the **robot laptop**; you run this MCP server on **your** laptop
and connect over the LAN.

1. **Robot laptop:** `station --tcp --web`  →  note its IP (`hostname -I`).
2. **Both laptops on the same Wi-Fi/LAN**; port `8888` reachable (`nc -zv <robot-ip> 8888`).
3. **Your laptop:** create `station_mcp/.env`:
   ```
   STATION_HOST=<robot-laptop-ip>
   STATION_PORT=8888
   NORMA_CORE_PATH=/mnt/d/normacore/norma-core
   # CAMERA_TOP=<serial-substring>      # optional, once serials are known
   # CAMERA_WRIST=<serial-substring>
   ```
4. In Claude Code: `/mcp` → reconnect `normacore-station` (or restart the session).
5. Ask: `call look on top then wrist, and call get_state` → expect **real** camera frames + **real**
   joint positions/current/ranges.

## What's left to wire (LIVE)
- `run_vla_task`: confirm with NormaCore exactly how the finetuned SmolVLA is triggered, then loop N tries.
- `locate` (ArUco + 2D→3D) and `move_to` (IK via `ikpy`/PyBullet + URDF).
- `send_joint_targets` (st3215 `sync_write` to `0x2A`) → unlocks live `grasp`/`release`/`home`.
- Confirm camera mapping (`CAMERA_TOP`/`CAMERA_WRIST`) once the real serials show up in the logs.
