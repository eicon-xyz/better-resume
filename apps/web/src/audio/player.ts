/**
 * One player for question playback (D15). Keeps a single Audio element, caches object
 * URLs per text+voice, unlocks autoplay on the first gesture and never leaves a blob
 * behind on unmount (§7.5's lessons).
 */

export type PlayerState = "idle" | "loading" | "playing" | "error";

export interface TtsRequest {
  text: string;
  voice?: string | null;
  cacheKey: string;
}

export interface PlayerDeps {
  load: (request: TtsRequest) => Promise<Blob>;
  createAudio?: () => HTMLAudioElement;
  createObjectURL?: (blob: Blob) => string;
  revokeObjectURL?: (url: string) => void;
  canPlayTimeoutMs?: number;
  setTimer?: (fn: () => void, ms: number) => unknown;
  clearTimer?: (handle: unknown) => void;
}

export interface TtsPlayer {
  primeFromGesture(): Promise<void>;
  play(request: TtsRequest): Promise<void>;
  stop(): void;
  dispose(): void;
  readonly state: PlayerState;
  readonly error: string | null;
  readonly source: string | null;
}

function silentWav(): Blob {
  // 0.1 s of silence is enough to satisfy the autoplay policy in Chrome/Edge.
  const samples = 800;
  const buffer = new ArrayBuffer(44 + samples * 2);
  const view = new DataView(buffer);
  const writeAscii = (offset: number, text: string) => {
    for (let index = 0; index < text.length; index += 1) {
      view.setUint8(offset + index, text.charCodeAt(index));
    }
  };
  writeAscii(0, "RIFF");
  view.setUint32(4, 36 + samples * 2, true);
  writeAscii(8, "WAVEfmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, 8000, true);
  view.setUint32(28, 16000, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeAscii(36, "data");
  view.setUint32(40, samples * 2, true);
  return new Blob([buffer], { type: "audio/wav" });
}

export function createTtsPlayer(deps: PlayerDeps): TtsPlayer {
  const {
    load,
    createAudio = () => new Audio(),
    createObjectURL = (blob) => URL.createObjectURL(blob),
    revokeObjectURL = (url) => URL.revokeObjectURL(url),
    canPlayTimeoutMs = 3000,
    setTimer = (fn, ms) => setTimeout(fn, ms),
    clearTimer = (handle) => clearTimeout(handle as ReturnType<typeof setTimeout>),
  } = deps;

  const urls = new Map<string, string>();
  let audio: HTMLAudioElement | null = null;
  let state: PlayerState = "idle";
  let error: string | null = null;
  let source: string | null = null;
  let primed = false;

  const element = () => {
    audio ??= createAudio();
    return audio;
  };

  const urlFor = async (request: TtsRequest): Promise<string> => {
    const cached = urls.get(request.cacheKey);
    if (cached) return cached;
    const blob = await load(request);
    const url = createObjectURL(blob);
    urls.set(request.cacheKey, url);
    return url;
  };

  return {
    get state() {
      return state;
    },
    get error() {
      return error;
    },
    get source() {
      return source;
    },

    async primeFromGesture() {
      if (primed) return;
      primed = true;
      const unlock = element();
      const url = createObjectURL(silentWav());
      try {
        unlock.src = url;
        unlock.volume = 0;
        await unlock.play().catch(() => undefined);
      } finally {
        unlock.pause();
        unlock.volume = 1;
        revokeObjectURL(url);
      }
    },

    async play(request: TtsRequest) {
      state = "loading";
      error = null;
      try {
        const url = await urlFor(request);
        const target = element();
        target.src = url;
        source = url;
        await new Promise<void>((resolve, reject) => {
          const timer = setTimer(() => reject(new Error("音频加载超时")), canPlayTimeoutMs);
          target.oncanplaythrough = () => {
            clearTimer(timer);
            resolve();
          };
          target.onerror = () => {
            clearTimer(timer);
            reject(new Error("音频无法播放"));
          };
          target.load();
        });
        await target.play();
        state = "playing";
      } catch (caught) {
        state = "error";
        error = caught instanceof Error ? caught.message : "播报失败";
      }
    },

    stop() {
      if (audio) {
        audio.pause();
        audio.currentTime = 0;
      }
      if (state === "playing" || state === "loading") state = "idle";
    },

    dispose() {
      this.stop();
      for (const url of urls.values()) revokeObjectURL(url);
      urls.clear();
      audio = null;
      source = null;
      state = "idle";
    },
  };
}
