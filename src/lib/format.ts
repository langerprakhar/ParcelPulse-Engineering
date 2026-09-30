import type {
  EventLocation,
  NotificationStatus,
  NotificationType,
  ShipmentStatus,
} from "@/lib/types";

const STATUS_LABELS: Record<ShipmentStatus, string> = {
  CREATED: "Awaiting carrier",
  LABEL_CREATED: "Label created",
  IN_TRANSIT: "In transit",
  AT_DISTRIBUTION_CENTER: "At distribution centre",
  OUT_FOR_DELIVERY: "Out for delivery",
  DELIVERED: "Delivered",
  DELIVERY_EXCEPTION: "Delivery exception",
  RETURNED: "Returned to sender",
};

export type StatusTone = "neutral" | "moving" | "active" | "done" | "problem";

const STATUS_TONES: Record<ShipmentStatus, StatusTone> = {
  CREATED: "neutral",
  LABEL_CREATED: "neutral",
  IN_TRANSIT: "moving",
  AT_DISTRIBUTION_CENTER: "moving",
  OUT_FOR_DELIVERY: "active",
  DELIVERED: "done",
  DELIVERY_EXCEPTION: "problem",
  RETURNED: "problem",
};

/** Human wording for a status. Unknown values (a newer API) are shown as sent. */
export function statusLabel(status: string): string {
  return STATUS_LABELS[status as ShipmentStatus] ?? status;
}

export function statusTone(status: string): StatusTone {
  return STATUS_TONES[status as ShipmentStatus] ?? "neutral";
}

const NOTIFICATION_TYPE_LABELS: Record<NotificationType, string> = {
  OUT_FOR_DELIVERY: "Out for delivery",
  DELIVERED: "Delivered",
  DELIVERY_EXCEPTION: "Delivery exception",
};

export function notificationTypeLabel(type: string): string {
  return NOTIFICATION_TYPE_LABELS[type as NotificationType] ?? type;
}

const NOTIFICATION_STATUS_LABELS: Record<NotificationStatus, string> = {
  PENDING: "Queued",
  SENDING: "Sending",
  SENT: "Sent",
  RETRYING: "Retrying",
  FAILED: "Failed",
};

export function notificationStatusLabel(status: string): string {
  return NOTIFICATION_STATUS_LABELS[status as NotificationStatus] ?? status;
}

export function notificationStatusTone(status: string): StatusTone {
  switch (status) {
    case "SENT":
      return "done";
    case "FAILED":
      return "problem";
    case "RETRYING":
      return "active";
    default:
      return "neutral";
  }
}

export function formatLocation(location: EventLocation | null | undefined): string | null {
  if (!location) return null;
  const parts = [location.facility, location.city, location.region, location.country].filter(
    (part): part is string => Boolean(part),
  );
  return parts.length > 0 ? parts.join(", ") : null;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function pad(value: number): string {
  return String(value).padStart(2, "0");
}

/**
 * A timestamp in UTC, e.g. "30 Sep 2026, 14:05 UTC". Built by hand so that the
 * server and every browser produce exactly the same text.
 */
export function formatUtc(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return (
    `${pad(date.getUTCDate())} ${MONTHS[date.getUTCMonth()]} ${date.getUTCFullYear()}, ` +
    `${pad(date.getUTCHours())}:${pad(date.getUTCMinutes())} UTC`
  );
}

const TRACKING_NUMBER_PATTERN = /^[A-Z0-9]{6,40}$/;

/** Mirrors the API: spaces and dashes are ignored, letters are upper-cased. */
export function normalizeTrackingNumber(input: string): string {
  return input.trim().replace(/[\s-]/g, "").toUpperCase();
}

export function isValidTrackingNumber(trackingNumber: string): boolean {
  return TRACKING_NUMBER_PATTERN.test(trackingNumber);
}
