# Robotics × AI Hackathon — Berlin (NormaCore Track)

**Track:** NormaCore — *"AI-Powered Robot Control: integrate the Station API into Codex or Claude so it
can control the robot by looking through the cameras."*

**What we built:** a **voice/chat-commanded robotic "third hand"** — an assistant you *talk to* (or type
to) that looks through the robot's camera, works out the physical task, does it on a real arm, and
**corrects itself when it misses**. **Claude itself is the brain**: we wrap NormaCore's Station API as
an **MCP server**, and Claude drives the arm by reading the camera and calling tools.

> One-liner: *Not a remote control — an assistant with eyes, judgment, and a conversation.*

**The reliable track (what actually runs):** SmolVLA was blocked on a checkpoint, so we built a
**SmolVLA-independent grid track** — Claude reads a target's **pixel** from the overhead camera, and a
**pre-taught pixel→joint grid** turns that pixel into motion (no IK, no ArUco, no API key for control).
Fine alignment uses the wrist camera; the grasp is verified by how far the jaws close. First full
autonomous **pick-and-place succeeded on hardware (2026-06-21)**, then drag, stacking, and voice.

### What it can do
- 🗣️ **Talk to it** — full **voice mode**: speak → Claude (brain) acts → it narrates and speaks back
  (browser STT → Claude → ElevenLabs TTS, with an optional OpenAI "narrator" for natural commentary).
- 🤖 **Fetch / pick-and-place** — "bring me the box": locate → align → grasp (verified) → deliver.
- ↔️ **Drag / reposition** — slide a held object to a spot without lifting.
- 🧱 **Stack** — place one box on top of another (raised-drop, height tuned per rig).
- 🛑 **Stop button + barge-in** — interrupt mid-task and ask something else.
- 👀 **"Watch it think"** dashboard — live tool calls, camera frames, and reasoning stream into the UI.

**⭐ As-built design:** [`docs/13-grid-control-implemented.md`](./docs/13-grid-control-implemented.md) ·
**Architecture:** [`docs/04-technical-architecture.md`](./docs/04-technical-architecture.md) ·
**How Claude connects:** [`docs/11-claude-integration.md`](./docs/11-claude-integration.md) ·
**Docs index:** [`docs/README.md`](./docs/README.md).

---

## How it works (flow)

```
            ┌─────────── you (voice or chat) ───────────┐
            ▼                                            │
   ┌──────────────────┐   WebSocket   ┌───────────────────────────┐
   │   Web UI (React) │◀─────────────▶│  Agent service = the      │
   │  chat · voice    │   events      │  Claude "brain" (Agent SDK)│
   │  watch-it-think  │               │  subscription auth         │
   └──────────────────┘               └─────────────┬─────────────┘
        ▲  ElevenLabs TTS                            │ MCP (stdio)
        │  OpenAI narrator                           ▼
        │  (browser, parallel)        ┌───────────────────────────┐
        └─────────────────────────────│  station_mcp (MCP server) │
                                       │  look / move_to_pixel /   │
                                       │  grasp / drag / stack_on  │
                                       │  pixel→joint GRID (no IK) │
                                       └─────────────┬─────────────┘
                                                     │ TCP :8888 (LAN)
                                                     ▼
                                       ┌───────────────────────────┐
                                       │  NormaCore Station        │
                                       │  arm + 2 USB cameras      │
                                       └───────────────────────────┘
```

**The "cloud" is only the brain.** Claude (via your subscription) decides *what* to do; the actual
**motor commands run locally** over LAN TCP. Motor bytes never travel through the cloud.

---

## Hardware / components

| Component | What we used | Notes |
|---|---|---|
| **Robot arm** | NormaCore 7-DoF follower arm, **ST3215** serial-bus servos (motors **1–7** + **gripper = motor 8**) | Pure joint-space control; every motion clamped to calibrated ranges. |
| **Overhead camera** | Logitech **C270** USB webcam (mounted above, slight angle) | Used to LOCATE objects (Claude reads the pixel). Noisy at 160×120 over usbip — we denoise with a frame-burst consensus. |
| **Wrist camera** | Small USB gripper-cam | Used for FINE alignment right before grasping. |
| **Motor bus adapter** | **CH343** USB-serial adapter(s) (`/dev/ttyACM*`) | Bind into WSL with `usbipd`; see `fix-camera.sh` for the camera permission fix. |
| **Host machine** | Windows + **WSL2** (6.x kernel) or Linux | Runs the NormaCore Station + arm + cameras. |
| **Brain (cloud)** | **Claude** subscription (Claude Code CLI or the Agent SDK) | No API key — subscription auth. |
| **Voice (cloud, optional)** | **ElevenLabs** (TTS) + **OpenAI** (narrator) + browser Web Speech (STT) | Only for voice mode; the robot works fully without them. |

