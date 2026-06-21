import { AudioLines, Mic, MicOff, PhoneOff, Hand, AlertTriangle } from "lucide-react";
import type { ChatState } from "../lib/useChat";
import type { VoiceApi, VoiceState } from "../lib/useVoice";

const STATE_COPY: Record<VoiceState, string> = {
  idle: "Tap to talk",
  listening: "Listening…",
  thinking: "Working…",
  speaking: "Speaking…",
};

// orb gradient per state (matches the design tokens)
const ORB: Record<VoiceState, string> = {
  idle: "from-gray-200 to-gray-300",
  listening: "from-sky-300 to-blue-500",
  thinking: "from-amber-300 to-orange-500",
  speaking: "from-emerald-300 to-teal-500",
};

/** Audio-style equalizer — animates while speaking or listening. */
function Equalizer({ on, tint }: { on: boolean; tint: string }) {
  return (
    <div className={`flex h-7 items-end justify-center gap-1 ${tint}`}>
      {[0, 1, 2, 3, 4, 5, 6].map((i) => (
        <span
          key={i}
          className={"w-1.5 origin-bottom rounded-full bg-current " + (on ? "animate-eq" : "")}
          style={{
            height: "100%",
            transform: on ? undefined : "scaleY(0.25)",
            animationDelay: `${(i % 4) * 0.12}s`,
            opacity: on ? 1 : 0.4,
          }}
        />
      ))}
    </div>
  );
}

function Orb({ state, onClick }: { state: VoiceState; onClick: () => void }) {
  const active = state === "listening" || state === "speaking";
  return (
    <button
      onClick={onClick}
      title={state === "idle" ? "Start" : "Tap to interrupt"}
      className="relative flex h-44 w-44 items-center justify-center"
    >
      {/* expanding rings while active */}
      {active && (
        <>
          <span
            className={`absolute inset-2 rounded-full bg-gradient-to-br ${ORB[state]} opacity-25 blur-lg animate-ping`}
          />
          <span
            className={`absolute inset-6 rounded-full bg-gradient-to-br ${ORB[state]} opacity-30 blur-md animate-ping`}
            style={{ animationDelay: "0.4s" }}
          />
        </>
      )}
      {/* soft halo */}
      <span
        className={`absolute inset-5 rounded-full bg-gradient-to-br ${ORB[state]} opacity-40 blur-md ${
          state === "thinking" ? "animate-spin-slow" : state === "idle" ? "animate-breathe" : "animate-pulse"
        }`}
      />
      {/* core */}
      <span
        className={`relative flex h-28 w-28 items-center justify-center rounded-full bg-gradient-to-br ${ORB[state]} shadow-lg transition-all ${
          state === "idle" ? "animate-breathe" : ""
        }`}
      >
        <AudioLines size={34} className="text-white/90" />
      </span>
    </button>
  );
}

function lastAction(chat: ChatState): string | null {
  for (let i = chat.items.length - 1; i >= 0; i--) {
    const it = chat.items[i];
    if (it.role === "tool" && !it.internal) return it.tool + (it.done ? "" : " …");
  }
  return null;
}

export default function VoicePanel({ chat, voice }: { chat: ChatState; voice: VoiceApi }) {
  const tint =
    voice.state === "speaking"
      ? "text-emerald-500"
      : voice.state === "listening"
        ? "text-blue-500"
        : "text-faint";

  return (
    <aside className="flex h-full min-h-0 flex-col rounded-xl border border-line bg-white">
      <div className="flex items-center justify-between border-b border-line px-4 py-3">
        <span className="flex items-center gap-2 text-[13px] font-semibold tracking-tightish">
          <AudioLines size={14} className="text-faint" />
          Voice agent
        </span>
        <span className="flex items-center gap-1.5 text-[12px] text-faint">
          <span
            className={"h-1.5 w-1.5 rounded-full " + (chat.connected ? "bg-emerald-500" : "bg-faint")}
          />
          {voice.active ? STATE_COPY[voice.state] : "off"}
        </span>
      </div>

      {/* Stage */}
      <div className="flex min-h-0 flex-1 flex-col items-center justify-center px-5 py-4">
        <Orb state={voice.state} onClick={voice.active ? voice.interrupt : voice.enter} />

        <div className="mt-4">
          <Equalizer
            on={voice.state === "speaking" || voice.state === "listening"}
            tint={tint}
          />
        </div>

        {/* live transcript while listening */}
        <div className="mt-3 h-5 text-center text-[13.5px] text-accent">{voice.heard}</div>

        {/* last thing the robot said */}
        <p className="mt-1 min-h-[3rem] max-w-[18rem] text-center text-[13.5px] text-muted">
          {voice.active ? voice.caption || "—" : "Start to talk with the robot."}
        </p>

        {voice.error && <p className="mt-1 text-[12px] text-red-600">mic: {voice.error}</p>}
      </div>

      {/* Now-doing line */}
      <div className="flex items-center justify-between border-t border-line px-4 py-2.5 text-[12.5px]">
        <span className="text-faint">Now</span>
        <span className="font-medium text-ink">{lastAction(chat) ?? "idle"}</span>
      </div>

      {/* Controls */}
      <div className="border-t border-line px-4 py-3">
        {voice.active ? (
          <div className="flex items-center justify-center gap-3">
            <button
              onClick={voice.toggleMute}
              title={voice.muted ? "Unmute voice" : "Mute voice"}
              className={
                "flex h-10 w-10 items-center justify-center rounded-full border " +
                (voice.muted
                  ? "border-red-200 bg-red-50 text-red-600"
                  : "border-line bg-white text-ink hover:bg-panel")
              }
            >
              {voice.muted ? <MicOff size={16} /> : <Mic size={16} />}
            </button>
            <button
              onClick={voice.interrupt}
              title="Interrupt the current task"
              className="flex h-10 items-center gap-2 rounded-full border border-line bg-white px-4 text-[13px] font-medium text-ink hover:bg-panel"
            >
              <Hand size={15} /> Interrupt
            </button>
            <button
              onClick={voice.exit}
              title="Leave voice mode"
              className="flex h-10 w-10 items-center justify-center rounded-full bg-red-600 text-white hover:bg-red-700"
            >
              <PhoneOff size={16} />
            </button>
          </div>
        ) : (
          <button
            onClick={voice.enter}
            disabled={!chat.connected}
            className="flex w-full items-center justify-center gap-2 rounded-full bg-ink px-4 py-2.5 text-[14px] font-medium text-white hover:opacity-90 disabled:opacity-40"
          >
            <Mic size={16} /> {chat.connected ? "Start voice mode" : "Connecting…"}
          </button>
        )}

        {(!voice.supported || !voice.configured) && (
          <div className="mt-3 space-y-1">
            {!voice.supported && (
              <p className="flex items-center gap-1.5 text-[11.5px] text-faint">
                <AlertTriangle size={11} /> Voice input needs Chrome/Edge.
              </p>
            )}
            {!voice.configured && (
              <p className="flex items-center gap-1.5 text-[11.5px] text-faint">
                <AlertTriangle size={11} /> Add VITE_ELEVENLABS_API_KEY for spoken replies.
              </p>
            )}
          </div>
        )}
      </div>
    </aside>
  );
}
