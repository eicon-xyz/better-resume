/** Interview room controller: restore on mount, idempotent submits, finish handshake. */

import { useCallback, useEffect, useRef, useState } from "react";

import type { ApiClient } from "../api/client";
import { ApiError } from "../api/errors";
import { useRoomStore } from "./roomStore";

const DOUBLE_SUBMIT_WINDOW_MS = 250;

export interface UseInterviewRoomOptions {
  client: ApiClient;
  sessionId: string;
  onFinished?: (sessionId: string) => void;
}

export interface InterviewRoomController {
  restoring: boolean;
  restoreError: string | null;
  submitAnswer(text: string): Promise<void>;
  finish(): Promise<void>;
  finishing: boolean;
}

function newRequestId(): string {
  return globalThis.crypto?.randomUUID?.() ?? `req-${Math.random().toString(36).slice(2)}`;
}

export function useInterviewRoom({
  client,
  sessionId,
  onFinished,
}: UseInterviewRoomOptions): InterviewRoomController {
  const [restoring, setRestoring] = useState(true);
  const [restoreError, setRestoreError] = useState<string | null>(null);
  const [finishing, setFinishing] = useState(false);
  const inFlight = useRef(false);
  const lastSubmitAt = useRef(0);

  const restore = useCallback(async () => {
    useRoomStore.getState().reset();
    setRestoring(true);
    setRestoreError(null);
    try {
      const view = await client.restoreInterview(sessionId);
      useRoomStore.getState().hydrate(sessionId, view);
    } catch (error) {
      setRestoreError(error instanceof ApiError ? error.message : "无法恢复面试会话");
    } finally {
      setRestoring(false);
    }
  }, [client, sessionId]);

  useEffect(() => {
    // Deferred a tick so the restore's own state updates never run inside the effect body
    // (React 19 flags synchronous setState in effects as cascading renders).
    queueMicrotask(() => void restore());
  }, [restore]);

  const submitAnswer = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      const question = useRoomStore.getState().currentQuestion;
      if (!trimmed || !question) return;

      // Two guards: an in-flight request and a 250ms window (double click / double Enter).
      const now = Date.now();
      if (inFlight.current || now - lastSubmitAt.current < DOUBLE_SUBMIT_WINDOW_MS) return;
      inFlight.current = true;
      lastSubmitAt.current = now;

      const store = useRoomStore.getState();
      store.submitStart(question.question_no, trimmed);
      try {
        const result = await client.submitInterviewAnswer(sessionId, {
          question_no: question.question_no,
          answer: trimmed,
          request_id: newRequestId(),
        });
        useRoomStore.getState().applyTurnResult(result);
        if (result.next_action === "finished") {
          onFinished?.(sessionId);
        }
      } catch (error) {
        const message = error instanceof ApiError ? error.message : "提交失败，请重试";
        useRoomStore.getState().failSubmit(message);
      } finally {
        inFlight.current = false;
      }
    },
    [client, onFinished, sessionId],
  );

  const finish = useCallback(async () => {
    setFinishing(true);
    try {
      await client.finishInterview(sessionId);
      onFinished?.(sessionId);
    } catch (error) {
      useRoomStore
        .getState()
        .failSubmit(error instanceof ApiError ? error.message : "结束面试失败");
    } finally {
      setFinishing(false);
    }
  }, [client, onFinished, sessionId]);

  return { restoring, restoreError, submitAnswer, finish, finishing };
}
