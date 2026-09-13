/** The single network seam: typed endpoints, cookie credentials, normalized errors. */

import { ApiError, fromResponse, toApiError } from "./errors";
import { streamChat as streamChatRequest } from "./sse";
import type { ChatStreamHandlers } from "./sse";
import type {
  AuthSessionRequest,
  ChatMessageView,
  ChatSessionCreateRequest,
  ChatSessionView,
  ChatStreamRequest,
  ModelView,
  Principal,
} from "./types";

export interface ApiClientOptions {
  baseUrl?: string;
  fetchImpl?: typeof fetch;
  timeoutMs?: number;
  onError?: (error: ApiError) => void;
}

export interface RequestOptions {
  method?: string;
  body?: unknown;
  signal?: AbortSignal;
  query?: Record<string, string | number | undefined>;
}

/** Callers may cancel a read without touching the client's timeout policy. */
export interface CallOptions {
  signal?: AbortSignal;
}

export interface ApiClient {
  readonly baseUrl: string;
  request<T>(path: string, options?: RequestOptions): Promise<T>;

  createChatSession(body?: ChatSessionCreateRequest): Promise<ChatSessionView>;
  listChatSessions(options?: CallOptions): Promise<ChatSessionView[]>;
  listChatMessages(
    sessionId: string,
    params?: { before?: number; limit?: number },
    options?: CallOptions,
  ): Promise<ChatMessageView[]>;
  renameChatSession(sessionId: string, title: string): Promise<void>;
  deleteChatSession(sessionId: string): Promise<void>;
  streamChat(
    sessionId: string,
    body: ChatStreamRequest,
    handlers: ChatStreamHandlers,
    options?: { signal?: AbortSignal },
  ): Promise<void>;

  listModels(options?: CallOptions): Promise<ModelView[]>;
  devLogin(body: AuthSessionRequest): Promise<Principal>;
  currentPrincipal(options?: CallOptions): Promise<Principal>;
  logout(): Promise<void>;
}

const DEFAULT_TIMEOUT_MS = 15_000;

function buildUrl(baseUrl: string, path: string, query?: RequestOptions["query"]): string {
  const url = `${baseUrl}${path}`;
  if (!query) return url;
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined) search.set(key, String(value));
  }
  const suffix = search.toString();
  return suffix ? `${url}?${suffix}` : url;
}

export function createApiClient(options: ApiClientOptions = {}): ApiClient {
  const baseUrl = options.baseUrl ?? "";
  const fetchImpl = options.fetchImpl ?? fetch;
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;

  async function request<T>(path: string, requestOptions: RequestOptions = {}): Promise<T> {
    const signal = combineSignals(requestOptions.signal, timeoutMs);
    try {
      const response = await fetchImpl(buildUrl(baseUrl, path, requestOptions.query), {
        method: requestOptions.method ?? "GET",
        credentials: "include",
        headers:
          requestOptions.body === undefined ? {} : { "Content-Type": "application/json" },
        body: requestOptions.body === undefined ? undefined : JSON.stringify(requestOptions.body),
        signal,
      });

      if (!response.ok) {
        throw await fromResponse(response);
      }
      if (response.status === 204) {
        return undefined as T;
      }
      return (await response.json()) as T;
    } catch (error) {
      const apiError = toApiError(error);
      options.onError?.(apiError);
      throw apiError;
    }
  }

  return {
    baseUrl,
    request,

    createChatSession: (body: ChatSessionCreateRequest = { title: "" }) =>
      request<ChatSessionView>("/api/v1/chat/sessions", { method: "POST", body }),

    listChatSessions: (options = {}) =>
      request<ChatSessionView[]>("/api/v1/chat/sessions", { signal: options.signal }),

    listChatMessages: (sessionId, params = {}, options = {}) =>
      request<ChatMessageView[]>(`/api/v1/chat/sessions/${sessionId}/messages`, {
        query: { before: params.before, limit: params.limit },
        signal: options.signal,
      }),

    renameChatSession: (sessionId, title) =>
      request<void>(`/api/v1/chat/sessions/${sessionId}`, { method: "PUT", body: { title } }),

    deleteChatSession: (sessionId) =>
      request<void>(`/api/v1/chat/sessions/${sessionId}`, { method: "DELETE" }),

    streamChat: (sessionId, body, handlers, streamOptions = {}) =>
      streamChatRequest(`${baseUrl}/api/v1/chat/sessions/${sessionId}/stream`, body, handlers, {
        fetchImpl,
        signal: streamOptions.signal,
      }),

    listModels: (options = {}) =>
      request<ModelView[]>("/api/v1/models", { signal: options.signal }),

    devLogin: (body) => request<Principal>("/api/v1/auth/session", { method: "POST", body }),

    currentPrincipal: (options = {}) =>
      request<Principal>("/api/v1/auth/me", { signal: options.signal }),

    logout: () => request<void>("/api/v1/auth/session", { method: "DELETE" }),
  };
}

/** Caller abort and timeout are different failures, so keep both reasons reachable. */
function combineSignals(signal: AbortSignal | undefined, timeoutMs: number): AbortSignal {
  const timeout = AbortSignal.timeout(timeoutMs);
  return signal ? AbortSignal.any([signal, timeout]) : timeout;
}
