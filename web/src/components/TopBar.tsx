import { Bell, BookOpen, MessageSquare, Sparkles } from "lucide-react";

function Pill({ icon: Icon, label }: { icon: typeof Bell; label: string }) {
  return (
    <button className="flex items-center gap-1.5 rounded-lg border border-line bg-white px-3 py-1.5 text-[13px] font-medium text-ink hover:bg-panel">
      <Icon size={14} className="text-faint" />
      {label}
    </button>
  );
}

export default function TopBar({ connected, title }: { connected: boolean; title: string }) {
  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-line px-6">
      <div className="flex items-center gap-2 text-sm">
        <span className="font-medium">{title}</span>
        <span
          className={
            "ml-2 flex items-center gap-1.5 rounded-full border border-line px-2.5 py-1 text-[12px] " +
            (connected ? "text-ink" : "text-faint")
          }
          title={connected ? "Connected to robot brain" : "Reconnecting…"}
        >
          <span className={"h-1.5 w-1.5 rounded-full " + (connected ? "bg-emerald-500" : "bg-faint")} />
          {connected ? "Brain online" : "Connecting…"}
        </span>
      </div>
      <div className="flex items-center gap-2">
        <Pill icon={Sparkles} label="What's new" />
        <Pill icon={MessageSquare} label="Feedback" />
        <Pill icon={BookOpen} label="Docs" />
        <button className="ml-1 rounded-lg p-2 hover:bg-panel">
          <Bell size={16} className="text-muted" />
        </button>
        <div className="h-8 w-8 rounded-full bg-gradient-to-br from-zinc-700 to-zinc-900" />
      </div>
    </header>
  );
}
