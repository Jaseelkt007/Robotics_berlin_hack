"""Station-MCP server — exposes the NormaCore Station to Claude (or Codex) as MCP tools.

This is the bridge that satisfies the track requirement: "integrate the Station API into Claude."
Two-stage execution (see docs/10): Stage 1 = `run_vla_task` (NormaCore finetuned SmolVLA);
Stage 2 fallback = `locate` + `move_to`/`grasp`/`release` (ArUco + IK; partly TODO).

Run:
    pip install -r requirements.txt
    # MOCK (no hardware) — default when STATION_HOST is unset:
    python server.py
    # LIVE — point at the (possibly remote) calibrated Station:
    STATION_HOST=192.168.x.y NORMA_CORE_PATH=../norma-core python server.py

Register with Claude Code:
    claude mcp add normacore-station -- python /abs/path/station_mcp/server.py
"""
from __future__ import annotations

import os
import sys
import json
import asyncio
import logging

# make sibling modules importable regardless of cwd (dir is NOT named "mcp" to avoid shadowing the SDK)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# optional .env loading (no hard dependency)
try:
    from dotenv import load_dotenv  # type: ignore
    # load .env sitting next to this script, regardless of the launcher's cwd
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except Exception:
    pass

from mcp.server.fastmcp import FastMCP, Image  # type: ignore

from backend import MockBackend, LiveBackend
from safety import clamp_targets
from gridmap import GridMap, load_waypoints, default_waypoints_path
import overlay

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("station-mcp")

# ----------------------------- config -----------------------------
STATION_HOST = os.environ.get("STATION_HOST", "").strip()
STATION_PORT = int(os.environ.get("STATION_PORT", "8888"))
NORMA_CORE_PATH = os.environ.get("NORMA_CORE_PATH", "../norma-core")
STATION_BUS_SERIAL = os.environ.get("STATION_BUS_SERIAL", "").strip()  # pin the arm bus (2 buses present)
MOCK_FRAME_PATH = os.environ.get("MOCK_FRAME_PATH") or None
VLA_MAX_TRIES = int(os.environ.get("VLA_MAX_TRIES", "3"))
FORCE_MOCK = os.environ.get("MOCK", "").lower() in ("1", "true", "yes")

USE_MOCK = FORCE_MOCK or not STATION_HOST
backend = (
    MockBackend(MOCK_FRAME_PATH)
    if USE_MOCK
    else LiveBackend(STATION_HOST, STATION_PORT, NORMA_CORE_PATH, STATION_BUS_SERIAL)
)
log.info("Backend: %s", "MOCK" if USE_MOCK else f"LIVE ({STATION_HOST}:{STATION_PORT})")

# ---- waypoints: the taught pixel->joint grid (reliable track). None => grid tools report uncalibrated.
WAYPOINTS_PATH = default_waypoints_path()
_wp = load_waypoints(WAYPOINTS_PATH)
_grid = GridMap(_wp) if _wp else None
if _grid and _grid.ready:
    log.info("waypoints: %s (%d grid points)", WAYPOINTS_PATH, len(_grid.grid_pixels()))
else:
    log.info("waypoints: none usable at %s — grid tools report not_calibrated", WAYPOINTS_PATH)

# Gripper constants come from waypoints when calibrated, else the placeholders below.
_g = (_wp or {}).get("gripper", {})
GRIPPER_ID = int(_g.get("id", 8))
GRIPPER_OPEN = int(_g.get("open_step", 1200))
GRIPPER_CLOSED = int(_g.get("closed_step", 2400))
GRASP_CURRENT_THRESHOLD_MA = int(_g.get("grasp_current_threshold_ma", 250))

# Last commanded pixel/height, so nudge() can step relative to the current placement.
_last_pixel: tuple[float, float] | None = None
_last_height: str = "hover"

mcp = FastMCP("normacore-station")
_connected = False


async def _ensure() -> None:
    global _connected
    if not _connected:
        await backend.connect()
        _connected = True


async def _current_ranges() -> dict[int, tuple[int, int]]:
    try:
        st = await backend.get_state()
        return st.ranges()
    except Exception:
        return {}


async def _settle(timeout: float = 5.0) -> None:
    """Block until the arm stops moving, so a tool returns only after arrival (the brain can then
    look() at a settled pose, not mid-motion). No-op in mock (state animates and never settles)."""
    if USE_MOCK:
        return
    prev = None
    for _ in range(int(timeout / 0.2)):
        await asyncio.sleep(0.2)
        try:
            pos = {m.id: m.position for m in (await backend.get_state()).motors}
        except Exception:
            return
        if prev is not None and max((abs(pos[k] - prev.get(k, pos[k])) for k in pos), default=0) < 6:
            return
        prev = pos


