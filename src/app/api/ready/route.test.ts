// @vitest-environment node
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GET } from "./route";

const fetchMock = vi.fn<typeof fetch>();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  vi.stubEnv("API_BASE_URL", "http://api.test:8000");
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("GET /api/ready", () => {
  it("is ready when the API reports ready", async () => {
    fetchMock.mockResolvedValue(new Response("{}", { status: 200 }));

    const response = await GET();

    expect(String(fetchMock.mock.calls[0][0])).toBe("http://api.test:8000/ready");
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ status: "ready", checks: { api: "ok" } });
  });

  it("is not ready when the API reports a failed dependency", async () => {
    fetchMock.mockResolvedValue(new Response("{}", { status: 503 }));

    const response = await GET();

    expect(response.status).toBe(503);
    expect(await response.json()).toEqual({ status: "not_ready", checks: { api: "not_ready" } });
  });

  it("is not ready when the API cannot be reached, and does not leak its address", async () => {
    fetchMock.mockRejectedValue(new TypeError("connect ECONNREFUSED api.test:8000"));

    const response = await GET();
    const text = JSON.stringify(await response.json());

    expect(response.status).toBe(503);
    expect(text).toContain("unreachable");
    expect(text).not.toContain("api.test");
  });
});
