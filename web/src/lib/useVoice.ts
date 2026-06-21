import { useCallback, useEffect, useRef, useState } from "react";
import type { ChatState } from "./useChat";
import type { FeedItem } from "../types";
import { TtsPlayer, ttsConfigured } from "./tts";
import { narrate, narratorConfigured } from "./narrator";

// ─── Minimal Web Speech API typings (not in the default DOM lib) ──────────────
interface SpeechRecognitionResultLike {
  0: { transcript: string };
  isFinal: boolean;
}
interface SpeechRecognitionEventLike {
  resultIndex: number;
  results: { length: number; [i: number]: SpeechRecognitionResultLike };
}
interface SpeechRecognitionLike {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  start(): void;
  stop(): void;
  abort(): void;
  onresult: ((e: SpeechRecognitionEventLike) => void) | null;
  onend: (() => void) | null;
  onerror: ((e: { error: string }) => void) | null;
}
type SpeechRecognitionCtor = new () => SpeechRecognitionLike;
function getRecognitionCtor(): SpeechRecognitionCtor | null {
  const w = window as unknown as {
    SpeechRecognition?: SpeechRecognitionCtor;
    webkitSpeechRecognition?: SpeechRecognitionCtor;
  };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

// ─── Fallback action cues (used only when no narrator LLM is configured) ──────
const TOOL_CUES: Record<string, string> = {
  look: "Taking a look.",
  move_to_pixel: "Lining up.",
  nudge: "Adjusting my aim.",
  grasp: "Grabbing it.",
  release: "Letting go.",
  deliver: "Bringing it over.",
  drag: "Sliding it across.",
  push: "Nudging it along.",
  home: "Heading back.",
  wave: "Saying hello.",
};

/** Strip markdown so speech sounds natural; collapse whitespace. */
function forSpeech(md: string): string {
  return md
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/[*_#>]/g, "")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/\s+/g, " ")
    .trim();
}

/** Compact one-line description of a chat item for the narrator's transcript. */
function transcriptLine(it: FeedItem): string | null {
  if (it.role === "user") return `Person: "${it.text}"`;
  if (it.role === "assistant") {
    const t = forSpeech(it.text);
    return t ? `(my note) ${t}` : null;
  }
  if (it.role === "tool" && !it.internal) {
    const input = it.input;
    let args = "";
    if (input && typeof input === "object" && !Array.isArray(input)) {
      args = Object.entries(input as Record<string, unknown>)
        .map(([k, v]) => `${k}=${typeof v === "string" ? v : JSON.stringify(v)}`)
        .join(", ");
    }
    return `Action: ${it.tool}(${args})`;
  }
  return null;
}

export type VoiceState = "idle" | "listening" | "thinking" | "speaking";

export interface VoiceApi {
  supported: boolean; // browser has Web Speech (mic input)
  configured: boolean; // ElevenLabs key present (voice output)
  active: boolean; // voice mode is on
  state: VoiceState;
  caption: string; // last thing said by the robot
  heard: string; // live (interim) transcript while listening
  muted: boolean; // TTS output muted
  error: string;
  enter: () => void;
  exit: () => void;
  interrupt: () => void;
  toggleMute: () => void;
}

const MILESTONE_GAP_MS = 2600; // min quiet time before a fresh play-by-play line

export function useVoice(chat: ChatState): VoiceApi {
  const [active, setActive] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [listening, setListening] = useState(false);
  const [caption, setCaption] = useState("");
  const [heard, setHeard] = useState("");
  const [muted, setMuted] = useState(false);
  const [error, setError] = useState("");

  const supported = getRecognitionCtor() !== null;
  const useNarrator = narratorConfigured();

  const ttsRef = useRef<TtsPlayer | null>(null);
  if (ttsRef.current === null) ttsRef.current = new TtsPlayer(setSpeaking);

  const recRef = useRef<SpeechRecognitionLike | null>(null);
  const runningRef = useRef(false);
  const lastIdxRef = useRef(0);

  // narrator state
  const transcriptRef = useRef<string[]>([]); // compact log of the current turn
  const saidRef = useRef<string[]>([]); // recent spoken lines (dedupe context)
  const dirtyRef = useRef(0); // new actions since last narration
  const narratingRef = useRef(false); // a narrate() call in flight
  const narratorHealthyRef = useRef(true); // false after a failed ack/summary → use cues instead
  const lastSpokeAtRef = useRef(0);
  const lastCueRef = useRef(""); // fallback-mode dedupe

  // live refs for callbacks
  const activeRef = useRef(active);
  const speakingRef = useRef(speaking);
  const busyRef = useRef(chat.busy);
  const mutedRef = useRef(muted);
  activeRef.current = active;
  speakingRef.current = speaking;
  busyRef.current = chat.busy;
  mutedRef.current = muted;

  // speak a line + record it for caption / dedupe
  const say = useCallback((line: string) => {
    const clean = line.trim();
    if (!clean) return;
    ttsRef.current?.speak(clean);
    setCaption(clean);
    saidRef.current = [...saidRef.current.slice(-5), clean];
    lastSpokeAtRef.current = Date.now();
    dirtyRef.current = 0;
  }, []);

  // ask the narrator LLM for a line, then speak it
  const runNarrate = useCallback(
    async (kind: "ack" | "milestone" | "summary") => {
      if (!useNarrator || narratingRef.current) return;
      if (!activeRef.current || mutedRef.current) return;
      narratingRef.current = true;
      try {
        const line = await narrate({
          kind,
          transcript: transcriptRef.current.join("\n"),
          recentlySaid: saidRef.current,
        });
        if (line) {
          say(line);
          narratorHealthyRef.current = true;
        } else if (kind !== "milestone") {
          // an empty ack/summary almost always means the narrator call failed
          // (bad key, quota, CORS) — fall back to speaking cues/replies directly
          narratorHealthyRef.current = false;
        }
      } finally {
        narratingRef.current = false;
      }
    },
    [useNarrator, say],
  );

  // ── Observe chat items: build transcript + narrate (or fall back to cues) ──
  useEffect(() => {
    for (let i = lastIdxRef.current; i < chat.items.length; i++) {
      const it = chat.items[i];

      if (useNarrator && narratorHealthyRef.current) {
        if (it.role === "user") {
          transcriptRef.current = [`Person: "${it.text}"`];
          dirtyRef.current = 0;
          lastCueRef.current = "";
          void runNarrate("ack");
          continue;
        }
        const line = transcriptLine(it);
        if (line) transcriptRef.current.push(line);
        if (it.role === "tool" && !it.internal) dirtyRef.current += 1;
        continue;
      }

      // ── Fallback (no narrator): speak short replies + action cues ──
      if (!active || muted) continue;
      if (it.role === "assistant") {
        const line = forSpeech(it.text);
        if (line) {
          // sentence-split so even a longer wrap-up gets spoken, not dropped
          line
            .split(/(?<=[.!?])\s+/)
            .slice(0, 6)
            .forEach((s) => ttsRef.current?.speak(s));
          setCaption(line);
        }
      } else if (it.role === "tool" && !it.internal) {
        const cue = TOOL_CUES[it.tool];
        if (cue && cue !== lastCueRef.current) {
          lastCueRef.current = cue;
          ttsRef.current?.speak(cue);
          setCaption(cue);
        }
      } else if (it.role === "user") {
        lastCueRef.current = "";
      }
    }
    lastIdxRef.current = chat.items.length;
  }, [chat.items, active, muted, useNarrator, runNarrate]);

  // ── Turn end → spoken summary (narrator only) ──────────────────────────────
  const prevBusyRef = useRef(chat.busy);
  useEffect(() => {
    if (useNarrator && prevBusyRef.current && !chat.busy && activeRef.current) {
      void runNarrate("summary");
    }
    prevBusyRef.current = chat.busy;
  }, [chat.busy, useNarrator, runNarrate]);

  // ── Milestone play-by-play: narrate into quiet gaps while the robot works ──
  useEffect(() => {
    if (!useNarrator) return;
    const id = setInterval(() => {
      const tts = ttsRef.current;
      if (!activeRef.current || mutedRef.current || !busyRef.current) return;
      if (!tts || tts.isSpeaking || narratingRef.current || dirtyRef.current === 0) return;
      if (Date.now() - lastSpokeAtRef.current < MILESTONE_GAP_MS) return;
      void runNarrate("milestone");
    }, 1200);
    return () => clearInterval(id);
  }, [useNarrator, runNarrate]);

  // ── Listening loop: mic on only when idle (not busy, not speaking) ─────────
  const kickListen = useCallback(() => {
    if (!activeRef.current || mutedRef.current) return;
    if (speakingRef.current || busyRef.current) return;
    if (runningRef.current) return;
    const Ctor = getRecognitionCtor();
    if (!Ctor) return;
    let rec = recRef.current;
    if (!rec) {
      rec = new Ctor();
      rec.lang = "en-US";
      rec.continuous = false;
      rec.interimResults = true;
      rec.onresult = (e) => {
        let interim = "";
        let final = "";
        for (let i = e.resultIndex; i < e.results.length; i++) {
          const r = e.results[i];
          if (r.isFinal) final += r[0].transcript;
          else interim += r[0].transcript;
        }
        setHeard(interim || final);
        if (final.trim()) {
          setHeard("");
          chat.send(final.trim());
        }
      };
      rec.onerror = (ev) => {
        if (ev.error !== "no-speech" && ev.error !== "aborted") setError(ev.error);
      };
      rec.onend = () => {
        runningRef.current = false;
        setListening(false);
        if (activeRef.current && !speakingRef.current && !busyRef.current && !mutedRef.current) {
          setTimeout(kickListen, 250);
        }
      };
      recRef.current = rec;
    }
    try {
      rec.start();
      runningRef.current = true;
      setListening(true);
      setError("");
    } catch {
      // already started — ignore
    }
  }, [chat]);

  useEffect(() => {
    if (active && !speaking && !chat.busy && !muted) {
      kickListen();
    } else if (recRef.current && runningRef.current) {
      recRef.current.abort();
    }
  }, [active, speaking, chat.busy, muted, kickListen]);

  const enter = useCallback(() => {
    setActive(true);
    setError("");
  }, []);

  const exit = useCallback(() => {
    setActive(false);
    ttsRef.current?.stop();
    if (recRef.current && runningRef.current) recRef.current.abort();
    setListening(false);
    setHeard("");
  }, []);

  const interrupt = useCallback(() => {
    ttsRef.current?.stop();
    chat.stop();
  }, [chat]);

  const toggleMute = useCallback(() => {
    setMuted((m) => {
      const next = !m;
      if (next) ttsRef.current?.stop();
      return next;
    });
  }, []);

  let state: VoiceState = "idle";
  if (active) {
    if (speaking) state = "speaking";
    else if (chat.busy) state = "thinking";
    else if (listening) state = "listening";
  }

  return {
    supported,
    configured: ttsConfigured(),
    active,
    state,
    caption,
    heard,
    muted,
    error,
    enter,
    exit,
    interrupt,
    toggleMute,
  };
}
