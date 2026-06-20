# NormaCore Station — Technical Reference

> Extracted from the cloned repo at `../norma-core/` (commit/state as of 2026-06-19). This is the
> ground truth for what the Station API actually exposes. Verify versions/behaviour on-site.

## What NormaCore is

A unified toolkit for physical systems. Key pieces:

| Project | Path | What it is |
|---|---|---|
| **Station** | `software/station/bin/station/` | Real-time robotics platform — data collection, inference, control. Single binary + web UI. |
| **ElRobot** | `hardware/elrobot/` | 3D-printed **7+1 DoF** arm (7 revolute joints + gripper). |
| **Parallel Jaw Gripper** | `hardware/pgripper/` | Modular gripper (~54 mm opening, ≥4 kg force). |
| **SmolVLA fine-tune** | `software/ai/smolvla_py/` | Train/deploy a SmolVLA VLA policy on the SO-101. |
| **Gremlin** | `shared/gremlin_{go,py}/` | Protobuf SDK used across the stack. |
| **station_py** | `software/station/shared/station_py/` | Python client library (what our MCP server wraps). |

## How you connect

- Station runs as a **local server**: `station --web --tcp`
  - **TCP** `:8888` (NormFS data server) · **WebSocket** `:8889` (web UI / clients)
  - Web UI at `http://localhost:8889`.
- **No API key for local access.** (The AES-256 "robot key" in the docs is for encrypting
  stored/offloaded data, not for connecting.)
- OS support: **macOS ✅, Linux ✅ (incl. Raspberry Pi ARM64), Windows 📋 planned.**
  → On Windows, run via **WSL + native host**; preferably run Station on a Pi/Mac (USB reasons).

## The API model — queues (NormFS)

Everything is a **queue** you subscribe to (`follow`) or write to (`enqueue`):

| Queue | Direction | Contents |
|---|---|---|
| `usbvideo` | read | Camera frames (**JPEG**), one per connected UVC camera. |
| `st3215/inference` | read | Full motor state @ ~100 Hz (position, current, temp, voltage, calibrated ranges). |
| `commands` | write | Motor commands (joint position targets, etc.). |
| `inference/normvla` | read | Pre-synced VLA frames (224×224 JPEG + joint state), also via shared memory. |

### Python client surface (`station_py`)
```python
client = await new_station_client("localhost", logger)   # connect
client.follow(queue_id, asyncio.Queue)                    # subscribe (e.g. "usbvideo")
await client.enqueue(queue_id, bytes)                     # write (e.g. "commands")
await send_commands(client, [DriverCommand, ...])         # helper for motor commands
```

## Cameras

- **UVC USB cameras only** (IP cameras 🚧 WIP). → plan on a **USB webcam**, not a phone/IP cam.
- **2D RGB, no depth** by default.
- Frames arrive as **JPEG** on the `usbvideo` queue.
- Hardware has **`gripper_camera_mounts`** → **eye-in-hand** (wrist camera) is a supported, likely-
  default config. Multiple cameras are supported.

## Robot control — IMPORTANT: joint-level only

- Control is **per-motor position** (ST3215 servos, **0–4095 steps**, ~0.088°/step).
- Target-position register `0x2A`; present-position `0x38`; current `0x45`; temp `0x3F`; voltage `0x3E`.
- Supports single writes and **atomic multi-motor sync writes**.
- **There is NO Cartesian / "move to (x,y,z)" command and NO inverse kinematics in the Station.**
  → Converting a target pose to joint angles is **our job** (IK — see below).
- Calibrated per-motor ranges (`range_min`/`range_max`) are available in the state stream → use for
  safe clamping.

## State feedback (for verification & servoing)

`st3215/inference` gives, per motor: position, **current (mA)**, temperature, voltage, calibrated
range. → Gripper **current + position** is a reliable "did I grasp something?" signal (jaws fully
closed = empty; stopped partway + current rise = holding).

## Robot model & kinematics — what ships

- ✅ **URDF files ship** (full joints + STL meshes):
  - `hardware/elrobot/simulation/elrobot_follower.urdf` (7 revolute `rev_motor_01..07` + gripper)
  - `software/station/clients/station-viewer/public/devices/elrobot/elrobot_follower.urdf`
  - SO-101 follower + leader URDFs under `.../devices/so101/`
- ✅ **Forward kinematics already used** by the station-viewer for 3D rendering (joint angles → pose).
- ❌ **No IK solver ships.** → We add IK with **`ikpy`** or **PyBullet**, loading the provided URDF.
  (URDF + meshes is exactly what those libraries need.)

## Hardware specs (from repo docs)

| Item | Spec |
|---|---|
| ElRobot | **7 revolute joints + 1 gripper** (8 ST3215 motors); reach ~430 mm; ~800 g; ~$220/arm. |
| SO-101 | 6-DoF arm (ST3215), modular parallel-jaw gripper. |
| Gripper (pgripper) | ~**54 mm** total opening, ≥**4 kg** closing force, 1 ST3215 motor. |
| Motors (ST3215) | Serial (Dynamixel-like); 0–4095 step position; current/temp/voltage telemetry. |
| Leader vs follower | Leader = back-drivable (7.4V, teleop); follower = high-torque (12V). |

## SmolVLA (the provided VLA) — what it is

- A **Vision-Language-Action** model: image + state + instruction → **low-level joint actions**,
  end-to-end. Small (~450M params), built for real-time control.
- Trained by **imitation learning** (teleoperate → collect dataset → fine-tune). `smolvla_py` is the
  fine-tune/deploy harness.
- **Our PRIMARY executor (Stage 1):** NormaCore provides a **finetuned SmolVLA** that we call **as-is**
  (no training by us initially). Claude decomposes the task, issues the VLA instruction, and the robot
  retries **N** times. **Fine-tuning on our objects is a conditional later step** if testing shows our
  objects aren't handled. Classical **ArUco-pose + IK** is the Stage-2 fallback. See `06` D8 and `10`.

## Examples worth reading in the repo

- `software/station/examples/so101-autocalibration-py/` — state subscription + commands.
- `software/station/examples/st3215-remote-teleop-py/` — leader→follower joint mirroring + position
  normalization.
- `software/station/shared/station_py/` — the client we wrap (`new_station_client`, `follow`,
  `enqueue`, `send_commands`).
- `software/ai/smolvla_py/` — the VLA policy (`predict_action_chunk`).
