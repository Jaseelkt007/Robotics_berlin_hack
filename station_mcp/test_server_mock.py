"""Smoke test: drive the new MCP tools in MOCK mode against a temp waypoints file.
Run with the station_mcp venv:  .venv/bin/python test_server_mock.py
"""
import os
import json
import asyncio
import tempfile

WP = {
    "version": 1,
    "frame": {"camera": "top", "width": 640, "height": 480},
    "arm_motor_ids": [1, 2, 3, 4, 5, 6, 7],
    "gripper": {"id": 8, "open_step": 1200, "closed_step": 2400, "grasp_current_threshold_ma": 250},
    "grasp_offsets": {"box": {"2": 25}, "bottle": {"2": -90}},
    "stack": {"lift_scale": 2.5},
    "home": {str(i): 2048 for i in range(1, 8)},
    "drop_zone": {"hover": {str(i): 2000 for i in range(1, 8)}, "grasp": {str(i): 2050 for i in range(1, 8)}},
    "nudge": {"default_step_px": 25},
    "grid": [
        {"id": "a", "pixel": [100, 100], "grasp": {str(i): 1600 for i in range(1, 8)}, "hover_delta": {"2": -150}},
        {"id": "b", "pixel": [500, 100], "grasp": {str(i): 2400 for i in range(1, 8)}, "hover_delta": {"2": -150}},
        {"id": "c", "pixel": [100, 380], "grasp": {str(i): 1700 for i in range(1, 8)}, "hover_delta": {"2": -150}},
        {"id": "d", "pixel": [500, 380], "grasp": {str(i): 2300 for i in range(1, 8)}, "hover_delta": {"2": -150}},
    ],
}

fd, path = tempfile.mkstemp(suffix="_waypoints.json")
with os.fdopen(fd, "w") as f:
    json.dump(WP, f)
os.environ["MOCK"] = "1"
os.environ["WAYPOINTS_PATH"] = path

import server  # noqa: E402  (import after env is set — server reads waypoints at import time)


async def main():
    img = await server.look("top", grid=True)
    assert img.__class__.__name__ == "Image", img
    print("look(top, grid=True): ok ->", type(img).__name__)

    r = await server.move_to_pixel(300, 240, "hover", "box")
    assert r["ok"] and not r["extrapolated"], r
    print("move_to_pixel(hover):", {k: r[k] for k in ("ok", "height", "extrapolated")})

    r = await server.nudge("right")
    assert r["ok"], r
    print("nudge(right): new px =", r["px"])

    r = await server.move_to_pixel(300, 240, "grasp", "box")
    assert r["ok"], r
    print("move_to_pixel(grasp, box): sent motor2 =", r["sent"][2])

    r = await server.grasp()
    assert r["holding"] is True, r
    print("grasp():", r)

    r = await server.deliver()
    assert r["ok"], r
    print("deliver(): ok")

    r = await server.home()
    assert r["ok"], r
    print("home(): ok")

    r = await server.grid_selftest("hover", dwell_s=0.0)
    assert r["ok"] and len(r["visited"]) == 4, r
    print("grid_selftest: visited", len(r["visited"]), "points")

    # extrapolation flag fires outside the taught hull
    r = await server.move_to_pixel(620, 470, "hover")
    assert r["extrapolated"] is True, r
    print("move_to_pixel outside hull: extrapolated =", r["extrapolated"])

    r = await server.push(300, 240, "left", 40)
    assert r["ok"] and r["to"] == [260, 240], r
    print("push(left): ", {k: r[k] for k in ("ok", "from", "to")})

    r = await server.wave(2)
    assert r["ok"] and r["cycles"] == 2, r
    print("wave():", r)

    r = await server.drag(300, 240, "box")
    assert r["ok"] and r["to"] == [300, 240] and r["released"], r
    print("drag():", {k: r[k] for k in ("ok", "to", "released")})

    # stack "height" raises the grasp pose by lift_scale * hover_delta
    grasp_j, _ = server._grid.interp(300, 240, "grasp")
    stack_j, _ = server._grid.interp(300, 240, "stack", lift_scale=2.5)
    assert stack_j[2] == grasp_j[2] + round(2.5 * -150), (grasp_j[2], stack_j[2])
    print("interp(stack): motor2", grasp_j[2], "->", stack_j[2])

    r = await server.stack_on(300, 240, "box")
    assert r["ok"] and r["on"] == [300, 240] and r["released"], r
    print("stack_on():", {k: r[k] for k in ("ok", "on", "released", "lift_scale")})

    print("\nALL SERVER MOCK TESTS PASSED")


asyncio.run(main())
os.unlink(path)
