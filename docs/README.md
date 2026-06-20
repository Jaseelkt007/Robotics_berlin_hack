# Project Documentation — Index

> **Purpose:** This folder is the single source of truth for our Robotics × AI Hackathon project.
> It exists so that (a) our teammates can read, analyze, and extend the plan, and (b) Claude / Codex
> always have the full project context when we build. This will be the **initial git push**.

**Last updated:** 2026-06-19 (day before the event)
**Status:** Pre-build — direction locked, feasibility validated, implementation plan NOT yet written.

---

## How to read these docs

Read in order if you're new to the project:

| File | What's inside |
|---|---|
| [`00-hackathon-overview.md`](./00-hackathon-overview.md) | Theme, schedule, timing, location, judging (what we know) |
| [`01-hackathon-tracks.md`](./01-hackathon-tracks.md) | All tracks + **the track we chose** and why |
| [`02-sponsors-and-resources.md`](./02-sponsors-and-resources.md) | Sponsors, what each provides, what's free/available to us, our tool choices |
| [`03-project-vision.md`](./03-project-vision.md) | The problem, the product ("intelligent third hand"), market, pitch, moat |
| [`04-technical-architecture.md`](./04-technical-architecture.md) | The full system design — how every piece fits together |
| [`05-normacore-station-reference.md`](./05-normacore-station-reference.md) | Technical map of the NormaCore Station API + hardware (from the repo) |
| [`06-feasibility-and-decisions.md`](./06-feasibility-and-decisions.md) | Resolved technical questions: training, depth, cameras, latency, CV, VLA |
| [`07-open-questions-and-next-steps.md`](./07-open-questions-and-next-steps.md) | What's still TBD, what to confirm on-site, next actions |
| [`08-station-api-capabilities.md`](./08-station-api-capabilities.md) | Full Station API capability tables (from the protobufs + client) |
| [`09-dh-parameters.md`](./09-dh-parameters.md) | DH parameters + exact kinematics for ElRobot & SO-101 (leader/follower) |
| [`scripts/dh_from_urdf.py`](./scripts/dh_from_urdf.py) | Reproducible URDF→DH derivation script (no deps) |

---

## One-paragraph summary

We are building a **voice-commanded robotic "third hand"** for people whose hands are busy or
incapable (disabled/elderly first; clinical/lab/technician as expansion). You talk to it; it looks
through the robot's camera, figures out what to do, does it, and corrects itself when it fails. The
breakthrough is that **Claude itself is the brain** — we wrap NormaCore's Station API as an **MCP
server** and run the **Claude Code CLI** (or Codex) as a live agentic loop. **No model training** is
required: Claude supplies the intelligence zero-shot; classical code (calibration + inverse
kinematics on NormaCore's URDF + simple primitives, all written by Claude) supplies the geometry.

## Conventions

- Items we have **not** confirmed are marked **`[TBD]`** or **`[CONFIRM ON-SITE]`**. Do not treat
  them as facts.
- The cloned NormaCore source lives at `../norma-core/` (reference only — not our code).
