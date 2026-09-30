// @vitest-environment node
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, ApiUnavailableError, createShipment, getShipmentByTrackingNumber } from "@/lib/api";
import type { Shipment } from "@/lib/types";

import { findShipment, registerShipment } from "./shipments";

const { RedirectSignal } = vi.hoisted(() => {
  /** next/navigation's redirect() works by throwing; this stands in for that. */
  class RedirectSignal extends Error {
    constructor(readonly url: string) {
      super(`redirect to ${url}`);
    }
  }
  return { RedirectSignal };
});

vi.mock("next/navigation", () => ({
  redirect: (url: string) => {
    throw new RedirectSignal(url);
  },
}));

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  getShipmentByTrackingNumber: vi.fn(),
  createShipment: vi.fn(),
}));

const SHIPMENT = { id: "11111111-2222-3333-4444-555555555555" } as Shipment;

function form(fields: Record<string, string>): FormData {
  const data = new FormData();
  for (const [name, value] of Object.entries(fields)) data.set(name, value);
  return data;
}

async function redirectTarget(action: Promise<unknown>): Promise<string> {
  const error = await action.catch((caught: unknown) => caught);
  expect(error).toBeInstanceOf(RedirectSignal);
  return (error as InstanceType<typeof RedirectSignal>).url;
}

beforeEach(() => {
  vi.mocked(getShipmentByTrackingNumber).mockReset();
  vi.mocked(createShipment).mockReset();
});

describe("findShipment", () => {
  it("redirects to the shipment when the tracking number is known", async () => {
    vi.mocked(getShipmentByTrackingNumber).mockResolvedValue(SHIPMENT);

    const target = await redirectTarget(
      findShipment({}, form({ tracking_number: " sc4f-7k2m 9q1x " })),
    );

    expect(target).toBe(`/shipments/${SHIPMENT.id}`);
    expect(getShipmentByTrackingNumber).toHaveBeenCalledWith("SC4F7K2M9Q1X");
  });

  it("rejects a malformed tracking number without calling the API", async () => {
    const state = await findShipment({}, form({ tracking_number: "bad!" }));

    expect(state.error).toMatch(/6 to 40 letters and digits/);
    expect(getShipmentByTrackingNumber).not.toHaveBeenCalled();
  });

  it("reports an untracked number so the form can offer to add it", async () => {
    vi.mocked(getShipmentByTrackingNumber).mockRejectedValue(
      new ApiError(404, "shipment_not_found", "No shipment"),
    );

    const state = await findShipment({}, form({ tracking_number: "SC0000000000" }));

    expect(state).toEqual({ trackingNumber: "SC0000000000", notFound: true });
  });

  it("explains an outage instead of failing", async () => {
    vi.mocked(getShipmentByTrackingNumber).mockRejectedValue(
      new ApiUnavailableError(new TypeError("fetch failed")),
    );

    const state = await findShipment({}, form({ tracking_number: "SC4F7K2M9Q1X" }));

    expect(state.error).toMatch(/not available right now/);
  });

  it("does not swallow unexpected API errors", async () => {
    vi.mocked(getShipmentByTrackingNumber).mockRejectedValue(
      new ApiError(500, "internal_error", "Internal server error"),
    );

    await expect(findShipment({}, form({ tracking_number: "SC4F7K2M9Q1X" }))).rejects.toThrow(
      ApiError,
    );
  });
});

describe("registerShipment", () => {
  const VALID = { tracking_number: "SC4F7K2M9Q1X", carrier: "simcarrier" };

  it("creates the shipment and redirects to it", async () => {
    vi.mocked(createShipment).mockResolvedValue(SHIPMENT);

    const target = await redirectTarget(
      registerShipment({}, form({ ...VALID, notification_email: " me@example.com " })),
    );

    expect(target).toBe(`/shipments/${SHIPMENT.id}`);
    expect(createShipment).toHaveBeenCalledWith({
      tracking_number: "SC4F7K2M9Q1X",
      carrier: "simcarrier",
      notification_email: "me@example.com",
    });
  });

  it("omits the email when none was entered", async () => {
    vi.mocked(createShipment).mockResolvedValue(SHIPMENT);

    await redirectTarget(registerShipment({}, form({ ...VALID, notification_email: "" })));

    expect(createShipment).toHaveBeenCalledWith(VALID);
  });

  it("validates before calling the API and keeps what was typed", async () => {
    const state = await registerShipment({}, form({ tracking_number: "x", carrier: "" }));

    expect(state.fieldErrors).toEqual({
      tracking_number: expect.stringMatching(/6 to 40/),
      carrier: expect.stringMatching(/Choose the carrier/),
    });
    expect(state.values?.tracking_number).toBe("X");
    expect(createShipment).not.toHaveBeenCalled();
  });

  it("opens the existing shipment when the parcel is already tracked", async () => {
    vi.mocked(createShipment).mockRejectedValue(
      new ApiError(409, "shipment_already_exists", "Already tracked", {
        shipment_id: "existing-id",
      }),
    );

    const target = await redirectTarget(registerShipment({}, form(VALID)));

    expect(target).toBe("/shipments/existing-id");
  });

  it("maps API validation details onto the form fields", async () => {
    vi.mocked(createShipment).mockRejectedValue(
      new ApiError(422, "validation_error", "Request validation failed", [
        { loc: ["body", "notification_email"], message: "value is not a valid email address" },
      ]),
    );

    const state = await registerShipment({}, form({ ...VALID, notification_email: "nope" }));

    expect(state.fieldErrors).toEqual({
      notification_email: expect.stringMatching(/valid email address/),
    });
    expect(state.values?.notification_email).toBe("nope");
  });

  it("reports an unsupported carrier on the carrier field", async () => {
    vi.mocked(createShipment).mockRejectedValue(
      new ApiError(422, "unsupported_carrier", "Carrier 'x' is not supported"),
    );

    const state = await registerShipment({}, form({ ...VALID, carrier: "pigeonpost" }));

    expect(state.fieldErrors).toEqual({ carrier: "This carrier is not supported." });
  });

  it("explains an outage instead of failing", async () => {
    vi.mocked(createShipment).mockRejectedValue(new ApiUnavailableError(new Error("down")));

    const state = await registerShipment({}, form(VALID));

    expect(state.error).toMatch(/not available right now/);
  });
});
