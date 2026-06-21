# 13 — Grid control (AS BUILT, the reliable track)

> **This is what actually runs.** Docs 10/11 describe the original *SmolVLA-primary + ArUco/IK* plan;
> SmolVLA was blocked on a checkpoint, so we built a **SmolVLA-independent grid track** that is now the
> primary path. First full autonomous-grid **pick-and-place succeeded on hardware (2026-06-21).**

## The idea in one paragraph

Claude **is the perception**. It looks at the overhead camera, finds the target, and hands back a
**pixel**. A **pre-taught calibration grid** turns that pixel into joint angles — no IK, no ArUco, no
ML policy, no API key (the brain uses the Claude subscription). Fine alignment uses the **wrist
camera**; the grasp is verified by how far the jaws closed. Everything is composed from small MCP
tools the brain calls.

```
look("top") → Claude reads the box pixel
move_to_pixel(px,py,"hover")        # grid interpolation → joints (replaces IK)
look("wrist") → nudge ×1-3          # fine-align on the close-up cam
move_to_pixel(px,py,"grasp") → grasp()   # descend, close, verify by close-gap
move_to_pixel(px,py,"hover") → deliver() → release() → home()
```

## Architecture (unchanged shells, new guts)

`agent_service/` (Claude Agent SDK brain, subscription auth) → **MCP tools** → `station_mcp/` → NormaCore
Station. The brain + web UI + MCP-server shells are the originals; the grid logic is **additive** inside
`station_mcp` (`run_vla_task`/`locate`/`move_to` stubs are left intact, just no longer the path).

New code: `gridmap.py` (pixel→joint IDW interpolation), `overlay.py` (top-frame coordinate grid),
`calibrate.py` (teach the grid), plus the tools below. Calibration output: `waypoints.json` (per-rig,
git-ignored).

## MCP tools (current)

| Tool | What it does |
|---|---|
| `look(camera, grid)` | `look("top", grid=True)` = overhead + pixel grid (LOCATE); returns the **cleanest of a frame burst** (top cam is noisy). `look("wrist")` = close-up (ALIGN/VERIFY). |
| `move_to_pixel(px,py,height,object_class)` | gripper → table point under a top-cam pixel via the grid. `height` = `hover`\|`grasp`. **Settles before returning.** `extrapolated:true` ⇒ outside the taught area. |
| `nudge(direction)` | small step `up\|down\|left\|right` in the top-image frame; re-place. |
| `grasp()` | close + verify; returns `holding` + `gap` (big gap ⇒ object held). |
| `release()` / `deliver()` / `home()` / `get_state()` | open / go to taught drop-zone / taught rest pose / live motor state. |
| `drag(px,py,object_class)` | after grasping, slide the held object (on the table, no lift) to a destination pixel and release — reliable repositioning. |
| `stack_on(px,py,object_class)` | after grasping, raise the held object to **stacking height** over the target box's pixel (grid pose + `stack.lift_scale`×hover_delta), set it down ON TOP, lift clear. Drives the **box-stacker** skill. |
| `push(px,py,direction,distance_px)` | blind shove with closed jaws (rough; can miss — prefer `drag`). |
| `wave(cycles)` | greeting gesture. |
| `grid_selftest()` | visit every taught point — **setup check only**, run before grasping. |
| `run_vla_task` / `locate` / `move_to` | original SmolVLA/ArUco/IK stubs — left in place, not the path. |

Every motion still passes `safety.clamp_targets()` (calibrated-range clamp).

## Calibration (one-time per rig — `calibrate.py`)

Run on the robot laptop with the Station live. Config comes from `station_mcp/.env`.

```bash
cd station_mcp
.venv/bin/python calibrate.py info      # list motor buses + dump a frame per camera → pick bus/cams
.venv/bin/python calibrate.py capture   # torque off; hand-pose ~12 grid points (grasp + lift),
                                        #   then home, drop-zone, gripper → waypoints.partial.json + frames
.venv/bin/python calibrate.py click     # browser at :8799 — click the gripper tip in each frame → waypoints.json
```
Then verify with `grid_selftest` (arm visits each taught point) **before** grasping anything.

`waypoints.json`: `grid[]` of `{pixel, grasp(joints), hover_delta}` + `home`, `drop_zone`, `gripper`
(`open_step`/`closed_step`/`grasp_current_threshold_ma`), `grasp_offsets` (per-object height), `nudge`,
`stack` (`lift_scale` — multiplier on hover_delta for `stack_on`/place-on-top, tuned per rig).
The grid is **object-independent for XY** — only grasp *height* is object-specific.

## Config (`station_mcp/.env`)

```
STATION_HOST=localhost            # unset ⇒ MOCK mode
STATION_PORT=8888
NORMA_CORE_PATH=../norma-core
STATION_DATA_DIR=/path/to/station_data   # so camera queues can be discovered (see gotcha #1)
STATION_BUS_SERIAL=<follower-serial>     # pin the arm bus (leader+follower = 2 buses)
CAMERA_TOP=<vid:pid substring>           # e.g. 1133:2085 (C270, overhead)
CAMERA_WRIST=<vid:pid substring>         # e.g. 7749:521 (gripper cam)
```
Read by both `server.py` and `calibrate.py`.

## Hardware gotchas / learnings (these cost us hours — read before bring-up)

1. **Camera frames are on per-camera queues** `usbvideo/<md5(camera_unique_id)>`, **not** a single
   `usbvideo` queue. The backend discovers them from `STATION_DATA_DIR`. Following the wrong id
   silently returns nothing.
2. **`st3215/inference` FREEZES present-position when torque is off** (it only re-publishes on
   triggers). Read **live** position/current from **`st3215/rx`**; take calibrated *ranges* from
   `inference`. This silently made every torque-off hand-pose capture identical until fixed.
3. **Stale `.pyc` on the WSL/Windows drive** (`/mnt/e`) can run old code despite edits. **Always
   `rm -rf station_mcp/__pycache__`** before a fresh run if behaviour looks wrong.
4. **`input()` blocks the asyncio loop** → background consumers stall → `get_state()` freezes during
   interactive scripts. `calibrate.py` uses an executor-backed `_ainput()`.
5. **The ST3215 gripper can't be back-driven by hand** — set open/closed by *powered* moves, not
   hand-posing (measured ~2917 open / ~1264 closed on this rig).
6. **Grasp verify must wait for the jaws to stop** (~2–4 s) and judge by **close-gap** (jaws stopping
   short ⇒ object held). Checking too early always reads "empty".
7. **The C270 top cam is noisy/low-res (160×120) over usbip.** `look("top")` returns the cleanest of a
   frame burst, but it's still too noisy for *fine* alignment — do the final cm on the **wrist cam**.
8. Keep the cameras **fixed** after calibration — the grid is tied to the top camera's exact view.

## Status & next steps

- ✅ Phases 0–2 done; Phase 3 proven end-to-end (one successful autonomous-grid box pick).
- ▶ **Next:** live brain test (`agent_service` + web, "bring me the box") to validate the autonomous
  loop on the real cam; then reliability reps, per-object grasp heights (or a contact-detect descent),
  and (stretch) voice. See `~/.claude` plan / `00–07` docs for the broader vision.

Bring-up tools (manual, in `station_mcp/`): `pick.py` (hover/grasp/lift/deliver/release/probe/park),
`look.py`, `run_selftest.py`. Tests: `test_gridmap.py`, `test_server_mock.py`, `test_calibrate_click.py`,
`test_cleanest.py`.
