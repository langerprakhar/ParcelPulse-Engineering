import "server-only";

import { apiBaseUrl } from "@/lib/config";
import type {
  Carrier,
  NewShipment,
  Notification,
  NotificationPreference,
  NotificationPreferenceInput,
  Page,
  Shipment,
  ShipmentStatus,
  TrackingEvent,
} from "@/lib/types";

const REQUEST_TIMEOUT_MS = 10_000;

/** The API answered with an error status. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly details: unknown = null,
    readonly correlationId: string | null = null,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** The API could not be reached at all (down, timed out, wrong address). */
export class ApiUnavailableError extends Error {
  constructor(cause: unknown) {
    super("The ParcelPulse API is not reachable", { cause });
    this.name = "ApiUnavailableError";
  }
}

export function isApiError(error: unknown, code?: string): error is ApiError {
  return error instanceof ApiError && (code === undefined || error.code === code);
}

async function request<T>(path: string, init: { method?: string; body?: unknown } = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl()}${path}`, {
      method: init.method ?? "GET",
      headers: {
        Accept: "application/json",
        ...(init.body === undefined ? {} : { "Content-Type": "application/json" }),
      },
      body: init.body === undefined ? undefined : JSON.stringify(init.body),
      // Tracking data changes from one request to the next; never serve it from a cache.
      cache: "no-store",
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
  } catch (cause) {
    throw new ApiUnavailableError(cause);
  }

  if (!response.ok) {
    throw await toApiError(response);
  }
  return (await response.json()) as T;
}

async function toApiError(response: Response): Promise<ApiError> {
  let envelope: unknown = null;
  try {
    envelope = await response.json();
  } catch {
    // Not JSON (for example a proxy error page): fall through to the generic error.
  }
  const error = (envelope as { error?: { code?: string; message?: string; details?: unknown } })
    ?.error;
  const correlationId =
    (envelope as { correlation_id?: string | null })?.correlation_id ??
    response.headers.get("X-Correlation-ID");
  return new ApiError(
    response.status,
    error?.code ?? "http_error",
    error?.message ?? `The API responded with HTTP ${response.status}`,
    error?.details ?? null,
    correlationId ?? null,
  );
}

function query(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

const id = encodeURIComponent;

export function listCarriers(): Promise<{ items: Carrier[] }> {
  return request("/carriers");
}

export function listShipments(
  options: { limit?: number; offset?: number; status?: ShipmentStatus } = {},
): Promise<Page<Shipment>> {
  return request(`/shipments${query(options)}`);
}

export function getShipment(shipmentId: string): Promise<Shipment> {
  return request(`/shipments/${id(shipmentId)}`);
}

export function getShipmentByTrackingNumber(
  trackingNumber: string,
  carrier?: string,
): Promise<Shipment> {
  return request(`/shipments/by-tracking/${id(trackingNumber)}${query({ carrier })}`);
}

export function createShipment(shipment: NewShipment): Promise<Shipment> {
  return request("/shipments", { method: "POST", body: shipment });
}

export function listEvents(
  shipmentId: string,
  options: { limit?: number; offset?: number; order?: "asc" | "desc" } = {},
): Promise<Page<TrackingEvent>> {
  return request(`/shipments/${id(shipmentId)}/events${query(options)}`);
}

export function getNotificationPreference(shipmentId: string): Promise<NotificationPreference> {
  return request(`/shipments/${id(shipmentId)}/notification-preferences`);
}

export function saveNotificationPreference(
  shipmentId: string,
  preference: NotificationPreferenceInput,
): Promise<NotificationPreference> {
  return request(`/shipments/${id(shipmentId)}/notification-preferences`, {
    method: "PUT",
    body: preference,
  });
}

export function listNotifications(
  shipmentId: string,
  options: { limit?: number; offset?: number } = {},
): Promise<Page<Notification>> {
  return request(`/shipments/${id(shipmentId)}/notifications${query(options)}`);
}
