import { useState } from "react";
import Sidebar, { type View } from "./components/Sidebar";
import TopBar from "./components/TopBar";
import ChatPanel from "./components/ChatPanel";
import CameraCard from "./components/CameraCard";
import ViewerEmbed from "./components/ViewerEmbed";
import SettingsView from "./components/SettingsView";
import { useChat } from "./lib/useChat";

const TITLES: Record<View, string> = {
  assistant: "Assistant",
  station: "Live Station",
  calibration: "Calibration",
  settings: "Settings",
};

export default function App() {
  const chat = useChat();
  const [view, setView] = useState<View>("assistant");

  return (
    <div className="flex h-full">
      <Sidebar active={view} onSelect={setView} />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar connected={chat.connected} title={TITLES[view]} />

        <main className="min-h-0 flex-1 px-6 py-5">
          {view === "assistant" && (
            // Conversation is the hero; live camera alongside.
            <div className="grid h-full grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
              <ChatPanel chat={chat} />
              <CameraCard />
            </div>
          )}

          {view === "station" && (
            <ViewerEmbed
              title="Live station — cameras & motor state"
              hint="Run station-viewer (norma-core) and set VITE_VIEWER_URL to see live cameras and per-motor state here."
            />
          )}

          {view === "calibration" && (
            <ViewerEmbed
              path="/st3215-bus-calibration"
              title="Calibration"
              hint="Calibration runs against live hardware. Start station-viewer connected to the station and set VITE_VIEWER_URL."
            />
          )}

          {view === "settings" && <SettingsView connected={chat.connected} />}
        </main>
      </div>
    </div>
  );
}
