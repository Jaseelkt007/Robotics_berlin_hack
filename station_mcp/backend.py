"""Backends for the Station-MCP server.

- MockBackend: works with NO hardware — synthetic camera frame + fake joint state. Use this to prove
  the MCP wiring + `look()` image path with Claude Code CLI today.
- LiveBackend: connects to a real (possibly remote) NormaCore Station via `station_py`. The methods
  that need hardware / NormaCore confirmation are marked `TODO` and raise NotImplementedError so it's
  obvious what remains to wire on-site.
"""
from __future__ import annotations

import asyncio
import glob
import io
import math
import os
import struct
import sys
import time
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
    async def set_torque(self, on: bool, motor_ids: list[int] | None = None) -> bool: ...
    async def grasp_with_verify(self, closed_step: int, open_step: int, current_threshold_ma: int,
                                gripper_id: int = 8, settle_s: float = 0.6) -> dict: ...
    async def run_vla(self, instruction: str, max_tries: int) -> dict: ...
    async def home(self, pose: dict[int, int] | None = None) -> bool: ...


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

    async def set_torque(self, on: bool, motor_ids: list[int] | None = None) -> bool:
        log.info("MOCK set_torque(on=%s, motors=%s)", on, motor_ids)
        return True

    async def grasp_with_verify(self, closed_step: int, open_step: int, current_threshold_ma: int,
                                gripper_id: int = 8, settle_s: float = 0.6) -> dict:
        # Pretend the jaws stalled short of full close with elevated current -> "holding".
        log.info("MOCK grasp_with_verify(closed=%s)", closed_step)
        return {"ok": True, "holding": True, "current_ma": current_threshold_ma + 50,
                "position": closed_step - (GRIPPER_SLACK + 60)}

    async def run_vla(self, instruction: str, max_tries: int) -> dict:
        log.info("MOCK VLA <- %r (max_tries=%d)", instruction, max_tries)
        return {"ok": True, "tries": 1, "stage": 1, "note": f"MOCK SmolVLA executed: {instruction!r}"}

    async def home(self, pose: dict[int, int] | None = None) -> bool:
        log.info("MOCK home (pose=%s)", "taught" if pose else "midpoint")
        return True