def _live_stack_scale() -> float | None:
    """Re-read stack.lift_scale from waypoints.json on each call so the stacking height can be
    tuned WITHOUT restarting the brain — edit the number, next stack picks it up. Falls back to
    the in-memory grid value on any error."""
    try:
        with open(WAYPOINTS_PATH) as f:
            wp = json.load(f)
        return float(wp.get("stack", {}).get("lift_scale", _grid.stack_lift_scale()))
    except Exception:
        return _grid.stack_lift_scale() if _grid else None


async def _do_move_to_pixel(px: float, py: float, height: str, object_class: str = "") -> dict:
    """Shared core for move_to_pixel / nudge / grid_selftest: interpolate the grid and send."""
    global _last_pixel, _last_height
    if _grid is None or not _grid.ready:
        return {"ok": False, "reason": "not_calibrated"}
    await _ensure()
    try:
        if height == "stack":
            joints, extrapolated = _grid.interp(px, py, "stack", lift_scale=_live_stack_scale())
        else:
            joints, extrapolated = _grid.interp(px, py, height)
    except ValueError as e:
        return {"ok": False, "reason": str(e)}
    if height == "grasp" and object_class:  # per-object-class grasp-height offset
        for mid, d in _grid.grasp_offset(object_class).items():
            joints[mid] = joints.get(mid, 0) + d
    targets = clamp_targets(joints, await _current_ranges())
    ok = await backend.send_joint_targets(targets)
    await _settle()  # return only once the arm has arrived, so the next look() isn't mid-motion
    _last_pixel, _last_height = (px, py), height
    return {"ok": ok, "sent": targets, "px": px, "py": py, "height": height,
            "object_class": object_class or None, "extrapolated": extrapolated}


# ----------------------------- tools -----------------------------
@mcp.tool()
async def look(camera: str = "top", grid: bool = False) -> Image:
    """Return the latest camera frame as an image.

    `camera`: 'top' (overhead — use to LOCATE objects) or 'wrist' (close-up — use to CONFIRM the
    object is between the jaws / is held). `grid=True` overlays a labelled pixel grid on the TOP
    frame so you can read an object's (x,y) pixel against the gridlines — pass that pixel to
    move_to_pixel. (Overlay applies to the top frame only.)
    """
    await _ensure()
    jpeg = await backend.get_frame(camera, denoise=(camera == "top"))  # top cam is noisy; pick cleanest
    if grid and camera == "top":
        try:
            jpeg = overlay.draw_grid(jpeg)
        except Exception as e:
            log.warning("grid overlay failed: %s", e)
    return Image(data=jpeg, format="jpeg")


@mcp.tool()
async def get_state() -> dict:
    """Live robot state: per-motor position, current (mA), and calibrated range_min/range_max."""
    await _ensure()
    st = await backend.get_state()
    return {"bus": st.bus_serial, "motors": [vars(m) for m in st.motors]}


@mcp.tool()
async def run_vla_task(instruction: str, max_tries: int = VLA_MAX_TRIES) -> dict:
    """STAGE 1 (primary): run NormaCore's finetuned SmolVLA with a natural-language instruction.

    Retries up to `max_tries`. Returns {ok, tries, ...}. If ok is False, the caller (Claude) should
    fall back to STAGE 2 (locate + move_to/grasp).
    """
    await _ensure()
    return await backend.run_vla(instruction, max_tries)


@mcp.tool()
async def locate(target: str) -> dict:
    """STAGE 2 fallback: estimate the target's 3D pose via ArUco markers + 2D->3D mapping.

    TODO: implement ArUco detection + 2D->3D using the top camera + calibration.
    """
    await _ensure()
    return {"ok": False, "todo": "ArUco + 2D->3D pose not implemented yet", "target": target}


@mcp.tool()
async def move_to(x: float, y: float, z: float) -> dict:
    """STAGE 2 fallback: move the gripper to a Cartesian target (metres, robot frame).

    TODO: inverse kinematics (ikpy/PyBullet + URDF) -> joint targets -> clamp -> send.
    """
    await _ensure()
    return {"ok": False, "todo": "IK (Cartesian->joints) not implemented yet", "target": [x, y, z]}


@mcp.tool()
async def grasp() -> dict:
    """Close the gripper and verify a hold from motor feedback.

    Returns `holding` (True/False) plus `current_ma`/`position`. `holding=True` means the jaws
    stalled short of fully closed with elevated current — something is between them. If False, open
    and retry the approach (the object is still where it was).
    """
    await _ensure()
    return await backend.grasp_with_verify(GRIPPER_CLOSED, GRIPPER_OPEN, GRASP_CURRENT_THRESHOLD_MA, GRIPPER_ID)


