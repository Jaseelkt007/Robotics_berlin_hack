#!/usr/bin/env python3
"""Teach the pixel->joint grid for the reliable track. Run on the robot laptop, Station live.

Two phases:

  1) CAPTURE (hardware + terminal) — hand-pose the arm; record joints + top-cam frames:
       STATION_HOST=<ip> NORMA_CORE_PATH=../norma-core python calibrate.py capture
     Writes  waypoints.partial.json  +  calib_frames/p*.jpg

  2) CLICK (any browser) — click the gripper tip in each captured frame:
       python calibrate.py click
     Opens http://localhost:8799 ; on Save writes  waypoints.json

Then run the MCP server (it loads waypoints.json by default) and call `grid_selftest` to confirm the
grid before grasping anything. The top camera must not move after capture, or the grid is invalid.
"""
from __future__ import annotations

import asyncio
import functools
import io
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from backend import LiveBackend  # noqa: E402

# optional .env (the same file the MCP server reads) so calibrate + server share one config
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except Exception:
    pass

_builtin_input = input


async def _ainput(prompt: str = "") -> str:
    """input() that runs off the event loop, so background tasks (the live st3215/rx state consumer)
    keep running while we wait at the prompt. A plain input() blocks the loop -> get_state() freezes."""
    return await asyncio.get_running_loop().run_in_executor(None, functools.partial(_builtin_input, prompt))


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PARTIAL = os.path.join(SCRIPT_DIR, "waypoints.partial.json")
FRAMES_DIR = os.path.join(SCRIPT_DIR, "calib_frames")
FINAL = os.environ.get("WAYPOINTS_PATH") or os.path.join(SCRIPT_DIR, "waypoints.json")
ARM_IDS = [int(x) for x in os.environ.get("ARM_MOTOR_IDS", "1,2,3,4,5,6,7").split(",")]
GRIPPER_ID = int(os.environ.get("GRIPPER_ID", "8"))
CLICK_PORT = int(os.environ.get("CALIB_PORT", "8799"))


# ----------------------------- phase 1: capture -----------------------------
def _arm_joints(state, ids) -> dict[str, int]:
    return {str(m.id): m.position for m in state.motors if m.id in ids}


def _motor_pos(state, mid) -> int:
    return next((m.position for m in state.motors if m.id == mid), 0)


async def _connect() -> "LiveBackend":
    host = os.environ.get("STATION_HOST", "").strip()
    if not host:
        sys.exit("Set STATION_HOST (and NORMA_CORE_PATH) to reach the live Station.")
    backend = LiveBackend(
        host,
        int(os.environ.get("STATION_PORT", "8888")),
        os.environ.get("NORMA_CORE_PATH", "../norma-core"),
        os.environ.get("STATION_BUS_SERIAL") or None,
    )
    print(f"Connecting to Station at {host} ...")
    await backend.connect()
    return backend


async def info() -> None:
    """List the motor buses and cameras so you can pin STATION_BUS_SERIAL / CAMERA_TOP / CAMERA_WRIST."""
    backend = await _connect()
    await backend.get_state()       # wait for joint state
    await backend.get_frame("top")  # wait for camera frames
    print("\nBUSES (pin the FOLLOWER as STATION_BUS_SERIAL):")
    for serial, motors in backend._motor_state.items():
        calib = sum(1 for m in motors.values() if m.range_max > m.range_min)
        marker = "  <- currently auto-selected" if serial == backend._select_bus(backend._motor_state) else ""
        print(f"  {serial}: {len(motors)} motors, {calib} calibrated{marker}")
    print("\nCAMERAS (set CAMERA_TOP / CAMERA_WRIST to a substring of the right id):")
    for i, key in enumerate(backend._frame_order):
        fn = f"cam_{i}.jpg"
        with open(os.path.join(SCRIPT_DIR, fn), "wb") as f:
            f.write(backend._frames[key])
        print(f"  [{i}] id={key!r}  -> saved {fn} (open it to see which view this is)")
    print("\nOpen the saved cam_*.jpg to tell which is the overhead (top) view, then set the env vars.")