You do **not** need the arm plugged into your own laptop — see the laptop split below.

---

## How the setup is split across laptops

The hardware (arm + cameras), calibration, and any model fine-tuning live on **one machine**; the rest
of the team develops on their own laptops and connects **over the network**.

| Machine | Runs | Notes |
|---|---|---|
| **Robot laptop** (has the hardware) | NormaCore **Station**, the **arm(s) + USB cameras**, **calibration** | Start with `station --tcp --web` so it's reachable on the LAN (`0.0.0.0:8888`). Find its IP: `hostname -I`. |
| **Dev laptops** | the **MCP server**, the **Claude brain**, the **web UI** | Point at the robot laptop: `STATION_HOST=<robot-laptop-ip>` in `station_mcp/.env`. |

Same Wi-Fi/LAN, port **8888** open. Calibration + training stay on the robot laptop.

---

## Components & environments (what to install)

Each component has its **own isolated environment**.

| Component | Dir | Environment | Needs |
|---|---|---|---|
| **MCP server** (wraps the Station as tools) | `station_mcp/` | Python venv via **`uv`** | `uv`; for LIVE mode also a cloned `norma-core` |
| **Agent service** (always-on Claude brain) | `agent_service/` | Python venv via **`uv`** | `uv` **+ the `claude` CLI installed & logged in** |
| **Web UI** (operator dashboard + voice) | `web/` | **Node** (`npm`) | Node ≥ 20.19 / 22, `npm` |
| **NormaCore source** (LIVE only) | `norma-core/` (cloned, not committed) | — | `git clone` next to this repo |

---

## Quickstart

Two ways to drive the robot — both use the same MCP server + the same `robot-operator` skill.

### Path A — Claude Code in a terminal (simplest)

```bash
cd station_mcp
uv venv && uv pip install -r requirements.txt
# register with Claude Code (mock mode = no hardware needed):
claude mcp add normacore-station -- uv run --directory $(pwd) python server.py
# then in a Claude Code session:  "call look and describe what you see"
```

### Path B — Web UI + always-on brain (the dashboard / voice demo)

```bash
# 0) one-time: set up station_mcp (Path A step 1) and log the Claude CLI in
claude login                       # subscription auth (NOT an API key)

# 1) the always-on Claude brain (refuses to start if ANTHROPIC_API_KEY is set)
cd agent_service
uv venv && uv pip install -r requirements.txt
unset ANTHROPIC_API_KEY
uv run python server.py            # ws://localhost:8770/chat

# 2) the web UI (separate terminal)
cd web
cp .env.example .env               # then add your keys (see Voice below)
npm install
npm run dev                        # http://localhost:5174
```

Open http://localhost:5174 and **chat**, or click **Voice mode** in the right panel.

### Live (real arm)

On the **robot laptop**: `station --tcp --web`. On your dev laptop, set in `station_mcp/.env`:

```
STATION_HOST=<robot-laptop-ip>     # unset ⇒ MOCK mode
STATION_PORT=8888
NORMA_CORE_PATH=/path/to/norma-core
STATION_BUS_SERIAL=<follower-bus-serial>     # pin the arm bus
STATION_DATA_DIR=/path/to/station_data       # so per-camera frame queues are discovered
CAMERA_TOP=<vid:pid>                          # overhead cam
CAMERA_WRIST=<vid:pid>                        # gripper cam
```

Then **calibrate the grid once** (teaches `waypoints.json`):

```bash
cd station_mcp
.venv/bin/python calibrate.py info      # list buses + dump a frame per camera
.venv/bin/python calibrate.py capture   # torque off; hand-pose grid points + home/drop-zone/gripper
.venv/bin/python calibrate.py click     # browser at :8799 — click the gripper tip per frame
.venv/bin/python run_selftest.py        # validate: arm visits every taught point before grasping
```

### Voice (optional)

Voice rides on top of the chat and runs **fully in parallel** — the robot is unaffected if it's off.
Add to `web/.env`:

```
VITE_ELEVENLABS_API_KEY=sk_...        # spoken replies (TTS); blank ⇒ voice output disabled
VITE_ELEVENLABS_VOICE_ID=21m00Tcm4TlvDq8ikWAM
VITE_OPENAI_API_KEY=sk-...            # optional narrator for natural commentary; blank ⇒ simple cues
VITE_OPENAI_MODEL=gpt-4o-mini
```

Speech-to-text uses the browser's built-in Web Speech API (Chrome/Edge), no key needed.

---

