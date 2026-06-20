# Technical Architecture

> High-level system design. Detailed Station API facts are in
> [`05-normacore-station-reference.md`](./05-normacore-station-reference.md). Resolved technical
> trade-offs are in [`06-feasibility-and-decisions.md`](./06-feasibility-and-decisions.md).

## The one rule that makes it all work

**ElevenLabs is the ears + mouth. Claude is the brain.**
If ElevenLabs' own LLM does the reasoning, we lose Claude's vision and fail the track. So ElevenLabs
does *voice I/O + conversation* only, and **hands off the task to Claude** via a client tool.

## The four layers

```
🎙️ VOICE  (ElevenLabs Conversational AI, embedded in the React web app)
        │  speech-to-text → the spoken goal; fires a CLIENT TOOL on actionable requests
        ▼
🧠 BRAIN  = Claude Code CLI  (run via the Claude Agent SDK as a PERSISTENT headless session)
        │  agentic loop: plan → call tool → SEE result → reason → act → verify → recover
        ▼  MCP tool calls
🔌 BRIDGE = Station-MCP server  (Python; wraps the station_py client) — WE BUILD THIS
        │  tools: look(), get_state(), move_to(x,y[,z]), grasp(), release(), home()
        │  ALSO the safety layer: clamp positions, current limits, validate commands
        ▼  TCP :8888 / WebSocket :8889
🦾 ROBOT  = NormaCore Station  →  arm (ST3215 servos) + UVC camera(s)
```

### Layer 1 — Voice (ElevenLabs)
- Natural, low-latency, interruptible conversation.
- Uses **client-side tools** so the tool call fires *in the browser* and calls our **local** backend
  (localhost) — no public tunnel needed. (Connectivity fallback: `cloudflared` tunnel.)
- **Voice fallback chain:** ElevenLabs (primary, ample credits) → **Gemini Live API** (backup, credits
  available; real-time voice, as used in Jarvis) → browser Web Speech API (free last resort).
- Replies **instantly** ("Sure, getting it now") then reports when the robot finishes — see Latency.

### Layer 2 — Brain (Claude Code CLI)
- Runs via the **Claude Agent SDK** as a **persistent subprocess** — one long-lived "brain" session,
  fed each voice command as a new turn (keeps context/scene memory). **Not** a fresh terminal per
  command. (Crude fallback: `claude -p` one-shot, stateless.)
- The agentic loop *is* the self-correction: it acts, re-looks, and retries natively.
- Codex works the same way (also MCP); we prefer Claude for stronger vision.

### Layer 3 — Bridge (Station-MCP server) — our main deliverable
- Wraps the `station_py` client; exposes the robot as clean MCP tools.
- **Why MCP** (not just an SDK function): works with both Claude *and* Codex (write-once), is the
  natural safety boundary between the LLM and the motors, encapsulates protobuf/TCP/IK complexity,
  and is a reusable platform artifact (good for the pitch + sponsor).
- `look()` returns the camera frame **as an image content block Claude can see** — the linchpin.

### Layer 4 — Robot (NormaCore Station)
- Local server over TCP/WebSocket. Owns the USB camera(s) and the servo bus.
- **Runs on a native host (Raspberry Pi / Mac / Linux), NOT in WSL** — see deployment below.

## Division of labor — Claude vs. classical code (CRITICAL)

There are **two roles for Claude**: *Claude-the-coder* writes all the code below at build time;
*Claude-the-brain* runs the intelligence at run time.

| Claude-the-brain does (zero-shot, NO training) | Classical code does (written by Claude-the-coder, NO training) |
|---|---|
| Scene understanding / visual analysis | **Inverse kinematics** (Cartesian → joint angles) via `ikpy`/PyBullet + NormaCore's **URDF** |
| Task decomposition / subtasks | **Waypoints / trajectory** (joint interpolation; servos self-smooth) |
| Identify *which* object + *approximate* pixel location + coarse orientation | **Metric pose estimation → NOT NEEDED;** replaced by **one-time calibration** |
| High-level grasp strategy | **Pixel → world** mapping (homography for fixed cam; FK-based for eye-in-hand) |
| **Verify** success (visual) + interpret gripper feedback | Optional **OpenCV** refinement (centroid/PCA) for a precise grasp point/angle |
| Detect failure → **retry/adjust** | Low-level servo control via the **Station API** |

> Claude does **not** do IK or pose estimation — by design. Those are solved classically. The repo
> ships the **URDF**, so IK is a few lines.

## The pick loop (end to end)

```
1. look()                         → Claude sees the frame
2. identify + locate object        → Claude (coarse pixel/region)  [+ optional OpenCV refine]
3. pixel → world coordinate        → calibration (+ FK if eye-in-hand)
4. world → joint angles            → IK on the URDF
5. move + grasp()                  → Station API joint targets; servos smooth
6. look() again + gripper feedback → Claude verifies "did I get it?"
7. if failed → reopen, adjust, retry  (self-correction loop)
```

## Camera strategy

- NormaCore cameras are **2D RGB UVC** (no depth by default), and the hardware supports
  **gripper-mounted (eye-in-hand)** cameras.
- **Eye-in-hand is good for us:** no self-occlusion, can get close, enables **visual servoing**
  (close-the-loop approach that gets *more* reliable as it nears the object).
- Camera pose while moving is known via **forward kinematics** (joint angles + URDF) — the
  station-viewer already does FK rendering.
- **Depth handled by constraining to a flat table** (height known) — no depth camera or training
  needed. Optional upgrades: RGB-D (RealSense) or monocular depth (Depth Anything v2). All no-training.
- Multiple cameras supported: `look(camera="overview")` to plan + `look(camera="wrist")` to grasp.

## Latency / "make it feel like a conversation"

- Talking: ~0.5–1 s (instant). Each Claude reasoning step: ~a few seconds. Full task: **~15–30 s**.
- **Decouple conversation from action:** voice acks instantly; robot works in background; reports when
  done — exactly like a human assistant saying "one sec."
- **Minimize Claude round-trips:** Claude looks once, plans the whole sequence; fast classical
  primitives execute; Claude only re-looks to verify. The tight visual-servo correction loop is
  **classical fast code**, with Claude *supervising* — not Claude per micro-nudge.

## Deployment map (avoids the WSL/USB trap)

| Component | Where it runs |
|---|---|
| **Station** (touches USB: camera + servo bus) | **Native** Pi / Mac / Linux at the robot. *Not WSL.* |
| Station-MCP server + Claude Code (Agent SDK) | WSL or any Linux/Mac — talks to Station over **TCP** (no USB). |
| React web app + ElevenLabs + local backend | Laptop/browser; browser ↔ backend over localhost. |

> WSL2 can't see USB without `usbipd` (fiddly, demo-killer). We sidestep it entirely by running
> **Station on a native host** and having everything else reach it over the network.

## Top integration risks (and mitigations)

1. **`look()` returns an image Claude actually sees** → prove in hour 1 before anything else.
2. **WSL ↔ USB** → run Station on Pi/Mac (above).
3. **ElevenLabs → local backend** → client-side tool calling localhost (fallback: cloudflared).
4. **Grasp accuracy** → OpenCV centroid/PCA refinement (planned fallback) + gripper tolerance (~54mm).
5. **True 3D needed** → add RGB-D camera (only if demo requires off-table objects).
6. **Smoother grasps wanted** → drop in a *pre-trained* SmolVLA as a single "grasp" tool (optional).

> Every risk is a **swappable module**, not an architecture change. The spine is fixed.
