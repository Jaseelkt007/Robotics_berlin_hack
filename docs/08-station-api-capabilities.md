# NormaCore Station — API Capability Reference

> Complete capability list pulled **directly from the protobuf definitions and the `station_py`
> client** in the cloned repo (`../norma-core/`, state as of 2026-06-19). This is the authoritative
> "what can the API actually do" reference. For the higher-level overview see
> [`05-normacore-station-reference.md`](./05-normacore-station-reference.md).

**Source files:**
- `protobufs/station/{drivers,commands,inference,inference_tags,startups,opts,dataset}.proto`
- `protobufs/drivers/{st3215,usbvideo,motors-mirroring,sysinfo,inferences}/*.proto`
- `software/station/shared/station_py/client.py`

---

## 1. Transport / Client API — how you talk to the Station
*(`station_py` — actual client methods)*

| Capability | Method | Direction | What it does |
|---|---|---|---|
| Connect | `new_station_client(server, logger)` | — | Open a session to the Station (TCP/WS) |
| Live subscribe | `follow(queue_id, target_queue)` | read | Stream new entries from a queue in real time |
| Read history (from offset) | `read_from_offset(queue_id, offset, limit, step, buf_size)` | read | Replay stored entries from a point |
| Read recent | `read_from_tail(queue_id, offset, limit, step, buf_size)` | read | Read the most recent N entries |
| Write one | `enqueue(queue_id, data)` | write | Push a single entry (e.g. a command) |
| Write batch | `enqueue_pack(queue_id, data[])` | write | Push multiple entries atomically |
| Send commands (helper) | `send_commands(client, [DriverCommand])` | write | Convenience wrapper for motor commands |
| Connection mgmt | `wait_ready`, `send_ping`, keep-alive | — | Readiness + heartbeat |

## 2. Subscribable data streams (queues)
*(from `QueueDataType` — everything in the Station is a queue)*

| Stream | Type | R/W | Contents |
|---|---|---|---|
| System | `QDT_SYSTEM` | read | System/meta events |
| Station commands | `QDT_STATION_COMMANDS` | write | Commands to drivers |
| Station startups | `QDT_STATION_STARTUPS` | read | Restart markers (uuid, version, git hash) |
| ST3215 serial TX | `QDT_ST3215_SERIAL_TX` | read | Raw commands sent to motors |
| ST3215 serial RX | `QDT_ST3215_SERIAL_RX` | read | Raw motor responses |
| ST3215 meta | `QDT_ST3215_META` | read | Calibration arcs / meta events |
| **ST3215 inference** | `QDT_ST3215_INFERENCE` | read | **Full motor state** (the main one) |
| FFMPEG video | `QDT_FFMPEG_VIDEO_STREAM_RX` | read | Video stream frames |
| **USB video frames** | `QDT_USB_VIDEO_FRAMES` | read | **Camera frames (JPEG/NCHW)** |
| Inference frames | `QDT_INFERENCE_FRAMES` | read | VLA frames (normvla) |
| Motor mirroring modes/rx | `QDT_MOTOR_MIRRORING_*` | read | Teleop leader/follower state |
| Inference tags | `QDT_INFERENCE_TAGS_RX` | read/write | Episode labels |

## 3. Robot motor control (ST3215)
*(`StationCommandType.STC_ST3215_COMMAND` → `st3215.Command`)*

| Capability | Command field | What it does |
|---|---|---|
| **Write register** | `write` (motor_id, address, value) | Set any register — e.g. **target position** (addr `0x2A`), torque, PID |
| Registered write | `reg_write` | Queue a write to apply later (via action) |
| **Sync write (multi-motor)** | `sync_write` (address, [motor→value]) | **Move multiple joints atomically** (key for whole-arm moves) |
| Trigger action | `action` (motor_id) | Execute a registered write |
| Reset motor | `reset` (port, motor_id) | Reset a servo |
| **Auto-calibrate** | `auto_calibrate` | Start automatic range calibration |
| Stop calibration | `stop_auto_calibrate` | Halt calibration |
| Reset calibration | `reset_calibration` | Clear calibrated ranges |
| **Freeze calibration** | `freeze_calibration` (arcs: min/max/midpoint) | Lock safe joint ranges |

## 4. Motor state & telemetry (read)
*(`st3215.InferenceState`)*

