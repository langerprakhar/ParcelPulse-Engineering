// @vitest-environment node
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  createSimulatedShipment,
  isSimulatorOperation,
  listSimulatedShipments,
  runOperation,
  SimulatorError,
} from "./simulator";

const fetchMock = vi.fn<typeof fetch>();

function respondWith(body: unknown, status = 200): void {
  fetchMock.mockImplementation(
    async () =>
      new Response(JSON.stringify(body), {
        status,
        headers: { "Content-Type": "application/json" },
      }),
  );
}

function lastRequest(): { url: string; init: RequestInit } {
  const [url, init] = fetchMock.mock.calls.at(-1)!;
  return { url: String(url), init: init ?? {} };
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  vi.stubEnv("SIMULATOR_BASE_URL", "http://simulator.test:8100/");
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("simulator client", () => {
  it("lists simulated shipments from the configured simulator", async () => {
    respondWith([]);

    await listSimulatedShipments();

    expect(lastRequest().url).toBe("http://simulator.test:8100/shipments");
  });

  it("always asks for new simulated shipments to be registered in ParcelPulse", async () => {
    respondWith({ tracking_number: "SC4F7K2M9Q1X" }, 201);

    await createSimulatedShipment({ scenario: "returned", notificationEmail: "dev@example.com" });

    const { url, init } = lastRequest();
    expect(url).toBe("http://simulator.test:8100/shipments");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({
      scenario: "returned",
      register: true,
      notification_email: "dev@example.com",
    });
  });

  it("posts operations to the shipment's operation path", async () => {
    respondWith({ tracking_number: "SC4F7K2M9Q1X", deliveries: [] });

    await runOperation("SC4F7K2M9Q1X", "release-held");

    const { url, init } = lastRequest();
    expect(url).toBe("http://simulator.test:8100/shipments/SC4F7K2M9Q1X/release-held");
    expect(init.method).toBe("POST");
  });

  it("surfaces the simulator's own error message", async () => {
    respondWith({ error: "no planned events left; the journey is complete" }, 409);

    const error = await runOperation("SC4F7K2M9Q1X", "advance").catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(SimulatorError);
    expect((error as SimulatorError).status).toBe(409);
    expect((error as SimulatorError).message).toBe(
      "no planned events left; the journey is complete",
    );
  });

  it("reports an unreachable simulator without leaking its address", async () => {
    fetchMock.mockRejectedValue(new TypeError("connect ECONNREFUSED simulator.test:8100"));

    const error = (await listSimulatedShipments().catch(
      (caught: unknown) => caught,
    )) as SimulatorError;

    expect(error).toBeInstanceOf(SimulatorError);
    expect(error.status).toBeNull();
    expect(error.message).not.toContain("simulator.test");
  });
});

describe("isSimulatorOperation", () => {
  it("accepts only the known operations", () => {
    expect(isSimulatorOperation("advance")).toBe(true);
    expect(isSimulatorOperation("release-held")).toBe(true);
    expect(isSimulatorOperation("reset")).toBe(false);
    expect(isSimulatorOperation("../bursts")).toBe(false);
  });
});
