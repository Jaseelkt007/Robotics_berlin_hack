# Joint Control Plan — `send_joint_targets` → `grasp` / `release` / `home`

> **Status: PLAN (not implemented).** This is the analysis + design for making the LIVE arm actually
> move. It is grounded in the real NormaCore code and our existing writers — every claim below has a
> source. Implementation is a separate step.
> Last updated: 2026-06-21.

## Why this is the keystone

On a real arm today, perception works (`look`, `get_state`) but **nothing moves**: `send_joint_targets`,
`grasp`, `release`, `home`, `move_to` are stubs (`backend.py` `LiveBackend`). Every motion primitive
flows through **one** function — `send_joint_targets`. Implement it correctly and `grasp`/`release`/`home`
become thin wrappers; `move_to` then only needs IK on top. So this is the highest-leverage unblock that
**does not depend on NormaCore's SmolVLA API** (that's the separate Stage-1 wire).

## Is it possible? Yes — confirmed against NormaCore's own code

The mechanism is exactly what NormaCore's **own SmolVLA policy runner** uses to drive the arm:

- `norma-core/software/ai/smolvla_py/scripts/run_policy.py` (~L147–166) — `build_sync_write_command(...)`
  builds an `ST3215SyncWriteCommand` to register **`0x2A` (GoalPosition)** with per-motor 2-byte
  little-endian values, and sends it via `send_commands`. This is the real, working "move the arm" path.
- Our own `station_mcp/enable_torque.py` already writes `0x2A` and `0x28` over the same API (single
  writes) — proven to land on hardware.
- Rust ground truth: `norma-core/software/drivers/st3215/src/protocol/memory.rs` defines the register
  map; `.../auto_calibrate/calibrator.rs` `set_position()` writes `GoalPosition` as `u16` LE — **no
  sign-bit on write**.

So we are mirroring a proven path, not inventing one.

## The protocol (verified facts)

**Command shape** (`target/gen_python/protobuf/drivers/st3215/st3215.py`):
- Single: `ST3215WriteCommand(motor_id, address, value: bytes)`
- **Multi (preferred): `ST3215SyncWriteCommand(address, motors=[ST3215SyncWriteCommand_MotorWrite(motor_id, value: bytes)])`** — writes one register to many motors **atomically** (all joints move together).
- Wrap: `st3215.Command(target_bus_serial=<serial>, sync_write=<cmd>)` → `DriverCommand(type=STC_ST3215_COMMAND, body=cmd.encode())` → `await send_commands(client, [driver_cmd])`.

**Registers** (`memory.rs`):
| Reg | Addr | Bytes | Use |
|---|---|---|---|
| TorqueEnable | `0x28` | 1 | 1 = servo on, 0 = limp |
| Acc | `0x29` | 1 | acceleration (optional, smoother) |
| **GoalPosition** | **`0x2A`** | **2** | **target, uint16 LE, 0–4095** |
| GoalSpeed | `0x2E` | 2 | max speed (optional, smoother) |
| PresentPosition | `0x38` | 2 | current (read; needs `_norm`) |
| PresentCurrent | `0x45` | 2 | gripper load (read; grasp confirm) |

**Encoding:** `value = int(step).to_bytes(2, "little")`, `step` clamped to `0..4095`. **No sign-bit on
write** (the `_norm`/`SIGN_BIT` logic in `enable_torque.py`/`backend.py` is for *reading* only).

**Bus serial:** required on the command. We already parse it — `RobotState.bus_serial` from `get_state()`.

## Gotchas (must handle or it won't move)

1. **Torque must be ON.** A limp motor ignores GoalPosition. Ensure `0x28 = 1` for target motors before
   (or alongside) the goal write. Safe-start pattern from `enable_torque.py`: set goal = present, then
   torque on, so it holds instead of snapping.
2. **Clamp to calibrated range.** Always clamp each target to that motor's `range_min..range_max`
   (from `get_state`) via `safety.clamp_targets()` — never write a raw value the LLM produced.
3. **Optional speed/accel.** For smooth, non-jerky motion, optionally pre-set `GoalSpeed (0x2E)` and
   `Acc (0x29)` once; the calibrator does this. Not required to move, but nicer/safer.
4. **No `action` needed.** Writing GoalPosition starts motion immediately (no registered-write/action).
5. **Sync vs single.** Use `sync_write` for multi-joint moves so joints start together; single `write`
   is fine for the gripper alone.

## Design

### `send_joint_targets(targets: dict[int, int]) -> bool` (LiveBackend)
1. `await get_state()` → `bus_serial` + per-motor `(range_min, range_max)` + error flags.
2. **Clamp** every `(motor_id → step)` to its range via `safety.clamp_targets()`; drop unknown motor ids.
3. **Safety gate:** if any targeted motor reports overload/overheat/error in state, **abort + report**
   (don't pile commands onto a faulted joint).
4. (Optional) ensure torque on for targeted motors (`0x28 = 1`).
5. Build one `ST3215SyncWriteCommand(address=0x2A, motors=[...2-byte LE...])`, wrap, `send_commands`.
6. Return `True` (optionally read back `last_command` = `CR_SUCCESS` from the next inference frame to
   confirm it landed).

### Thin wrappers
- **`home()`** → `send_joint_targets(HOME_POSE)`. `HOME_POSE` = a safe per-motor dict (mid-range, or a
  pose we capture once on the real arm). Define in config, clamp anyway.
- **`grasp()` / `release()`** → `send_joint_targets({GRIPPER_ID: CLOSED/OPEN})`, then poll `get_state()`
  gripper **`PresentCurrent`**: a rising current that then holds ⇒ object grasped; near-zero ⇒ empty.
  Confirms hold visually-independently (the skill already says "don't trust ok alone").
- **`move_to(x,y,z)`** stays Stage-2: needs **IK** (ikpy/PyBullet + URDF) to turn Cartesian → joint
  steps, then calls `send_joint_targets`. Separate task; `send_joint_targets` is its prerequisite.

### Safety layer (`safety.py`)
`clamp_targets(targets, ranges)` already exists for this. The plan keeps **all** motion behind it, so the
LLM can never command out-of-range values. Add the error-state abort (gotcha #2/#3) here or in the backend.

## What we still need before/while implementing

- **Confirm on hardware:** `HOME_POSE` values, gripper `GRIPPER_ID` (mock assumes `8`) and its
  open/closed steps, and the grasp current threshold — these are arm-specific, captured on the robot
  laptop. Until then, code is written + clamped but the constants are placeholders.
- **Torque policy:** decide whether `send_joint_targets` auto-enables torque or assumes the operator
  enabled it via `enable_torque.py`. (Proposed: auto-ensure on, safe-start.)

## Risk / confidence

**High confidence it works in code** — we mirror NormaCore's own `run_policy.py` sync-write and our
proven `enable_torque.py` writer; the encoding, register, and send path are all verified against source.
**Residual risk is hardware-only** (home pose, gripper steps, current threshold), which we tune in one
short session on the real arm. No protocol unknowns remain.

## Out of scope here

`run_vla_task` live (Stage 1) — separate, blocked on NormaCore's SmolVLA trigger API. `locate` (ArUco)
and `move_to` IK (Stage 2) — separate tasks that build *on top of* `send_joint_targets`.
