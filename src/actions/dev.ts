"use server";

import { refresh } from "next/cache";

import { devToolsEnabled } from "@/lib/config";
import {
  createSimulatedShipment,
  isSimulatorOperation,
  runOperation,
  SimulatorError,
} from "@/lib/simulator";

export interface DevState {
  message?: string;
  error?: string;
  /** One line per webhook the simulator sent, e.g. "IN_TRANSIT → PROCESSED". */
  lines?: string[];
}

/**
 * Server Functions can be called directly, not only through the page, so each
 * one checks the switch itself instead of relying on the page being hidden.
 */
function assertDevToolsEnabled(): void {
  if (!devToolsEnabled()) {
    throw new Error("Developer tools are disabled");
  }
}

function failure(error: unknown): DevState {
  if (error instanceof SimulatorError) return { error: error.message };
  throw error;
}

export async function createSimulated(_previous: DevState, formData: FormData): Promise<DevState> {
  assertDevToolsEnabled();
  const scenario = String(formData.get("scenario") ?? "standard");
  const notificationEmail = String(formData.get("notification_email") ?? "").trim();

  let trackingNumber: string;
  try {
    const created = await createSimulatedShipment({ scenario, notificationEmail });
    trackingNumber = created.tracking_number;
  } catch (error) {
    return failure(error);
  }
  refresh();
  return { message: `Created ${trackingNumber} and registered it in ParcelPulse.` };
}

export async function simulate(_previous: DevState, formData: FormData): Promise<DevState> {
  assertDevToolsEnabled();
  const trackingNumber = String(formData.get("tracking_number") ?? "");
  const operation = String(formData.get("operation") ?? "");
  if (!trackingNumber || !isSimulatorOperation(operation)) {
    return { error: "Unknown simulator operation." };
  }

  let lines: string[];
  try {
    const result = await runOperation(trackingNumber, operation);
    lines = [
      ...(result.held ?? []).map((event) => `${event.event_type} held back`),
      ...(result.deliveries ?? []).map((delivery) => {
        const outcome = delivery.delivered ? (delivery.result ?? "accepted") : "NOT DELIVERED";
        const retries = delivery.attempts.length > 1 ? ` (${delivery.attempts.length} attempts)` : "";
        return `${delivery.event_type}${delivery.duplicate ? " (duplicate)" : ""} → ${outcome}${retries}`;
      }),
    ];
  } catch (error) {
    return failure(error);
  }
  refresh();
  return { lines };
}
