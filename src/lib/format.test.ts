// @vitest-environment node
import { describe, expect, it } from "vitest";

import {
  formatLocation,
  formatUtc,
  isValidTrackingNumber,
  normalizeTrackingNumber,
  notificationStatusLabel,
  notificationStatusTone,
  statusLabel,
  statusTone,
} from "./format";
import { SHIPMENT_STATUSES } from "./types";

describe("statusLabel and statusTone", () => {
  it("has wording and a tone for every known status", () => {
    for (const status of SHIPMENT_STATUSES) {
      expect(statusLabel(status)).not.toBe(status);
      expect(["neutral", "moving", "active", "done", "problem"]).toContain(statusTone(status));
    }
  });

  it("uses distinct tones for the states a user cares about", () => {
    expect(statusTone("OUT_FOR_DELIVERY")).toBe("active");
    expect(statusTone("DELIVERED")).toBe("done");
    expect(statusTone("DELIVERY_EXCEPTION")).toBe("problem");
    expect(statusTone("IN_TRANSIT")).toBe("moving");
  });

  it("shows a status this version does not know as the API sent it", () => {
    expect(statusLabel("HELD_AT_CUSTOMS")).toBe("HELD_AT_CUSTOMS");
    expect(statusTone("HELD_AT_CUSTOMS")).toBe("neutral");
  });
});

describe("notification status", () => {
  it("maps worker states to user wording", () => {
    expect(notificationStatusLabel("PENDING")).toBe("Queued");
    expect(notificationStatusLabel("SENT")).toBe("Sent");
    expect(notificationStatusTone("SENT")).toBe("done");
    expect(notificationStatusTone("FAILED")).toBe("problem");
    expect(notificationStatusTone("RETRYING")).toBe("active");
  });
});

describe("formatLocation", () => {
  it("joins the parts that are present", () => {
    expect(
      formatLocation({ facility: "Leeds Parcel Hub", city: "Leeds", region: "ENG", country: "GB" }),
    ).toBe("Leeds Parcel Hub, Leeds, ENG, GB");
    expect(formatLocation({ city: "Bristol", country: "GB" })).toBe("Bristol, GB");
  });

  it("returns null when there is nothing to show", () => {
    expect(formatLocation(null)).toBeNull();
    expect(formatLocation({})).toBeNull();
  });
});

describe("formatUtc", () => {
  it("formats a timestamp in UTC whatever offset it was written with", () => {
    expect(formatUtc("2026-09-30T14:05:00Z")).toBe("30 Sep 2026, 14:05 UTC");
    expect(formatUtc("2026-09-30T16:05:00+02:00")).toBe("30 Sep 2026, 14:05 UTC");
    expect(formatUtc("2026-01-02T03:04:05.678Z")).toBe("02 Jan 2026, 03:04 UTC");
  });

  it("returns unparseable input unchanged", () => {
    expect(formatUtc("not a date")).toBe("not a date");
  });
});

describe("tracking numbers", () => {
  it("normalizes the way the API does", () => {
    expect(normalizeTrackingNumber("  sc4f-7k2m 9q1x ")).toBe("SC4F7K2M9Q1X");
  });

  it("accepts 6 to 40 letters and digits", () => {
    expect(isValidTrackingNumber("SC4F7K2M9Q1X")).toBe(true);
    expect(isValidTrackingNumber("ABC12")).toBe(false);
    expect(isValidTrackingNumber("A".repeat(41))).toBe(false);
    expect(isValidTrackingNumber("SC4F7K2M!")).toBe(false);
    expect(isValidTrackingNumber("")).toBe(false);
  });
});
