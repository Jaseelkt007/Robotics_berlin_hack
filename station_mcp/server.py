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

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("station-mcp")

# ----------------------------- config -----------------------------
STATION_HOST = os.environ.get("STATION_HOST", "").strip()
STATION_PORT = int(os.environ.get("STATION_PORT", "8888"))
NORMA_CORE_PATH = os.environ.get("NORMA_CORE_PATH", "../norma-core")
MOCK_FRAME_PATH = os.environ.get("MOCK_FRAME_PATH") or None
VLA_MAX_TRIES = int(os.environ.get("VLA_MAX_TRIES", "3"))
FORCE_MOCK = os.environ.get("MOCK", "").lower() in ("1", "true", "yes")

USE_MOCK = FORCE_MOCK or not STATION_HOST
backend = (
    MockBackend(MOCK_FRAME_PATH)
    if USE_MOCK
    else LiveBackend(STATION_HOST, STATION_PORT, NORMA_CORE_PATH)
)
log.info("Backend: %s", "MOCK" if USE_MOCK else f"LIVE ({STATION_HOST}:{STATION_PORT})")

GRIPPER_ID = 8
GRIPPER_OPEN = 1200
GRIPPER_CLOSED = 2400

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


# ----------------------------- tools -----------------------------
@mcp.tool()
async def look(camera: str = "top") -> Image:
    """Return the latest camera frame as an image. `camera`: 'top' (overhead) or 'wrist'."""
    await _ensure()
    jpeg = await backend.get_frame(camera)
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
    """Close the gripper (clamped to calibrated range)."""
    await _ensure()
    targets = clamp_targets({GRIPPER_ID: GRIPPER_CLOSED}, await _current_ranges())
    ok = await backend.send_joint_targets(targets)
    return {"ok": ok, "sent": targets}


@mcp.tool()
async def release() -> dict:
    """Open the gripper (clamped to calibrated range)."""
    await _ensure()
    targets = clamp_targets({GRIPPER_ID: GRIPPER_OPEN}, await _current_ranges())
    ok = await backend.send_joint_targets(targets)
    return {"ok": ok, "sent": targets}


@mcp.tool()
async def home() -> dict:
    """Return the arm to its home/rest pose."""
    await _ensure()
    return {"ok": await backend.home()}


if __name__ == "__main__":
    mcp.run()  # stdio transport (for `claude mcp add`)
