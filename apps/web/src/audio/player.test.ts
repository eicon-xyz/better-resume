import { describe, expect, it, vi } from "vitest";

import { createTtsPlayer } from "./player";

class FakeAudio {
  src = "";
  volume = 1;
  currentTime = 0;
  paused = true;
  oncanplaythrough: (() => void) | null = null;
  onerror: (() => void) | null = null;
  play = vi.fn(async () => {
    this.paused = false;
  });
  pause = vi.fn(() => {
    this.paused = true;
  });
  load = vi.fn(() => {
    this.oncanplaythrough?.();
  });

  static instances: FakeAudio[] = [];
  constructor() {
    FakeAudio.instances.push(this);
  }
}

function deps(overrides: Record<string, unknown> = {}) {
  const load = vi.fn(async () => new Blob([new Uint8Array([1, 2, 3])]));
  const revoked: string[] = [];
  let counter = 0;
  return {
    load,
    revoked,
    deps: {
      load,
      createAudio: () => new FakeAudio() as unknown as HTMLAudioElement,
      createObjectURL: () => `blob:fake/${(counter += 1)}`,
      revokeObjectURL: (url: string) => revoked.push(url),
      ...overrides,
    },
  };
}

describe("createTtsPlayer", () => {
  it("reuses one audio element and reuses the cached blob", async () => {
    FakeAudio.instances = [];
    const { load, deps: playerDeps } = deps();
    const player = createTtsPlayer(playerDeps);

    await player.play({ text: "第一题", cacheKey: "k1" });
    await player.play({ text: "第一题", cacheKey: "k1" });

    expect(FakeAudio.instances).toHaveLength(1);
    expect(load).toHaveBeenCalledTimes(1);
    expect(player.state).toBe("playing");
  });

  it("loads once per cache key", async () => {
    const { load, deps: playerDeps } = deps();
    const player = createTtsPlayer(playerDeps);

    await player.play({ text: "第一题", cacheKey: "k1" });
    await player.play({ text: "第二题", cacheKey: "k2" });

    expect(load).toHaveBeenCalledTimes(2);
  });

  it("unlocks autoplay once, on the first gesture", async () => {
    const { deps: playerDeps } = deps();
    const player = createTtsPlayer(playerDeps);

    await player.primeFromGesture();
    await player.primeFromGesture();

    const element = FakeAudio.instances.at(-1)!;
    expect(element.play).toHaveBeenCalledTimes(1);
    expect(element.paused).toBe(true); // the silent primer stops itself
  });

  it("fails loudly when the file never becomes playable", async () => {
    const timers: Array<() => void> = [];
    const { deps: playerDeps } = deps({
      createAudio: () =>
        ({
          play: vi.fn(async () => undefined),
          pause: vi.fn(),
          load: vi.fn(), // never fires canplaythrough
        }) as unknown as HTMLAudioElement,
      createObjectURL: () => "blob:fake/timeout",
      revokeObjectURL: () => undefined,
      setTimer: (fn: () => void) => {
        timers.push(fn);
        return 0;
      },
    });
    const player = createTtsPlayer(playerDeps);

    const playing = player.play({ text: "卡住", cacheKey: "k" });
    // play() awaits the blob first, so the timeout is only armed a tick later.
    await vi.waitFor(() => expect(timers).toHaveLength(1));
    timers.forEach((fn) => fn());
    await playing;

    expect(player.state).toBe("error");
    expect(player.error).toBe("音频加载超时");
  });

  it("stops playback and revokes every blob on dispose", async () => {
    const { revoked, deps: playerDeps } = deps();
    const player = createTtsPlayer(playerDeps);
    await player.play({ text: "一", cacheKey: "k1" });
    await player.play({ text: "二", cacheKey: "k2" });
    const first = FakeAudio.instances.at(-1)!;
    first.paused = false;

    player.stop();
    player.dispose();

    expect(first.pause).toHaveBeenCalled();
    expect(revoked.length).toBeGreaterThanOrEqual(2);
    expect(player.state).toBe("idle");
  });
});
