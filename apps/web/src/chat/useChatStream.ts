/**
 * Chat controller: owns the request lifecycle (session handshake, SSE, renderer, store).
 * Components stay dumb; this hook is the only place the four pieces meet.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { useQueryClient } from "@tanstack/react-query";

import type { ApiClient } from "../api/client";
import { ApiError, toApiError } from "../api/errors";
import { createStreamRenderer } from "../stream/renderer";
import type { StreamRenderer } from "../stream/renderer";
import { chatKeys, DEFAULT_AUTH_EPOCH } from "./queries";
import { useChatStore } from "./store";

export interface UseChatStreamOptions {
  client: ApiClient;
  sessionId: string | null;
  authEpoch?: string;
  onSessionCreated?: (sessionId: string) => void;
}

export interface SendOptions {
  modelRef?: string | null;
}

export interface ChatStreamController {
  send(content: string, options?: SendOptions): Promise<void>;
  /** Re-send the last user turn (used by the overload banner). */
  retry(): Promise<void>;
  cancel(): void;
  streaming: boolean;
  error: string | null;
  /** Typed failure so the page can explain 429/503/504 and offer a retry. */
  failure: ApiError | null;
}

function newId(): string {
  return globalThis.crypto?.randomUUID?.() ?? `id-${Math.random().toString(36).slice(2)}`;
}

export function useChatStream({
  client,
  sessionId,
  authEpoch = DEFAULT_AUTH_EPOCH,
  onSessionCreated,
}: UseChatStreamOptions): ChatStreamController {
  const queryClient = useQueryClient();
  const store = useChatStore();
  const rendererRef = useRef<StreamRenderer | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const modelRefRef = useRef<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [failure, setFailure] = useState<ApiError | null>(null);

  useEffect(() => {
    return () => {
      rendererRef.current?.stop();
      abortRef.current?.abort();
    };
  }, []);

  const cancel = useCallback(() => {
    abortRef.current?.abort();
    rendererRef.current?.stop();
    const activeRequestId = useChatStore.getState().activeRequestId;
    if (activeRequestId) {
      useChatStore.getState().finishAssistant(activeRequestId, "已取消");
    }
  }, []);

  const send = useCallback(
    async (content: string, options: SendOptions = {}) => {
      const trimmed = content.trim();
      if (!trimmed) return;

      setError(null);
      setFailure(null);
      modelRefRef.current = options.modelRef ?? null;
      let targetSessionId = sessionId;

      try {
        if (!targetSessionId) {
          // "Create the session before navigating": the page follows onSessionCreated.
          const created = await client.createChatSession({ title: trimmed.slice(0, 30) });
          targetSessionId = created.id;
          useChatStore.getState().openSession(targetSessionId);
          onSessionCreated?.(targetSessionId);
        }
      } catch (createError) {
        const apiError = toApiError(createError);
        setFailure(apiError);
        setError(apiError.message);
        useChatStore.getState().setError(apiError.message);
        return;
      }

      const requestId = newId();
      const clientMessageId = newId();
      const state = useChatStore.getState();
      state.appendUser({ clientMessageId, content: trimmed });
      state.startAssistant(requestId);

      const renderer = createStreamRenderer({
        onContent: (text) => useChatStore.getState().appendContent(requestId, text),
        onReasoning: (text) => useChatStore.getState().appendReasoning(requestId, text),
        onDone: () => {
          useChatStore.getState().finishAssistant(requestId);
          void queryClient.invalidateQueries({
            queryKey: chatKeys.messages(authEpoch, targetSessionId),
          });
        },
        isActive: () => useChatStore.getState().activeRequestId === requestId,
      });
      rendererRef.current = renderer;

      const controller = new AbortController();
      abortRef.current = controller;

      await client.streamChat(
        targetSessionId,
        {
          content: trimmed,
          client_message_id: clientMessageId,
          model_ref: options.modelRef ?? null,
        },
        {
          onContent: (text) => renderer.push("content", text),
          onReasoning: (text) => renderer.push("reasoning", text),
          onDone: () => renderer.done(),
          onError: (streamError) => {
            renderer.stop();
            setFailure(streamError);
            setError(streamError.message);
            useChatStore.getState().finishAssistant(requestId, streamError.message);
          },
        },
        { signal: controller.signal },
      );
    },
    [authEpoch, client, onSessionCreated, queryClient, sessionId],
  );

  const retry = useCallback(async () => {
    const messages = useChatStore.getState().messages;
    const lastUser = [...messages].reverse().find((message) => message.role === "user");
    if (!lastUser) return;
    await send(lastUser.content, { modelRef: modelRefRef.current });
  }, [send]);

  return { send, retry, cancel, streaming: store.streaming, error, failure };
}