async def capture() -> None:
    backend = await _connect()
    print("Releasing torque on ALL motors (incl. the gripper) so you can hand-pose it ...")
    await backend.set_torque(False)  # ALL motors incl. gripper (motor 8) — ARM_IDS-only left it locked

    os.makedirs(FRAMES_DIR, exist_ok=True)
    n = int((await _ainput("How many grid points? [12]: ")).strip() or "12")
    print("\nKEEP THE SAME GRIPPER ORIENTATION at every point (jaws aligned to a fixed table axis).")

    grid, frame_w, frame_h = [], 0, 0
    for i in range(n):
        await _ainput(f"\n[{i + 1}/{n}] Hand-pose the gripper TIP at GRASP height over a table spot, hold steady, ENTER...")
        st = await backend.get_state()
        grasp = _arm_joints(st, ARM_IDS)
        jpeg = await backend.get_frame("top")
        fname = f"p{i}.jpg"
        with open(os.path.join(FRAMES_DIR, fname), "wb") as f:
            f.write(jpeg)
        if not frame_w:
            from PIL import Image
            frame_w, frame_h = Image.open(io.BytesIO(jpeg)).size

        await _ainput("        Now lift the gripper STRAIGHT UP ~5 cm, hold steady, ENTER...")
        st2 = await backend.get_state()
        hover = _arm_joints(st2, ARM_IDS)
        hover_delta = {k: hover[k] - grasp[k] for k in grasp}
        dup = grid and grid[-1]["grasp"] == grasp
        grid.append({"id": f"p{i}", "pixel": None, "frame": f"calib_frames/{fname}",
                     "grasp": grasp, "hover_delta": hover_delta})
        if dup:
            print("        captured.  !! WARNING: IDENTICAL to the previous point — state looks stale. "
                  "Stop (Ctrl+C) and tell me; don't keep going.")
        else:
            print("        captured.")

    await _ainput("\nHand-pose the arm at the HOME / transit pose, ENTER...")
    home = _arm_joints(await backend.get_state(), ARM_IDS)
    await _ainput("Hand-pose the gripper at the DROP-ZONE HOVER height, ENTER...")
    dz_hover = _arm_joints(await backend.get_state(), ARM_IDS)
    await _ainput("Lower to the DROP-ZONE RELEASE height, ENTER...")
    dz_grasp = _arm_joints(await backend.get_state(), ARM_IDS)

    await _ainput("Open the gripper fully (by hand), ENTER...")
    g_open = _motor_pos(await backend.get_state(), GRIPPER_ID)
    await _ainput("Close the gripper on the box (by hand), ENTER...")
    g_closed = _motor_pos(await backend.get_state(), GRIPPER_ID)

    threshold = 250

    def _save(thr: int) -> None:
        wp = {
            "version": 1,
            "frame": {"camera": "top", "width": frame_w, "height": frame_h},
            "orientation_note": "all grid poses share one locked gripper orientation",
            "arm_motor_ids": ARM_IDS,
            "gripper": {"id": GRIPPER_ID, "open_step": g_open, "closed_step": g_closed,
                        "grasp_current_threshold_ma": thr},
            "grasp_offsets": {"box": {}, "bottle": {}, "cup": {}},
            "home": home,
            "drop_zone": {"hover": dz_hover, "grasp": dz_grasp},
            "nudge": {"default_step_px": 25},
            "grid": grid,
        }
        with open(PARTIAL, "w") as f:
            json.dump(wp, f, indent=2)

    # Save NOW — BEFORE any command-write, which can time out on a long-lived connection — so the
    # captured points can never be lost to a late failure.
    _save(threshold)
    print(f"\nSaved {PARTIAL} ({len(grid)} points); frames in {FRAMES_DIR}/")

    # Optional grasp-current measurement — fully non-fatal; re-saves with a tuned threshold on success.
    if (await _ainput("Measure grasp current with a powered close on the box? [y/N]: ")).strip().lower() == "y":
        try:
            await backend.set_torque(True, [GRIPPER_ID])
            await backend.send_joint_targets({GRIPPER_ID: g_closed})
            await asyncio.sleep(0.9)
            cur = next((m.current_ma for m in (await backend.get_state()).motors if m.id == GRIPPER_ID), 0)
            threshold = max(80, int(cur * 0.6))
            _save(threshold)
            print(f"        held current {cur} mA -> threshold {threshold} mA (saved)")
        except Exception as e:
            print(f"        current measurement skipped ({e or type(e).__name__}); kept default {threshold} mA")
        finally:
            try:
                await backend.set_torque(False, [GRIPPER_ID])
            except Exception:
                pass

    print("Next:  python calibrate.py click")


