import { describe, expect, it, vi } from "vitest";

import { startCapture } from "./capture";

class FakeProcessor {
  onaudioprocess: ((event: { inputBuffer: { getChannelData: (c: number) => Float32Array } }) => void) | null =
    null;
  connect = vi.fn();
  disconnect = vi.fn();

  emit(samples: Float32Array) {
    this.onaudioprocess?.({ inputBuffer: { getChannelData: () => samples } });
  }
}

function fakeContext(sampleRate = 48000) {
  const processor = new FakeProcessor();
  const source = { connect: vi.fn(), disconnect: vi.fn() };
  const sink = { gain: { value: 1 }, connect: vi.fn(), disconnect: vi.fn() };
  const destination = { id: 'destination' };
  const context = {
    sampleRate,
    destination,
    resume: vi.fn(async () => undefined),
    close: vi.fn(async () => undefined),
    createMediaStreamSource: vi.fn(() => source),
    createScriptProcessor: vi.fn(() => processor),
    createGain: vi.fn(() => sink),
    // audioWorklet is intentionally missing: this covers the fallback branch.
  } as unknown as AudioContext;
  return { context, processor, source, sink, destination };
}

function fakeDevices() {
  const track = { stop: vi.fn() };
  return {
    track,
    mediaDevices: {
      getUserMedia: vi.fn(async () => ({ getTracks: () => [track] }) as unknown as MediaStream),
    },
  };
}

describe("startCapture", () => {
  it("converts microphone audio into 16 kHz frames", async () => {
    const { context, processor } = fakeContext();
    const { mediaDevices } = fakeDevices();
    const frames: Int16Array[] = [];

    const handle = await startCapture({
      onFrame: (frame) => frames.push(frame),
      frameSamples: 4,
      audioContextFactory: () => context,
      mediaDevices: mediaDevices as unknown as MediaDevices,
    });

    processor.emit(new Float32Array(48000).fill(0.5).slice(0, 48)); // 1 ms @48k -> 16 samples @16k

    expect(handle.usingWorklet).toBe(false);
    expect(handle.sampleRate).toBe(48000);
    expect(frames.map((frame) => frame.length)).toEqual([4, 4, 4, 4]);
    expect(Array.from(frames[0]!)).toEqual([16384, 16384, 16384, 16384]);
  });

  it("keeps the capture node on a path to the destination (or nothing ever fires)", async () => {
    const { context, processor, sink, destination } = fakeContext();
    const { mediaDevices } = fakeDevices();

    await startCapture({
      onFrame: () => undefined,
      audioContextFactory: () => context,
      mediaDevices: mediaDevices as unknown as MediaDevices,
    });

    // A real browser only calls process()/onaudioprocess for nodes that reach the
    // destination; the sink is muted so the microphone is not echoed to the speakers.
    expect(processor.connect).toHaveBeenCalledWith(sink);
    expect(sink.connect).toHaveBeenCalledWith(destination);
    expect(sink.gain.value).toBe(0);
  });


  it("flushes the tail and releases the microphone on stop", async () => {
    // 16 kHz input keeps the tail-padding assertion about padding, not resampling.
    const { context, processor, source, sink } = fakeContext(16000);
    const { mediaDevices, track } = fakeDevices();
    const frames: Int16Array[] = [];

    const handle = await startCapture({
      onFrame: (frame) => frames.push(frame),
      frameSamples: 4,
      audioContextFactory: () => context,
      mediaDevices: mediaDevices as unknown as MediaDevices,
    });
    processor.emit(new Float32Array([0.5, 0.5, 0.5]));

    handle.stop();

    expect(frames).toHaveLength(1);
    expect(Array.from(frames[0]!)).toEqual([16384, 16384, 16384, 0]);
    expect(track.stop).toHaveBeenCalledTimes(1);
    expect(processor.disconnect).toHaveBeenCalled();
    expect(source.disconnect).toHaveBeenCalled();
    expect(sink.disconnect).toHaveBeenCalled();
    expect(context.close).toHaveBeenCalled();
  });

  it("surfaces a rejected permission request", async () => {
    const { context } = fakeContext();
    const mediaDevices = {
      getUserMedia: vi.fn(async () => {
        throw new Error("NotAllowedError");
      }),
    };

    await expect(
      startCapture({
        onFrame: () => undefined,
        audioContextFactory: () => context,
        mediaDevices: mediaDevices as unknown as MediaDevices,
      }),
    ).rejects.toThrow("NotAllowedError");
  });
});
