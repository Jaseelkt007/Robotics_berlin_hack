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
- **Drag / reposition** — grasp an object and slide it to a new spot WITHOUT lifting (`drag`) — the
  reliable way to "move X over there".
- **Push / topple / move-aside** — shove an object with closed jaws (`push`) — rougher; can miss.
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
- `drag(px, py, object_class)` — after you've **grasped** an object, slide it (still on the table) to
  destination pixel (px,py) and release it there. The reliable way to reposition something.
- `push(px, py, direction, distance_px, object_class)` — blind shove with closed jaws (rough; can miss
  — prefer `drag` when precision matters).
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
2. **Locate (coarse).** `look("top", grid=True)`. Read the pixel of the object's **base** — the edge
   where it meets the table, on the side **nearest the camera** — NOT its center or top. The overhead
   cam is at a slight angle, so a tall object's top projects offset from where the gripper must go;
   aiming at the base removes that error. If not in view, ask the person to place it on the table;
   `extrapolated:true` later → ask them to move it inward.
3. **Open + hover.** `release()`, then `move_to_pixel(px, py, "hover")`.
4. **Align on the WRIST cam** (the top cam is too noisy for fine work). `look("wrist")`. Get the object
   **centered between the jaws, at the jaw line.** Use SMALL `nudge` steps. The nudge→wrist-view mapping
   isn't obvious, so make ONE small nudge, `look("wrist")` to see which way the object moved, then
   correct in that light. Keep steps small and stop the moment it's centered (~2–4 nudges). If a nudge
   throws the object out of the small wrist frame, reverse and go smaller.
5. **Descend + grasp.** `move_to_pixel(px, py, "grasp", object_class="box")` then `grasp()`. The drop is
   short, so good centering survives it. Check `gap`: large → held → continue. `gap≈0` → **missed, and
   the descent likely bumped the object** — `home()`, then `look("top", grid=True)` to **re-locate it
   fresh** (it moved) and retry from step 2. Re-descending at the same pixel won't work. Retry ~twice,
   then stop and report.
6. **Lift + deliver.** `move_to_pixel(px, py, "hover")`, then `deliver()`, `release()`, `home()`.
7. **Report** in one short sentence.

## Procedure — DRAG / reposition (move X to a spot, keep it on the table) — PREFERRED for "move it there"
This is a **pick that puts down instead of lifting** — it reuses the reliable grasp, so it doesn't miss:
1. **Grasp the object** exactly as in FETCH steps 2–5: locate the base → `release()` → hover →
   `look("wrist")` + small `nudge`s to center → descend → `grasp()`. **Confirm `holding:true`** (big
   `gap`). If it missed, re-locate and retry — do NOT drag without a confirmed hold.
2. **Read the destination pixel** from your earlier `look("top", grid=True)` (where it should end up).
3. **`drag(dest_px, dest_py, object_class)`** — slides the held object at table height to the
   destination and releases it. Then `home()`.
4. **Report.** Prefer this over `push` whenever the destination matters.

## Procedure — PUSH / topple / move-aside (rough only)
For a quick shove/topple where precision doesn't matter: `look("top", grid=True)` → read the object
pixel → `push(px, py, direction, distance_px)` (small distance, ~30–45). It's blind and can miss — use
**DRAG** for anything that needs to land in a specific place. Confirm with `look()` afterward.

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
