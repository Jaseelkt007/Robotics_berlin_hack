// Parallel "narrator": a fast LLM that turns the robot's event stream into warm,
// spoken commentary. Fully decoupled from the brain — it only READS what already
// happened and produces a line for ElevenLabs to speak. Browser-direct (OpenAI
// supports CORS); leave the key blank to disable and fall back to action cues.

const KEY = import.meta.env.VITE_OPENAI_API_KEY ?? "";
const MODEL = import.meta.env.VITE_OPENAI_MODEL ?? "gpt-4o-mini";

export const narratorConfigured = (): boolean => KEY.length > 0;

export type NarrateKind = "ack" | "milestone" | "summary";

const SYSTEM =
  "You are the voice of NormaCore, a friendly tabletop robot arm assistant talking out loud to the " +
  "person in front of you. Speak in short, natural, SPOKEN sentences in the first person (\"I'm…\", " +
  "\"I just…\"). Be warm and a little playful, never robotic. No markdown, no emojis, no lists, no " +
  "stage directions. You narrate what you are physically doing on the table.";

function userPrompt(kind: NarrateKind, transcript: string, recentlySaid: string[]): string {
  const said = recentlySaid.length
    ? `\n\nYou've recently said (do NOT repeat these):\n- ${recentlySaid.join("\n- ")}`
    : "";
  if (kind === "ack") {
    return (
      `The person just said:\n${transcript}\n\n` +
      `Reply with ONE short, friendly line acknowledging it and what you're about to do.` +
      said
    );
  }
  if (kind === "milestone") {
    return (
      `Here's what's happened so far on the current task:\n${transcript}\n\n` +
      `Say ONE short, fresh line about what you're doing RIGHT NOW. If there's nothing new worth ` +
      `saying out loud, reply with exactly "-".` +
      said
    );
  }
  return (
    `The task just finished. Here is the full log of what happened:\n${transcript}\n\n` +
    `Give a warm, brief spoken wrap-up (1-2 sentences) telling the person what you did and how it ` +
    `turned out.` +
    said
  );
}

/** Returns a spoken line, or "" if disabled / nothing to say / on error. */
export async function narrate(opts: {
  kind: NarrateKind;
  transcript: string;
  recentlySaid: string[];
  signal?: AbortSignal;
}): Promise<string> {
  if (!KEY || !opts.transcript.trim()) return "";
  try {
    const res = await fetch("https://api.openai.com/v1/chat/completions", {
      method: "POST",
      headers: { Authorization: `Bearer ${KEY}`, "Content-Type": "application/json" },
      body: JSON.stringify({
        model: MODEL,
        messages: [
          { role: "system", content: SYSTEM },
          { role: "user", content: userPrompt(opts.kind, opts.transcript, opts.recentlySaid) },
        ],
        max_tokens: 80,
        temperature: 0.7,
      }),
      signal: opts.signal,
    });
    if (!res.ok) return "";
    const data = (await res.json()) as {
      choices?: { message?: { content?: string } }[];
    };
    const line = (data.choices?.[0]?.message?.content ?? "").trim();
    return line === "-" ? "" : line;
  } catch {
    return "";
  }
}
