// Events streamed by agent_service/server.py over ws://.../chat
export type AgentEvent =
  | { kind: "text"; text: string }
  | { kind: "thinking"; text: string }
  | { kind: "tool_use"; tool: string; input: unknown; id: string }
  | { kind: "tool_result"; tool_use_id: string; content: unknown }
  | { kind: "result"; is_error: boolean; result: string | null; session_id: string }
  | { kind: "error"; message: string }
  | { kind: "turn_end" };

// Flattened items we render in the conversation / watch-it-think feed.
export type FeedItem =
  | { id: string; role: "user"; text: string }
  | { id: string; role: "assistant"; text: string }
  | { id: string; role: "thinking"; text: string }
  | {
      id: string;
      role: "tool";
      toolUseId: string;
      tool: string;
      input: unknown;
      internal: boolean; // true for the SDK's own ToolSearch noise
      done: boolean;
      image?: string;
      summary?: string;
    }
  | { id: string; role: "error"; text: string };
