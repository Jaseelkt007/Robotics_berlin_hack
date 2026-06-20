# Implementation Strategy (CANONICAL)

> **This is the single source of truth for HOW we build the pick-and-place.** Where older docs said
> "no training," "SmolVLA not used," or "pose estimation not needed," **this doc supersedes them** —
> they have been reconciled to match this.
> Last updated: 2026-06-20.

## Core: two-stage executor, orchestrated by Claude

### Stage 1 — PRIMARY: NormaCore finetuned SmolVLA
- **Flow:** text/voice from the UI → **Claude decomposes** the language into a robot task → Claude
  issues the **VLA language instruction** → calls the **NormaCore API that runs the finetuned SmolVLA**
  → robot attempts the pick → **N fixed retries** → place at the target location.
- **Training policy:** **initially NO training by us** — we use NormaCore's **already-finetuned**
  SmolVLA *as-is*. **Conditional later step:** as testing continues, if our objects aren't handled
  reliably, **fine-tune NormaCore's SmolVLA on the objects we use.** (Future — not now.)

### Stage 2 — FALLBACK: traditional pose estimation + IK
- **Trigger:** Stage 1 fails after the N retries.
- **Pose estimation:** **ArUco markers + 2D→3D mapping** (current direction).
- **IK:** URDF-based (`ikpy`/PyBullet) — the repo ships the URDF.
- **Grasping strategy: NOT FINALIZED → PLACEHOLDER.** A teammate is deciding the approach. Once
  finalized, we add the grasping + UI integration details here.

```
UI / voice text
      │
      ▼
🧠 CLAUDE — decompose language → choose action → monitor → decide
      │
      ├── STAGE 1 (primary) ─► NormaCore API → finetuned SmolVLA → attempt ×N → place
      │        (no training by us initially; fine-tune on our objects later if needed)
      │
      └── if N tries fail ─► STAGE 2 (fallback) ─► ArUco + 2D→3D pose → IK → pick-place
                                                   (grasping method = PLACEHOLDER / TBD)
```

## Claude's role (exact)
1. **Decompose** the natural-language input (chat box / voice) into a concrete robot task.
2. **Translate** it into the SmolVLA instruction and **call the NormaCore API** that runs Stage 1.
3. **Monitor** the N retries; judge success/failure.
4. **Trigger the Stage-2 fallback** when Stage 1 fails.

> Claude does **not** train the VLA, do IK, or do pose estimation. Those are: the (NormaCore-finetuned)
> model, and the classical fallback module, respectively.

## UI (React — built in stages)
- A **button slides open a window** containing:
  - NormaCore **calibration + home** controls.
  - **Two camera views: wrist + top.**
  - A **chat box** for text task input.
- UI code + integration are built **progressively** (stages).

## Build stages (sequence)
1. **Stage 1 path:** language → Claude decompose → NormaCore finetuned-SmolVLA API → N retries → place.
2. **UI:** slide-out window (NormaCore calibration + home, wrist + top cameras, chat box).
3. **Stage 2 fallback:** ArUco + 2D→3D pose → IK → pick-place (**grasping = placeholder**).
4. **Conditional:** fine-tune SmolVLA on our objects *if* Stage-1 testing shows it's needed.
5. **Voice** layer (ElevenLabs primary / Gemini backup) + demo rehearsal + pitch.

## Open / placeholder (to finalize with the team)
- **Grasping method for the Stage-2 fallback** — TBD (teammate deciding).
- **Whether SmolVLA needs fine-tuning** for our objects — decide after Stage-1 tests.
- **N** (retry count) — TBD.
- ArUco marker setup (sizes, placement, board) for the 2D→3D mapping — TBD.

## Cross-references
- Architecture & layers: [`04-technical-architecture.md`](./04-technical-architecture.md)
- Decisions (D1, D4, D8 reflect this two-stage plan): [`06-feasibility-and-decisions.md`](./06-feasibility-and-decisions.md)
- Station API used by both stages: [`08-station-api-capabilities.md`](./08-station-api-capabilities.md)
