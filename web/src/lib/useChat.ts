import { useCallback, useEffect, useRef, useState } from "react";
import type { AgentEvent, FeedItem } from "../types";

const WS_URL = import.meta.env.VITE_AGENT_WS ?? "ws://localhost:8770/chat";

let _seq = 0;
const nextId = () => `it_${Date.now()}_${_seq++}`;

/** Pretty tool name + flag for the noisy internal ToolSearch. */
function prettyTool(name: string): { label: string; internal: boolean } {
  if (name === "ToolSearch") return { label: "discovering tools", internal: true };
  const m = name.match(/^mcp__[^_]+(?:_[^_]+)*__(.+)$/);
  return { label: m ? m[1] : name, internal: false };
}

/** Best-effort: pull a base64 image out of an MCP tool_result content payload. */
function extractImage(content: unknown): string | undefined {
  const blocks = Array.isArray(content) ? content : [content];
  for (const b of blocks) {
    if (b && typeof b === "object") {
      const o = b as Record<string, unknown>;
      if (o.type === "image" && typeof o.data === "string") {
        return `data:${(o.mimeType as string) ?? "image/png"};base64,${o.data}`;
      }
      const src = o.source as Record<string, unknown> | undefined;
      if (o.type === "image" && src && typeof src.data === "string") {
        return `data:${(src.media_type as string) ?? "image/png"};base64,${src.data}`;
      }
    }
  }
  return undefined;
}

function summarize(content: unknown): string {
  const blocks = Array.isArray(content) ? content : [content];
  const text = blocks
    .map((b) => {
      if (b && typeof b === "object") {
        const o = b as Record<string, unknown>;
        if (typeof o.text === "string") return o.text;
      }
      return typeof b === "string" ? b : "";
    })
    .filter(Boolean)
    .join(" ");
  return text.slice(0, 200);
}

export interface ChatState {
  items: FeedItem[];
  connected: boolean;
  busy: boolean;
  send: (text: string) => void;
}

export function useChat(): ChatState {
  const [items, setItems] = useState<FeedItem[]>([]);
  const [connected, setConnected] = useState(false);
  const [busy, setBusy] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  const push = useCallback((item: FeedItem) => setItems((prev) => [...prev, item]), []);

  // Mark a running tool item done when its result arrives; attach image / summary.
  const completeTool = useCallback((toolUseId: string, content: unknown) => {
    const image = extractImage(content);
    const summary = summarize(content);
    setItems((prev) =>
      prev.map((it) =>
        it.role === "tool" && it.toolUseId === toolUseId && !it.done
          ? { ...it, done: true, image, summary: it.internal ? undefined : summary }
          : it,
      ),
    );
  }, []);

  useEffect(() => {
    let closed = false;
    let retry: ReturnType<typeof setTimeout> | undefined;

    const connect = () => {
      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;
      ws.onopen = () => setConnected(true);
      ws.onclose = () => {
        setConnected(false);
        if (!closed) retry = setTimeout(connect, 1500);
      };
      ws.onerror = () => ws.close();
      ws.onmessage = (ev) => {
        const event = JSON.parse(ev.data) as AgentEvent;
        switch (event.kind) {
          case "text":
            if (event.text.trim()) push({ id: nextId(), role: "assistant", text: event.text });
            break;
          case "thinking":
            if (event.text.trim()) push({ id: nextId(), role: "thinking", text: event.text });
            break;
          case "tool_use": {
            const { label, internal } = prettyTool(event.tool);
            push({
              id: nextId(),
              role: "tool",
              toolUseId: event.id,
              tool: label,
              input: event.input,
              internal,
              done: false,
            });
            break;
          }
          case "tool_result":
            completeTool(event.tool_use_id, event.content);
            break;
          case "error":
            push({ id: nextId(), role: "error", text: event.message });
            break;
          case "turn_end":
            // Stop any lingering spinners (defensive — every tool should already be done).
            setItems((prev) => prev.map((it) => (it.role === "tool" ? { ...it, done: true } : it)));
            setBusy(false);
            break;
          case "result":
            break;
        }
      };
    };

    connect();
    return () => {
      closed = true;
      if (retry) clearTimeout(retry);
      wsRef.current?.close();
    };
  }, [push, completeTool]);

  const send = useCallback(
    (text: string) => {
      const ws = wsRef.current;
      if (!ws || ws.readyState !== WebSocket.OPEN || !text.trim()) return;
      push({ id: nextId(), role: "user", text });
      setBusy(true);
      ws.send(JSON.stringify({ text }));
    },
    [push],
  );

  return { items, connected, busy, send };
}