@mcp.tool()
async def release() -> dict:
    """Open the gripper (clamped to calibrated range)."""
    await _ensure()
    targets = clamp_targets({GRIPPER_ID: GRIPPER_OPEN}, await _current_ranges())
    ok = await backend.send_joint_targets(targets)
    return {"ok": ok, "sent": targets}


@mcp.tool()
async def home() -> dict:
    """Return the arm to its home/rest pose (taught pose if calibrated, else range midpoint)."""
    await _ensure()
    pose = _grid.home() if (_grid and _grid.ready) else None
    return {"ok": await backend.home(pose or None)}


# ----------------------------- reliable (grid) track -----------------------------
@mcp.tool()
async def move_to_pixel(px: float, py: float, height: str = "hover", object_class: str = "") -> dict:
    """Move the gripper to the table point under TOP-camera pixel (px, py).

    Read (px, py) from `look("top", grid=True)`. `height`: 'hover' (safe approach height — always go
    here first) or 'grasp' (object-grasp height — descend only when aligned, gripper already open).
    `object_class` (box|bottle|cup) applies that object's taught grasp-height offset at 'grasp'.
    Interpolates the taught pixel->joint grid (no IK). `extrapolated:true` means (px, py) is outside
    the taught area — ask the person to move the object inward rather than trusting the result.
    """
    return await _do_move_to_pixel(px, py, height, object_class)


@mcp.tool()
async def nudge(direction: str, step_px: int = 0) -> dict:
    """Fine-align by stepping the target a little in the TOP-camera image frame, then re-place.

    `direction`: up|down|left|right as seen in the top frame (up = toward smaller y). Use after
    move_to_pixel: look("top"), judge which way the gripper must shift to sit over the object, nudge,
    repeat (~1-3 times). `step_px` overrides the default step. Requires a prior move_to_pixel.
    """
    if _grid is None or not _grid.ready:
        return {"ok": False, "reason": "not_calibrated"}
    if _last_pixel is None:
        return {"ok": False, "reason": "call move_to_pixel first"}
    step = int(step_px) if step_px else _grid.nudge_step_px()
    delta = {"left": (-step, 0), "right": (step, 0), "up": (0, -step), "down": (0, step)}.get(direction)
    if delta is None:
        return {"ok": False, "reason": f"direction must be up/down/left/right, got {direction!r}"}
    return await _do_move_to_pixel(_last_pixel[0] + delta[0], _last_pixel[1] + delta[1], _last_height)


@mcp.tool()
async def deliver() -> dict:
    """Move to the taught drop-zone (hover height). Call release() afterward to let go."""
    if _grid is None or not _grid.ready:
        return {"ok": False, "reason": "not_calibrated"}
    await _ensure()
    dz = _grid.drop_zone("hover")
    if not dz:
        return {"ok": False, "reason": "no drop_zone taught"}
    targets = clamp_targets(dz, await _current_ranges())
    return {"ok": await backend.send_joint_targets(targets), "sent": targets}


@mcp.tool()
async def grid_selftest(height: str = "hover", dwell_s: float = 1.5) -> dict:
    """Visit every taught grid pixel in turn so a human can confirm the grid is correct.

    Run this (and watch the arm) BEFORE grasping any object — it catches bad pixel clicks or a
    swapped axis immediately. Returns the per-point send results.
    """
    if _grid is None or not _grid.ready:
        return {"ok": False, "reason": "not_calibrated"}
    await _ensure()
    visited = []
    for (sx, sy) in _grid.grid_pixels():
        r = await _do_move_to_pixel(sx, sy, height)
        visited.append({"px": sx, "py": sy, "ok": r.get("ok")})
        await asyncio.sleep(dwell_s)
    return {"ok": True, "height": height, "visited": visited}


@mcp.tool()
async def push(px: float, py: float, direction: str, distance_px: int = 45, object_class: str = "") -> dict:
    """Push / topple / shove an object instead of picking it.

    Closes the jaws (to use the gripper as a blunt tool), descends onto the object at top-camera pixel
    (px, py), then drags `distance_px` in the given TOP-image direction (up|down|left|right) and lifts.
    Use to move something aside, knock it over, or slide it. Read (px, py) from look("top", grid=True).
    """
    if _grid is None or not _grid.ready:
        return {"ok": False, "reason": "not_calibrated"}
    delta = {"left": (-distance_px, 0), "right": (distance_px, 0),
             "up": (0, -distance_px), "down": (0, distance_px)}.get(direction)
    if delta is None:
        return {"ok": False, "reason": f"direction must be up/down/left/right, got {direction!r}"}
    await _ensure()
    await backend.send_joint_targets(clamp_targets({GRIPPER_ID: GRIPPER_CLOSED}, await _current_ranges()))
    await _do_move_to_pixel(px, py, "hover")
    await _do_move_to_pixel(px, py, "grasp", object_class)
    await _do_move_to_pixel(px + delta[0], py + delta[1], "grasp", object_class)  # drag
    r = await _do_move_to_pixel(px + delta[0], py + delta[1], "hover")            # lift clear
    return {"ok": r.get("ok"), "from": [px, py], "to": [px + delta[0], py + delta[1]],
            "direction": direction, "extrapolated": r.get("extrapolated")}


