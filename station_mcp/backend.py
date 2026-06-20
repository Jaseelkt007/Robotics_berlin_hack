"""Backends for the Station-MCP server.

- MockBackend: works with NO hardware — synthetic camera frame + fake joint state. Use this to prove
  the MCP wiring + `look()` image path with Claude Code CLI today.
- LiveBackend: connects to a real (possibly remote) NormaCore Station via `station_py`. The methods
  that need hardware / NormaCore confirmation are marked `TODO` and raise NotImplementedError so it's
  obvious what remains to wire on-site.
"""
from __future__ import annotations

import asyncio
import io
import math
import os
import struct
import sys
import logging
from dataclasses import dataclass

# sibling import works regardless of the launcher's cwd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from safety import clamp_targets  # noqa: E402

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


# ----------------------------- ST3215 register parsing -----------------------------
# Present-position (2B LE) and present-current (2B LE) live in the raw motor state dump.
_POS_ADDR, _CUR_ADDR = 0x38, 0x45
_MAX_STEP, _SIGN_BIT = 4095, 0x8000
_GOAL_POSITION, _TORQUE_ENABLE = 0x2A, 0x28  # write registers (goal=2B LE, torque=1B)


def _norm_pos(raw: int) -> int:
    """Normalize a raw encoder reading (handles the sign bit), per the NormaCore examples."""
    if raw & _SIGN_BIT:
        return (_MAX_STEP + 1 - (raw & _MAX_STEP)) & _MAX_STEP
    return raw & _MAX_STEP


def _u16(buf: bytes, addr: int) -> int:
    return struct.unpack_from("<H", buf, addr)[0] if len(buf) >= addr + 2 else 0


