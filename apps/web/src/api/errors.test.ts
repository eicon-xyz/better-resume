import { describe, expect, it } from "vitest";

import { ApiError, fromResponse, kindForStatus, toApiError } from "./errors";

describe("kindForStatus", () => {
  it.each([
    [401, "unauthorized"],
    [403, "forbidden"],
    [404, "not_found"],
    [409, "conflict"],
    [422, "invalid"],
    [500, "server"],
    [503, "server"],
    [418, "invalid"],
  ])("maps %i to %s", (status, kind) => {
    expect(kindForStatus(status)).toBe(kind);
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
