# Open Questions & Next Steps

## A. To confirm ON-SITE (hardware & logistics)

- [ ] **Which arm** do we get — ElRobot (7+1 DoF) or SO-101 (6 DoF)? (Affects URDF + IK chain.)
- [ ] **Camera setup** — gripper-mounted (eye-in-hand), an overview cam, or both? Model/resolution?
- [ ] **Is depth available?** (Any RealSense/Orbbec on hand, or RGB only?)
- [ ] **Station host** — does NormaCore provide a Pi/Mac already running Station? (Avoids WSL/USB.)
- [ ] **Is a pre-trained SmolVLA checkpoint available** for the provided arm? (Enables D8 upgrade.)
- [ ] **Network** — can our laptop reach the Station host over TCP `:8888`? Same LAN/Wi-Fi?
- [ ] **Workspace** — flat table for top-down grasps? Lighting?

## B. To confirm (event meta)

- [ ] Exact **venue address** + Wi-Fi.
- [ ] **Per-track judging rubric** for the NormaCore track (does one exist?).
- [ ] **Free credits/quotas** for sponsor tools (AWS, Mistral, HF, Apify, Lovable).
- [x] **Voice cost — resolved:** ElevenLabs credits = plenty ✅; Gemini credits available as backup ✅.

## C. Decisions still OPEN (need the team)

- [ ] **Project name** (placeholder: "Third Hand" / "HandsFree").
- [ ] **Beachhead for the *demo*** — assistive/care is chosen; pick the exact demo scenario
      (e.g. "hand me my water bottle" + "pick up the pills I dropped" + a deliberate miss → recovery).
- [ ] **Brain:** Claude Code vs Codex (default Claude; confirm subscription/model = Opus 4.8).
- [ ] **Voice:** default **ElevenLabs** (ample credits) → backup **Gemini Live** (credits available) →
      Web Speech (free). All three available; pick primary at build time.
- [ ] How much **web-app polish** vs robustness to invest (the "watch it think" dashboard is the
      differentiator — worth real time).

## D. Technical linchpins to PROVE first (in order)

1. [ ] **Hour 1:** an MCP tool returns a camera frame **as an image Claude actually sees & describes.**
       *(If this fails, the whole concept needs rework — prove it before anything else.)*
2. [ ] Read robot **state** + send a **single joint command** through the Station API (round-trip).
3. [ ] **Calibration** working (pixel → world, or hand-eye for eye-in-hand).
4. [ ] **IK** working (`ikpy`/PyBullet + URDF → reach a target (x,y) on the table).
5. [ ] One full **pick** primitive (move → grasp → lift), then the **verify + retry** loop.
6. [ ] Voice → Claude handoff → spoken result (instant ack + background action).

## E. Build order — STAGED (see [`10-implementation-strategy.md`](./10-implementation-strategy.md))

**Stage 1 — primary executor:**
1. Station-MCP server scaffold + `look()` vision proof (linchpin).
2. Claude **language decomposition** → call the **NormaCore finetuned-SmolVLA** API → **N retries** → place.
3. After tests, decide if our objects are handled; if not → **fine-tune SmolVLA on our objects** (later).

**UI (staged):**
4. Slide-out window: NormaCore **calibration + home**, **wrist + top** camera views, **chat box**.

**Stage 2 — fallback executor:**
5. **Pose estimation: ArUco + 2D→3D mapping** → **IK** (URDF). **Grasping method = placeholder (TBD).**
6. Wire the fallback trigger (after N failed Stage-1 tries).

**Voice + polish:**
7. Voice (ElevenLabs / Gemini backup) handoff; demo rehearsal + pitch.

## F. Known risks (carried from architecture doc)

| Risk | Mitigation | Severity |
|---|---|---|
| `look()` image not seen by Claude | Prove hour 1; fallback = describe-via-separate-vision-call | 🔴 high |
| WSL ↔ USB | Run Station on native Pi/Mac | 🟡 medium |
| ElevenLabs → local backend reach | Client-side tool → localhost; fallback cloudflared / Web Speech | 🟡 medium |
| Grasp accuracy too coarse | OpenCV centroid/PCA refine + gripper tolerance (~54 mm) | 🟡 medium |
| Need true 3D (off-table objects) | Add RGB-D camera | 🟢 low (scope control) |
| Finetuned SmolVLA can't handle our objects | Pose+IK fallback (Stage 2); fine-tune SmolVLA on our objects later | 🟡 medium |
| Fallback grasping method undecided | Placeholder; teammate finalizing the approach | 🟡 medium |

## G. Immediate next action

- Get the team to read these docs and push back / add.
- Do the initial **git push** of this `docs/` folder.
- (When ready) ask Claude to scaffold the **Station-MCP server + hour-1 `look()` vision proof** — it's
  hardware-independent until final wiring, so it can start before we have the arm.
