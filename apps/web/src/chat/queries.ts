/** Server state lives here (TanStack Query); the store only holds run state. */

import { useQuery } from "@tanstack/react-query";
import type { UseQueryResult } from "@tanstack/react-query";

import type { ApiClient } from "../api/client";
import type { ChatMessageView, ChatSessionView, ModelView } from "../api/types";

export const DEFAULT_AUTH_EPOCH = "local";

export const chatKeys = {
  all: (authEpoch: string) => ["chat", authEpoch] as const,
  sessions: (authEpoch: string) => [...chatKeys.all(authEpoch), "sessions"] as const,
  messages: (authEpoch: string, sessionId: string) =>
    [...chatKeys.all(authEpoch), "messages", sessionId] as const,
  models: (authEpoch: string) => [...chatKeys.all(authEpoch), "models"] as const,
};

export function useChatSessions(
  client: ApiClient,
  authEpoch: string = DEFAULT_AUTH_EPOCH,
): UseQueryResult<ChatSessionView[]> {
  return useQuery({
    queryKey: chatKeys.sessions(authEpoch),
    queryFn: () => client.listChatSessions(),
  });
}

export function useChatHistory(
  client: ApiClient,
  sessionId: string | null,
  authEpoch: string = DEFAULT_AUTH_EPOCH,
): UseQueryResult<ChatMessageView[]> {
  return useQuery({
    queryKey: chatKeys.messages(authEpoch, sessionId ?? "none"),
    queryFn: () => client.listChatMessages(sessionId ?? "", { limit: 100 }),
    enabled: Boolean(sessionId),
  });
}

export function useModels(
  client: ApiClient,
  authEpoch: string = DEFAULT_AUTH_EPOCH,
): UseQueryResult<ModelView[]> {
  return useQuery({
    queryKey: chatKeys.models(authEpoch),
    queryFn: () => client.listModels(),
  });
}
