"""Backends for the Station-MCP server.

- MockBackend: works with NO hardware — synthetic camera frame + fake joint state. Use this to prove
  the MCP wiring + `look()` image path with Claude Code CLI today.
- LiveBackend: connects to a real (possibly remote) NormaCore Station via `station_py`. The methods
  that need hardware / NormaCore confirmation are marked `TODO` and raise NotImplementedError so it's
  obvious what remains to wire on-site.
"""
from __future__ import annotations

import io
import math
import os
import sys
import logging
from dataclasses import dataclass

log = logging.getLogger("station-mcp.backend")


# ----------------------------- data shapes -----------------------------
@dataclass
class MotorState:
    id: int
    position: int
    current_ma: int
    range_min: int
    range_max: int


@dataclass
class RobotState:
    bus_serial: str
    motors: list[MotorState]

    def ranges(self) -> dict[int, tuple[int, int]]:
        return {m.id: (m.range_min, m.range_max) for m in self.motors}


# ----------------------------- image helpers -----------------------------
def _placeholder_jpeg(text: str) -> bytes:
    try:
        from PIL import Image as PImage, ImageDraw
    except ImportError as e:  # keep the failure actionable
        raise RuntimeError(
            "Mock frame needs Pillow (`pip install pillow`) or set MOCK_FRAME_PATH to an image."
        ) from e
    img = PImage.new("RGB", (640, 480), (28, 30, 40))
    d = ImageDraw.Draw(img)
    d.rectangle([16, 16, 624, 464], outline=(80, 160, 255), width=3)
    d.text((40, 220), text, fill=(255, 255, 255))
    d.text((40, 250), "(MOCK MODE — no hardware)", fill=(150, 150, 170))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _ensure_jpeg(data: bytes) -> bytes:
    if data[:3] == b"\xff\xd8\xff":  # already JPEG
        return data
    try:
        from PIL import Image as PImage
        img = PImage.open(io.BytesIO(data)).convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return buf.getvalue()
    except Exception:
        return data


# ----------------------------- backends -----------------------------
class StationBackend:
    async def connect(self) -> None: ...
    async def get_frame(self, camera: str) -> bytes: ...
    async def get_state(self) -> RobotState: ...
    async def send_joint_targets(self, targets: dict[int, int]) -> bool: ...
    async def run_vla(self, instruction: str, max_tries: int) -> dict: ...
    async def home(self) -> bool: ...


class MockBackend(StationBackend):
    """No hardware. Lets us validate the MCP <-> Claude path (esp. look() returning an image)."""

    GRIPPER_ID = 8

    def __init__(self, frame_path: str | None = None):
        self.frame_path = frame_path
        self._t = 0.0

    async def connect(self) -> None:
        log.info("MockBackend ready (no hardware).")

    async def get_frame(self, camera: str = "top") -> bytes:
        if self.frame_path and os.path.exists(self.frame_path):
            with open(self.frame_path, "rb") as f:
                return _ensure_jpeg(f.read())
        return _placeholder_jpeg(f"{camera.upper()} camera")

    async def get_state(self) -> RobotState:
        # Fake 8-motor ElRobot-ish state that gently animates.
        motors = [
            MotorState(i, 2048 + int(200 * math.sin(self._t + i)), 30, 1000, 3000)
            for i in range(1, 9)
        ]
        self._t += 0.1
        return RobotState("MOCK-BUS-0001", motors)

    async def send_joint_targets(self, targets: dict[int, int]) -> bool:
        log.info("MOCK move -> %s", targets)
        return True

    async def run_vla(self, instruction: str, max_tries: int) -> dict:
        log.info("MOCK VLA <- %r (max_tries=%d)", instruction, max_tries)
        return {"ok": True, "tries": 1, "stage": 1, "note": f"MOCK SmolVLA executed: {instruction!r}"}

    async def home(self) -> bool:
        log.info("MOCK home")
        return True


class LiveBackend(StationBackend):
    """Talks to a real NormaCore Station over TCP via station_py (host can be remote)."""

    def __init__(self, host: str, port: int, norma_core_path: str):
        self.host = host
        self.port = port
        self.norma_core_path = os.path.abspath(norma_core_path)
        self.client = None

    async def connect(self) -> None:
        # Put station_py + generated protobufs on the path (from the cloned norma-core repo).
        sys.path.insert(0, self.norma_core_path)
        sys.path.insert(0, os.path.join(self.norma_core_path, "software/station/shared"))
        try:
            from station_py import new_station_client  # type: ignore
        except Exception as e:
            raise RuntimeError(
                f"Could not import station_py from {self.norma_core_path}. "
                "Set NORMA_CORE_PATH to the cloned norma-core repo, or run in mock mode."
            ) from e
        self.client = await new_station_client(f"{self.host}:{self.port}", log)
        log.info("Connected to Station at %s:%s", self.host, self.port)

    async def get_frame(self, camera: str = "top") -> bytes:
        # TODO(hardware): follow "usbvideo", parse usbvideo.RxEnvelope, return frames.frames_data[0]
        # (JPEG). Pick the right camera by serial/unique_id ("top" vs "wrist"). Confirm queue name(s).
        raise NotImplementedError("LIVE get_frame: parse usbvideo RxEnvelope -> JPEG (wire on hardware)")

    async def get_state(self) -> RobotState:
        # TODO(hardware): follow "st3215/inference", parse InferenceState; map per-motor position,
        # current, range_min/range_max.
        raise NotImplementedError("LIVE get_state: parse st3215/inference (wire on hardware)")

    async def send_joint_targets(self, targets: dict[int, int]) -> bool:
        # TODO(hardware): build an st3215 sync_write to target-position register 0x2A and send via
        # send_commands. ALWAYS clamp via safety.clamp_targets(...) before this point.
        raise NotImplementedError("LIVE send_joint_targets: st3215 sync_write (wire on hardware)")

    async def run_vla(self, instruction: str, max_tries: int) -> dict:
        # TODO(NormaCore): confirm HOW the finetuned SmolVLA is triggered (Station command? inference
        # queue? script?). Wrap that here; loop up to max_tries; report success/failure.
        raise NotImplementedError("LIVE run_vla: confirm NormaCore finetuned-SmolVLA run API")

    async def home(self) -> bool:
        raise NotImplementedError("LIVE home: send home joint targets (wire on hardware)")
