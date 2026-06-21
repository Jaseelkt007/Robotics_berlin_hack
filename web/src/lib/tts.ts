// ElevenLabs streaming TTS — browser-side, fully decoupled from the brain.
// Speaks short conversational lines and supports barge-in (stop()). If the API
// key is unset, every call is a silent no-op (voice output simply disabled).

const API_KEY = import.meta.env.VITE_ELEVENLABS_API_KEY ?? "";
const VOICE_ID = import.meta.env.VITE_ELEVENLABS_VOICE_ID ?? "21m00Tcm4TlvDq8ikWAM"; // "Rachel"
const MODEL = import.meta.env.VITE_ELEVENLABS_MODEL ?? "eleven_turbo_v2_5";

export const ttsConfigured = (): boolean => API_KEY.length > 0;

type StateCb = (speaking: boolean) => void;

/**
 * A tiny sentence queue → ElevenLabs `/stream` → HTMLAudio player.
 * One line is fetched + played at a time so we can `stop()` instantly (barge-in).
 */
export class TtsPlayer {
  private queue: string[] = [];
  private playing = false;
  private audio: HTMLAudioElement | null = null;
  private abort: AbortController | null = null;
  private readonly onState: StateCb;

  constructor(onState: StateCb) {
    this.onState = onState;
  }

  /** Enqueue a line to speak. No-op if TTS isn't configured or the text is empty. */
  speak(text: string): void {
    const clean = text.trim();
    if (!clean || !ttsConfigured()) return;
    this.queue.push(clean);
    if (!this.playing) void this.drain();
  }

  /** Barge-in: drop the queue, abort any in-flight fetch, and silence playback. */
  stop(): void {
    this.queue = [];
    this.abort?.abort();
    this.abort = null;
    if (this.audio) {
      this.audio.pause();
      this.audio.src = "";
      this.audio = null;
    }
    if (this.playing) {
      this.playing = false;
      this.onState(false);
    }
  }

  get isSpeaking(): boolean {
    return this.playing;
  }

  private async drain(): Promise<void> {
    this.playing = true;
    this.onState(true);
    while (this.queue.length) {
      const line = this.queue.shift() as string;
      try {
        await this.playOne(line);
      } catch {
        // aborted (barge-in) or a network/audio error — skip this line, keep going
      }
    }
    this.playing = false;
    this.onState(false);
  }

  private async playOne(text: string): Promise<void> {
    this.abort = new AbortController();
    const res = await fetch(
      `https://api.elevenlabs.io/v1/text-to-speech/${VOICE_ID}/stream?optimize_streaming_latency=3&output_format=mp3_44100_128`,
      {
        method: "POST",
        headers: { "xi-api-key": API_KEY, "Content-Type": "application/json" },
        body: JSON.stringify({
          text,
          model_id: MODEL,
          voice_settings: {
            stability: 0.4,
            similarity_boost: 0.8,
            style: 0.35,
            use_speaker_boost: true,
          },
        }),
        signal: this.abort.signal,
      },
    );
    if (!res.ok) throw new Error(`tts ${res.status}`);
    const buf = await res.arrayBuffer();
    const url = URL.createObjectURL(new Blob([buf], { type: "audio/mpeg" }));
    await new Promise<void>((resolve, reject) => {
      const a = new Audio(url);
      this.audio = a;
      a.onended = () => {
        URL.revokeObjectURL(url);
        resolve();
      };
      a.onerror = () => {
        URL.revokeObjectURL(url);
        reject(new Error("audio playback failed"));
      };
      void a.play().catch(reject);
    });
  }
}
