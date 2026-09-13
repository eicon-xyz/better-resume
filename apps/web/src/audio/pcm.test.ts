import { describe, expect, it } from "vitest";

import { FrameSlicer, encodePcm16, resampleTo16k } from "./pcm";

function sine(sampleRate: number, frequency: number, seconds: number): Float32Array {
  const length = Math.round(sampleRate * seconds);
  const samples = new Float32Array(length);
  for (let index = 0; index < length; index += 1) {
    samples[index] = Math.sin((2 * Math.PI * frequency * index) / sampleRate);
  }
  return samples;
}

function zeroCrossings(samples: Float32Array): number {
  let crossings = 0;
  for (let index = 1; index < samples.length; index += 1) {
    if ((samples[index - 1] ?? 0) < 0 !== (samples[index] ?? 0) < 0) crossings += 1;
  }
  return crossings;
}

describe("resampleTo16k", () => {
  it("passes 16 kHz input through untouched", () => {
    const input = new Float32Array([0.1, 0.2, 0.3]);
    expect(resampleTo16k(input, 16000)).toEqual(input);
  });

  it("shrinks 48 kHz audio to a third of the samples", () => {
    const input = sine(48000, 1000, 0.1);
    const output = resampleTo16k(input, 48000);
    expect(output.length).toBe(Math.floor(input.length / 3));
  });

  it("keeps a 1 kHz tone at 1 kHz", () => {
    const output = resampleTo16k(sine(48000, 1000, 0.1), 48000);
    // 0.1 s of 1 kHz = 100 cycles = 200 zero crossings (±2 for edges).
    expect(zeroCrossings(output)).toBeGreaterThanOrEqual(198);
    expect(zeroCrossings(output)).toBeLessThanOrEqual(202);
  });

  it("handles 44.1 kHz and empty input", () => {
    const output = resampleTo16k(sine(44100, 440, 0.05), 44100);
    expect(output.length).toBeGreaterThan(700);
    expect(output.length).toBeLessThan(810);
    expect(resampleTo16k(new Float32Array(0), 48000).length).toBe(0);
  });

  it("refuses a nonsense sample rate", () => {
    expect(() => resampleTo16k(new Float32Array(4), 0)).toThrow(/sample rate/);
  });
});

describe("encodePcm16", () => {
  it("maps the range without overflowing", () => {
    const encoded = encodePcm16(new Float32Array([0, 1, -1, 2, -2, 0.5]));
    expect(Array.from(encoded)).toEqual([0, 32767, -32767, 32767, -32767, 16384]);
  });
});

describe("FrameSlicer", () => {
  it("emits 40 ms frames and keeps the remainder", () => {
    const slicer = new FrameSlicer(640);
    const frames = slicer.push(new Int16Array(1500));

    expect(frames.map((frame) => frame.length)).toEqual([640, 640]);
    expect(slicer.pendingSamples).toBe(220);
  });

  it("zero-pads the tail on flush so the vendor always gets a full frame", () => {
    const slicer = new FrameSlicer(640);
    slicer.push(Int16Array.from([1, 2, 3]));

    const tail = slicer.flush();

    expect(tail?.length).toBe(640);
    expect(Array.from(tail!.slice(0, 3))).toEqual([1, 2, 3]);
    expect(tail?.[639]).toBe(0);
    expect(slicer.flush()).toBeNull();
  });
});
