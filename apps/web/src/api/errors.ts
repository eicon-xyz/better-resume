/** One error type for every network failure (replaces the old AppError zoo). */

export type ApiErrorKind =
  | "unauthorized"
  | "forbidden"
  | "not_found"
  | "conflict"
  | "invalid"
  | "rate_limited"
  | "unavailable"
  | "gateway_timeout"
  | "server"
  | "network"
  | "timeout"
  | "aborted"
  | "unknown";

export interface ApiErrorOptions {
  kind: ApiErrorKind;
  status?: number | null;
  requestId?: string | null;
  retryAfterSeconds?: number | null;
  detail?: unknown;
  cause?: unknown;
}

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status: number | null;
  readonly requestId: string | null;
  readonly retryAfterSeconds: number | null;
  readonly detail: unknown;

  constructor(message: string, options: ApiErrorOptions) {
    super(message);
    this.name = "ApiError";
    this.kind = options.kind;
    this.status = options.status ?? null;
    this.requestId = options.requestId ?? null;
    this.retryAfterSeconds = options.retryAfterSeconds ?? null;
    this.detail = options.detail;
    if (options.cause !== undefined) {
      this.cause = options.cause;
    }
  }

  get isUnauthorized(): boolean {
    return this.kind === "unauthorized";
  }
}

/** M3 taxonomy: the backend now says "busy" (429), "shedding" (503) or "slow" (504). */
export function kindForStatus(status: number): ApiErrorKind {
  if (status === 401) return "unauthorized";
  if (status === 403) return "forbidden";
  if (status === 404) return "not_found";
  if (status === 409) return "conflict";
  if (status === 422) return "invalid";
  if (status === 429) return "rate_limited";
  if (status === 503) return "unavailable";
  if (status === 504) return "gateway_timeout";
  if (status >= 500) return "server";
  if (status >= 400) return "invalid";
  return "unknown";
}

const OVERLOAD_KINDS = new Set<ApiErrorKind>(["rate_limited", "unavailable", "gateway_timeout"]);

/** True when waiting and retrying the same request is the right move. */
export function isRetryableError(error: ApiError): boolean {
  return OVERLOAD_KINDS.has(error.kind);
}

/** One place for user-facing copy: every kind gets a sentence, none says "unknown error". */
export function describeApiError(error: ApiError): string {
  switch (error.kind) {
    case "rate_limited": {
      const seconds = error.retryAfterSeconds;
      return seconds && seconds > 0 ? `服务繁忙，请 ${seconds} 秒后重试` : "服务繁忙，请稍后重试";
    }
    case "unavailable":
      return "服务繁忙（上游不可用或排队已满），请稍后重试";
    case "gateway_timeout":
      return "上游模型超时，请重试";
    case "unauthorized":
      return "登录已过期，请重新登录";
    case "network":
      return "网络异常，请检查网络后重试";
    case "timeout":
      return "请求超时，请重试";
    case "aborted":
      return "请求已取消";
    default:
      return error.message;
  }
}

/** Retry-After is either delta-seconds or an HTTP date (RFC 9110). */
export function parseRetryAfter(header: string | null): number | null {
  if (header === null) return null;
  const value = header.trim();
  if (value === "") return null;

  const seconds = Number(value);
  if (Number.isFinite(seconds) && seconds >= 0) {
    return Math.ceil(seconds);
  }
  const date = Date.parse(value);
  if (Number.isNaN(date)) return null;
  return Math.max(0, Math.ceil((date - Date.now()) / 1000));
}

function detailMessage(detail: unknown): string | null {
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && "detail" in detail) {
    const inner = (detail as { detail?: unknown }).detail;
    if (typeof inner === "string") return inner;
  }
  return null;
}

export async function fromResponse(response: Response): Promise<ApiError> {
  let payload: unknown;
  try {
    const text = await response.text();
    payload = text ? (JSON.parse(text) as unknown) : null;
  } catch {
    payload = null;
  }

  const kind = kindForStatus(response.status);
  const message =
    detailMessage(payload) ?? `${response.status} ${response.statusText || "request failed"}`;

  return new ApiError(message, {
    kind,
    status: response.status,
    requestId: response.headers.get("x-request-id"),
    retryAfterSeconds: parseRetryAfter(response.headers.get("retry-after")),
    detail: payload,
  });
}

/** Classify a fetch rejection: abort, timeout and offline are different problems. */
export function toApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error;

  if (error instanceof DOMException || error instanceof Error) {
    const name = error.name;
    if (name === "AbortError") {
      return new ApiError("request aborted", { kind: "aborted", cause: error });
    }
    if (name === "TimeoutError") {
      return new ApiError("request timed out", { kind: "timeout", cause: error });
    }
  }

  return new ApiError(error instanceof Error ? error.message : "network error", {
    kind: "network",
    cause: error,
  });
}
