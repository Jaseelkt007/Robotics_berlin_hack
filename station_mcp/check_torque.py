"""Check TorqueEnable (ST3215 register 0x28) per motor from the st3215/inference stream.

A single inference frame doesn't always carry the full register dump for every motor, so we sample a
few frames and keep the latest valid reading per motor. Exits cleanly once all motors are seen.

Run:
    NORMA_CORE_PATH=/mnt/d/normacore/norma-core uv run python check_torque.py
    STATION_HOST=<ip> NORMA_CORE_PATH=... uv run python check_torque.py     # remote Station
"""
import asyncio
import logging
import os
import sys

NC = os.path.abspath(os.environ.get("NORMA_CORE_PATH", "../norma-core"))
sys.path.insert(0, NC)
sys.path.insert(0, os.path.join(NC, "software/station/shared"))

from station_py import new_station_client  # type: ignore
from target.gen_python.protobuf.drivers.st3215 import st3215  # type: ignore

logging.basicConfig(level=logging.WARNING)
log = logging.getLogger("torque")

HOST = os.environ.get("STATION_HOST", "localhost")
PORT = os.environ.get("STATION_PORT", "8888")
TORQUE_ENABLE = 0x28          # RamRegister::TorqueEnable (1 byte): 1=ON, 0=OFF
MAX_FRAMES = 15


async def main() -> None:
    client = await new_station_client(f"{HOST}:{PORT}", log)
    q: asyncio.Queue = asyncio.Queue()
    client.follow("st3215/inference", q)

    torque: dict[int, int] = {}
    bus_serial = "?"
    for _ in range(MAX_FRAMES):
        try:
            entry = await asyncio.wait_for(q.get(), timeout=2.0)
        except asyncio.TimeoutError:
            break
        if entry is None:
            break
        r = st3215.InferenceStateReader(memoryview(bytes(entry.Data)))
        for bus in r.get_buses():
            bi = bus.get_bus()
            if bi:
                bus_serial = bi.get_serial_number()
            for mo in bus.get_motors():
                sb = bytes(mo.get_state())
                if len(sb) > TORQUE_ENABLE:
                    torque[mo.get_id()] = sb[TORQUE_ENABLE]   # keep latest valid
        if len(torque) >= 8:
            break

    print(f"bus {bus_serial}")
    if not torque:
        print("  (no motor state received — Station running? bus connected?)")
        return
    on = sum(1 for v in torque.values() if v == 1)
    for mid in sorted(torque):
        v = torque[mid]
        print(f"  motor {mid}: torque {'ON ' if v == 1 else 'OFF'} (reg0x28={v})")
    print(f"summary: {on}/{len(torque)} motors have torque ENABLED")


if __name__ == "__main__":
    asyncio.run(main())
