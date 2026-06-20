# Feasibility & Decisions Log

> Resolved technical questions from our analysis. Each entry: **Question → Verdict → Why.** This is the
> record of *what we decided and the reasoning*, so we (and our friends, and Claude/Codex) don't
> re-litigate settled points.

## D1 — Do we need to train any model? **No (for the demo).**
- **Verdict:** No imitation learning / VLA training. We use Claude (zero-shot intelligence) +
  **one-time calibration** + **inverse kinematics** (on the shipped URDF) + simple primitives.
- **Why:** Recognition, localization (coarse), planning, verification, and recovery are all zero-shot
  for Claude. The only "robot-specific" parts are calibration + IK, which are *math/config*, not
  training. Training (SmolVLA) only buys smoothness/dexterity — a roadmap item, not a requirement.

## D2 — Can Claude "do everything"? **No — precise split.**
- **Verdict:** Claude does the **intelligence**, not the geometry.
  - Claude (zero-shot): scene understanding, task decomposition, *which* object + *approximate* pixel
    location + coarse orientation, grasp strategy, **verification**, error recovery, conversation.
  - **NOT Claude:** inverse kinematics, trajectory/waypoints, **metric 6-DoF pose estimation**,
    low-level servo control.
- **Why:** Our friends were right — Claude is a high-level decision maker, not an IK solver or a
  metric pose estimator. The architecture never asked it to be. (See D3, D4.)

## D3 — Waypoints: IK or training? **IK (no training).**
- **Verdict:** Claude gives the target; **inverse kinematics** converts target pose → joint angles;
  waypoints = joint-space interpolation (servos self-smooth). Use `ikpy`/PyBullet.
- **Why:** The Station controls at **joint level only** (no Cartesian/IK). But the repo **ships the
  URDF**, so IK is a few lines. Training is the *alternative* to IK, not a requirement.

## D4 — Pose estimation: can Claude do it? **No — we don't need it.**
- **Verdict:** Claude is **not** a metric pose estimator (won't give mm/degree-accurate 6-DoF). We
  **replace pose estimation with calibration**: pixel → world via a homography (fixed cam) or FK
  (eye-in-hand). Orientation via OpenCV PCA or Claude's coarse estimate (irrelevant for round objects).
- **Why:** For top-down grasps on a known surface, calibration fully determines the world coordinate.
  No pose model required.

## D5 — How much extra computer vision? **Minimal; Claude codes it.**
- **Verdict:** At most a homography (a matrix multiply) + optional ~20 lines of OpenCV
  (centroid/principal axis) for grasp precision. No deep learning, no training.
- **Why:** Claude can point directly at the grasp pixel; CV refinement is a cheap precision boost.
  **All of it is written by Claude-the-coder.**

## D6 — Depth / cameras: how, without training? **Constrain to a flat table.**
- **Verdict:** NormaCore cameras are **2D RGB UVC (no depth)**. We avoid the depth problem by using a
  **top-down / known-surface** setup (height is known). Optional upgrades (all no-training):
  **RGB-D** (RealSense/Orbbec → per-pixel depth) or **monocular depth** (Depth Anything v2).
- **Why:** "Usually done" = remove the need for depth via geometry, or add a cheap depth sensor. The
  tabletop assumption is the robust weekend path.

## D7 — Fixed camera vs. camera on the gripper? **Eye-in-hand is good; spine unchanged.**
- **Verdict:** Camera-on-gripper ("eye-in-hand") changes **one module** (pixel→world becomes
  FK-based instead of a static homography) and **nothing else**. It is arguably **more reliable**
  because it enables **visual servoing** (closed-loop approach that improves as the gripper nears).
- **Why:** The moving camera's pose is always known from joint angles (forward kinematics; the viewer
  already does FK). Calibrate the fixed camera↔gripper offset once (`cv2.calibrateHandEye`). Best of
  both: an overview cam to plan + a wrist cam to grasp.

## D8 — Will we use SmolVLA? **Default no; optional drop-in.**
- **Verdict:** Don't depend on it (it needs training). If NormaCore provides a **pre-trained**
  checkpoint, Claude can call it as a single "smart grasp" tool (Claude decides what/where; VLA
  executes smoothly).
- **Why:** SmolVLA is the opposite trade-off from Claude (fast/smooth but needs demos, can't reason).
  Complementary, not required.

## D9 — Latency: can it feel conversational? **Yes, with UX design.**
- **Verdict:** Talking is instant (~1 s); a full physical task is **~15–30 s**. **Decouple
  conversation from action** (instant voice ack + background work + report) and **minimize Claude
  round-trips** (look once, plan all, classical primitives execute, re-look to verify).
- **Why:** Voice-commanded assistance is inherently discrete ("one sec, reaching over"), so
  smart-but-not-instant is correct. Millisecond real-time control is the VLA/training regime — not our
  use case.

## D10 — MCP: only to connect to the CLI? **Primary reason, not the only one.**
- **Verdict:** Use an MCP server. Yes, its headline job is connecting the Station API to Claude/Codex
  (the literal track ask). It *also* gives: agent-agnostic write-once (Claude **or** Codex), the
  **safety boundary** (clamp/validate before motors), encapsulation, and a reusable platform artifact.
- **Why:** Cheap to build, and the four secondary benefits are real.

## D11 — Voice: ElevenLabs as the brain? **No — voice I/O only.**
- **Verdict:** ElevenLabs = ears + mouth + conversation; it **hands off** the task to Claude via a
  client tool. Claude is the brain (and the only one with vision).
- **Why:** Letting ElevenLabs' LLM reason would lose Claude's vision and fail the track.

## D12 — Where does Station run? **Native host, not WSL.**
- **Verdict:** Run Station on a **Pi / Mac / Linux** at the robot; everything else reaches it over
  TCP. Claude/MCP/backend can live in WSL (no USB there).
- **Why:** WSL2 can't see USB (camera + servo bus) without `usbipd` — a fiddly demo-killer. Avoid it.

---

## Net feasibility verdict

**Possible this weekend, with no training:** voice-commanded pick/hand/place of graspable objects on
a surface, with self-correction, at conversational-feeling speed. The architecture is **modular** —
the worry-items (better CV, depth, a VLA, smoother motion) are **drop-in upgrades, not rewrites.**
