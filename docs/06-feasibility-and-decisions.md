# Feasibility & Decisions Log

> Resolved technical questions from our analysis. Each entry: **Question → Verdict → Why.** This is the
> record of *what we decided and the reasoning*, so we (and our friends, and Claude/Codex) don't
> re-litigate settled points.

## D1 — Do we need to train any model? **Not initially — Stage 1 uses NormaCore's *finetuned* SmolVLA as-is.**
- **Verdict:** Stage-1 execution uses NormaCore's **already-finetuned SmolVLA** (we call it as-is, **no
  training by us**). The **Stage-2 fallback** (ArUco pose + IK) needs no training either. **Conditional
  later step:** if tests show our objects aren't handled reliably, **fine-tune NormaCore's SmolVLA on
  our objects.**
- **Why:** Claude's reasoning/decomposition is zero-shot; the learned grasp skill comes pre-finetuned
  from NormaCore; the classical fallback is math/config. See [`10-implementation-strategy.md`](./10-implementation-strategy.md).

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

## D4 — Pose estimation: do we use it? **Yes — as the Stage-2 fallback.**
- **Verdict:** Claude is **not** a metric pose estimator. The **fallback** path uses a classical
  **pose-estimation module: ArUco markers + 2D→3D mapping**, then **IK**. (Stage 1 / SmolVLA is
  end-to-end and needs no explicit pose.) **The fallback grasping method is not finalized — placeholder**
  until the teammate decides.
- **Why:** ArUco gives a reliable, training-free 3D pose from known markers — the deterministic backup
  when the VLA fails its N tries. (Earlier homography/calibration notes in D5–D7 are fallback details.)

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

## D8 — Will we use SmolVLA? **Yes — it's the PRIMARY executor (Stage 1).**
- **Verdict:** Claude decomposes the request and issues a language instruction to **NormaCore's
  finetuned SmolVLA** via the Station API; the robot retries **N** times. Used **as-is** at first (no
  training by us); **fine-tune on our objects later only if needed.** Classical **ArUco-pose + IK** is
  the Stage-2 fallback.
- **Why:** NormaCore provides the finetuned model, so we get a learned grasp skill for free; the
  fallback guarantees a deterministic path. See [`10-implementation-strategy.md`](./10-implementation-strategy.md).

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

**Possible this weekend:** text/voice-commanded pick-and-place via a **two-stage executor** — **Stage 1**
NormaCore **finetuned SmolVLA** (no training by us initially), **Stage 2** **ArUco-pose + IK** fallback
(grasping TBD) — orchestrated by Claude (decompose → run → retry → fallback). The architecture is
**modular**; fine-tuning SmolVLA on our objects is a conditional later upgrade. See
[`10-implementation-strategy.md`](./10-implementation-strategy.md).
