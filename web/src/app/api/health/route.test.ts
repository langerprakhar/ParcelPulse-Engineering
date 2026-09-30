import { describe, expect, it } from "vitest";

import { GET } from "./route";

describe("GET /api/health", () => {
  it("reports that the web server is up", async () => {
    const response = GET();

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({
      status: "ok",
      service: "parcelpulse-web",
      version: expect.stringMatching(/^\d+\.\d+\.\d+$/),
    });
  });
});
