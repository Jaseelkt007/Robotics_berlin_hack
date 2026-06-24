"""Does a one-shot read_from_tail stay live after the connection ages (when the cached follow stalls)?
Waits ~25s, then: pose A, ENTER; move to a DIFFERENT B, ENTER. Compares cached vs one-shot."""
import asyncio
import functools
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
import backend as bk

_bi = input


async def ainp(p=""):
    return await asyncio.get_running_loop().run_in_executor(None, functools.partial(_bi, p))


async def main():
    b = bk.LiveBackend("localhost", 8888, os.environ.get("NORMA_CORE_PATH", "../norma-core"),
                       os.environ.get("STATION_BUS_SERIAL"))
    await b.connect()
    await b.set_torque(False)
    st = b._st3215

    async def oneshot():
        qr = b.client.read_from_tail("st3215/rx", b"\x00", 60, 1, 80)
        latest = {}
        while True:
            try:
                e = await asyncio.wait_for(qr.data.get(), timeout=1.0)
            except asyncio.TimeoutError:
                break
            if e is None:
                break
            try:
                r = st.RxEnvelopeReader(memoryview(bytes(e.Data)))
                data = bytes(r.get_data())
                if len(data) >= 0x47:
                    latest[r.get_motor_id()] = struct.unpack_from("<H", data, 0x38)[0]
            except Exception:
                pass
        return [latest.get(j) for j in range(1, 8)]

    async def cached():
        st_ = await b.get_state()
        return [next((m.position for m in st_.motors if m.id == j), None) for j in range(1, 8)]

    print("aging the connection ~25s (like the real capture)...", flush=True)
    await asyncio.sleep(25)
    await ainp(">>> Pose A, hold, ENTER...")
    ca, oa = await cached(), await oneshot()
    print("  cached  A =", ca)
    print("  oneshot A =", oa)
    await ainp(">>> Move to a CLEARLY DIFFERENT B, hold, ENTER...")
    cb, ob = await cached(), await oneshot()
    print("  cached  B =", cb)
    print("  oneshot B =", ob)
    print("\nCACHED follow live? ", ca != cb)
    print("ONE-SHOT read live? ", oa != ob)


asyncio.run(main())
