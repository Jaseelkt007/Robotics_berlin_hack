# Project Vision

## Working name

**[TBD]** — placeholder: *"Third Hand"* / *"HandsFree"*. Decide before the pitch.

## The problem

Many people physically **cannot free their hands**, yet constantly need objects manipulated. Today
the only solution is **a second human standing by** — expensive, scarce, or simply absent. This is
true in four distinct situations, unified by one fact: *the hands are unavailable.*

1. **Hands incapable** — a person with a disability or limited mobility.
2. **Hands sterile + busy** — a surgeon/dentist mid-procedure.
3. **Hands inside a delicate task** — a lab scientist pipetting, a technician soldering.
4. **Hands isolated** — glovebox / hazmat / cleanroom / semiconductor work.

In every case voice is **load-bearing**, not a gimmick: it is the *only free channel the person has.*

## The product

> **A voice-commanded robotic "third hand" that you talk to like a colleague.** It looks through the
> robot's camera, understands the scene, does the physical task you ask for, and **corrects itself
> when it fails.**

Not a remote control. Not a pre-scripted machine. An **assistant with eyes, judgment, and a
conversation.** It is **collaboration, not replacement** — a fundamentally different shape from what
the robotics giants build.

## Beachhead & expansion

- **Beachhead (demo + first market): Assistive / care** — help a disabled/elderly person whose hands
  can't. Biggest TAM, strongest emotional pitch, clean tabletop demo. Voice + "show it through the
  camera" interaction.
- **Expansion (the unicorn ceiling): clinical / surgical "scrub assistant"** — the same brain scales
  to the operating room. Surgical robotics (e.g. Intuitive/da Vinci, ~$170B) is **teleoperated**;
  nobody ships an *autonomous, voice-commanded* assistant. Also: lab automation, field technician.

## Why this is defensible (the moat)

- **The giants do autonomous *replacement* in structured spaces** (Amazon/Covariant warehouses,
  Physical Intelligence general models). **Nobody does real-time *collaboration* with a skilled human
  via natural conversation.** That is our white space.
- **The robot is almost incidental.** The moat is the **domain workflow + UX + the reasoning layer**,
  not the hardware (which is commoditizing — NormaCore arms are ~$220).
- **Zero per-task training** (Claude generalizes) means it handles novel objects/tasks instantly,
  where trained VLAs need data per task.

## Market & comparables (validates the thesis is real, not hype)

- **Assistive robotics market:** ~**$10.5B (2024) → ~$58B (2033), ~20.9% CAGR**. Incumbents
  (e.g. **Kinova Jaco**) are **joystick-controlled and cost $6k–$100k** — dumb and expensive. The
  LLM-brain unlock = "a cheap arm you just talk to that figures it out." (Gap = intelligence + cost.)
- **Physical Intelligence:** foundation models for robots — **~$5.6B valuation**, open-sourced π0.
  → validates "the software brain layer is the valuable part" (and that the general brain is becoming
  a commodity we can *use*, not a moat to rebuild).
- **Covariant → Amazon Robotics:** "pick any item" foundation models, acqui-hired ~2024.
  → validates "AI that handles object variety without per-item training."
- **AMP Robotics:** ~$1B (recycling) — validates the broader "AI + manipulation" market, *but* line
  sorting is owned by optical sorters (no arm) — which is **why we did NOT pick sorting.**

## What we deliberately rejected (and why) — anti-goals

| Rejected idea | Why |
|---|---|
| Recycling / e-waste **sorting** | Solved by optical sorters (conveyor + vision + air-jets); an arm is the *wrong, slower* tool. |
| Warehouse "pick any item" | Owned by Amazon/Covariant. |
| A better general "robot brain" | Owned by Physical Intelligence ($5.6B, open π0). |
| High-mix machine tending (CNC) | Already a crowded cobot market (UR, FANUC, Doosan, Standard Bots). |
| Generic "teach it anything in English" | No story — too vague; not a real application. |

## The 30-second pitch (current draft)

> Millions of people — someone with a disability, a surgeon mid-operation, a scientist with both
> hands in a glovebox — physically can't free their hands, so they need a second person just to fetch
> and hand them things. We're building the robotic "third hand" you simply **talk to**: you say "hand
> me my water bottle" or "pick up the pills I dropped," and it does it. The breakthrough is we make
> **Claude itself the brain** — we wrap NormaCore's Station API as an MCP server (`look`, `move_to`,
> `grasp`, `release`) and run the Claude Code CLI as a live agentic loop: it looks through the robot's
> camera, reasons about how to grab the object, acts, then looks again to verify and retries if it
> missed — real self-correction, **zero per-object training.** Voice is an ElevenLabs agent, the whole
> thing runs in a React web app where you watch the AI think in real time. It's not a remote
> control — it's an assistant with eyes, judgment, and a conversation.

## Why we win the room

- **Demoable tomorrow** on real hardware, with a visible "wow" (self-correction).
- **Emotional + huge TAM** (assistive) with a billion-dollar ceiling (surgical).
- **Literal track answer** (Station API integrated into Claude/Codex as the brain).
- **~60% built already** via our existing assets (voice agent, agent orchestration, dashboards).
