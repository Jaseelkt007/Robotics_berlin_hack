/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_AGENT_WS?: string;
  readonly VITE_VIEWER_URL?: string;
}
interface ImportMeta {
  readonly env: ImportMetaEnv;
}