## How to run / test

```bash
# MCP server tools, no hardware (drives pick → grasp → deliver → drag → stack in mock):
cd station_mcp && .venv/bin/python test_server_mock.py

# grid interpolation unit tests:
cd station_mcp && .venv/bin/python test_gridmap.py

# the brain alone (Agent SDK wiring, talks to the MCP):
cd agent_service && uv run python smoke_test.py

# on hardware: visit every taught grid point to validate calibration BEFORE grasping:
cd station_mcp && .venv/bin/python run_selftest.py
```

---

## Repository structure

```
.
├── .claude/skills/
│   ├── robot-operator/SKILL.md      ← operator "brain" policy: fetch / drag / push / point / wave
│   └── box-stacker/SKILL.md         ← narrow skill: stack one box on top of another
├── docs/                            ← all project documentation (start at docs/README.md)
│   ├── 00–09 …                      ← hackathon, vision, architecture, Station API, DH params
│   ├── 10–12 …                      ← original two-stage SmolVLA+IK plan (superseded by 13)
│   └── 13-grid-control-implemented.md   ← ⭐ AS-BUILT: grid track + calibration + hardware gotchas
├── station_mcp/                     ← ⭐ the Station-MCP server (Python; wraps the arm as tools)
│   ├── server.py  backend.py  safety.py
│   ├── gridmap.py                   ← pixel→joint IDW interpolation (replaces IK)
│   ├── overlay.py                   ← labeled pixel grid drawn on the top frame
│   ├── calibrate.py                 ← teach the grid → waypoints.json (rig-specific, gitignored)
│   ├── pick.py  look.py  run_selftest.py   ← manual bring-up tools
│   └── requirements.txt  .env.example  README.md
├── agent_service/                   ← always-on Claude brain (Agent SDK) behind the web UI
│   ├── agent.py  server.py  smoke_test.py  requirements.txt  README.md
├── web/                             ← operator dashboard (React + Vite + Tailwind)
│   └── src/
│       ├── components/  (ChatPanel, VoicePanel, Sidebar, …)
│       └── lib/  useChat.ts · useVoice.ts · tts.ts · narrator.ts
├── .gitignore                       ← ignores norma-core clone, venvs, node_modules, .env, waypoints.json
└── README.md                        ← you are here
```
*(NormaCore's source `norma-core/` is **not** committed — clone it separately for LIVE mode.)*

---

## MCP tools (what Claude can call)

| Tool | What it does |
|---|---|
| `look(camera, grid)` | overhead frame + pixel grid (LOCATE) / wrist close-up (ALIGN). Returns the cleanest of a burst. |
| `move_to_pixel(px,py,height,object_class)` | gripper → table point under a top-cam pixel via the grid. `height` = `hover`/`grasp`/`stack`. |
| `nudge(direction)` | small step up/down/left/right in the image frame. |
| `grasp()` / `release()` | close + verify by close-gap / open. |
| `deliver()` / `home()` / `get_state()` | taught drop-zone / taught rest pose / live motor state. |
| `drag(px,py)` | slide a held object on the table to a pixel and release (reliable reposition). |
| `stack_on(px,py)` | raise a held object and set it ON TOP of the box at a pixel. |
| `push(px,py,…)` / `wave()` / `grid_selftest()` | rough shove / gesture / calibration check. |

Every motion passes a calibrated-range clamp — Claude never writes raw motor values.

---

## Status (2026-06-21)

- ✅ **Grid track live on hardware** — calibrated pixel→joint grid; **autonomous pick-and-place,
  drag, and stacking** working. Live state from `st3215/rx`; camera frames from per-camera
  `usbvideo/<hash>` queues; grasp verified by close-gap.
- ✅ **Claude brain + web UI** — always-on persistent session (subscription auth), loads the
  `robot-operator` + `box-stacker` skills, streams a "watch it think" feed; **Stop button** + barge-in.
- ✅ **Voice mode** — speak → Claude acts → it narrates and speaks back, fully parallel with the arm.
- ▶ **Tuning:** per-object grasp heights; stacking height (`stack.lift_scale`); reliability reps.

Full as-built detail + the hardware gotchas that cost us hours: `docs/13-grid-control-implemented.md`.

---

## The NormaCore source (external dependency — not committed)

We reference NormaCore's repo but don't vendor it (own git history, large). Clone it next to this repo
for LIVE mode (provides `station_py` + protobufs + URDFs):

```bash
git clone https://github.com/norma-core/norma-core.git
```
Point the MCP server at it with `NORMA_CORE_PATH=/path/to/norma-core`. What we extracted from it is in
`docs/05`, `docs/08`, `docs/09`.
