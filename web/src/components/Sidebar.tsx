import { MessagesSquare, Settings, ChevronsUpDown } from "lucide-react";
import type { ComponentType } from "react";

export type View = "assistant" | "settings";

interface NavItem {
  id: View;
  label: string;
  icon: ComponentType<{ size?: number; className?: string }>;
}
interface NavGroup {
  title?: string;
  items: NavItem[];
}

const GROUPS: NavGroup[] = [
  { title: "Operate", items: [{ id: "assistant", label: "Assistant", icon: MessagesSquare }] },
];

export default function Sidebar({
  active,
  onSelect,
}: {
  active: View;
  onSelect: (v: View) => void;
}) {
  return (
    <aside className="flex w-60 shrink-0 flex-col border-r border-line bg-white">
      <div className="flex h-14 items-center gap-2 px-5">
        <div className="h-5 w-5 rounded-[6px] bg-ink" />
        <span className="text-[15px] font-semibold tracking-tightish">NormaCore</span>
      </div>

      <div className="px-3 pb-2">
        <button className="flex w-full items-center justify-between rounded-lg border border-line px-3 py-2 text-sm hover:bg-panel">
          <span className="flex items-center gap-2">
            <span className="h-4 w-4 rounded-full bg-gradient-to-br from-emerald-400 to-sky-500" />
            <span className="font-medium">Robot Station</span>
          </span>
          <ChevronsUpDown size={14} className="text-faint" />
        </button>
      </div>

      <nav className="flex-1 overflow-y-auto px-3 py-2">
        {GROUPS.map((group, gi) => (
          <div key={gi} className="mb-4">
            {group.title && (
              <div className="px-2 pb-1 text-[11px] font-medium uppercase tracking-wide text-faint">
                {group.title}
              </div>
            )}
            {group.items.map((it) => {
              const Icon = it.icon;
              const isActive = active === it.id;
              return (
                <button
                  key={it.id}
                  onClick={() => onSelect(it.id)}
                  className={
                    "flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm " +
                    (isActive
                      ? "bg-panel font-medium text-ink"
                      : "text-muted hover:bg-panel hover:text-ink")
                  }
                >
                  <Icon size={16} className={isActive ? "text-ink" : "text-faint"} />
                  {it.label}
                </button>
              );
            })}
          </div>
        ))}
      </nav>

      <div className="border-t border-line p-3">
        <button
          onClick={() => onSelect("settings")}
          className={
            "flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm " +
            (active === "settings"
              ? "bg-panel font-medium text-ink"
              : "text-muted hover:bg-panel hover:text-ink")
          }
        >
          <Settings size={16} className={active === "settings" ? "text-ink" : "text-faint"} />
          Settings
        </button>
      </div>
    </aside>
  );
}
