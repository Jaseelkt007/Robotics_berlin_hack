const AGENT_WS = import.meta.env.VITE_AGENT_WS ?? "ws://localhost:8770/chat";
const VIEWER_URL = import.meta.env.VITE_VIEWER_URL ?? "";

function Row({ label, value, ok }: { label: string; value: string; ok?: boolean }) {
  return (
    <div className="flex items-center justify-between border-b border-line py-3 last:border-0">
      <span className="text-[13px] text-muted">{label}</span>
      <span className="flex items-center gap-2 text-[13px] text-ink">
        {ok !== undefined && (
          <span className={"h-1.5 w-1.5 rounded-full " + (ok ? "bg-emerald-500" : "bg-faint")} />
        )}
        <code className="rounded bg-panel px-1.5 py-0.5 text-[12px]">{value || "— not set —"}</code>
      </span>
    </div>
  );
}

export default function SettingsView({ connected }: { connected: boolean }) {
  return (
    <div className="mx-auto max-w-2xl">
      <div className="rounded-xl border border-line bg-white p-5">
        <h2 className="text-[15px] font-semibold tracking-tightish">Connections</h2>
        <p className="mt-1 text-[13px] text-muted">
          Endpoints this dashboard talks to. Set these in <code>web/.env</code> (see{" "}
          <code>.env.example</code>).
        </p>
        <div className="mt-4">
          <Row label="Robot brain (WebSocket)" value={AGENT_WS} ok={connected} />
          <Row label="station-viewer (embed)" value={VIEWER_URL} ok={!!VIEWER_URL} />
        </div>
      </div>

      <div className="mt-4 rounded-xl border border-line bg-white p-5 text-[13px] text-muted">
        <h2 className="text-[15px] font-semibold tracking-tightish text-ink">Tips</h2>
        <ul className="mt-3 list-disc space-y-1.5 pl-5">
          <li>
            Start the brain: <code>cd agent_service &amp;&amp; uv run python server.py</code> (uses your
            Claude subscription).
          </li>
          <li>
            For live cameras &amp; calibration, run station-viewer and set{" "}
            <code>VITE_VIEWER_URL=http://localhost:5173</code>.
          </li>
        </ul>
      </div>
    </div>
  );
}
