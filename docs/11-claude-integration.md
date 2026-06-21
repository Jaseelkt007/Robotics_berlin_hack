# Claude Integration Plan — connecting Claude to the Station

> ℹ️ The MCP/skill/Agent-SDK wiring here is still accurate, but the **execution path** changed: the
> grid track replaced SmolVLA/IK. See [`13-grid-control-implemented.md`](./13-grid-control-implemented.md)
> for the tools and flow that actually run.


> **How Claude actually drives the robot.** Companion to
> [`10-implementation-strategy.md`](./10-implementation-strategy.md) (the two-stage *what*) — this is
> the *how* (the wiring). Last updated: 2026-06-20.

## The connection: Station API → our MCP server → Claude

```
        our code (Python)                       Claude-native
┌──────────────┐   station_py   ┌──────────────────────┐   MCP    ┌──────────────┐
│ NormaCore    │◄──TCP :8888────│  Station-MCP server   │◄────────►│   CLAUDE     │
│ Station      │   (network)    │  exposes TOOLS +      │  tools   │ agent loop   │
│ +arm+cameras │                │  the SAFETY layer     │          │ + a Skill    │
└──────────────┘                └──────────────────────┘          └──────────────┘
 (robot host /                   (our laptop)                       (our laptop)
  calibration laptop)
```

**Yes — the connection is MCP.** We build a **Station-MCP server** (our main deliverable; it literally
satisfies the track ask "integrate the Station API into Claude/Codex"). It wraps the `station_py`
client and exposes the robot to Claude as **tools**.

## The Station-MCP server

- **Language:** Python (uses the MCP Python SDK / FastMCP + `station_py`).
- **Connects to Station over TCP** — the address is configurable, so it can talk to a **remote** Station
  (e.g. the calibration laptop / Pi). **We do NOT need to copy calibration to our laptop** — we point
  the MCP server at whichever host runs the calibrated Station. (Only copy `station_data`/normfs if we
  later host Station ourselves.)
- **Transport:** `stdio` for the Claude Code CLI (simplest); `HTTP/SSE` when the backend/SDK drives it.
- **It is also the SAFETY layer** — clamp commands to calibrated `range_min/range_max`, enforce current
  limits, validate before anything reaches the motors.

### Tools exposed (maps to the two-stage plan)

| Tool | Stage | Does |
|---|---|---|
| `run_vla_task(instruction, max_tries=N)` | **1 (primary)** | Runs NormaCore's **finetuned SmolVLA** via the Station; retries N times; returns success/fail. |
| `look(camera="top"\|"wrist")` | both | Returns a camera frame **as an image Claude sees**. |
| `get_state()` | both | Joint positions + **gripper current** (grasp check). |
| `locate(target)` / `detect()` | 2 (fallback) | **ArUco + 2D→3D** pose of the target. |
| `move_to(x,y,z)` / `grasp()` / `release()` / `home()` | 2 (fallback) | Classical primitives (IK on the URDF). **Grasp method = TBD placeholder.** |

> ⚠️ **Confirm with NormaCore:** the exact API to *run the finetuned SmolVLA* (a Station command? the
> inference queue? a script?). `run_vla_task` wraps whatever that mechanism is — to be finalized on-site.

## How Claude runs (two modes, same MCP server + same Skill)

**(A) Dev / testing now — Claude Code CLI**
- Register the server: `claude mcp add` (or a project `.mcp.json`).
- In a session, Claude **auto-discovers the tools** and calls them. Test the full loop in the terminal,
  **no UI needed.**

**(B) Product / demo with UI + voice — Claude Agent SDK**
- Run Claude Code **headless as a persistent process** inside our backend (Python/TS Agent SDK), with
  the MCP server attached and a fixed allowed-tool list.
- The React app / voice feed each task in as a new turn (keeps scene/context across turns).

## Claude's inbuilt agent capabilities we use

| Capability | Role |
|---|---|
| **MCP** | The wiring — *how* Claude reaches the Station (the connection itself). |
| **Agentic loop** | The orchestration: decompose → `run_vla_task` → check → if N fail, run fallback → report. We don't build a control loop; Claude's loop *is* it. |
| **Skill** (`.claude/skills/<name>/SKILL.md`) | The brain's job description: operator persona, the **two-stage policy**, safety rules, when to use which tool, N-retry + fallback logic. **One Skill, invoked per task.** |
| **Agent SDK** | Embeds Claude in the backend so the UI/voice can drive it (mode B). |
| **Subagents** | *Optional, not now* (e.g. a separate vision-verifier) — keep it simple. |

> No external orchestration engine: **MCP = wiring, agentic loop = brain in motion, Skill = brain's
> instructions, Agent SDK = how the UI talks to it.**

## Codex

Later. Codex also speaks MCP, so the **same MCP server works unchanged** (write-once). We lead with
Claude for stronger vision.

## Config / secrets

- **Anthropic API key** for the Agent SDK / CLI.
- **Station address** (host:8888) for the MCP server — env/config (points at the remote calibrated Station).
- Voice keys (ElevenLabs / Gemini) — later, on the backend.

## Build sequencing (recommended)

1. **MCP server skeleton** + `look()` / `get_state()` / one safe move → prove against the (remote) Station via **Claude Code CLI**. *(Critical path — do this first.)* **Scaffold exists: [`/station_mcp/`](../station_mcp/) — runs in mock mode today; live hooks stubbed with `TODO`s.**
2. **Stage-1 tool** `run_vla_task` wired to NormaCore's finetuned SmolVLA + the **Skill** (decompose → run → N retries).
3. **Stage-2 fallback** tools (ArUco locate → move/grasp; grasping placeholder).
4. **UI** (see below) consuming the frozen tool contract — can start in parallel once tools are defined.
5. **Voice** (ElevenLabs/Gemini) handoff.

## UI approach (recommended — confirm before building)

- **Reuse NormaCore's `station-viewer`** (React/Vite/Three.js, already has camera feeds + 3D robot +
  **calibration tools**) for the **calibration + home slide-out window**. Don't rebuild calibration.
- **Build our own clean main app** (chat box, two-stage "watch it think" status, wrist + top camera
  views) with **Lovable** (fast, minimalistic, sponsor tool) — wired to our backend (Agent SDK) and
  Station's WebSocket for live frames.
- Don't fork their whole app (their Three.js/conventions slow down a hackathon look).

## Open items
- Exact NormaCore **SmolVLA run API** (what `run_vla_task` calls) — confirm on-site.
- MCP transport choice (stdio vs HTTP) for the backend.
- Final **Skill** contents (operator policy + safety rules).
- Fallback **grasping method** (placeholder — teammate deciding).
