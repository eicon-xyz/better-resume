/** The single network seam: typed endpoints, cookie credentials, normalized errors. */

import { ApiError, fromResponse, kindForStatus, toApiError } from "./errors";
import { streamChat as streamChatRequest } from "./sse";
import type { ChatStreamHandlers } from "./sse";
import type {
  AnswerSubmitRequest,
  AnswerSubmitView,
  AuthSessionRequest,
  ChatMessageView,
  ChatSessionCreateRequest,
  ChatSessionView,
  ChatStreamRequest,
  InterviewReportView,
  InterviewSessionCreateRequest,
  InterviewSessionView,
  ModelView,
  Principal,
  QuestionBatchView,
  RestoreResponseView,
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

  createInterviewSession(
    body?: InterviewSessionCreateRequest,
  ): Promise<InterviewSessionView>;
  listInterviewSessions(options?: CallOptions): Promise<InterviewSessionView[]>;
  uploadResumeAndGenerateQuestions(
    sessionId: string,
    file: File,
    options?: UploadOptions,
  ): Promise<QuestionBatchView>;
  submitInterviewAnswer(
    sessionId: string,
    body: AnswerSubmitRequest,
    options?: CallOptions,
  ): Promise<AnswerSubmitView>;
  restoreInterview(sessionId: string, options?: CallOptions): Promise<RestoreResponseView>;
  finishInterview(sessionId: string, options?: CallOptions): Promise<InterviewReportView>;
  getInterviewReport(sessionId: string, options?: CallOptions): Promise<InterviewReportView>;

  listModels(options?: CallOptions): Promise<ModelView[]>;
  devLogin(body: AuthSessionRequest): Promise<Principal>;
  currentPrincipal(options?: CallOptions): Promise<Principal>;
  logout(): Promise<void>;
}

const DEFAULT_TIMEOUT_MS = 15_000;
const UPLOAD_TIMEOUT_MS = 120_000;

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

    createInterviewSession: (body: InterviewSessionCreateRequest = {}) =>
      request<InterviewSessionView>("/api/v1/interview/sessions", { method: "POST", body }),

    listInterviewSessions: (options = {}) =>
      request<InterviewSessionView[]>("/api/v1/interview/sessions", { signal: options.signal }),

    uploadResumeAndGenerateQuestions: (sessionId, file, uploadOptions = {}) =>
      uploadResume(
        `${baseUrl}/api/v1/interview/sessions/${sessionId}/questions`,
        file,
        uploadOptions,
        uploadOptions.xhrFactory,
      ),

    submitInterviewAnswer: (sessionId, body, options = {}) =>
      request<AnswerSubmitView>(`/api/v1/interview/sessions/${sessionId}/answers`, {
        method: "POST",
        body,
        signal: options.signal,
      }),

    restoreInterview: (sessionId, options = {}) =>
      request<RestoreResponseView>(`/api/v1/interview/sessions/${sessionId}/restore`, {
        signal: options.signal,
      }),

    finishInterview: (sessionId, options = {}) =>
      request<InterviewReportView>(`/api/v1/interview/sessions/${sessionId}/finish`, {
        method: "POST",
        signal: options.signal,
      }),

    getInterviewReport: (sessionId, options = {}) =>
      request<InterviewReportView>(`/api/v1/interview/sessions/${sessionId}/report`, {
        signal: options.signal,
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

export interface UploadOptions {
  signal?: AbortSignal;
  /** 0..1, only fires while the browser reports a computable length. */
  onProgress?: (ratio: number) => void;
  /** Injectable for tests; defaults to XMLHttpRequest (fetch cannot report upload progress). */
  xhrFactory?: () => XMLHttpRequest;
}

/** Multipart upload with real progress; errors go through the same ApiError mapping. */
export function uploadResume(
  url: string,
  file: File,
  options: UploadOptions = {},
  xhrFactory: (() => XMLHttpRequest) | undefined = undefined,
): Promise<QuestionBatchView> {
  return new Promise((resolve, reject) => {
    const xhr = (xhrFactory ?? (() => new XMLHttpRequest()))();
    const form = new FormData();
    form.append("file", file);

    xhr.open("POST", url);
    xhr.withCredentials = true;
    xhr.timeout = UPLOAD_TIMEOUT_MS;
    xhr.responseType = "text";

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && event.total > 0) {
        options.onProgress?.(event.loaded / event.total);
      }
    };
    xhr.onload = () => {
      const body = xhr.responseText || "";
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(body) as QuestionBatchView);
        } catch {
          reject(new ApiError("响应不是合法 JSON", { kind: "unknown", status: xhr.status }));
        }
        return;
      }
      let detail: unknown = body;
      try {
        detail = JSON.parse(body) as unknown;
      } catch {
        /* keep the raw text */
      }
      reject(
        new ApiError(
          typeof detail === "object" && detail !== null && "detail" in detail
            ? String(detail.detail)
            : `${xhr.status} 上传失败`,
          { kind: kindForStatus(xhr.status), status: xhr.status, detail },
        ),
      );
    };
    xhr.onerror = () => {
      reject(new ApiError("上传失败：网络错误", { kind: "network" }));
    };
    xhr.ontimeout = () => {
      reject(new ApiError("上传超时", { kind: "timeout" }));
    };
    xhr.onabort = () => {
      reject(new ApiError("上传已取消", { kind: "aborted" }));
    };
    options.signal?.addEventListener("abort", () => {
      xhr.abort();
    });

    xhr.send(form);
  });
}