class LiveBackend(StationBackend):
    """Talks to a real NormaCore Station over TCP via station_py (host can be remote).

    Background `follow` tasks keep the latest camera frame(s) and joint state in memory, so the
    on-demand MCP tools (`look`/`get_state`) return instantly. Uses the Gremlin reader API exactly
    as the repo's `example_follow.py` does.

    `send_joint_targets` / `run_vla` / `home` are the next milestone (still stubbed).
    """

    ET_FRAMES = 0   # usbvideo.RxEnvelopeType.ET_FRAMES
    FF_JPEG = 1     # frame.FrameFormatKind.FF_JPEG

    def __init__(self, host: str, port: int, norma_core_path: str):
        self.host = host
        self.port = port
        self.norma_core_path = os.path.abspath(norma_core_path)
        self.client = None
        self._st3215 = None
        self._usbvideo = None
        self._send_commands = None
        self._commands = None
        self._drivers = None
        self._torque_on: set[int] = set()  # motors we've safe-started (goal=present, then torque on)
        self._latest_state: bytes | None = None
        self._frames: dict[str, bytes] = {}   # camera key -> latest JPEG
        self._frame_order: list[str] = []      # discovery order of cameras
        self._tasks: list = []
        # optional explicit camera selection by serial/unique_id substring
        self._cam_map = {
            "top": os.environ.get("CAMERA_TOP", "").strip(),
            "wrist": os.environ.get("CAMERA_WRIST", "").strip(),
        }

    async def connect(self) -> None:
        # norma_core root -> resolves `target.gen_python.*` AND `shared.gremlin_py.*`
        sys.path.insert(0, self.norma_core_path)
        # station_py lives here
        sys.path.insert(0, os.path.join(self.norma_core_path, "software/station/shared"))
        try:
            from station_py import new_station_client, send_commands  # type: ignore
            from target.gen_python.protobuf.drivers.st3215 import st3215 as st3215_pb2  # type: ignore
            from target.gen_python.protobuf.drivers.usbvideo import usbvideo as usbvideo_pb2  # type: ignore
            from target.gen_python.protobuf.station import commands as commands_pb2, drivers as drivers_pb2  # type: ignore
        except Exception as e:
            raise RuntimeError(
                f"Could not import station_py / protobufs from {self.norma_core_path}. "
                "Set NORMA_CORE_PATH to the cloned norma-core repo, or run in mock mode."
            ) from e
        self._st3215 = st3215_pb2
        self._usbvideo = usbvideo_pb2
        self._send_commands = send_commands
        self._commands = commands_pb2
        self._drivers = drivers_pb2
        self.client = await new_station_client(f"{self.host}:{self.port}", log)
        log.info("Connected to Station at %s:%s", self.host, self.port)

        state_q: asyncio.Queue = asyncio.Queue()
        video_q: asyncio.Queue = asyncio.Queue()
        self.client.follow("st3215/inference", state_q)
        self.client.follow("usbvideo", video_q)
        self._tasks.append(asyncio.create_task(self._consume_state(state_q)))
        self._tasks.append(asyncio.create_task(self._consume_video(video_q)))

    async def _consume_state(self, q: asyncio.Queue) -> None:
        while True:
            entry = await q.get()
            if entry is None:
                break
            try:
                self._latest_state = bytes(entry.Data)
            except Exception as e:
                log.debug("state cache error: %s", e)

    async def _consume_video(self, q: asyncio.Queue) -> None:
        while True:
            entry = await q.get()
            if entry is None:
                break
            try:
                env = self._usbvideo.RxEnvelopeReader(memoryview(bytes(entry.Data)))
                if env.get_type() != self.ET_FRAMES:
                    continue  # device-connected / recording / error events carry no frame
                cam = env.get_camera()
                key = cam.get_unique_id() or cam.get_serial_number() or cam.get_product() or "cam0"
                data = env.get_frames().get_frames_data()
                if not data:
                    continue
                self._frames[key] = bytes(data[-1])  # newest frame in the pack (assumed JPEG)
                if key not in self._frame_order:
                    self._frame_order.append(key)
                    log.info("camera discovered: %s", key)
            except Exception as e:
                log.debug("video parse skip: %s", e)

    async def _await_first(self, predicate, what: str, timeout_s: float = 5.0) -> None:
        for _ in range(int(timeout_s / 0.1)):
            if predicate():
                return
            await asyncio.sleep(0.1)
        raise RuntimeError(f"No {what} received from Station within {timeout_s:.0f}s (is it connected?)")

    async def get_frame(self, camera: str = "top") -> bytes:
        await self._await_first(lambda: bool(self._frames), "camera frames (usbvideo)")
        want = self._cam_map.get(camera, "")
        if want:
            for key, jpeg in self._frames.items():
                if want in key:
                    return jpeg
            log.warning("camera %r mapping %r not found; using discovery order", camera, want)
        # fallback: top -> first discovered, wrist -> second (if present)
        idx = 1 if (camera == "wrist" and len(self._frame_order) > 1) else 0
        return self._frames[self._frame_order[idx]]

    async def get_state(self) -> RobotState:
        await self._await_first(lambda: self._latest_state is not None, "joint state (st3215/inference)")
        reader = self._st3215.InferenceStateReader(memoryview(self._latest_state))
        buses = reader.get_buses()
        if not buses:
            return RobotState("(no bus)", [])
        bus = buses[0]
        info = bus.get_bus()
        serial = info.get_serial_number() if info else "?"
        motors: list[MotorState] = []
        for m in bus.get_motors():
            sb = m.get_state()
            pos = cur = 0
            if sb:
                buf = bytes(sb)
                pos = _norm_pos(_u16(buf, _POS_ADDR))
                cur = _u16(buf, _CUR_ADDR)
            motors.append(MotorState(m.get_id(), pos, cur, m.get_range_min(), m.get_range_max()))
        return RobotState(serial, motors)

    def _sync_write(self, bus_serial: str, address: int, values: dict[int, bytes]):
        """Build one ST3215 sync-write DriverCommand (same register, many motors, atomic)."""
        st = self._st3215
        motors = [
            st.ST3215SyncWriteCommand_MotorWrite(motor_id=mid, value=val)
            for mid, val in values.items()
        ]
        sync = st.ST3215SyncWriteCommand(address=address, motors=motors)
        cmd = st.Command(target_bus_serial=bus_serial, sync_write=sync)
        return self._commands.DriverCommand(
            type=self._drivers.StationCommandType.STC_ST3215_COMMAND, body=cmd.encode()
        )

    async def send_joint_targets(self, targets: dict[int, int]) -> bool:
        """Move joints by sync-writing GoalPosition (0x2A) — mirrors NormaCore's run_policy.py.

        Targets are normalized encoder steps (0..4095): the same domain as get_state() positions and
        calibrated ranges. Every target is clamped to its [range_min, range_max] (defense in depth — the
        MCP tools clamp too). Torque is safe-started per motor on first use (write goal=present, then
        enable torque) so turning it on never snaps the arm. See docs/12-joint-control-plan.md.
        """
        if not targets:
            return True
        st = await self.get_state()
        bus = st.bus_serial
        present = {m.id: m.position for m in st.motors}
        safe = clamp_targets({int(k): int(v) for k, v in targets.items()}, st.ranges())
        safe = {mid: v for mid, v in safe.items() if mid in present}  # only motors actually on the bus
        if not safe:
            log.warning("send_joint_targets: no valid target motors after clamp (targets=%s)", targets)
            return False

        # First move for a given motor: hold at present, then enable torque (avoids a snap).
        new_ids = [mid for mid in safe if mid not in self._torque_on]
        if new_ids:
            hold = {mid: int(present[mid]).to_bytes(2, "little") for mid in new_ids}
            await self._send_commands(self.client, [self._sync_write(bus, _GOAL_POSITION, hold)])
            await asyncio.sleep(0.2)
            torque_on = {mid: b"\x01" for mid in new_ids}
            await self._send_commands(self.client, [self._sync_write(bus, _TORQUE_ENABLE, torque_on)])
            await asyncio.sleep(0.2)
            self._torque_on.update(new_ids)

        goals = {mid: int(v).to_bytes(2, "little") for mid, v in safe.items()}
        await self._send_commands(self.client, [self._sync_write(bus, _GOAL_POSITION, goals)])
        log.info("send_joint_targets -> %s (bus %s)", safe, bus)
        return True

    async def run_vla(self, instruction: str, max_tries: int) -> dict:
        # Stage 1 needs NormaCore's FINETUNED SmolVLA checkpoint (config.json + model.safetensors +
        # stats.safetensors) — run_policy.py requires --checkpoint; a VLA cannot run without one.
        # Wire this to their runner once we have the checkpoint path. See docs/12.
        raise NotImplementedError(
            "LIVE run_vla: needs NormaCore's finetuned SmolVLA checkpoint + trigger (Stage 1; see docs/12)"
        )

    async def home(self) -> bool:
        """Move every calibrated joint to the midpoint of its range — a safe, deterministic rest pose.

        (A hand-tuned HOME_POSE can replace the midpoint once captured on the real arm.)
        """
        st = await self.get_state()
        mid = {m.id: (m.range_min + m.range_max) // 2 for m in st.motors if m.range_max > m.range_min}
        if not mid:
            log.warning("home: no calibrated ranges in state; cannot compute a midpoint pose")
            return False
        return await self.send_joint_targets(mid)
