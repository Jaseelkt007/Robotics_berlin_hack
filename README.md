# Robotics × AI Hackathon — Berlin (NormaCore Track)

**Track:** NormaCore — *"AI-Powered Robot Control: integrate the Station API into Codex or Claude so it
can control the robot by looking through the cameras."*

**What we're building:** a **voice/chat-commanded robotic "third hand"** — an assistant you *talk to*
that looks through the robot's camera, figures out the physical task, does it, and **corrects itself
when it fails**. **Claude itself is the brain**, orchestrating a **two-stage executor** — **Stage 1:**
NormaCore's **finetuned SmolVLA**; **Stage 2 fallback:** **pose estimation (ArUco + 2D→3D) + IK**.
NormaCore's Station API is wrapped as an **MCP server**.
*(We train nothing ourselves initially; fine-tuning SmolVLA on our objects is a possible later step.)*

> One-liner: *Not a remote control — an assistant with eyes, judgment, and a conversation.*

**Full plan:** [`docs/10-implementation-strategy.md`](./docs/10-implementation-strategy.md) ·
**How Claude connects:** [`docs/11-claude-integration.md`](./docs/11-claude-integration.md) ·
**Joint-control plan:** [`docs/12-joint-control-plan.md`](./docs/12-joint-control-plan.md) ·
**Docs index:** [`docs/README.md`](./docs/README.md).

---

## ⭐ How the setup is split across laptops (read this first)

The hardware (arm + cameras), calibration, and any model fine-tuning live on **one machine**; the rest
of us develop on our own laptops and connect to it **over the network**. You do **not** need the arm
plugged into your laptop.

| Machine | Runs | Notes |
|---|---|---|
| **Robot laptop** (has the hardware) | NormaCore **Station**, the **arm(s) + USB cameras**, **calibration**, any **SmolVLA fine-tuning** | Start Station with `station --tcp --web` so it's reachable on the LAN (`0.0.0.0:8888`). Find its IP: `hostname -I`. |
| **Dev laptops** (rest of the team) | our **MCP server**, the **Claude brain** (CLI or `agent_service`), the **web UI** | Connect to the robot laptop's Station via TCP. Set `STATION_HOST=<robot-laptop-ip>`. |

So: **calibration & training stay on the robot laptop**; everyone else points their MCP server at it.
All on the **same Wi-Fi/LAN**, port **8888** open.

> **Where does the "cloud" come in?** Only the **brain** (Claude) is cloud — via your Claude
> subscription. The actual **motor commands run locally**: `agent_service`/Claude decides *what* to do,
> then calls the MCP tools, which send commands to the Station over **local/LAN TCP**. Motor bytes never
> travel through the cloud.

---

## Components & environments (what to install)

Each component has its **own isolated environment** — set them up independently. Nothing is shared.

| Component | Dir | Environment | Needs |
|---|---|---|---|
| **MCP server** (wraps the Station as tools) | `station_mcp/` | its own **Python venv** (`uv`) | `uv`; for LIVE mode also a cloned `norma-core` |
| **Agent service** (always-on Claude brain for the web UI) | `agent_service/` | its own **Python venv** (`uv`) | `uv` **+ the `claude` CLI installed & logged in** (subscription auth) |
| **Web UI** (operator dashboard) | `web/` | **Node** (`npm`) | Node ≥ 22, `npm` |
| **NormaCore source** (LIVE only) | `norma-core/` (cloned, not committed) | — | `git clone` next to this repo |

---

## Quickstart

There are **two ways to drive the robot** — both use the same MCP server + the same `robot-operator`
skill. Pick A for a terminal, B for the web UI.

### Path A — Claude Code in a terminal (simplest)

```bash
# 1) MCP server (mock mode = no hardware)
cd station_mcp
uv venv && uv pip install -r requirements.txt

# 2) register it with Claude Code
claude mcp add normacore-station -- uv run --directory $(pwd) python server.py

# 3) in a Claude Code session:  "call look and describe what you see"
```

### Path B — Web UI + always-on brain (the dashboard demo)

