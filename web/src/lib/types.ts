/** Shapes returned by parcelpulse-api. Field names match the API's JSON exactly. */

export const SHIPMENT_STATUSES = [
  "CREATED",
  "LABEL_CREATED",
  "IN_TRANSIT",
  "AT_DISTRIBUTION_CENTER",
  "OUT_FOR_DELIVERY",
  "DELIVERED",
  "DELIVERY_EXCEPTION",
  "RETURNED",
] as const;

export type ShipmentStatus = (typeof SHIPMENT_STATUSES)[number];
export type EventType = Exclude<ShipmentStatus, "CREATED">;

export interface Shipment {
  id: string;
  tracking_number: string;
  carrier: string;
  current_status: ShipmentStatus;
  estimated_delivery_at: string | null;
  last_event_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface EventLocation {
  facility?: string;
  city?: string;
  region?: string;
  country?: string;
}

export interface TrackingEvent {
  id: string;
  shipment_id: string;
  provider: string;
  provider_event_id: string;
  event_type: EventType;
  /** When it happened, by the carrier's clock. The timeline is ordered by this. */
  event_at: string;
  /** When ParcelPulse received the event. */
  received_at: string;
  location: EventLocation | null;
  description: string | null;
  estimated_delivery_at: string | null;
  /** True when the event was delivered after one that happened later. */
  arrived_out_of_order: boolean;
  changed_status: boolean;
  status_after: ShipmentStatus;
}

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface Carrier {
  code: string;
}

export interface NotificationPreference {
  shipment_id: string;
  email: string | null;
  notify_out_for_delivery: boolean;
  notify_delivered: boolean;
  notify_delivery_exception: boolean;
  /** Null while the defaults apply because nothing has been saved yet. */
  updated_at: string | null;
}

export type NotificationPreferenceInput = Omit<NotificationPreference, "shipment_id" | "updated_at">;

export type NotificationType = "OUT_FOR_DELIVERY" | "DELIVERED" | "DELIVERY_EXCEPTION";
export type NotificationStatus = "PENDING" | "SENDING" | "SENT" | "RETRYING" | "FAILED";

export interface Notification {
  id: string;
  shipment_id: string;
  tracking_event_id: string;
  type: NotificationType;
  channel: string;
  destination: string;
  status: NotificationStatus;
  attempts: number;
  created_at: string;
  sent_at: string | null;
  last_error: string | null;
}

export interface NewShipment {
  tracking_number: string;
  carrier: string;
  notification_email?: string;
}
