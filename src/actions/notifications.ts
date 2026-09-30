"use server";

import { refresh } from "next/cache";

import { ApiUnavailableError, isApiError, saveNotificationPreference } from "@/lib/api";

export interface PreferenceState {
  saved?: boolean;
  error?: string;
  fieldErrors?: { email?: string };
}

/**
 * Replaces a shipment's notification preferences. Bind the shipment id first:
 * `savePreferences.bind(null, shipmentId)`.
 */
export async function savePreferences(
  shipmentId: string,
  _previous: PreferenceState,
  formData: FormData,
): Promise<PreferenceState> {
  const email = String(formData.get("email") ?? "").trim();

  try {
    await saveNotificationPreference(shipmentId, {
      // An empty address switches notifications off.
      email: email === "" ? null : email,
      // Unchecked checkboxes are absent from the form data.
      notify_out_for_delivery: formData.get("notify_out_for_delivery") === "on",
      notify_delivered: formData.get("notify_delivered") === "on",
      notify_delivery_exception: formData.get("notify_delivery_exception") === "on",
    });
  } catch (error) {
    if (isApiError(error, "validation_error")) {
      return { fieldErrors: { email: "Enter a valid email address, or leave it empty." } };
    }
    if (isApiError(error, "shipment_not_found")) {
      return { error: "This shipment no longer exists." };
    }
    if (error instanceof ApiUnavailableError) {
      return { error: "The tracking service is not available right now. Please try again." };
    }
    throw error;
  }

  // Re-render the page so it shows what the API now holds.
  refresh();
  return { saved: true };
}
