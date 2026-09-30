import type { Metadata } from "next";
import Link from "next/link";

import { AutoRefresh } from "@/components/AutoRefresh";
import { NotificationHistory } from "@/components/NotificationHistory";
import { NotificationPreferencesForm } from "@/components/NotificationPreferencesForm";
import { getNotificationPreference, listNotifications } from "@/lib/api";
import { loadShipmentOr404 } from "@/lib/shipment";

export const metadata: Metadata = { title: "Notifications" };

const HISTORY_LIMIT = 50;

export default async function ShipmentNotificationsPage({
  params,
}: PageProps<"/shipments/[id]/notifications">) {
  const { id } = await params;
  const shipment = await loadShipmentOr404(id);
  const [preference, notifications] = await Promise.all([
    getNotificationPreference(shipment.id),
    listNotifications(shipment.id, { limit: HISTORY_LIMIT }),
  ]);

  return (
    <div className="stack">
      <p className="breadcrumbs">
        <Link href="/shipments">Shipments</Link> /{" "}
        <Link href={`/shipments/${shipment.id}`} className="mono">
          {shipment.tracking_number}
        </Link>{" "}
        / Notifications
      </p>

      <div className="stack-small">
        <h1>Notifications</h1>
        <p className="muted">
          Choose where ParcelPulse sends updates about{" "}
          <span className="mono">{shipment.tracking_number}</span>. Changes apply to events
          received from now on.
        </p>
      </div>

      <section className="card" aria-labelledby="preferences-heading">
        <h2 id="preferences-heading" className="card-title">
          Preferences
        </h2>
        <NotificationPreferencesForm preference={preference} />
      </section>

      <section className="card card-flush" aria-labelledby="history-heading">
        <div className="row-between card-header">
          <h2 id="history-heading">History</h2>
          <AutoRefresh />
        </div>
        <NotificationHistory notifications={notifications.items} />
        {notifications.total > notifications.items.length ? (
          <p className="pagination">
            Showing the {notifications.items.length} most recent of {notifications.total}.
          </p>
        ) : null}
      </section>
    </div>
  );
}
