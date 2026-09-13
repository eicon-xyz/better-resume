/** One error type for every network failure (replaces the old AppError zoo). */

export type ApiErrorKind =
  | "unauthorized"
  | "forbidden"
  | "not_found"
  | "conflict"
  | "invalid"
  | "server"
  | "network"
  | "timeout"
  | "aborted"
  | "unknown";

export interface ApiErrorOptions {
  kind: ApiErrorKind;
  status?: number | null;
  requestId?: string | null;
  detail?: unknown;
  cause?: unknown;
}

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status: number | null;
  readonly requestId: string | null;
  readonly detail: unknown;

  constructor(message: string, options: ApiErrorOptions) {
    super(message);
    this.name = "ApiError";
    this.kind = options.kind;
    this.status = options.status ?? null;
    this.requestId = options.requestId ?? null;
    this.detail = options.detail;
    if (options.cause !== undefined) {
      this.cause = options.cause;
    }
  }

  get isUnauthorized(): boolean {
    return this.kind === "unauthorized";
  }
}

export function kindForStatus(status: number): ApiErrorKind {
  if (status === 401) return "unauthorized";
  if (status === 403) return "forbidden";
  if (status === 404) return "not_found";
  if (status === 409) return "conflict";
  if (status === 422) return "invalid";
  if (status >= 500) return "server";
  if (status >= 400) return "invalid";
  return "unknown";
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
