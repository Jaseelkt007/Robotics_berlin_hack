"""Grid self-test: move to home, then visit each taught hover point. Run on hardware."""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

import backend
from gridmap import GridMap
from safety import clamp_targets

HERE = os.path.dirname(os.path.abspath(__file__))


async def main():
    b = backend.LiveBackend("localhost", 8888,
                            os.environ.get("NORMA_CORE_PATH", "../norma-core"),
                            os.environ.get("STATION_BUS_SERIAL"))
    await b.connect()
    gm = GridMap(json.load(open(os.path.join(HERE, "waypoints.json"))))
    ranges = (await b.get_state()).ranges()

    home = gm.home()
    print("--> moving to HOME", flush=True)
    await b.send_joint_targets(clamp_targets(home, ranges))
    await asyncio.sleep(3.0)

    for i, (px, py) in enumerate(gm.grid_pixels()):
        j, ext = gm.interp(px, py, "hover")
        await b.send_joint_targets(clamp_targets(j, ranges))
        # wait until the arm actually stops moving (up to 6s), then measure
        prev = None
        for _ in range(24):
            await asyncio.sleep(0.25)
            pos = {mm.id: mm.position for mm in (await b.get_state()).motors}
            if prev is not None and max(abs(pos[k] - prev[k]) for k in pos) < 5:
                break
            prev = pos
        err = max(abs(pos.get(mid, 0) - v) for mid, v in j.items())
        flag = "  <-- still off after settling" if err > 60 else ""
        print(f"point {i + 1:2d}/12  px=({px:.0f},{py:.0f})  extrap={ext}  settle_err={err}{flag}", flush=True)

    print("--> back to HOME", flush=True)
    await b.send_joint_targets(clamp_targets(home, ranges))
    await asyncio.sleep(2.0)
    print("DONE", flush=True)


asyncio.run(main())