# ----------------------------- ST3215 register parsing -----------------------------
# Present-position (2B LE) and present-current (2B LE) live in the raw motor state dump.
_POS_ADDR, _CUR_ADDR = 0x38, 0x45
_MAX_STEP, _SIGN_BIT = 4095, 0x8000
_GOAL_POSITION, _TORQUE_ENABLE = 0x2A, 0x28  # write registers (goal=2B LE, torque=1B)
_STATE_LEN = 0x47  # full per-motor register buffer (71 bytes); shorter = partial discovery entry
GRIPPER_SLACK = 40  # steps; a close that stalls >this far short of closed_step implies an object


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

    def __init__(self, host: str, port: int, norma_core_path: str, target_bus: str | None = None):
        self.host = host
        self.port = port
        self.norma_core_path = os.path.abspath(norma_core_path)
        self.target_bus = (target_bus or "").strip() or None  # pin which bus/arm to read+command
        self.client = None
        self._st3215 = None
        self._usbvideo = None
        self._send_commands = None
        self._commands = None
        self._drivers = None
        self._torque_on: set[int] = set()  # motors we've safe-started (goal=present, then torque on)
        self._latest_state: bytes | None = None
        self._motor_state: "dict[str, dict[int, MotorState]]" = {}  # accumulated per-bus per-motor state
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
        rx_q: asyncio.Queue = asyncio.Queue()
        video_q: asyncio.Queue = asyncio.Queue()
        self.client.follow("st3215/inference", state_q)  # calibrated RANGES (static; freezes when idle)
        self.client.follow("st3215/rx", rx_q)            # LIVE present position/current (works torque-off)
        # Cameras publish to per-camera queues `usbvideo/<md5(camera_unique_id)>` (see norma-core
        # usbvideo/src/pipeline.rs generate_queue_id) — NOT a single "usbvideo" queue. Discover the
        # live ones and follow each into the same consumer.
        video_ids = self._discover_video_queue_ids()
        if video_ids:
            for qid in video_ids:
                self.client.follow(qid, video_q)
            log.info("following %d camera queue(s): %s", len(video_ids), video_ids)
        else:
            self.client.follow("usbvideo", video_q)  # fallback (usually empty)
            log.warning("no usbvideo/<hash> camera queues found; set STATION_DATA_DIR to the "
                        "station's data dir so look() can get frames")
        self._tasks.append(asyncio.create_task(self._consume_state(state_q)))
        self._tasks.append(asyncio.create_task(self._consume_rx(rx_q)))
        self._tasks.append(asyncio.create_task(self._consume_video(video_q)))
        await self._warmup_state()

    def _discover_video_queue_ids(self, max_age_s: float = 180.0) -> list[str]:
        """Find live `usbvideo/<hash>` queues by scanning the station data dir.

        The queue id is `usbvideo/{md5(camera_unique_id)}`; we can't list queues over the protocol,
        so we read the station's on-disk queue dirs (localhost). Prefers recently-written queues so
        stale dirs from past sessions are ignored. Override the search root with STATION_DATA_DIR.
        """
        roots = [
            os.environ.get("STATION_DATA_DIR", "").strip(),
            os.path.join(self.norma_core_path, "..", "..", "station_data"),
            os.path.join(self.norma_core_path, "..", "station_data"),
            os.path.join(os.getcwd(), "station_data"),
        ]
        found: list[str] = []
        for root in roots:
            if not root or not os.path.isdir(root):
                continue
            for d in glob.glob(os.path.join(root, "*", "usbvideo", "*")):
                name = os.path.basename(d)
                if len(name) == 32 and all(c in "0123456789abcdef" for c in name) and os.path.isdir(d):
                    found.append(d)
            if found:
                break
        if not found:
            return []

        now = time.time()

        def age(d: str) -> float:
            times = [os.path.getmtime(d)]
            for sub in ("wal", "store"):
                p = os.path.join(d, sub)
                if os.path.isdir(p):
                    for f in os.listdir(p):
                        try:
                            times.append(os.path.getmtime(os.path.join(p, f)))
                        except OSError:
                            pass
            return now - max(times)

        live = [d for d in found if age(d) <= max_age_s]
        use = live if live else found
        return sorted({"usbvideo/" + os.path.basename(d) for d in use})

    async def _consume_state(self, q: asyncio.Queue) -> None:
        while True:
            entry = await q.get()
            if entry is None:
                break
            try:
                raw = bytes(entry.Data)
                self._latest_state = raw
                # inference is authoritative only for calibrated RANGES; live position/current come
                # from st3215/rx (inference freezes when torque is off). Update ranges, keep rx position.
                for serial, motors in self._parse_buses(raw).items():
                    slot = self._motor_state.setdefault(serial, {})
                    for mid, m in motors.items():
                        if mid in slot:
                            slot[mid].range_min = m.range_min
                            slot[mid].range_max = m.range_max
                        else:
                            slot[mid] = m
            except Exception as e:
                log.debug("state cache error: %s", e)

    async def _consume_rx(self, q: asyncio.Queue) -> None:
        """st3215/rx carries per-motor raw register reads ~continuously (even torque-off), so it is the
        LIVE source of present position/current. inference only re-publishes on triggers, so it freezes
        during torque-off hand-posing — which silently broke calibration captures."""
        while True:
            entry = await q.get()
            if entry is None:
                break
            try:
                r = self._st3215.RxEnvelopeReader(memoryview(bytes(entry.Data)))
                data = bytes(r.get_data())
                if len(data) < _STATE_LEN:
                    continue
                bus = r.get_bus()
                serial = bus.get_serial_number() if bus else None
                mid = r.get_motor_id()
                if not serial or mid == 0:
                    continue
                position = _norm_pos(_u16(data, _POS_ADDR))
                current = _u16(data, _CUR_ADDR)
                slot = self._motor_state.setdefault(serial, {})
                if mid in slot:
                    slot[mid].position = position
                    slot[mid].current_ma = current
                else:
                    slot[mid] = MotorState(mid, position, current, 0, _MAX_STEP)
                self._rx_count = getattr(self, "_rx_count", 0) + 1
            except Exception as e:
                log.debug("rx cache error: %s", e)

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
                # The C270 over usbip emits occasional corrupt JPEGs. Keep the newest STRUCTURALLY
                # VALID frame (SOI..EOI markers); if the whole pack is bad, keep the last good one.
                jpeg = None
                for cand in reversed(data):
                    b = bytes(cand)
                    if len(b) > 4 and b[:2] == b"\xff\xd8" and b[-2:] == b"\xff\xd9":
                        jpeg = b
                        break
                if jpeg is None:
                    continue
                self._frames[key] = jpeg
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

    def _parse_buses(self, raw: bytes) -> "dict[str, dict[int, MotorState]]":
        """Aggregate motors per bus-serial. One bus can appear multiple times in a frame (a partial
        discovery entry with empty state + a full entry); keep only motors with a full register dump."""
        reader = self._st3215.InferenceStateReader(memoryview(raw))
        by_bus: dict[str, dict[int, MotorState]] = {}
        for bus in reader.get_buses():
            info = bus.get_bus()
            serial = info.get_serial_number() if info else "?"
            slot = by_bus.setdefault(serial, {})
            for m in bus.get_motors():
                sb = bytes(m.get_state())
                if len(sb) < _STATE_LEN:
                    continue  # partial entry — no register dump yet
                slot[m.get_id()] = MotorState(
                    m.get_id(), _norm_pos(_u16(sb, _POS_ADDR)), _u16(sb, _CUR_ADDR),
                    m.get_range_min(), m.get_range_max(),
                )
        return {se: ms for se, ms in by_bus.items() if ms}

    def _select_bus(self, by_bus: "dict[str, dict[int, MotorState]]") -> str:
        """Pick the arm to read/command: pinned STATION_BUS_SERIAL if present, else the bus with the
        most CALIBRATED motors (range_min < range_max), then the most motors."""
        if self.target_bus and self.target_bus in by_bus:
            return self.target_bus

        def score(item):
            _, ms = item
            calibrated = sum(1 for m in ms.values() if m.range_max > m.range_min)
            return (calibrated, len(ms))

        return max(by_bus.items(), key=score)[0]

    async def _warmup_state(self, settle_s: float = 1.5, max_s: float = 6.0) -> None:
        # Motor frames are per-motor incremental; let the accumulator fill until the selected bus
        # motor count holds steady for settle_s (all joints reported), capped at max_s.
        stable_needed = int(settle_s / 0.05)
        prev, stable = -1, 0
        for _ in range(int(max_s / 0.05)):
            best = 0
            if self._motor_state:
                best = len(self._motor_state.get(self._select_bus(self._motor_state), {}))
            if best > 0 and best == prev:
                stable += 1
                if stable >= stable_needed:
                    break
            else:
                stable = 0
            prev = best
            await asyncio.sleep(0.05)
        if self._motor_state:
            serial = self._select_bus(self._motor_state)
            log.info("state warmup: bus %s, %d motors", serial, len(self._motor_state[serial]))

    async def get_state(self) -> RobotState:
        await self._await_first(lambda: bool(self._motor_state), "joint state (st3215/inference)")
        serial = self._select_bus(self._motor_state)
        motors = sorted(self._motor_state[serial].values(), key=lambda m: m.id)
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

    async def set_torque(self, on: bool, motor_ids: list[int] | None = None) -> bool:
        """Enable/disable torque on motors (reg 0x28). Enabling safe-starts (goal=present first) so
        the arm never snaps; disabling lets `calibrate.py` hand-pose the arm limp.
        """
        st = await self.get_state()
        bus = st.bus_serial
        present = {m.id: m.position for m in st.motors}
        ids = [i for i in (motor_ids if motor_ids is not None else present.keys()) if i in present]
        if not ids:
            log.warning("set_torque: no valid motors (requested=%s)", motor_ids)
            return False
        if on:
            hold = {mid: int(present[mid]).to_bytes(2, "little") for mid in ids}
            await self._send_commands(self.client, [self._sync_write(bus, _GOAL_POSITION, hold)])
            await asyncio.sleep(0.2)
            await self._send_commands(self.client, [self._sync_write(bus, _TORQUE_ENABLE, {mid: b"\x01" for mid in ids})])
            self._torque_on.update(ids)
        else:
            await self._send_commands(self.client, [self._sync_write(bus, _TORQUE_ENABLE, {mid: b"\x00" for mid in ids})])
            self._torque_on.difference_update(ids)
        log.info("set_torque(on=%s) -> motors %s (bus %s)", on, ids, bus)
        return True

    async def grasp_with_verify(self, closed_step: int, open_step: int, current_threshold_ma: int,
                                gripper_id: int = 8, settle_s: float = 0.6) -> dict:
        """Close the gripper, then decide if something is held from motor feedback.

        A grasp on an object stalls the jaws SHORT of `closed_step` (position gap) AND raises current.
        An empty close reaches `closed_step` with low current. We require BOTH signals (conservative —
        a false "holding" that lifts nothing looks broken on stage; a false "empty" just retries).
        """
        await self.send_joint_targets({gripper_id: closed_step})
        direction = 1 if closed_step >= open_step else -1
        current_ma, position = 0, closed_step
        for _ in range(max(1, int(settle_s / 0.1))):
            await asyncio.sleep(0.1)
            st = await self.get_state()
            m = next((mm for mm in st.motors if mm.id == gripper_id), None)
            if m is not None:
                current_ma, position = m.current_ma, m.position
        stopped_short = (closed_step - position) * direction > GRIPPER_SLACK
        current_ok = current_threshold_ma <= 0 or current_ma >= current_threshold_ma
        holding = stopped_short and current_ok
        log.info("grasp_with_verify: pos=%s (short=%s) cur=%smA (ok=%s) -> holding=%s",
                 position, stopped_short, current_ma, current_ok, holding)
        return {"ok": True, "holding": holding, "current_ma": current_ma, "position": position}

    async def run_vla(self, instruction: str, max_tries: int) -> dict:
        # Stage 1 needs NormaCore's FINETUNED SmolVLA checkpoint (config.json + model.safetensors +
        # stats.safetensors) — run_policy.py requires --checkpoint; a VLA cannot run without one.
        # Wire this to their runner once we have the checkpoint path. See docs/12.
        raise NotImplementedError(
            "LIVE run_vla: needs NormaCore's finetuned SmolVLA checkpoint + trigger (Stage 1; see docs/12)"
        )

    async def home(self, pose: dict[int, int] | None = None) -> bool:
        """Move to a taught home pose if given (from waypoints.json), else the midpoint of each
        calibrated range. Midpoint is a safe fallback but not guaranteed useful on a 7-DoF arm —
        prefer a hand-taught `home` captured during calibration.
        """
        if pose:
            return await self.send_joint_targets(pose)
        st = await self.get_state()
        mid = {m.id: (m.range_min + m.range_max) // 2 for m in st.motors if m.range_max > m.range_min}
        if not mid:
            log.warning("home: no calibrated ranges in state; cannot compute a midpoint pose")
            return False
        return await self.send_joint_targets(mid)