```bash
# 0) one-time: make sure station_mcp is set up (Path A step 1) and you have the Claude CLI logged in
claude login                 # subscription auth (NOT an API key)

# 1) the always-on Claude brain (uses your subscription; refuses to start if ANTHROPIC_API_KEY is set)
cd agent_service
uv venv && uv pip install -r requirements.txt
unset ANTHROPIC_API_KEY
uv run python server.py      # ws://localhost:8770/chat

# 2) the web UI (separate terminal)
cd web
npm install
npm run dev                  # http://localhost:5174
```

Then open http://localhost:5174 and chat. Smoke-test the brain alone with
`cd agent_service && uv run python smoke_test.py`.

**Live (real arm):** set `STATION_HOST=<robot-laptop-ip>` (and `NORMA_CORE_PATH`) in
`station_mcp/.env`; see [`station_mcp/README.md`](./station_mcp/README.md). To embed live cameras +
calibration in the web UI, run NormaCore's `station-viewer` and set `VITE_VIEWER_URL` in `web/.env`.

## Repository structure

```
.
├── .claude/skills/robot-operator/SKILL.md   ← the operator "brain" policy (team-shared skill)
├── docs/                                     ← all project documentation (start at docs/README.md)
│   ├── 00–09 …                               ← hackathon, vision, architecture, Station API, DH params
│   ├── 10-implementation-strategy.md         ← ⭐ canonical two-stage plan + UI spec
│   ├── 11-claude-integration.md              ← how Claude connects (MCP, tools, Skill, Agent SDK)
│   └── 12-joint-control-plan.md              ← plan for send_joint_targets → grasp/release/home
├── station_mcp/                              ← ⭐ the Station-MCP server (Python; wraps the arm as tools)
│   ├── server.py  backend.py  safety.py
│   ├── enable_torque.py  check_torque.py  subscribe_normvla.py
│   └── requirements.txt  .env.example  README.md
├── agent_service/                            ← always-on Claude brain (Agent SDK) behind the web UI
│   ├── agent.py  server.py  smoke_test.py
│   └── requirements.txt  README.md
├── web/                                      ← operator dashboard (React + Vite + Tailwind, ElevenLabs style)
│   └── src/ …  package.json  README.md  .env.example
├── .gitignore                                ← ignores norma-core clone, venvs, node_modules, .env
└── README.md                                 ← you are here
```
*(The NormaCore source `norma-core/` is **not** committed — see below.)*

## Status (2026-06-21)

- ✅ **MCP server** — mock mode works; **vision linchpin proven** (Claude *sees* camera frames via
  `look()`); live `look()` + `get_state()` implemented.
- ✅ **Agent service (brain)** — always-on persistent Claude session over WebSocket, **uses the Claude
  subscription** (no API key), loads the `robot-operator` skill + the MCP. End-to-end verified in mock
  (chat → Claude → skill → MCP → camera frame).
- ✅ **Web UI** — clean operator dashboard; chat + "watch it think" feed (markdown + animated tool
  calls), sidebar (Assistant / Live Station / Calibration / Settings), station-viewer embeddable.
- ⏳ **Next:** `send_joint_targets` → `grasp`/`release`/`home` (plan in `docs/12`; unlocks real motion) ·
  `run_vla_task` live (confirm NormaCore's SmolVLA trigger) · Stage-2 `locate`/`move_to` (ArUco + IK) ·
  end-to-end run on the real arm. See
  [`docs/07-open-questions-and-next-steps.md`](./docs/07-open-questions-and-next-steps.md).

## Stack

Claude (brain — Claude Code CLI **or** the `agent_service` Agent SDK, subscription auth) ·
**Station-MCP server** (Python) · NormaCore Station + arm (robot laptop) ·
**Web UI** (React + Vite + Tailwind v4 + Inter, reusing NormaCore's `station-viewer` for
cameras/calibration via embed) · ElevenLabs voice + Gemini Live backup (later). Detail:
[`docs/04-technical-architecture.md`](./docs/04-technical-architecture.md).

## The NormaCore source (external dependency — not committed)

We reference NormaCore's repo but don't vendor it (own git history, large). Clone it next to this repo
if you need the source/URDFs/`station_py` (required for LIVE mode):

```bash
git clone https://github.com/norma-core/norma-core.git
```
Point the MCP server at it with `NORMA_CORE_PATH=/path/to/norma-core`. Everything we extracted from it
is in `docs/05`, `docs/08`, `docs/09`.
