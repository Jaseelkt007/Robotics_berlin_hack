"""Manual pick driver (I act as the brain). Stages:
  pick.py hover <px> <py>     -> open jaws, move above pixel, recapture top
  pick.py grasp <px> <py>     -> descend to grasp height (box offset), close + verify
  pick.py lift  <px> <py>     -> raise back to hover at that pixel
  pick.py deliver             -> go to drop-zone hover
  pick.py release             -> open jaws
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
import backend as bk
import overlay
from gridmap import GridMap
from safety import clamp_targets

HERE = os.path.dirname(os.path.abspath(__file__))


async def settle(b, target, timeout=6.0):
    prev = None
    for _ in range(int(timeout / 0.25)):
        await asyncio.sleep(0.25)
        pos = {m.id: m.position for m in (await b.get_state()).motors}
        if prev is not None and max(abs(pos[k] - prev[k]) for k in pos) < 5:
            break
        prev = pos
    return pos


async def move_pixel(b, gm, ranges, px, py, height, oclass=""):
    j, ext = gm.interp(px, py, height)
    if height == "grasp" and oclass:
        for mid, d in gm.grasp_offset(oclass).items():
            j[mid] = j.get(mid, 0) + d
    await b.send_joint_targets(clamp_targets(j, ranges))
    await settle(b, j)
    return ext


async def main():
    cmd = sys.argv[1]
    b = bk.LiveBackend("localhost", 8888, os.environ.get("NORMA_CORE_PATH", "../norma-core"),
                       os.environ.get("STATION_BUS_SERIAL"))
    await b.connect()
    ranges = (await b.get_state()).ranges()
    gm = GridMap(json.load(open(os.path.join(HERE, "waypoints.json"))))
    g = gm.gripper()

    if cmd == "hover":
        px, py = float(sys.argv[2]), float(sys.argv[3])
        await b.send_joint_targets({8: g["open_step"]})  # open
        ext = await move_pixel(b, gm, ranges, px, py, "hover")
        jpeg = await b.get_frame("top")
        with open(os.path.join(HERE, "hover_check.jpg"), "wb") as f:
            f.write(overlay.draw_grid(jpeg, step=20))
        print(f"HOVER at ({px},{py}) done, extrapolated={ext} -> saved hover_check.jpg")

    elif cmd == "grasp":
        px, py = float(sys.argv[2]), float(sys.argv[3])
        await move_pixel(b, gm, ranges, px, py, "grasp", "box")
        res = await b.grasp_with_verify(g["closed_step"], g["open_step"], g["grasp_current_threshold_ma"])
        print("GRASP:", res)

    elif cmd == "lift":
        px, py = float(sys.argv[2]), float(sys.argv[3])
        await move_pixel(b, gm, ranges, px, py, "hover")
        print("LIFTED to hover")

    elif cmd == "deliver":
        dz = gm.drop_zone("hover")
        await b.send_joint_targets(clamp_targets(dz, ranges))
        await settle(b, dz)
        print("DELIVERED to drop-zone hover")

    elif cmd == "release":
        await b.send_joint_targets({8: g["open_step"]})
        await asyncio.sleep(1.0)
        print("RELEASED")

    elif cmd == "probe":
        # go to GRASP height at a pixel WITHOUT closing; capture top. At table level the tip should
        # appear at the target pixel if the pixel->joint grid + camera are still consistent.
        px, py = float(sys.argv[2]), float(sys.argv[3])
        await b.send_joint_targets({8: g["open_step"]})
        await move_pixel(b, gm, ranges, px, py, "grasp")
        jpeg = await b.get_frame("top")
        with open(os.path.join(HERE, "probe.jpg"), "wb") as f:
            f.write(overlay.draw_grid(jpeg, step=20))
        print(f"PROBE grasp-height at pixel ({px},{py}) -> probe.jpg (tip should be at that pixel)")

    elif cmd == "park":
        await b.send_joint_targets({8: g["open_step"]})  # open
        h = gm.home()
        await b.send_joint_targets(clamp_targets(h, ranges))
        await settle(b, h)
        top = await b.get_frame("top")
        wrist = await b.get_frame("wrist")
        with open(os.path.join(HERE, "look_top.jpg"), "wb") as f:
            f.write(overlay.draw_grid(top, step=20))
        with open(os.path.join(HERE, "look_wrist.jpg"), "wb") as f:
            f.write(wrist)
        print("PARKED at home, jaws open -> look_top.jpg / look_wrist.jpg")


asyncio.run(main())
