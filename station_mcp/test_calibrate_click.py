"""Test calibrate.py's pixel-picker server + merge (no hardware). Run: python test_calibrate_click.py"""
import json
import os
import tempfile
import threading
import urllib.request
from http.server import ThreadingHTTPServer

import calibrate

d = tempfile.mkdtemp()
calibrate.PARTIAL = os.path.join(d, "partial.json")
calibrate.FRAMES_DIR = os.path.join(d, "frames")
calibrate.FINAL = os.path.join(d, "waypoints.json")
os.makedirs(calibrate.FRAMES_DIR)
for nm in ("p0.jpg", "p1.jpg"):
    with open(os.path.join(calibrate.FRAMES_DIR, nm), "wb") as f:
        f.write(b"\xff\xd8\xff\xe0fakejpeg")

partial = {
    "version": 1, "arm_motor_ids": [1, 2, 3],
    "gripper": {"id": 8, "open_step": 1200, "closed_step": 2400, "grasp_current_threshold_ma": 250},
    "grasp_offsets": {"box": {}}, "home": {"1": 2048}, "drop_zone": {"hover": {"1": 2000}, "grasp": {"1": 2050}},
    "nudge": {"default_step_px": 25},
    "grid": [
        {"id": "p0", "pixel": None, "frame": "calib_frames/p0.jpg", "grasp": {"1": 1600}, "hover_delta": {"1": 0}},
        {"id": "p1", "pixel": None, "frame": "calib_frames/p1.jpg", "grasp": {"1": 2400}, "hover_delta": {"1": 0}},
    ],
}
with open(calibrate.PARTIAL, "w") as f:
    json.dump(partial, f)


def post(url, obj):
    req = urllib.request.Request(url, data=json.dumps(obj).encode(), method="POST")
    return json.load(urllib.request.urlopen(req))


srv = ThreadingHTTPServer(("127.0.0.1", 0), calibrate.ClickHandler)
port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{port}"

points = json.load(urllib.request.urlopen(base + "/api/points"))
assert len(points) == 2 and points[0]["url"] == "/frame/p0.jpg", points
assert points[0]["pixel"] is None
print("api/points:", points)

frame = urllib.request.urlopen(base + "/frame/p0.jpg").read()
assert frame.startswith(b"\xff\xd8\xff"), "frame should serve jpeg bytes"

res = post(base + "/api/save", {"p0": [120, 90], "p1": [500, 300]})
assert res["ok"] and res["count"] == 2 and res["total"] == 2, res
print("api/save:", res)

with open(calibrate.FINAL) as f:
    final = json.load(f)
assert final["grid"][0]["pixel"] == [120, 90], final["grid"][0]
assert final["grid"][1]["pixel"] == [500, 300]
assert "frame" not in final["grid"][0], "frame key should be dropped on save"

# the saved file must be loadable by the real GridMap (2 pts loads; >=3 needed for ready)
from gridmap import GridMap
gm = GridMap(final)
assert len(gm.grid_pixels()) == 2 and gm.ready is False  # ready needs >=3 taught points

srv.shutdown()
print("\nALL CALIBRATE CLICK TESTS PASSED")
