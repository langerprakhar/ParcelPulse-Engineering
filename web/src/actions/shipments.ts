"use server";

import { redirect } from "next/navigation";

import {
  ApiUnavailableError,
  createShipment,
  getShipmentByTrackingNumber,
  isApiError,
} from "@/lib/api";
import { isValidTrackingNumber, normalizeTrackingNumber } from "@/lib/format";
import type { Shipment } from "@/lib/types";

const INVALID_TRACKING_NUMBER = "Enter a tracking number: 6 to 40 letters and digits.";
const SERVICE_UNAVAILABLE = "The tracking service is not available right now. Please try again.";

export interface SearchState {
  trackingNumber?: string;
  error?: string;
  /** Set when the number is well-formed but ParcelPulse is not tracking it. */
  notFound?: boolean;
}

export async function findShipment(
  _previous: SearchState,
  formData: FormData,
): Promise<SearchState> {
  const trackingNumber = normalizeTrackingNumber(String(formData.get("tracking_number") ?? ""));
  if (!isValidTrackingNumber(trackingNumber)) {
    return { trackingNumber, error: INVALID_TRACKING_NUMBER };
  }

  let shipment: Shipment;
  try {
    shipment = await getShipmentByTrackingNumber(trackingNumber);
  } catch (error) {
    if (isApiError(error, "shipment_not_found")) {
      return { trackingNumber, notFound: true };
    }
    if (isApiError(error, "ambiguous_tracking_number")) {
      return {
        trackingNumber,
        error: "This tracking number exists for more than one carrier. Open it from Shipments.",
      };
    }
    if (error instanceof ApiUnavailableError) {
      return { trackingNumber, error: SERVICE_UNAVAILABLE };
    }
    throw error;
  }
  // redirect() works by throwing, so it must stay outside the try block.
  redirect(`/shipments/${shipment.id}`);
}

export type RegisterField = "tracking_number" | "carrier" | "notification_email";

export interface RegisterState {
  values?: Partial<Record<RegisterField, string>>;
  error?: string;
  fieldErrors?: Partial<Record<RegisterField, string>>;
}

export async function registerShipment(
  _previous: RegisterState,
  formData: FormData,
): Promise<RegisterState> {
  const values = {
    tracking_number: normalizeTrackingNumber(String(formData.get("tracking_number") ?? "")),
    carrier: String(formData.get("carrier") ?? "").trim(),
    notification_email: String(formData.get("notification_email") ?? "").trim(),
  };

  const fieldErrors: RegisterState["fieldErrors"] = {};
  if (!isValidTrackingNumber(values.tracking_number)) {
    fieldErrors.tracking_number = INVALID_TRACKING_NUMBER;
  }
  if (!values.carrier) {
    fieldErrors.carrier = "Choose the carrier that is delivering the parcel.";
  }
  if (Object.keys(fieldErrors).length > 0) {
    return { values, fieldErrors };
  }

  let shipmentId: string;
  try {
    const shipment = await createShipment({
      tracking_number: values.tracking_number,
      carrier: values.carrier,
      ...(values.notification_email ? { notification_email: values.notification_email } : {}),
    });
    shipmentId = shipment.id;
  } catch (error) {
    if (isApiError(error, "shipment_already_exists")) {
      // Already tracked: take the user to it instead of reporting a failure.
      const existing = (error.details as { shipment_id?: string } | null)?.shipment_id;
      if (existing) redirect(`/shipments/${existing}`);
      return { values, error: "This parcel is already being tracked." };
    }
    if (isApiError(error, "unsupported_carrier")) {
      return { values, fieldErrors: { carrier: "This carrier is not supported." } };
    }
    if (isApiError(error, "validation_error")) {
      return { values, fieldErrors: fieldErrorsFrom(error.details) };
    }
    if (error instanceof ApiUnavailableError) {
      return { values, error: SERVICE_UNAVAILABLE };
    }
    throw error;
  }
  redirect(`/shipments/${shipmentId}`);
}

const FIELD_MESSAGES: Record<RegisterField, string> = {
  tracking_number: INVALID_TRACKING_NUMBER,
  carrier: "Choose the carrier that is delivering the parcel.",
  notification_email: "Enter a valid email address, or leave it empty.",
};

/** Maps the API's validation details (`loc: ["body", field]`) onto form fields. */
function fieldErrorsFrom(details: unknown): RegisterState["fieldErrors"] {
  const fieldErrors: RegisterState["fieldErrors"] = {};
  if (Array.isArray(details)) {
    for (const detail of details) {
      const field = (detail as { loc?: unknown[] })?.loc?.[1];
      if (typeof field === "string" && field in FIELD_MESSAGES) {
        fieldErrors[field as RegisterField] = FIELD_MESSAGES[field as RegisterField];
      }
    }
  }
  return fieldErrors;
}
