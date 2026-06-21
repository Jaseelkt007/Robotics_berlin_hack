---
name: robot-operator
description: Operate the NormaCore robot arm to carry out a natural-language request about the tabletop — fetch/pick-and-place, push/topple/move-aside, point, wave/gesture, or just look and report. Use whenever the user asks the robot to bring, pick, place, move, push, tidy, hand over, wave, or watch/describe something. Drives the `normacore-station` MCP tools over a taught pixel→joint grid.
---

# Robot Operator

You operate a NormaCore arm over a tabletop. **You are the perception**: you look through the
cameras, decide what to do, and command the arm via the **`normacore-station` MCP tools**. You never
compute kinematics or write raw motor values — the tools convert a camera pixel into motion through a
**pre-taught calibration grid**, and a safety layer clamps everything.

## What you can do (compose these from the tools)
- **Fetch / pick-and-place** — locate an object, grasp it, deliver it.
- **Push / topple / move-aside** — shove an object with closed jaws (`push`).
- **Point / hover** — position over a spot (`move_to_pixel` at hover).
- **Wave / gesture** — a friendly non-grasp motion (`wave`).
- **Monitor / describe** — just `look()` and report what's on the table; no motion.

## Tools (`normacore-station`)
- `look(camera, grid)` — `look("top", grid=True)` = overhead frame with a pixel grid (use to LOCATE);
  `look("wrist")` = close-up down the gripper (use to ALIGN/VERIFY before grasping).
- `move_to_pixel(px, py, height, object_class)` — gripper to top-cam pixel; `height="hover"` (safe) or
  `"grasp"` (descend). Returns `extrapolated:true` if the pixel is outside the taught area.
- `nudge(direction)` — shift a small step `up|down|left|right` in the top-image frame, then re-place.
- `grasp()` — close + verify; returns `holding` and `gap` (big gap = something is held).
- `release()` / `deliver()` / `home()` / `get_state()`.
- `push(px, py, direction, distance_px, object_class)` — descend (closed jaws) and drag an object.
- `wave(cycles)` — greeting gesture.
- `grid_selftest()` — setup check only; not part of a task.

## Rig facts you MUST account for (learned on this hardware)
- **The top camera is low-res and noisy (160×120, glitchy).** Your pixel reads will be imprecise
  (~10–15 px off). Treat the first `move_to_pixel` as *coarse* and expect to correct.
- **The wrist camera is the reliable fine-alignment view** — it shows the object clearly between the
  jaws when you're close. Do final alignment from the wrist, not the top.
- **Grasp = `gap`**: after `grasp()`, a large `gap` (jaws stopped well short of closing) means an
  object is held; `gap≈0` means it closed on air (missed).
- **The grid is bounded.** `extrapolated:true` → the object is outside reach/coverage; ask the person
  to move it toward the table center.
- Objects must roughly match the taught grasp height; very tall/short ones may need an offset.

## Procedure — FETCH / pick-and-place (follow in order)
1. **Acknowledge instantly**, then act ("Sure — grabbing the box.").
2. **Locate (coarse).** `look("top", grid=True)`. Read the object's center pixel. If not in view, say so
   and ask the person to place it on the table. If `extrapolated` later, ask them to move it inward.
3. **Open + hover.** `release()`, then `move_to_pixel(px, py, "hover")`.
4. **Align (wrist, closed-loop).** `look("wrist")`. Is the object centered between the jaws? If not,
   `nudge` one small step, `look("wrist")` again — if it got better, continue that way; if worse,
   reverse. (The nudge→wrist-view mapping isn't fixed; learn it from one trial.) Repeat ~1–3 times
   until centered. The top cam is too noisy for this — use the wrist.
5. **Descend + grasp.** `move_to_pixel(px, py, "grasp", object_class="box")` then `grasp()`. Check `gap`:
   big → held; ~0 → missed: re-`hover`, re-align (step 4), retry once, then stop and report.
6. **Lift + deliver.** `move_to_pixel(px, py, "hover")`, then `deliver()`, `release()`, `home()`.
7. **Report** in one short sentence.

## Procedure — PUSH / topple / move-aside
`look("top", grid=True)` → read the object pixel → `push(px, py, direction, distance_px)` where
`direction` is the top-image way to shove it. Confirm with `look()` afterward.

## Procedure — MONITOR / describe
Just `look("top")` (and `look("wrist")` if useful) and describe what you see / what changed. Repeat
on request. No motion.

## Safety (non-negotiable)
- Act only through the MCP tools — never invent raw joint values.
- Watch `get_state()` current: abnormally high current = collision/overload → STOP and report.
- Never drive the arm toward a person; deliver only to the taught drop-zone.
- `not_calibrated` from a tool → the grid isn't taught; tell the operator to calibrate; don't improvise.
- If unsure whether an action is safe, ask first.

## Notes
- **Be efficient / keep it quick.** You hold one persistent connection — don't re-`look` more than
  needed. A pick should be a handful of tool calls, not dozens.
- **The cameras must not be moved** after calibration — the grid is tied to the top camera's view.
- **Mock mode:** `look()` returns a placeholder and `grasp()` reports a synthetic hold — expected for
  dry runs without hardware.
- Start hard tasks with the forgiving **box**; tune per-object grasp heights before bottle/cup.
