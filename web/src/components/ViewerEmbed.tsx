import { ExternalLink, MonitorPlay } from "lucide-react";

// station-viewer (norma-core) runs its own dev server; we embed its pages here.
const VIEWER_URL = import.meta.env.VITE_VIEWER_URL ?? "";

interface Props {
  /** sub-route of station-viewer, e.g. "" (home) or "/st3215-bus-calibration" */
  path?: string;
  title: string;
  hint?: string;
}

export default function ViewerEmbed({ path = "", title, hint }: Props) {
  const src = VIEWER_URL ? `${VIEWER_URL}${path}` : "";
  return (
    <div className="flex h-full flex-col rounded-xl border border-line bg-white">
      <div className="flex items-center justify-between border-b border-line px-4 py-3">
        <span className="flex items-center gap-2 text-[13px] font-semibold tracking-tightish">
          <MonitorPlay size={14} className="text-faint" />
          {title}
        </span>
        {src && (
          <a
            href={src}
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-1 text-[12px] text-muted hover:text-ink"
          >
            open in new tab <ExternalLink size={12} />
          </a>
        )}
      </div>
      <div className="min-h-0 flex-1 overflow-hidden rounded-b-xl">
        {src ? (
          <iframe title={title} src={src} className="h-full w-full border-0" />
        ) : (
          <div className="flex h-full flex-col items-center justify-center px-8 text-center">
            <MonitorPlay size={26} className="text-faint" />
            <p className="mt-3 text-[14px] text-muted">station-viewer not embedded yet.</p>
            <p className="mt-1 max-w-md text-[12.5px] text-faint">
              {hint ??
                "Run norma-core's station-viewer and set VITE_VIEWER_URL (e.g. http://localhost:5173) so its live pages appear here."}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
