# Robotics × AI Hackathon — Berlin (NormaCore Track)

**Track:** NormaCore — *"AI-Powered Robot Control: integrate the Station API into Codex or Claude so it
can control the robot by looking through the cameras."*

**What we're building:** a **voice-commanded robotic "third hand"** — an assistant you *talk to* that
looks through the robot's camera, figures out the physical task, does it, and **corrects itself when it
fails**. **Claude itself is the brain** (Claude Code agentic loop) orchestrating a **two-stage
executor** — **Stage 1:** NormaCore's **finetuned SmolVLA**; **Stage 2 fallback:** **pose estimation
(ArUco + 2D→3D) + IK**. NormaCore's Station API is wrapped as an **MCP server**.
*(We train nothing ourselves initially; fine-tuning SmolVLA on our objects is a possible later step.)*

> One-liner: *Not a remote control — an assistant with eyes, judgment, and a conversation.*

**Full plan:** [`docs/10-implementation-strategy.md`](./docs/10-implementation-strategy.md) ·
**How Claude connects:** [`docs/11-claude-integration.md`](./docs/11-claude-integration.md) ·
**Docs index:** [`docs/README.md`](./docs/README.md).

---

## ⭐ How the setup is split across laptops (read this first)

The hardware (arm + cameras), calibration, and any model fine-tuning live on **one machine**; the rest
of us develop on our own laptops and connect to it **over the network**. You do **not** need the arm
plugged into your laptop.

| Machine | Runs | Notes |
|---|---|---|
| **Robot laptop** (has the hardware) | NormaCore **Station**, the **arm(s) + USB cameras**, **calibration**, any **SmolVLA fine-tuning** | Start Station with `station --tcp --web` so it's reachable on the LAN (`0.0.0.0:8888`). Find its IP: `hostname -I`. |
| **Dev laptops** (rest of the team) | our **Station-MCP server** + **Claude** (the brain), later the **web UI** | The MCP server connects to the robot laptop's Station via TCP. Set `STATION_HOST=<robot-laptop-ip>`. |

So: **calibration & training stay on the robot laptop**; everyone else points their MCP server at it.
All on the **same Wi-Fi/LAN**, port **8888** open.

## Quickstart (dev laptop — works with no hardware via mock mode)

```bash
# 1) get the MCP server running (uses uv)
cd station_mcp
uv venv && uv pip install -r requirements.txt
uv run python server.py                      # MOCK mode (no hardware)

# 2) register it with Claude Code
claude mcp add normacore-station -- uv run --directory /mnt/d/normacore/station_mcp python server.py

# 3) in a Claude Code session:  "call look and describe what you see"
```
For the **live** connection to the real arm, see [`station_mcp/README.md`](./station_mcp/README.md)
(set `STATION_HOST` in `station_mcp/.env`).

## Repository structure

```
.
├── .claude/skills/robot-operator/SKILL.md   ← the operator "brain" policy (v0 draft, team-shared)
├── docs/                                     ← all project documentation (start at docs/README.md)
│   ├── 00–09 …                               ← hackathon, vision, architecture, Station API, DH params
│   ├── 10-implementation-strategy.md         ← ⭐ canonical two-stage plan + UI spec
│   ├── 11-claude-integration.md              ← how Claude connects (MCP, tools, Skill, Agent SDK)
│   └── scripts/dh_from_urdf.py               ← reproducible URDF→DH derivation
├── station_mcp/                              ← ⭐ the Station-MCP server (our main deliverable)
│   ├── server.py  backend.py  safety.py
│   ├── requirements.txt  .env.example  README.md
├── dh_from_urdf.py                           ← DH script (repo-root copy)
├── .gitignore                                ← ignores the norma-core clone, .env, local .claude config
└── README.md                                 ← you are here
```
*(The NormaCore source `norma-core/` is **not** committed — see below.)*

## Status (2026-06-21)

- ✅ **Strategy + full docs** locked (`docs/`).
- ✅ **Station-MCP server built** — runs in mock mode; **linchpin proven**: Claude sees camera frames
  through MCP (`look()`), and `get_state` / `run_vla_task` call through.
- ✅ **Live parsers implemented** for `look()` (usbvideo→JPEG) and `get_state()`
  (st3215/inference→joints); verified against the real protobufs — **pending an end-to-end run on the arm.**
- ✅ **`robot-operator` Skill** v0 (draft — will be rewritten once the full system is in).
- ⏳ **Next:** live test vs the real arm · `run_vla_task` (confirm NormaCore's SmolVLA trigger) ·
  Stage-2 fallback (ArUco + IK) · web UI. See
  [`docs/07-open-questions-and-next-steps.md`](./docs/07-open-questions-and-next-steps.md).

## Stack

Claude Code CLI / Agent SDK (brain) · **Station-MCP server** (Python — built) · NormaCore Station +
arm (robot laptop) · ElevenLabs voice + **Gemini Live** backup (later) · React web app via **Lovable**
\+ reuse NormaCore's `station-viewer` for the calibration/home panel (hybrid; later). Detail:
[`docs/04-technical-architecture.md`](./docs/04-technical-architecture.md).

## The NormaCore source (external dependency — not committed)

We reference NormaCore's repo but don't vendor it (own git history, large). Clone it next to this repo
if you need the source/URDFs/`station_py`:

```bash
git clone https://github.com/norma-core/norma-core.git
```
Point the MCP server at it with `NORMA_CORE_PATH=/path/to/norma-core`. Everything we extracted from it
is in `docs/05`, `docs/08`, `docs/09`.
