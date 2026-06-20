import { Camera, ExternalLink } from "lucide-react";

// station-viewer (norma-core) runs its own dev server; embed it for live cameras + calibration.
const VIEWER_URL = import.meta.env.VITE_VIEWER_URL ?? "";

export default function CameraCard() {
  return (
    <div className="flex h-full flex-col rounded-xl border border-line bg-white">
      <div className="flex items-center justify-between border-b border-line px-4 py-3">
        <span className="flex items-center gap-2 text-[13px] font-semibold tracking-tightish">
          <Camera size={14} className="text-faint" />
          Cameras &amp; calibration
        </span>
        {VIEWER_URL && (
          <a
            href={VIEWER_URL}
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-1 text-[12px] text-muted hover:text-ink"
          >
            open viewer <ExternalLink size={12} />
          </a>
        )}
      </div>

      <div className="flex-1 overflow-hidden rounded-b-xl">
        {VIEWER_URL ? (
          <iframe title="station-viewer" src={VIEWER_URL} className="h-full w-full border-0" />
        ) : (
          <div className="flex h-full flex-col items-center justify-center px-6 text-center">
            <Camera size={26} className="text-faint" />
            <p className="mt-3 text-[14px] text-muted">No viewer embedded yet.</p>
            <p className="mt-1 text-[12.5px] text-faint">
              Run station-viewer, then set <code className="text-muted">VITE_VIEWER_URL</code> (e.g.
              http://localhost:5173) to embed its live cameras &amp; calibration here.
            </p>
            <p className="mt-3 text-[12.5px] text-faint">
              Meanwhile, frames from <code className="text-muted">look()</code> appear inline in the
              conversation.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
