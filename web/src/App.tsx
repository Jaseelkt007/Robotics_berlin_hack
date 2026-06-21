import { useState } from "react";
import Sidebar, { type View } from "./components/Sidebar";
import TopBar from "./components/TopBar";
import ChatPanel from "./components/ChatPanel";
import VoicePanel from "./components/VoicePanel";
import SettingsView from "./components/SettingsView";
import { useChat } from "./lib/useChat";
import { useVoice } from "./lib/useVoice";

const TITLES: Record<View, string> = {
  assistant: "Assistant",
  settings: "Settings",
};

export default function App() {
  const chat = useChat();
  const voice = useVoice(chat);
  const [view, setView] = useState<View>("assistant");

  return (
    <div className="flex h-full overflow-hidden">
      <Sidebar active={view} onSelect={setView} />
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        <TopBar connected={chat.connected} title={TITLES[view]} />

        <main className="scroll-slim min-h-0 flex-1 overflow-y-auto px-6 py-5">
          {view === "assistant" && (
            // Conversation is the hero in the middle; voice agent rides alongside.
            <div className="grid h-full min-h-0 grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1.7fr)_minmax(0,360px)] lg:grid-rows-1">
              <ChatPanel chat={chat} />
              <VoicePanel chat={chat} voice={voice} />
            </div>
          )}

          {view === "settings" && <SettingsView connected={chat.connected} />}
        </main>
      </div>
    </div>
  );
}
