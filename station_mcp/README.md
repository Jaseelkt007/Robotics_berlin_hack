# Station-MCP server

The bridge that lets **Claude (or Codex) drive the NormaCore Station** — the literal track deliverable
("integrate the Station API into Claude"). It wraps `station_py` and exposes the robot to Claude as
**MCP tools**. Connects to a **local or remote** Station over TCP (so the arm can be on another laptop).

**AS-BUILT design:** [`../docs/13-grid-control-implemented.md`](../docs/13-grid-control-implemented.md)
— the **grid track** that actually runs (Claude reads a pixel → grid → joints; no IK/ArUco/VLA).
Original two-stage plan: docs/10–11.

## Status (2026-06-21)

- ✅ **Grid track live on hardware** — first full autonomous-grid **pick-and-place succeeded**
  (locate → grasp → lift → deliver). Calibration + `grid_selftest` validated.
- ✅ Live `look`/`get_state`/`move_to_pixel`/`grasp`/`release`/`deliver`/`home` working. State read from
  **`st3215/rx`** (the live queue); camera frames from per-camera `usbvideo/<hash>` queues.
- ▶ **Next:** live brain test (`agent_service` + web, "bring me the box"); reliability; per-object heights.

## Tools

| Tool | What it does |
|---|---|
| `look(camera, grid)` | `look("top", grid=True)` = overhead + pixel grid (LOCATE); returns the **cleanest of a frame burst**. `look("wrist")` = close-up (ALIGN). |
| `move_to_pixel(px,py,height,object_class)` | gripper → table point under a top-cam pixel via the grid (no IK). `height`=`hover`\|`grasp`; **settles before returning**; `extrapolated:true` ⇒ outside taught area. |
| `nudge(direction)` | small `up\|down\|left\|right` step in the top-image frame. |
| `grasp()` / `release()` | close + verify (`holding`/`gap`) / open. |
| `deliver()` / `home()` / `get_state()` | taught drop-zone / taught rest pose / live motor state. |
| `push(px,py,direction,distance_px)` | descend (closed jaws) and shove an object (topple/move-aside). |
| `wave(cycles)` / `grid_selftest()` | greeting gesture / setup check (visit all taught points). |
| `run_vla_task` / `locate` / `move_to` | original SmolVLA/ArUco/IK stubs — left in place, not the path. |

Every motion passes `safety.clamp_targets()` (calibrated-range clamp) — the LLM never writes raw values.

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
| `STATION_BUS_SERIAL` | pin the arm bus (leader+follower = 2 buses); else auto-selects most-calibrated |
| `STATION_DATA_DIR` | Station data dir, so per-camera `usbvideo/<hash>` queues can be discovered |
| `CAMERA_TOP` / `CAMERA_WRIST` | camera vid:pid (or serial) substring → name mapping (else discovery order) |
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

## Calibrate the grid (one-time per rig)
```bash
.venv/bin/python calibrate.py info      # list buses + dump a frame per camera → pick STATION_BUS_SERIAL / CAMERA_*
.venv/bin/python calibrate.py capture   # torque off; hand-pose ~12 grid points + home/drop-zone/gripper
.venv/bin/python calibrate.py click     # browser :8799 — click the gripper tip per frame → waypoints.json
```
Then call `grid_selftest` (arm visits each taught point) before grasping. Full flow + `waypoints.json`
schema: [`../docs/13-grid-control-implemented.md`](../docs/13-grid-control-implemented.md).


## Live bring-up notes (WSL, one machine)

Everything (Station + arm + cameras) on a single Windows+WSL box. Lessons from a real bring-up:

1. **Bind USB into WSL** (admin PowerShell, `usbipd`): the **motor buses** are the two `CH343` serial
   adapters (show up as `/dev/ttyACM*`), e.g. `usbipd attach --wsl --busid 6-2` and `6-3`. Cameras
   (`usbipd attach --wsl --busid <cam>`) also need the kernel bit below.
2. **`.env`**: `STATION_HOST=127.0.0.1`, `STATION_PORT=8888`, `NORMA_CORE_PATH=<clone>`.
3. **Two buses (leader + follower).** `get_state` auto-selects the **most-calibrated** bus; pin a
   specific arm with `STATION_BUS_SERIAL=<serial>` (serials are printed in the server logs / `get_state`).
   The frame stream is per-motor *incremental* and lists a bus twice (a partial entry + the full one) —
   the backend accumulates full register dumps and ignores the partials, so all joints appear.
4. **Calibration is NormaCore's, not ours.** Calibrate each arm in NormaCore's **station-viewer**
   calibration page (`/st3215-bus-calibration`). Our MCP only *reads* the calibrated ranges (used to
   clamp motion). An uncalibrated bus shows degenerate ranges (min==max / min>max).
5. **Cameras need a UVC/V4L2 kernel — fix is `wsl --update`.** The old 5.15 WSL2 kernel lacks
   `uvcvideo` → no `/dev/video*` even when `usbipd` shows the camera Attached (motors still work,
   since serial uses a built-in driver). **CONFIRMED:** `wsl --update` brings a **6.x** WSL2 kernel
   that includes `uvcvideo` — no custom kernel needed (verified on a teammate's box: kernel 6.18.x,
   C270 → `/dev/video0`). After updating: `wsl --shutdown`, re-attach USB, then verify
   `v4l2-ctl --list-devices` / `ls /dev/video*` before expecting `look()` to work.
6. **Read live joint state from `st3215/rx`, not `st3215/inference`** — inference freezes present
   position when torque is off (silently broke torque-off calibration capture until fixed).
7. **Camera frames are on per-camera `usbvideo/<md5(id)>` queues** — set `STATION_DATA_DIR` so the
   backend can discover them; following plain `usbvideo` returns nothing.
8. **Clear stale bytecode** (`rm -rf __pycache__`) on the `/mnt` Windows drive if edits don't take effect.
9. **Gripper can't be hand-moved** — set open/closed by powered moves; **grasp verify waits for the
   jaws to stop** and judges by close-gap. The top cam is noisy → do **fine alignment on the wrist cam**.

Full gotcha list + learnings: [`../docs/13-grid-control-implemented.md`](../docs/13-grid-control-implemented.md).
