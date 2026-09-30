import "server-only";

import { notFound } from "next/navigation";

import { getShipment, isApiError } from "@/lib/api";
import type { Shipment } from "@/lib/types";

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** Loads the shipment for a page, rendering the not-found page when it does not exist. */
export async function loadShipmentOr404(shipmentId: string): Promise<Shipment> {
  // A malformed id can never match; do not bother the API with it.
  if (!UUID_PATTERN.test(shipmentId)) notFound();
  try {
    return await getShipment(shipmentId);
  } catch (error) {
    if (isApiError(error, "shipment_not_found")) notFound();
    throw error;
  }
}
