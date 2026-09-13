import { describe, expect, it } from "vitest";

import {
  ApiError,
  describeApiError,
  fromResponse,
  isRetryableError,
  kindForStatus,
  parseRetryAfter,
  toApiError,
} from "./errors";

describe("kindForStatus", () => {
  it.each([
    [401, "unauthorized"],
    [403, "forbidden"],
    [404, "not_found"],
    [409, "conflict"],
    [422, "invalid"],
    [500, "server"],
    [502, "server"],
    [429, "rate_limited"],
    [503, "unavailable"],
    [504, "gateway_timeout"],
    [418, "invalid"],
  ])("maps %i to %s", (status, kind) => {
    expect(kindForStatus(status)).toBe(kind);
  });
});

describe("describeApiError", () => {
  it("explains overload with the retry window", () => {
    const limited = new ApiError("rate limit exceeded", {
      kind: "rate_limited",
      status: 429,
      retryAfterSeconds: 3,
    });
    expect(describeApiError(limited)).toBe("服务繁忙，请 3 秒后重试");
    expect(isRetryableError(limited)).toBe(true);
  });

  it("explains shedding and upstream timeouts", () => {
    expect(describeApiError(new ApiError("circuit open", { kind: "unavailable", status: 503 }))).toBe(
      "服务繁忙（上游不可用或排队已满），请稍后重试",
    );
    const timedOut = new ApiError("stage evaluation exceeded 20s", {
      kind: "gateway_timeout",
      status: 504,
    });
    expect(describeApiError(timedOut)).toBe("上游模型超时，请重试");
    expect(isRetryableError(timedOut)).toBe(true);
  });

  it("never falls back to an unknown-error sentence for known kinds", () => {
    const kinds = [
      "rate_limited",
      "unavailable",
      "gateway_timeout",
      "unauthorized",
      "network",
      "timeout",
      "aborted",
    ] as const;
    for (const kind of kinds) {
      const copy = describeApiError(new ApiError("raw", { kind }));
      expect(copy).not.toBe("raw");
      expect(copy).not.toContain("未知");
    }
    // Business errors keep the backend detail.
    expect(describeApiError(new ApiError("题目不存在", { kind: "not_found" }))).toBe("题目不存在");
  });
});

describe("parseRetryAfter", () => {
  it("accepts seconds and HTTP dates", () => {
    expect(parseRetryAfter("5")).toBe(5);
    expect(parseRetryAfter(" 0 ")).toBe(0);
    const future = new Date(Date.now() + 4000).toUTCString();
    const parsed = parseRetryAfter(future);
    expect(parsed).toBeGreaterThan(0);
    expect(parsed).toBeLessThanOrEqual(5);
  });

  it("returns null when the header is missing or unusable", () => {
    expect(parseRetryAfter(null)).toBeNull();
    expect(parseRetryAfter("")).toBeNull();
    expect(parseRetryAfter("soon")).toBeNull();
  });
});

describe("fromResponse", () => {
  it("keeps the backend detail and request id", async () => {
    const response = new Response(JSON.stringify({ detail: "conversation not found" }), {
      status: 404,
      headers: { "x-request-id": "req-42" },
    });

    const error = await fromResponse(response);

    expect(error).toBeInstanceOf(ApiError);
    expect(error.kind).toBe("not_found");
    expect(error.message).toBe("conversation not found");
    expect(error.status).toBe(404);
    expect(error.requestId).toBe("req-42");
  });

  it("carries Retry-After into the error for overload responses", async () => {
    const response = new Response(
      JSON.stringify({ detail: "rate limit exceeded for read", bucket: "read", retry_after: 2 }),
      { status: 429, headers: { "retry-after": "2" } },
    );

    const error = await fromResponse(response);

    expect(error.kind).toBe("rate_limited");
    expect(error.retryAfterSeconds).toBe(2);
    expect(isRetryableError(error)).toBe(true);
    expect(describeApiError(error)).toBe("服务繁忙，请 2 秒后重试");
  });

  it("falls back to the status text when the body is not JSON", async () => {
    const response = new Response("boom", { status: 500, statusText: "Server Error" });

    const error = await fromResponse(response);

    expect(error.kind).toBe("server");
    expect(error.message).toContain("500");
  });
});

describe("toApiError", () => {
  it("classifies aborts, timeouts and network failures apart", () => {
    expect(toApiError(new DOMException("stop", "AbortError")).kind).toBe("aborted");
    expect(toApiError(new DOMException("slow", "TimeoutError")).kind).toBe("timeout");
    expect(toApiError(new TypeError("failed to fetch")).kind).toBe("network");
  });

  it("passes an existing ApiError through", () => {
    const original = new ApiError("nope", { kind: "conflict" });

    expect(toApiError(original)).toBe(original);
  });
});