# ----------------------------- phase 2: click -----------------------------
CLICK_HTML = """<!doctype html><meta charset=utf-8>
<title>Grid pixel picker</title>
<style>body{font:14px system-ui;margin:16px}canvas{border:1px solid #888;cursor:crosshair;max-width:90vw}
.pt{margin:14px 0}button{font:15px system-ui;padding:8px 14px}</style>
<h2>Click the GRIPPER TIP in each frame</h2>
<p>Click where the gripper tip touched the table. Click again to correct. Then Save.</p>
<button onclick="save()">Save waypoints.json</button>
<div id=c></div>
<script>
let clicks={};
function mark(cv,img,x,y){const g=cv.getContext('2d');g.drawImage(img,0,0);
 g.strokeStyle='red';g.lineWidth=2;g.beginPath();g.arc(x,y,7,0,7);g.stroke();
 g.beginPath();g.moveTo(x-12,y);g.lineTo(x+12,y);g.moveTo(x,y-12);g.lineTo(x,y+12);g.stroke();}
async function load(){
 const pts=await (await fetch('/api/points')).json();
 const root=document.getElementById('c');
 for(const p of pts){
  const w=document.createElement('div');w.className='pt';
  const t=document.createElement('div');t.textContent=p.id+(p.pixel?` (${p.pixel[0]}, ${p.pixel[1]})`:' — not set');
  const cv=document.createElement('canvas');const img=new Image();
  img.onload=()=>{cv.width=img.width;cv.height=img.height;cv.getContext('2d').drawImage(img,0,0);
    if(p.pixel){clicks[p.id]=p.pixel;mark(cv,img,p.pixel[0],p.pixel[1]);}};
  img.src=p.url;
  cv.onclick=e=>{const r=cv.getBoundingClientRect();
    const x=Math.round((e.clientX-r.left)*cv.width/r.width);
    const y=Math.round((e.clientY-r.top)*cv.height/r.height);
    clicks[p.id]=[x,y];t.textContent=p.id+` (${x}, ${y})`;mark(cv,img,x,y);
    fetch('/api/click',{method:'POST',body:JSON.stringify({id:p.id,px:x,py:y})});};
  w.appendChild(t);w.appendChild(cv);root.appendChild(w);
 }
}
async function save(){const r=await (await fetch('/api/save',{method:'POST',body:JSON.stringify(clicks)})).json();
 alert(r.ok?`Saved ${r.path} (${r.count} of ${r.total} points have pixels)`:'Error: '+r.error);}
load();
</script>"""


def _load_partial() -> dict:
    if not os.path.exists(PARTIAL):
        sys.exit(f"No {PARTIAL} — run `python calibrate.py capture` first.")
    with open(PARTIAL) as f:
        return json.load(f)


class ClickHandler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def _send(self, code, body: bytes, ctype="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/index"):
            return self._send(200, CLICK_HTML.encode(), "text/html; charset=utf-8")
        if self.path.startswith("/frame/"):
            name = os.path.basename(self.path)
            fp = os.path.join(FRAMES_DIR, name)
            if os.path.exists(fp):
                with open(fp, "rb") as f:
                    return self._send(200, f.read(), "image/jpeg")
            return self._send(404, b'{"error":"no frame"}')
        if self.path == "/api/points":
            wp = _load_partial()
            pts = [{"id": g["id"], "url": "/frame/" + os.path.basename(g["frame"]), "pixel": g.get("pixel")}
                   for g in wp["grid"]]
            return self._send(200, json.dumps(pts).encode())
        return self._send(404, b'{"error":"not found"}')

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length) or b"{}")
        if self.path == "/api/click":
            _CLICKS[body["id"]] = [int(body["px"]), int(body["py"])]
            return self._send(200, b'{"ok":true}')
        if self.path == "/api/save":
            for k, v in body.items():  # the page posts the full map on save
                _CLICKS[k] = [int(v[0]), int(v[1])]
            wp = _load_partial()
            count = 0
            for g in wp["grid"]:
                if g["id"] in _CLICKS:
                    g["pixel"] = _CLICKS[g["id"]]
                    g.pop("frame", None)
                    count += 1
            with open(FINAL, "w") as f:
                json.dump(wp, f, indent=2)
            return self._send(200, json.dumps({"ok": True, "path": FINAL,
                                               "count": count, "total": len(wp["grid"])}).encode())
        return self._send(404, b'{"error":"not found"}')


_CLICKS: dict[str, list[int]] = {}


def click_server() -> None:
    _load_partial()  # fail fast if capture wasn't run
    srv = ThreadingHTTPServer(("0.0.0.0", CLICK_PORT), ClickHandler)
    print(f"Pixel picker: open http://localhost:{CLICK_PORT}  (Ctrl+C to stop)")
    print(f"On Save it writes {FINAL}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")


# ----------------------------- entry -----------------------------
if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "info":
        asyncio.run(info())
    elif cmd == "capture":
        asyncio.run(capture())
    elif cmd == "click":
        click_server()
    else:
        sys.exit("usage: python calibrate.py [info|capture|click]")
