---
name: box-stacker
description: Stack one object on top of another on the NormaCore tabletop — pick a box (or cup/bottle) and place it ON TOP of a second box. Use ONLY when the user explicitly asks to stack, or to put/place one thing ON TOP OF another (e.g. "stack the small box on the big one", "put the cup on top of the box"). For ordinary pick-and-place, drag, or fetch, use the robot-operator skill instead. Drives the `normacore-station` MCP tools over the taught pixel→joint grid.
---

# Box Stacker

You stack one object on top of another on the tabletop. You are the perception: you look through the
cameras, pick the **source** object, raise it, move it over the **target** object, and set it down on
top. You never compute kinematics — the tools convert a camera pixel into motion through the taught
**calibration grid**, and a safety layer clamps everything.

This is a normal grasp followed by a **`stack_on`** placement. The grasp is the same reliable
procedure as robot-operator; the only new piece is placing at **stacking height** over the target.

## When to use this (vs robot-operator)
- USE THIS only for **stacking / "on top of"** requests. Two objects: a **source** (the one that
  moves) and a **target** (the one it lands on top of).
- For fetch, ordinary place-in-tray, drag-across-table, push, point, or wave → use **robot-operator**.

## Tools (`normacore-station`)
- `look(camera, grid)` — `look("top", grid=True)` = overhead frame + pixel grid (LOCATE both objects);
  `look("wrist")` = close-up down the gripper (ALIGN before grasping).
- `move_to_pixel(px, py, height, object_class)` — gripper to a top-cam pixel. `height="hover"` (safe)
  or `"grasp"` (descend). `extrapolated:true` ⇒ pixel outside the taught area.
- `nudge(direction)` — small `up|down|left|right` step in the top-image frame.
- `grasp()` — close + verify; returns `holding` and `gap` (big gap = something is held).
- `stack_on(px, py, object_class)` — **the stacking move**: with an object already grasped, raise it
  to stacking height over the TARGET box's pixel (px,py), open the jaws to set it down, then lift
  clear. Height is taught per-rig (`stack.lift_scale`).
- `release()` / `home()` / `get_state()`.

## Rig facts you MUST account for (same hardware as robot-operator)
- **The top camera is low-res and noisy (160×120).** Pixel reads are ~10–15 px off; treat the first
  `move_to_pixel` as coarse and correct on the wrist cam.
- **Read BOTH object pixels up front**, from the SAME initial `look("top", grid=True)`. Once you're
  holding the source object, it (and the arm) can occlude the target — so note the target's pixel
  before you pick. The camera is fixed, so an early reading stays valid.
- **Aim at each object's base** — the edge where it meets the table on the side nearest the camera —
  not its center or top (the overhead cam is angled; the base removes parallax).
- **Grasp = `gap`:** after `grasp()`, a large `gap` means it's held; `gap≈0` means it closed on air.
- **Stacking height is tuned, not computed.** `stack_on` raises by `stack.lift_scale × hover_delta`.
  If it isn't tuned yet it may place too high or clip the target — tell the operator to adjust
  `stack.lift_scale` in `waypoints.json` (live-editable, no restart): raise it if the held box clips
  the target going in, lower it if it drops from too high.

## Procedure — STACK source ON TOP OF target (follow in order)
1. **Acknowledge instantly**, then act ("Sure — stacking the small box on the big one.").
2. **Locate both (coarse).** `look("top", grid=True)`. Read the **base pixel of the SOURCE** (the one
   to move) AND the **top-center pixel of the TARGET** (where the source should land). Keep both. If
   you only see one object, or which-is-which is ambiguous, ask the person to clarify. If either is
   `extrapolated` later, ask them to move it toward the table center.
3. **Pick the source** (exactly like a fetch grasp):
   - `release()` (pre-open), then `move_to_pixel(src_px, src_py, "hover")`.
   - **Align on the WRIST cam:** `look("wrist")`, center the object between the jaws using SMALL
     `nudge` steps (make one nudge, `look("wrist")`, see which way it moved, correct). Stop when
     centered (~2–4 nudges).
   - `move_to_pixel(src_px, src_py, "grasp", object_class)` then `grasp()`. Check `gap`: large → held →
     continue. `gap≈0` → **missed** (and likely bumped it): `home()`, `look("top", grid=True)` to
     **re-locate the source fresh**, retry from this step. Retry ~twice, then stop and report.
4. **Lift clear.** `move_to_pixel(src_px, src_py, "hover")` — raise the box off the table before
   traversing, so it doesn't drag.
5. **Stack.** `stack_on(target_px, target_py, object_class)` — raises over the target and sets the box
   down on top. Then `home()`.
6. **Confirm + report.** `look("top")` to verify the stack stands; say one short sentence. If the box
   slid off or landed beside the target, report it and suggest tuning `stack.lift_scale`.

## Safety (non-negotiable)
- Act only through the MCP tools — never invent raw joint values.
- Watch `get_state()` current: abnormally high current = collision/overload → STOP and report.
- Don't `stack_on` without a **confirmed hold** (big `gap`) — placing air does nothing and wastes a move.
- `not_calibrated` from a tool → the grid isn't taught; tell the operator to calibrate; don't improvise.
- Never drive the arm toward a person.

## Notes
- **Be efficient.** One persistent connection — don't re-`look` more than needed. A stack is: one top
  look, a handful of grasp calls, `stack_on`, `home`.
- The cameras must not move after calibration — the grid is tied to the top camera's view.
- Start with the forgiving **box** on a flat-topped target; tune `stack.lift_scale` once, then it holds.
