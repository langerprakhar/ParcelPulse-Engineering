import type { Metadata } from "next";
import Link from "next/link";

import { AutoRefresh } from "@/components/AutoRefresh";
import { LocalTime } from "@/components/LocalTime";
import { StatusBadge } from "@/components/StatusBadge";
import { Timeline } from "@/components/Timeline";
import { getNotificationPreference, listEvents } from "@/lib/api";
import { loadShipmentOr404 } from "@/lib/shipment";
import type { NotificationPreference } from "@/lib/types";

export const metadata: Metadata = { title: "Shipment" };

// The API returns at most this many events per request.
const TIMELINE_LIMIT = 100;

function enabledNotifications(preference: NotificationPreference): string[] {
  return [
    preference.notify_out_for_delivery ? "out for delivery" : null,
    preference.notify_delivered ? "delivered" : null,
    preference.notify_delivery_exception ? "delivery problems" : null,
  ].filter((label): label is string => label !== null);
}

export default async function ShipmentPage({ params }: PageProps<"/shipments/[id]">) {
  const { id } = await params;
  const shipment = await loadShipmentOr404(id);
  const [events, preference] = await Promise.all([
    listEvents(shipment.id, { order: "desc", limit: TIMELINE_LIMIT }),
    getNotificationPreference(shipment.id),
  ]);

  // Newest first, so the first event of the current status is the one that set it.
  const currentEvent = events.items.find((event) => event.event_type === shipment.current_status);
  const delivered = shipment.current_status === "DELIVERED";
  const notifyFor = enabledNotifications(preference);

  return (
    <div className="stack">
      <p className="breadcrumbs">
        <Link href="/shipments">Shipments</Link> / <span className="mono">{shipment.tracking_number}</span>
      </p>

      <section className="card stack" aria-labelledby="shipment-heading">
        <div className="row-between">
          <div className="row">
            <h1 id="shipment-heading" className="mono">
              {shipment.tracking_number}
            </h1>
            <StatusBadge status={shipment.current_status} />
          </div>
          <AutoRefresh />
        </div>
        <dl className="facts">
          <div>
            <dt>Carrier</dt>
            <dd>{shipment.carrier}</dd>
          </div>
          <div>
            <dt>{delivered ? "Delivered" : "Estimated delivery"}</dt>
            <dd>
              {delivered && currentEvent ? (
                <LocalTime iso={currentEvent.event_at} />
              ) : shipment.estimated_delivery_at ? (
                <LocalTime iso={shipment.estimated_delivery_at} />
              ) : (
                <span className="muted">Not provided by the carrier</span>
              )}
            </dd>
          </div>
          <div>
            <dt>Last carrier update</dt>
            <dd>
              {shipment.last_event_at ? (
                <LocalTime iso={shipment.last_event_at} />
              ) : (
                <span className="muted">No events yet</span>
              )}
            </dd>
          </div>
          <div>
            <dt>Tracking since</dt>
            <dd>
              <LocalTime iso={shipment.created_at} />
            </dd>
          </div>
        </dl>
      </section>

      <div className="grid-two">
        <section className="card" aria-labelledby="timeline-heading">
          <div className="row-between card-title">
            <h2 id="timeline-heading">Timeline</h2>
            <span className="small muted">
              {events.total === 1 ? "1 event" : `${events.total} events`}, newest first
            </span>
          </div>
          <Timeline events={events.items} currentEventId={currentEvent?.id} />
          {events.total > events.items.length ? (
            <p className="small muted">
              Showing the {events.items.length} most recent of {events.total} events.
            </p>
          ) : null}
        </section>

        <section className="card stack-small" aria-labelledby="notifications-heading">
          <h2 id="notifications-heading">Notifications</h2>
          {preference.email && notifyFor.length > 0 ? (
            <p>
              Emails go to <strong>{preference.email}</strong> for: {notifyFor.join(", ")}.
            </p>
          ) : (
            <p className="muted">
              {preference.email
                ? "Every notification is switched off for this shipment."
                : "Off. Add an email address to be told when this parcel is on its way."}
            </p>
          )}
          <div>
            <Link
              href={`/shipments/${shipment.id}/notifications`}
              className="button button-secondary"
            >
              Manage notifications
            </Link>
          </div>
        </section>
      </div>
    </div>
  );
}
