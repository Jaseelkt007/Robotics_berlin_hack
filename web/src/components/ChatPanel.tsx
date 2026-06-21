import { useEffect, useRef, useState } from "react";
import { ArrowUp, Brain, Check, Loader2, Search, Square, Wrench } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { FeedItem } from "../types";
import type { ChatState } from "../lib/useChat";

const SUGGESTIONS = [
  "Call look on the top camera and describe what you see",
  "Pick up the red block and place it in the tray",
  "What's the current arm state?",
];

/** Render Claude's markdown (bold, lists, code, links) instead of raw text. */
function Markdown({ text }: { text: string }) {
  return (
    <div className="md text-[14px] leading-relaxed text-ink">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
    </div>
  );
}

function formatInput(input: unknown): string {
  if (input && typeof input === "object" && !Array.isArray(input)) {
    const entries = Object.entries(input as Record<string, unknown>);
    if (entries.length === 0) return "";
    return entries.map(([k, v]) => `${k}: ${typeof v === "string" ? v : JSON.stringify(v)}`).join(", ");
  }
  return input == null ? "" : JSON.stringify(input);
}

function ToolRow({ item }: { item: Extract<FeedItem, { role: "tool" }> }) {
  // Internal SDK tool discovery — keep it as a quiet single line with a spinner while it runs.
  if (item.internal) {
    return (
      <div className="flex items-center gap-2 text-[12.5px] text-faint">
        {item.done ? <Search size={12} /> : <Loader2 size={12} className="animate-spin" />}
        <span>{item.done ? "discovered tools" : "discovering tools…"}</span>
      </div>
    );
  }

  const args = formatInput(item.input);
  return (
    <div className="space-y-2">
      <div className="inline-flex items-center gap-2 rounded-lg border border-line bg-panel px-2.5 py-1.5 text-[13px]">
        {item.done ? (
          <Check size={13} className="text-emerald-600" />
        ) : (
          <Loader2 size={13} className="animate-spin text-accent" />
        )}
        <Wrench size={12} className="text-faint" />
        <span className="font-medium text-ink">{item.tool}</span>
        {args && <span className="text-muted">· {args}</span>}
      </div>
      {item.image && (
        <img
          src={item.image}
          alt={`${item.tool} result`}
          className="block max-h-60 rounded-lg border border-line"
        />
      )}
    </div>
  );
}

function FeedRow({ item }: { item: FeedItem }) {
  switch (item.role) {
    case "user":
      return (
        <div className="flex justify-end">
          <div className="max-w-[80%] rounded-2xl rounded-br-md bg-ink px-3.5 py-2 text-[14px] text-white">
            {item.text}
          </div>
        </div>
      );
    case "assistant":
      return <Markdown text={item.text} />;
    case "thinking":
      return (
        <div className="flex items-start gap-2 text-[13px] italic text-faint">
          <Brain size={14} className="mt-0.5 shrink-0" />
          <span className="line-clamp-4">{item.text}</span>
        </div>
      );
    case "tool":
      return <ToolRow item={item} />;
    case "error":
      return (
        <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-[13px] text-red-700">
          {item.text}
        </div>
      );
  }
}

export default function ChatPanel({ chat }: { chat: ChatState }) {
  const [draft, setDraft] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [chat.items]);

  const submit = () => {
    if (!draft.trim() || chat.busy) return;
    chat.send(draft);
    setDraft("");
  };

  return (
    <div className="flex h-full flex-col rounded-xl border border-line bg-white">
      <div className="flex items-center justify-between border-b border-line px-4 py-3">
        <span className="text-[13px] font-semibold tracking-tightish">Conversation</span>
        <span className="text-[12px] text-faint">watch it think</span>
      </div>

      <div ref={scrollRef} className="scroll-slim flex-1 space-y-3.5 overflow-y-auto px-4 py-4">
        {chat.items.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center text-center">
            <Brain size={28} className="text-faint" />
            <p className="mt-3 text-[14px] text-muted">Ask the robot to do something.</p>
            <div className="mt-4 flex flex-col gap-2">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => chat.send(s)}
                  disabled={chat.busy || !chat.connected}
                  className="rounded-full border border-line px-3 py-1.5 text-[13px] text-muted hover:bg-panel hover:text-ink disabled:opacity-50"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          chat.items.map((it) => <FeedRow key={it.id} item={it} />)
        )}
        {chat.busy && (
          <div className="flex items-center gap-2 text-[13px] text-faint">
            <Loader2 size={13} className="animate-spin" />
            working…
          </div>
        )}
      </div>

      <div className="border-t border-line p-3">
        <div className="flex items-end gap-2 rounded-xl border border-line px-3 py-2 focus-within:border-faint">
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
            }}
            rows={1}
            placeholder={chat.connected ? "Message the robot…" : "Connecting to brain…"}
            disabled={!chat.connected}
            className="max-h-32 flex-1 resize-none bg-transparent text-[14px] outline-none placeholder:text-faint disabled:opacity-50"
          />
          {chat.busy ? (
            <button
              onClick={() => chat.stop()}
              title="Stop the current task"
              className="flex h-8 w-8 items-center justify-center rounded-lg bg-red-600 text-white hover:bg-red-700"
            >
              <Square size={14} fill="currentColor" />
            </button>
          ) : (
            <button
              onClick={submit}
              disabled={!draft.trim() || !chat.connected}
              className="flex h-8 w-8 items-center justify-center rounded-lg bg-ink text-white disabled:opacity-30"
            >
              <ArrowUp size={16} />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
