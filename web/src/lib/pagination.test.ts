// @vitest-environment node
import { describe, expect, it } from "vitest";

import { pageWindow, parsePage } from "./pagination";

describe("parsePage", () => {
  it("reads a positive page number", () => {
    expect(parsePage("3")).toBe(3);
    expect(parsePage(["2", "9"])).toBe(2);
  });

  it("falls back to the first page for anything else", () => {
    for (const value of [undefined, "", "0", "-4", "abc", "1.5e9x"]) {
      expect(parsePage(value)).toBeGreaterThanOrEqual(1);
    }
    expect(parsePage("0")).toBe(1);
    expect(parsePage("abc")).toBe(1);
  });
});

describe("pageWindow", () => {
  it("describes a middle page", () => {
    expect(pageWindow(53, 2, 20)).toEqual({
      page: 2,
      pageCount: 3,
      first: 21,
      last: 40,
      total: 53,
      hasPrevious: true,
      hasNext: true,
    });
  });

  it("stops at the total on the last page", () => {
    const last = pageWindow(53, 3, 20);
    expect([last.first, last.last, last.hasNext]).toEqual([41, 53, false]);
  });

  it("handles an empty result", () => {
    expect(pageWindow(0, 1, 20)).toMatchObject({
      pageCount: 1,
      first: 0,
      last: 0,
      hasPrevious: false,
      hasNext: false,
    });
  });

  it("offers a way back from a page beyond the end", () => {
    const beyond = pageWindow(5, 4, 20);
    expect([beyond.first, beyond.last]).toEqual([0, 0]);
    expect(beyond.hasPrevious).toBe(true);
    expect(beyond.hasNext).toBe(false);
  });
});
