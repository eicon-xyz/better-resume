/** Server state lives here (TanStack Query); the store only holds run state. */

import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import type {
  InfiniteData,
  UseInfiniteQueryResult,
  UseQueryResult,
} from "@tanstack/react-query";

import type { ApiClient } from "../api/client";
import type { ChatMessageView, ChatSessionView, ModelView } from "../api/types";

export const DEFAULT_AUTH_EPOCH = "local";
export const HISTORY_PAGE_SIZE = 50;

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
  enabled = true,
): UseQueryResult<ChatSessionView[]> {
  return useQuery({
    queryKey: chatKeys.sessions(authEpoch),
    queryFn: () => client.listChatSessions(),
    enabled,
  });
}

/**
 * History is paged backwards with a seq cursor (newest page first); each page itself is
 * ascending, so the UI flattens pages in reverse to replay the conversation in order.
 */
export function useChatHistory(
  client: ApiClient,
  sessionId: string | null,
  authEpoch: string = DEFAULT_AUTH_EPOCH,
): UseInfiniteQueryResult<InfiniteData<ChatMessageView[], number | null>, Error> {
  return useInfiniteQuery({
    queryKey: chatKeys.messages(authEpoch, sessionId ?? "none"),
    queryFn: ({ pageParam }) =>
      client.listChatMessages(sessionId ?? "", {
        before: pageParam ?? undefined,
        limit: HISTORY_PAGE_SIZE,
      }),
    initialPageParam: null as number | null,
    getNextPageParam: (lastPage) =>
      lastPage.length === HISTORY_PAGE_SIZE ? (lastPage[0]?.seq ?? null) : undefined,
    enabled: Boolean(sessionId),
  });
}

/** Flatten infinite pages into chronological order. */
export function flattenHistory(
  data: InfiniteData<ChatMessageView[], number | null> | undefined,
): ChatMessageView[] {
  if (!data) return [];
  return data.pages
    .slice()
    .reverse()
    .flat();
}

export function useModels(
  client: ApiClient,
  authEpoch: string = DEFAULT_AUTH_EPOCH,
  enabled = true,
): UseQueryResult<ModelView[]> {
  return useQuery({
    queryKey: chatKeys.models(authEpoch),
    queryFn: () => client.listModels(),
    enabled,
  });
}
