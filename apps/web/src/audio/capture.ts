/**
 * Microphone capture: browser audio APIs -> 16 kHz mono Int16 frames (40 ms).
 *
 * AudioWorklet is preferred (no main-thread jank); ScriptProcessor is the fallback for
 * browsers without it. The worklet source is inlined and loaded from a blob URL so the
 * build needs no extra asset configuration.
 */

import { FRAME_SAMPLES, FrameSlicer, encodePcm16, resampleTo16k } from "./pcm";

export interface CaptureOptions {
  onFrame: (frame: Int16Array) => void;
  frameSamples?: number;
  mediaDevices?: Pick<MediaDevices, "getUserMedia">;
  audioContextFactory?: () => AudioContext;
}

export interface CaptureHandle {
  stop(): void;
  readonly sampleRate: number;
  readonly usingWorklet: boolean;
}

export const WORKLET_SOURCE = `
class PcmTap extends AudioWorkletProcessor {
  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (channel && channel.length) this.port.postMessage(channel.slice(0));
    return true;
  }
}
registerProcessor("pcm-tap", PcmTap);
`;

export async function startCapture(options: CaptureOptions): Promise<CaptureHandle> {
  const {
    onFrame,
    frameSamples = FRAME_SAMPLES,
    mediaDevices = navigator.mediaDevices,
    audioContextFactory = () => new AudioContext(),
  } = options;

  const stream = await mediaDevices.getUserMedia({
    audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
  });
  const context = audioContextFactory();
  await context.resume?.();

  const slicer = new FrameSlicer(frameSamples);
  const emit = (samples: Float32Array) => {
    const mono = resampleTo16k(samples, context.sampleRate);
    for (const frame of slicer.push(encodePcm16(mono))) onFrame(frame);
  };

  const source = context.createMediaStreamSource(stream);
  // Web Audio only runs a node that reaches the destination, so the capture node goes
  // through a zero-gain sink: without it process()/onaudioprocess never fires in a real
  // browser (the unit tests faked the frames, which is how this slipped through in M4).
  const sink = context.createGain();
  sink.gain.value = 0;
  sink.connect(context.destination);
  let node: AudioWorkletNode | ScriptProcessorNode | null = null;
  let workletUrl: string | null = null;
  let usingWorklet = false;

  if (context.audioWorklet && typeof AudioWorkletNode !== "undefined") {
    try {
      workletUrl = URL.createObjectURL(new Blob([WORKLET_SOURCE], { type: "text/javascript" }));
      await context.audioWorklet.addModule(workletUrl);
      const tap = new AudioWorkletNode(context, "pcm-tap");
      tap.port.onmessage = (event: MessageEvent<Float32Array>) => emit(event.data);
      source.connect(tap);
      tap.connect(sink);
      node = tap;
      usingWorklet = true;
    } catch {
      node?.disconnect?.();
      node = null;
    }
  }

  if (node === null) {
    const processor = context.createScriptProcessor?.(4096, 1, 1);
    if (!processor) {
      stream.getTracks().forEach((track) => track.stop());
      throw new Error("this browser cannot capture audio");
    }
    processor.onaudioprocess = (event: AudioProcessingEvent) => {
      emit(event.inputBuffer.getChannelData(0));
    };
    source.connect(processor);
    processor.connect(sink);
    node = processor;
  }

  return {
    sampleRate: context.sampleRate,
    usingWorklet,
    stop() {
      const tail = slicer.flush();
      if (tail) onFrame(tail);
      try {
        node?.disconnect();
        source.disconnect();
        sink.disconnect();
      } catch {
        /* already torn down */
      }
      stream.getTracks().forEach((track) => track.stop());
      void context.close?.();
      if (workletUrl) URL.revokeObjectURL(workletUrl);
    },
  };
}
