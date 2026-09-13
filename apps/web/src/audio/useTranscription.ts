/**
 * Transcription controller: ticket -> socket -> capture -> store (D15's single channel).
 * Pages only see {recording, status, error} plus the merged text via onTranscript.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import type { ApiClient } from "../api/client";
import { toApiError } from "../api/errors";
import { startCapture } from "./capture";
import type { CaptureHandle } from "./capture";
import { createTranscriptionSocket } from "./transcriptionSocket";
import type { TranscriptionSocket } from "./transcriptionSocket";
import { transcriptText, useTranscriptStore } from "./transcriptStore";

export interface UseTranscriptionOptions {
  client: ApiClient;
  onTranscript?: (text: string) => void;
  captureFactory?: typeof startCapture;
  socketFactory?: typeof createTranscriptionSocket;
  wsUrl?: string;
}

export interface TranscriptionController {
  recording: boolean;
  status: string;
  error: string | null;
  supported: boolean;
  start(): Promise<void>;
  stop(): void;
}

export function defaultTranscribeUrl(): string {
  const scheme = window.location.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${window.location.host}/api/v1/media/transcribe`;
}

export function useTranscription({
  client,
  onTranscript,
  captureFactory = startCapture,
  socketFactory = createTranscriptionSocket,
  wsUrl,
}: UseTranscriptionOptions): TranscriptionController {
  const [recording, setRecording] = useState(false);
  const [status, setStatus] = useState<string>("idle");
  const [error, setError] = useState<string | null>(null);
  const captureRef = useRef<CaptureHandle | null>(null);
  const socketRef = useRef<TranscriptionSocket | null>(null);
  const supported = Boolean(globalThis.navigator?.mediaDevices);

  useEffect(
    () =>
      useTranscriptStore.subscribe((state) => {
        setStatus(state.status);
        setError(state.error);
        onTranscript?.(transcriptText(state));
      }),
    [onTranscript],
  );

  const stop = useCallback(() => {
    captureRef.current?.stop();
    captureRef.current = null;
    socketRef.current?.finish();
    socketRef.current = null;
    setRecording(false);
  }, []);

  useEffect(() => () => stop(), [stop]);

  const start = useCallback(async () => {
    if (captureRef.current) return;
    const store = useTranscriptStore.getState();
    store.reset();
    setError(null);
    setRecording(true);
    try {
      const { ticket } = await client.createWsTicket();
      const socket = socketFactory({
        url: wsUrl ?? defaultTranscribeUrl(),
        ticket,
        onEvent: (event) => useTranscriptStore.getState().applyEvent(event),
        onStatus: (next, detail) => useTranscriptStore.getState().setStatus(next, detail ?? null),
        onDroppedFrames: (count) => useTranscriptStore.getState().noteDroppedFrames(count),
      });
      socketRef.current = socket;
      captureRef.current = await captureFactory({
        onFrame: (frame) => socketRef.current?.send(frame),
      });
    } catch (caught) {
      const apiError = toApiError(caught);
      const message = apiError.kind === "network" ? "未获得麦克风权限" : apiError.message;
      setError(message);
      setRecording(false);
      socketRef.current?.stop();
      socketRef.current = null;
      useTranscriptStore.getState().setStatus("error", message);
    }
  }, [captureFactory, client, socketFactory, wsUrl]);

  return { recording, status, error, supported, start, stop };
}
