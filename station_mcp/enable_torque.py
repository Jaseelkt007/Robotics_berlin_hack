"""Enable / disable ST3215 torque over the Station API (safe hold).

ENABLE is done safely: we first set each motor's Goal Position (0x2A) = its present position, THEN
write TorqueEnable (0x28)=1 — so the arm HOLDS its current pose instead of snapping to a stale goal.

Run (watch the arm!):
    NORMA_CORE_PATH=/mnt/d/normacore/norma-core uv run python enable_torque.py            # ON (hold)
    NORMA_CORE_PATH=/mnt/d/normacore/norma-core uv run python enable_torque.py --off       # OFF (limp)
    STATION_HOST=<ip> NORMA_CORE_PATH=... uv run python enable_torque.py                    # remote
"""
import argparse
import asyncio
import logging
import os
import struct
import sys

NC = os.path.abspath(os.environ.get("NORMA_CORE_PATH", "../norma-core"))
sys.path.insert(0, NC)
sys.path.insert(0, os.path.join(NC, "software/station/shared"))

from station_py import new_station_client, send_commands  # type: ignore
from target.gen_python.protobuf.station import commands, drivers  # type: ignore
from target.gen_python.protobuf.drivers.st3215 import st3215  # type: ignore

logging.basicConfig(level=logging.WARNING)
log = logging.getLogger("torque")

HOST = os.environ.get("STATION_HOST", "localhost")
PORT = os.environ.get("STATION_PORT", "8888")

TORQUE_ENABLE = 0x28   # 1 byte
GOAL_POSITION = 0x2A   # 2 bytes
PRESENT_POSITION = 0x38  # 2 bytes
SIGN_BIT, MAX_STEP = 0x8000, 4095


def _norm(raw: int) -> int:
    return (MAX_STEP + 1 - (raw & MAX_STEP)) & MAX_STEP if raw & SIGN_BIT else raw & MAX_STEP


def _write(bus: str, motor_id: int, addr: int, value: bytes):
    cmd = st3215.Command(
        target_bus_serial=bus,
        write=st3215.ST3215WriteCommand(motor_id=motor_id, address=addr, value=value),
    )
    return commands.DriverCommand(
        type=drivers.StationCommandType.STC_ST3215_COMMAND, body=cmd.encode()
    )


async def collect_present(client) -> dict[str, dict[int, int]]:
    """Sample a few frames → {bus_serial: {motor_id: present_position}}."""
    q: asyncio.Queue = asyncio.Queue()
    client.follow("st3215/inference", q)
    out: dict[str, dict[int, int]] = {}
    for _ in range(15):
        try:
            entry = await asyncio.wait_for(q.get(), timeout=2.0)
        except asyncio.TimeoutError:
            break
        if entry is None:
            break
        r = st3215.InferenceStateReader(memoryview(bytes(entry.Data)))
        for bus in r.get_buses():
            bi = bus.get_bus()
            if not bi:
                continue
            serial = bi.get_serial_number()
            d = out.setdefault(serial, {})
            for mo in bus.get_motors():
                sb = bytes(mo.get_state())
                if len(sb) >= PRESENT_POSITION + 2:
                    d[mo.get_id()] = _norm(struct.unpack_from("<H", sb, PRESENT_POSITION)[0])
        if out and all(len(v) >= 8 for v in out.values()):
            break
    return out


async def main(turn_on: bool) -> None:
    client = await new_station_client(f"{HOST}:{PORT}", log)
    motors = await collect_present(client)
    if not motors:
        print("No motor state — is Station running + bus connected?")
        return

    if turn_on:
        # 1) goal = present (so it holds, no snap)
        hold = [_write(bus, mid, GOAL_POSITION, int(pos).to_bytes(2, "little"))
                for bus, mp in motors.items() for mid, pos in mp.items()]
        await send_commands(client, hold)
        await asyncio.sleep(0.3)
        # 2) torque on
        en = [_write(bus, mid, TORQUE_ENABLE, b"\x01")
              for bus, mp in motors.items() for mid in mp]
        await send_commands(client, en)
        n = sum(len(v) for v in motors.values())
        print(f"✅ torque ENABLED on {n} motor(s) — arm now holds its pose. Verify: check_torque.py")
    else:
        off = [_write(bus, mid, TORQUE_ENABLE, b"\x00")
               for bus, mp in motors.items() for mid in mp]
        await send_commands(client, off)
        n = sum(len(v) for v in motors.values())
        print(f"⚠️  torque DISABLED on {n} motor(s) — arm goes LIMP (support it!).")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--off", action="store_true", help="disable torque (arm goes limp)")
    a = ap.parse_args()
    asyncio.run(main(turn_on=not a.off))
