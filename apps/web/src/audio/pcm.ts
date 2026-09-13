/**
 * PCM plumbing for the transcription channel: 16 kHz mono Int16, 40 ms frames.
 *
 * The vendor wants pcm_s16le @16k in 1280-byte frames (§4.4); browsers hand us Float32 at
 * whatever the hardware runs at (44.1/48 kHz), so this module is the only place that
 * converts. Resampling is linear interpolation on purpose: it is cheap, allocation-light
 * and good enough for speech — the old project did the same on the server side.
 */

export const TARGET_SAMPLE_RATE = 16000;
export const FRAME_SAMPLES = 640; // 40 ms at 16 kHz

export function resampleTo16k(input: Float32Array, inputRate: number): Float32Array {
  if (!Number.isFinite(inputRate) || inputRate <= 0) {
    throw new Error(`invalid input sample rate: ${inputRate}`);
  }
  if (inputRate === TARGET_SAMPLE_RATE || input.length === 0) {
    return input.slice();
  }
  const ratio = inputRate / TARGET_SAMPLE_RATE;
  const outputLength = Math.floor(input.length / ratio);
  const output = new Float32Array(outputLength);

  for (let index = 0; index < outputLength; index += 1) {
    const position = index * ratio;
    const left = Math.floor(position);
    const fraction = position - left;
    const first = input[left] ?? 0;
    const second = input[left + 1] ?? first;
    output[index] = first + (second - first) * fraction;
  }
  return output;
}

export function encodePcm16(samples: Float32Array): Int16Array {
  const output = new Int16Array(samples.length);
  for (let index = 0; index < samples.length; index += 1) {
    const clamped = Math.max(-1, Math.min(1, samples[index] ?? 0));
    output[index] = Math.round(clamped * 32767);
  }
  return output;
}

/** Accumulates samples and hands out whole 40 ms frames; flush() zero-pads the tail. */
export class FrameSlicer {
  readonly frameSamples: number;
  private pending: number[] = [];

  constructor(frameSamples: number = FRAME_SAMPLES) {
    this.frameSamples = frameSamples;
  }

  push(samples: Int16Array): Int16Array[] {
    for (const sample of samples) {
      this.pending.push(sample);
    }
    const frames: Int16Array[] = [];
    while (this.pending.length >= this.frameSamples) {
      frames.push(Int16Array.from(this.pending.splice(0, this.frameSamples)));
    }
    return frames;
  }

  flush(): Int16Array | null {
    if (this.pending.length === 0) return null;
    const padded = this.pending.slice();
    while (padded.length < this.frameSamples) padded.push(0);
    this.pending = [];
    return Int16Array.from(padded);
  }

  get pendingSamples(): number {
    return this.pending.length;
  }
}
