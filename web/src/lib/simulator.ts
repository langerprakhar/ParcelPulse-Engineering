import "server-only";

import { simulatorBaseUrl } from "@/lib/config";

/**
 * Client for the carrier simulator (parcelpulse-infra/carrier-simulator).
 * Only the developer tools use it; the product itself never talks to the simulator.
 */

export const SIMULATOR_OPERATIONS = [
  "advance",
  "duplicate",
  "hold",
  "release-held",
  "out-of-order",
  "exception",
  "lifecycle",
] as const;

export type SimulatorOperation = (typeof SIMULATOR_OPERATIONS)[number];

export function isSimulatorOperation(value: string): value is SimulatorOperation {
  return (SIMULATOR_OPERATIONS as readonly string[]).includes(value);
}

export interface SimulatedShipmentSummary {
  tracking_number: string;
  scenario: string;
  registered: boolean;
  planned: number;
  held: number;
  sent: number;
}

export interface SimulatedDelivery {
  event_id: string;
  event_type: string;
  occurred_at: string;
  duplicate: boolean;
  delivered: boolean;
  /** What ParcelPulse answered: PROCESSED, DUPLICATE, ... */
  result: string | null;
  attempts: { number: number; status_code: number | null; error: string | null }[];
}

export interface OperationResult {
  tracking_number: string;
  /** Present for every operation except "hold", which sends nothing. */
  deliveries?: SimulatedDelivery[];
  held?: { event_type: string }[];
}

export class SimulatorError extends Error {
  constructor(
    readonly status: number | null,
    message: string,
  ) {
    super(message);
    this.name = "SimulatorError";
  }
}

async function request<T>(path: string, init: { method?: string; body?: unknown } = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${simulatorBaseUrl()}${path}`, {
      method: init.method ?? "GET",
      headers: init.body === undefined ? {} : { "Content-Type": "application/json" },
      body: init.body === undefined ? undefined : JSON.stringify(init.body),
      cache: "no-store",
      // A full lifecycle with carrier-style retries can take a while.
      signal: AbortSignal.timeout(60_000),
    });
  } catch {
    throw new SimulatorError(null, "The carrier simulator is not reachable.");
  }

  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { error?: string } | null;
    throw new SimulatorError(
      response.status,
      body?.error ?? `The carrier simulator responded with HTTP ${response.status}.`,
    );
  }
  return (await response.json()) as T;
}

export function listScenarios(): Promise<Record<string, unknown[]>> {
  return request("/scenarios");
}

export function listSimulatedShipments(): Promise<SimulatedShipmentSummary[]> {
  return request("/shipments");
}

export function createSimulatedShipment(options: {
  scenario: string;
  notificationEmail?: string;
}): Promise<{ tracking_number: string }> {
  return request("/shipments", {
    method: "POST",
    body: {
      scenario: options.scenario,
      // Developer tools always register the shipment so its events are accepted.
      register: true,
      ...(options.notificationEmail ? { notification_email: options.notificationEmail } : {}),
    },
  });
}

export function runOperation(
  trackingNumber: string,
  operation: SimulatorOperation,
): Promise<OperationResult> {
  return request(`/shipments/${encodeURIComponent(trackingNumber)}/${operation}`, {
    method: "POST",
  });
}
