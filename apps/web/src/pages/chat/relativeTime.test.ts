import { describe, expect, it } from "vitest";

import { formatRelativeTime } from "./relativeTime";

const NOW = Date.parse("2026-10-12T12:00:00Z");

describe("formatRelativeTime", () => {
  it("reads recent timestamps as 刚刚 / 分钟前 / 小时前", () => {
    expect(formatRelativeTime("2026-10-12T11:59:40Z", NOW)).toBe("刚刚");
    expect(formatRelativeTime("2026-10-12T11:30:00Z", NOW)).toBe("30 分钟前");
    expect(formatRelativeTime("2026-10-12T09:00:00Z", NOW)).toBe("3 小时前");
  });

  it("falls back to days and then to the calendar date", () => {
    expect(formatRelativeTime("2026-10-09T12:00:00Z", NOW)).toBe("3 天前");
    expect(formatRelativeTime("2026-09-13T00:00:00Z", NOW)).toBe("2026-09-13");
  });
});
