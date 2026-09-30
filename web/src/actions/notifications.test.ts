// @vitest-environment node
import { refresh } from "next/cache";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, ApiUnavailableError, saveNotificationPreference } from "@/lib/api";
import type { NotificationPreference } from "@/lib/types";

import { savePreferences } from "./notifications";

vi.mock("next/cache", () => ({ refresh: vi.fn() }));

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  saveNotificationPreference: vi.fn(),
}));

const SHIPMENT_ID = "11111111-2222-3333-4444-555555555555";

function form(fields: Record<string, string>): FormData {
  const data = new FormData();
  for (const [name, value] of Object.entries(fields)) data.set(name, value);
  return data;
}

beforeEach(() => {
  vi.mocked(saveNotificationPreference).mockReset();
  vi.mocked(refresh).mockReset();
});

describe("savePreferences", () => {
  it("saves the address and the ticked notification types", async () => {
    vi.mocked(saveNotificationPreference).mockResolvedValue({} as NotificationPreference);

    const state = await savePreferences(
      SHIPMENT_ID,
      {},
      form({ email: " me@example.com ", notify_out_for_delivery: "on", notify_delivered: "on" }),
    );

    expect(state).toEqual({ saved: true });
    expect(saveNotificationPreference).toHaveBeenCalledWith(SHIPMENT_ID, {
      email: "me@example.com",
      notify_out_for_delivery: true,
      notify_delivered: true,
      // The unticked checkbox was not in the form data at all.
      notify_delivery_exception: false,
    });
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it("sends null for an empty address, which switches notifications off", async () => {
    vi.mocked(saveNotificationPreference).mockResolvedValue({} as NotificationPreference);

    await savePreferences(SHIPMENT_ID, {}, form({ email: "   " }));

    expect(vi.mocked(saveNotificationPreference).mock.calls[0][1].email).toBeNull();
  });

  it("reports an invalid address on the email field without refreshing", async () => {
    vi.mocked(saveNotificationPreference).mockRejectedValue(
      new ApiError(422, "validation_error", "Request validation failed", [
        { loc: ["body", "email"] },
      ]),
    );

    const state = await savePreferences(SHIPMENT_ID, {}, form({ email: "nope" }));

    expect(state.fieldErrors?.email).toMatch(/valid email address/);
    expect(state.saved).toBeUndefined();
    expect(refresh).not.toHaveBeenCalled();
  });

  it("explains a vanished shipment and an outage", async () => {
    vi.mocked(saveNotificationPreference).mockRejectedValueOnce(
      new ApiError(404, "shipment_not_found", "Shipment not found"),
    );
    expect((await savePreferences(SHIPMENT_ID, {}, form({ email: "" }))).error).toMatch(
      /no longer exists/,
    );

    vi.mocked(saveNotificationPreference).mockRejectedValueOnce(
      new ApiUnavailableError(new Error("down")),
    );
    expect((await savePreferences(SHIPMENT_ID, {}, form({ email: "" }))).error).toMatch(
      /not available right now/,
    );
  });
});