@mcp.tool()
async def wave(cycles: int = 3) -> dict:
    """Wave the arm in greeting: go home, then oscillate the wrist a few times, return home.

    A friendly non-grasp gesture (e.g. when greeting or acknowledging). No object needed.
    """
    await _ensure()
    ranges = await _current_ranges()
    home = _grid.home() if (_grid and _grid.ready) else None
    if home:
        await backend.send_joint_targets(clamp_targets(home, ranges))
        await asyncio.sleep(1.2)
    base = home or {m.id: m.position for m in (await backend.get_state()).motors}
    wj = 6 if 6 in base else max(base)  # wrist joint (fallback: highest-id arm joint)
    if wj not in base:
        return {"ok": False, "reason": "no wrist joint to wave"}
    for _ in range(max(1, cycles)):
        await backend.send_joint_targets(clamp_targets({wj: base[wj] + 250}, ranges))
        await asyncio.sleep(0.4)
        await backend.send_joint_targets(clamp_targets({wj: base[wj] - 250}, ranges))
        await asyncio.sleep(0.4)
    await backend.send_joint_targets(clamp_targets({wj: base[wj]}, ranges))
    return {"ok": True, "cycles": cycles, "wrist_joint": wj}


@mcp.tool()
async def drag(px: float, py: float, object_class: str = "") -> dict:
    """Move an object you have ALREADY grasped to top-camera pixel (px, py) while keeping it ON the
    table (a drag, NOT a lift), then release it there.

    Use for "drag/move X to <spot>, don't pick it up". Flow: locate → hover → align on the wrist cam →
    `grasp()` and confirm `holding:true` → THEN `drag(px, py)`. This slides the held object at grasp
    height to the destination and opens the jaws to leave it there. (Unlike `push`, it can't miss — it
    moves an object it's already holding — so it's the reliable way to reposition something.)
    """
    if _grid is None or not _grid.ready:
        return {"ok": False, "reason": "not_calibrated"}
    await _ensure()
    r = await _do_move_to_pixel(px, py, "grasp", object_class)  # slide the held object at table height
    await backend.send_joint_targets(clamp_targets({GRIPPER_ID: GRIPPER_OPEN}, await _current_ranges()))
    await asyncio.sleep(0.8)
    return {"ok": r.get("ok"), "to": [px, py], "released": True, "extrapolated": r.get("extrapolated")}


@mcp.tool()
async def stack_on(px: float, py: float, object_class: str = "") -> dict:
    """Place an object you have ALREADY grasped ON TOP of the box at top-camera pixel (px, py).

    Use for "stack X on Y / put X on top of Y". Flow: pick X exactly like a normal grasp and confirm
    `holding:true` FIRST, then `stack_on(px, py)` where (px,py) is the TARGET box's pixel. This raises
    the held object to stacking height over that pixel (grid pose + `stack.lift_scale` x hover_delta),
    opens the jaws to set it down, then lifts straight up to clear the new stack. Call `home()` after.

    Height is tuned per rig via `stack.lift_scale` in waypoints.json (editable live — no restart):
    raise it if the box clips the target on the way in, lower it if it drops from too high.
    """
    if _grid is None or not _grid.ready:
        return {"ok": False, "reason": "not_calibrated"}
    await _ensure()
    r = await _do_move_to_pixel(px, py, "stack", object_class)  # raise + move over the target box
    await backend.send_joint_targets(clamp_targets({GRIPPER_ID: GRIPPER_OPEN}, await _current_ranges()))
    await asyncio.sleep(0.6)
    # rise a little higher straight up so leaving doesn't knock the fresh stack over
    try:
        clear, _ = _grid.interp(px, py, "stack", lift_scale=(_live_stack_scale() or 2.5) + 1.2)
        await backend.send_joint_targets(clamp_targets(clear, await _current_ranges()))
        await _settle()
    except Exception:
        pass
    return {"ok": r.get("ok"), "on": [px, py], "released": True,
            "extrapolated": r.get("extrapolated"), "lift_scale": _live_stack_scale()}


if __name__ == "__main__":
    mcp.run()  # stdio transport (for `claude mcp add`)
