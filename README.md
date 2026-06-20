# Robotics × AI Hackathon — Berlin (NormaCore Track)

**Track:** NormaCore — *"AI-Powered Robot Control: integrate the Station API into Codex or Claude so it
can control the robot by looking through the cameras."*

**What we're building:** a **voice-commanded robotic "third hand"** — an assistant you *talk to* that
looks through the robot's camera, figures out the physical task, does it, and **corrects itself when it
fails**. The breakthrough is that **Claude itself is the brain** (Claude Code CLI agentic loop), with
NormaCore's Station API wrapped as an **MCP server** — **no model training required**.

> One-liner: *Not a remote control — an assistant with eyes, judgment, and a conversation.*

---

## Repository structure

```
.
├── docs/                          ← all project documentation (start here)
│   ├── README.md                  ← docs index
│   ├── 00-hackathon-overview.md
│   ├── 01-hackathon-tracks.md
│   ├── 02-sponsors-and-resources.md
│   ├── 03-project-vision.md
│   ├── 04-technical-architecture.md
│   ├── 05-normacore-station-reference.md
│   ├── 06-feasibility-and-decisions.md
│   ├── 07-open-questions-and-next-steps.md
│   ├── 08-station-api-capabilities.md
│   ├── 09-dh-parameters.md
│   └── scripts/dh_from_urdf.py    ← reproducible URDF→DH derivation (no deps)
├── dh_from_urdf.py                ← same script (repo root copy)
├── .gitignore
└── README.md                      ← you are here
```

**New here?** Read [`docs/README.md`](./docs/README.md) — it orders the docs and gives a one-paragraph
summary.

## The NormaCore source (external dependency — not committed here)

We reference NormaCore's repo but do **not** vendor it (it has its own git history and is large).
Clone it next to this repo if you need the source/URDFs:

```bash
git clone https://github.com/norma-core/norma-core.git
```

Everything we extracted from it (Station API, capabilities, hardware specs, URDF kinematics, DH
parameters) is captured in `docs/05`, `docs/08`, and `docs/09` so you usually don't need the clone.

## Status (2026-06-20)

- ✅ Direction locked, feasibility validated, technical decisions logged.
- ✅ Documentation complete (this push).
- ⏳ Implementation not started — build order & open questions in
  [`docs/07-open-questions-and-next-steps.md`](./docs/07-open-questions-and-next-steps.md).

## Stack (planned)

Claude Code CLI (brain) · Station-MCP server (Python, our build) · NormaCore Station + arm ·
ElevenLabs voice (Gemini Live backup) · React web app (Lovable) — see
[`docs/04-technical-architecture.md`](./docs/04-technical-architecture.md).
