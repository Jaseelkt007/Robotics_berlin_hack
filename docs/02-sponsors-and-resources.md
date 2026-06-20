# Sponsors & Resources Available to Us

> ⚠️ **Credits / "free" access:** the event lists these as infrastructure & tooling partners, but the
> exact free credits/quotas were not published. Treat specific allowances as **[CONFIRM ON-SITE]**.

## Sponsors (from the event listing)

| Sponsor | What they are | Relevance to us |
|---|---|---|
| **NormaCore** ⭐ | Unified toolkit for physical systems; makes the **robot arm + Station platform**. Our track host. | **Provides our hardware + Station API.** Core dependency. |
| **ITQ** | Experts in mechatronics, software, systems engineering. | Mentorship on the hardware/robotics side. |
| **Apify** | Web scraping, automation, serverless "Actors". | Optional — data ingestion if needed. |
| **MyBotShop** | Distributes advanced robotic systems (research/education/industry). | Possible additional hardware. |
| **Hugging Face** ⭐ | The hub for open-source ML models; **LeRobot** + **SmolVLA**. | VLA models, LeRobot ecosystem (optional upgrade path). |
| **Spiced Academy** | Web dev / data science bootcamps. | Community/mentorship. |
| **n8n** | Open-source workflow automation (no-code + full code). | Optional — automate backend workflows. |
| **Lovable** ⭐ | "Describe an idea → working app." App builder. | **Our web app frontend (React).** |
| **Migrapreneur** | AI skills for migrants → employment. | Community partner. |
| **Konvo** | Proactive AI agent platform for customer support/sales. | Reference for agent UX. |
| **MARSO** | AI-powered autonomous robots for logistics warehouses. | Domain reference (robotics startup). |
| **pdm solutions** | Structures real-world location/business data for AI/robotics. | Domain reference. |
| **Mistral** ⭐ | Paris-based open-weight LLMs (Europe's OpenAI challenger). | Possible LLM (esp. for a EU/open-weight story); fallback brain. |
| **AWS builder center** | Cloud skills, workshops, AI tooling. | Possible cloud credits / compute. **[CONFIRM]** |

## What we actually plan to use

| Need | Tool | Source | Notes |
|---|---|---|---|
| Robot arm + camera + control | **NormaCore arm + Station** | Sponsor (free at event) | ElRobot 7+1 DoF or SO-101; eye-in-hand camera. |
| The "brain" (agentic loop) | **Claude Code CLI** (or Codex) | Our subscription | Opus 4.8. Track explicitly allows Codex too. |
| Robot ↔ brain bridge | **MCP server** (we build) | Our code | Wraps the Station API. See architecture doc. |
| Web app / UI | **Lovable → React** | Sponsor tool | Run locally; "watch it think" dashboard + camera feeds. |
| Voice agent (primary) | **ElevenLabs Conversational AI** | ⚠️ Not a sponsor, **but we have ample credits** ✅ | Voice I/O only; hands off to Claude. Swappable. |
| Voice agent (backup) | **Gemini (Live API)** | **We have Gemini credits** ✅ | Real-time conversational voice fallback if ElevenLabs runs out (same role used in our Jarvis project). Can also serve as a backup vision/LLM. |
| Voice agent (last resort) | Browser **Web Speech API** | Free | Zero-cost fallback for STT; pair with any TTS. |
| Optional VLA "smart grasp" | **SmolVLA** (HF/LeRobot) | Sponsor ecosystem | Only if a pre-trained checkpoint is provided; needs training otherwise → default **not used**. |
| Optional LLM alternative | **Mistral** open-weight | Sponsor | EU/open-weight story; primary brain is Claude, backup is Gemini. |

> **Resource status (confirmed by team):** ElevenLabs credits = **plenty** ✅. Gemini credits =
> **available** ✅ (backup voice + backup vision/LLM). No budget concern for voice.

## Hardware we expect from NormaCore  [CONFIRM ON-SITE]

- A robot arm: **ElRobot (7+1 DoF)** and/or **SO-101 (6 DoF)**, both with a **parallel-jaw gripper**.
- At least one **UVC USB camera** (likely **gripper-mounted / eye-in-hand**).
- A host running the **Station** binary (Linux / Raspberry Pi / macOS). See station reference doc.
