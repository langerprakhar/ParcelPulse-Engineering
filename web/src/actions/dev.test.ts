// @vitest-environment node
import { refresh } from "next/cache";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { createSimulatedShipment, runOperation, SimulatorError } from "@/lib/simulator";

import { createSimulated, simulate } from "./dev";

vi.mock("next/cache", () => ({ refresh: vi.fn() }));

vi.mock("@/lib/simulator", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/simulator")>()),
  createSimulatedShipment: vi.fn(),
  runOperation: vi.fn(),
}));

function form(fields: Record<string, string>): FormData {
  const data = new FormData();
  for (const [name, value] of Object.entries(fields)) data.set(name, value);
  return data;
}

beforeEach(() => {
  vi.mocked(createSimulatedShipment).mockReset();
  vi.mocked(runOperation).mockReset();
  vi.mocked(refresh).mockReset();
  vi.stubEnv("ENABLE_DEV_TOOLS", "true");
});

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("when developer tools are disabled", () => {
  it.each(["false", "", "1", "TRUE"])("refuses to act (ENABLE_DEV_TOOLS=%j)", async (value) => {
    vi.stubEnv("ENABLE_DEV_TOOLS", value);

    await expect(createSimulated({}, form({ scenario: "standard" }))).rejects.toThrow(/disabled/);
    await expect(
      simulate({}, form({ tracking_number: "SC4F7K2M9Q1X", operation: "advance" })),
    ).rejects.toThrow(/disabled/);
    expect(createSimulatedShipment).not.toHaveBeenCalled();
    expect(runOperation).not.toHaveBeenCalled();
  });
});

describe("createSimulated", () => {
  it("creates a registered simulated shipment and refreshes the page", async () => {
    vi.mocked(createSimulatedShipment).mockResolvedValue({ tracking_number: "SC4F7K2M9Q1X" });

    const state = await createSimulated(
      {},
      form({ scenario: "exception", notification_email: " dev@example.com " }),
    );

    expect(createSimulatedShipment).toHaveBeenCalledWith({
      scenario: "exception",
      notificationEmail: "dev@example.com",
    });
    expect(state.message).toContain("SC4F7K2M9Q1X");
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it("reports a simulator failure", async () => {
    vi.mocked(createSimulatedShipment).mockRejectedValue(
      new SimulatorError(null, "The carrier simulator is not reachable."),
    );

    const state = await createSimulated({}, form({ scenario: "standard" }));

    expect(state).toEqual({ error: "The carrier simulator is not reachable." });
    expect(refresh).not.toHaveBeenCalled();
  });
});

describe("simulate", () => {
  it("runs the operation and summarises what ParcelPulse answered", async () => {
    vi.mocked(runOperation).mockResolvedValue({
      tracking_number: "SC4F7K2M9Q1X",
      deliveries: [
        {
          event_id: "evt_1",
          event_type: "IN_TRANSIT",
          occurred_at: "2026-09-29T12:00:00Z",
          duplicate: false,
          delivered: true,
          result: "PROCESSED",
          attempts: [{ number: 1, status_code: 200, error: null }],
        },
        {
          event_id: "evt_1",
          event_type: "IN_TRANSIT",
          occurred_at: "2026-09-29T12:00:00Z",
          duplicate: true,
          delivered: true,
          result: "DUPLICATE",
          attempts: [
            { number: 1, status_code: 503, error: null },
            { number: 2, status_code: 200, error: null },
          ],
        },
        {
          event_id: "evt_2",
          event_type: "DELIVERED",
          occurred_at: "2026-09-30T12:00:00Z",
          duplicate: false,
          delivered: false,
          result: "http_500",
          attempts: [{ number: 1, status_code: 500, error: null }],
        },
      ],
    });

    const state = await simulate(
      {},
      form({ tracking_number: "SC4F7K2M9Q1X", operation: "lifecycle" }),
    );

    expect(runOperation).toHaveBeenCalledWith("SC4F7K2M9Q1X", "lifecycle");
    expect(state.lines).toEqual([
      "IN_TRANSIT → PROCESSED",
      "IN_TRANSIT (duplicate) → DUPLICATE (2 attempts)",
      "DELIVERED → NOT DELIVERED",
    ]);
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it("describes held events, which send nothing", async () => {
    vi.mocked(runOperation).mockResolvedValue({
      tracking_number: "SC4F7K2M9Q1X",
      held: [{ event_type: "AT_DISTRIBUTION_CENTER" }],
    });

    const state = await simulate({}, form({ tracking_number: "SC4F7K2M9Q1X", operation: "hold" }));

    expect(state.lines).toEqual(["AT_DISTRIBUTION_CENTER held back"]);
  });

  it("rejects operations that are not on the list", async () => {
    const state = await simulate(
      {},
      form({ tracking_number: "SC4F7K2M9Q1X", operation: "../../shipments" }),
    );

    expect(state.error).toBe("Unknown simulator operation.");
    expect(runOperation).not.toHaveBeenCalled();
  });

  it("passes on the simulator's explanation when the operation is not possible", async () => {
    vi.mocked(runOperation).mockRejectedValue(new SimulatorError(409, "no held events to release"));

    const state = await simulate(
      {},
      form({ tracking_number: "SC4F7K2M9Q1X", operation: "release-held" }),
    );

    expect(state).toEqual({ error: "no held events to release" });
  });
});
