import Link from "next/link";

import { AddShipmentForm } from "@/components/AddShipmentForm";
import { ShipmentTable } from "@/components/ShipmentTable";
import { TrackingSearchForm } from "@/components/TrackingSearchForm";
import { listCarriers, listShipments } from "@/lib/api";
import { isValidTrackingNumber, normalizeTrackingNumber } from "@/lib/format";
import type { Carrier, Shipment } from "@/lib/types";

const RECENT_COUNT = 5;

async function loadHomeData(): Promise<{
  carriers: Carrier[];
  recent: Shipment[];
  total: number;
  unavailable: boolean;
}> {
  try {
    const [carriers, shipments] = await Promise.all([
      listCarriers(),
      listShipments({ limit: RECENT_COUNT }),
    ]);
    return {
      carriers: carriers.items,
      recent: shipments.items,
      total: shipments.total,
      unavailable: false,
    };
  } catch {
    // The search form still renders; submitting it reports the outage too.
    return { carriers: [], recent: [], total: 0, unavailable: true };
  }
}

export default async function HomePage({ searchParams }: PageProps<"/">) {
  const { add } = await searchParams;
  const requested = normalizeTrackingNumber(typeof add === "string" ? add : "");
  const defaultTrackingNumber = isValidTrackingNumber(requested) ? requested : "";
  const { carriers, recent, total, unavailable } = await loadHomeData();

  return (
    <div className="stack">
      <div className="stack-small">
        <h1>Track a parcel</h1>
        <p className="muted">
          Follow a shipment from label to doorstep and get an email when it is out for delivery,
          delivered, or when something goes wrong.
        </p>
      </div>

      {unavailable ? (
        <p className="notice notice-error" role="alert">
          The tracking service is not available right now. Shipments cannot be shown or added
          until it is back.
        </p>
      ) : null}

      <section className="card" aria-labelledby="find-heading">
        <h2 id="find-heading" className="card-title">
          Find a shipment
        </h2>
        <TrackingSearchForm />
      </section>

      <section className="card" id="add-shipment" aria-labelledby="add-heading">
        <h2 id="add-heading" className="card-title">
          Add a shipment
        </h2>
        <AddShipmentForm
          key={defaultTrackingNumber}
          carriers={carriers}
          defaultTrackingNumber={defaultTrackingNumber}
        />
      </section>

      <section className="card card-flush" aria-labelledby="recent-heading">
        <div className="row-between card-header">
          <h2 id="recent-heading">Recent shipments</h2>
          {total > RECENT_COUNT ? <Link href="/shipments">View all {total}</Link> : null}
        </div>
        {recent.length > 0 ? (
          <ShipmentTable shipments={recent} />
        ) : (
          <p className="empty">No shipments yet. Add one above to start tracking.</p>
        )}
      </section>
    </div>
  );
}