| Capability | Field | What you get |
|---|---|---|
| Per-bus info | `BusState.bus` | port, VID/PID, serial, manufacturer, baud rate |
| **Full motor register dump** | `MotorState.state` (bytes) | Position, current, temp, voltage, torque, PIDs — *all registers* |
| Calibrated range | `range_min`, `range_max`, `range_freezed` | Safe limits per motor (for clamping) |
| Last command + result | `last_command` (`CR_SUCCESS/REJECTED/FAILED/PROCESSING`) | Did the command land? |
| Auto-calibration status | `AutoCalibrationState` | status, current step / total, phase, error |
| Bus/drive signals | `ST3215SignalType` | connect/disconnect, command success/rejected/failed |
| Error detail | `ST3215Error` | overload, **overheat**, voltage, angle-limit, checksum, range, timeout, IO |

## 5. Cameras / video (read)
*(`usbvideo` + `frame`)*

| Capability | Field | What you get |
|---|---|---|
| **Camera frames** | `FramesPack.frames_data` | **JPEG** images (or `linear_data` for raw NCHW) |
| Frame format | `FrameFormat` | width, height, kind (JPEG / NCHW) |
| Frame timing | `FrameStamp` | monotonic/local timestamps + frame index |
| Camera identity | `Camera` | vendor, product, serial, unique_id, bus/device number |
| Supported formats | `CameraFormat` | fourcc, width, height, FPS |
| Device events | `RxEnvelopeType` | connected, disconnected, recording start/end, error |

> Note: **UVC USB cameras, 2D RGB, no depth** by default. IP cameras 🚧 WIP.

## 6. Teleoperation — motor mirroring
*(`STC_MOTOR_MIRRORING_COMMAND` → `motors_mirroring`)*

| Capability | Field | What it does |
|---|---|---|
| Start mirroring | `CT_START_MIRROR` (source → targets) | Leader arm drives follower arm(s) in real time |
| Stop mirroring | `CT_STOP_MIRROR` | End teleop link |
| Mirroring state | `InferenceState` | Bus modes (leader/follower) + source→target maps |

## 7. ML inference / VLA integration
*(`inference` + `normvla` + `inference_tags`)*

| Capability | Field | What you get |
|---|---|---|
| Pre-synced VLA frames | `normvla.Frame` | Joints (`position_norm`, `goal_norm`, `current_ma`, velocity, range) + **224×224 JPEG** images, time-aligned |
| Shared-memory feed | inference `shm` config | Low-latency action handoff to a policy |
| Episode tagging | `inference_tags` (add/remove) | Label inference states for training data |

## 8. Datasets & data pipeline
*(`dataset` + bins)*

| Capability | Source | What it does |
|---|---|---|
| Episodes / frames | `dataset.Frame` | goal, states, actions, raw_states/actions, image paths |
| Full lifetime history | NormFS | Every sensor reading & command stored permanently |
| Dataset assembly | `dataset-generator`, `dataset-mp4` | Build ML-ready datasets / MP4s from history |
| Parquet export | `docs/datasets/export-parquet` | Export training datasets |
| Cloud offload | `cloud-offload` (S3/MinIO/R2) | Push data to object storage |

## 9. System monitoring (read)
*(`sysinfo`)*

| Capability | Field | What you get |
|---|---|---|
| OS / host | `OsInfo`, `hostname`, `cpu_arch` | OS, kernel, architecture |
| CPU / memory | `CPU.usage`, `Memory` | Per-core usage, RAM/swap |
| Disks / network | `Disk`, `Network` | Space, I/O, interfaces, traffic |
| **Temperatures** | `TemperatureSensor` | Per-sensor value, max, critical |

---

## What OUR project actually needs (mapping)

| Our MCP tool | Built on | Station capability |
|---|---|---|
| `look()` | §5 cameras | `follow("usbvideo")` → latest JPEG frame |
| `get_state()` | §4 telemetry | `follow("st3215/inference")` → joint positions + **gripper current** (grasp check) |
| `move_to(x,y[,z])` / joint move | §3 control | `sync_write` / `write` to target-position register `0x2A` (after our IK) |
| `grasp()` / `release()` | §3 control + §4 | gripper motor `write` + current feedback to confirm hold |
| safety clamps | §4 ranges | `range_min` / `range_max` per motor |

Everything else (mirroring §6, VLA §7, datasets §8, sysinfo §9) is **bonus** — available if useful,
not required for the core demo.
