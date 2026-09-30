import Link from "next/link";

import { LocalTime } from "@/components/LocalTime";
import { StatusBadge } from "@/components/StatusBadge";
import type { Shipment } from "@/lib/types";

export function ShipmentTable({ shipments }: { shipments: Shipment[] }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th scope="col">Tracking number</th>
            <th scope="col">Carrier</th>
            <th scope="col">Status</th>
            <th scope="col">Estimated delivery</th>
            <th scope="col">Last update</th>
          </tr>
        </thead>
        <tbody>
          {shipments.map((shipment) => (
            <tr key={shipment.id}>
              <td>
                <Link href={`/shipments/${shipment.id}`} className="mono">
                  {shipment.tracking_number}
                </Link>
              </td>
              <td>{shipment.carrier}</td>
              <td>
                <StatusBadge status={shipment.current_status} />
              </td>
              <td>
                {shipment.estimated_delivery_at ? (
                  <LocalTime iso={shipment.estimated_delivery_at} />
                ) : (
                  <span className="muted">Not provided</span>
                )}
              </td>
              <td>
                {shipment.last_event_at ? (
                  <LocalTime iso={shipment.last_event_at} />
                ) : (
                  <span className="muted">No events yet</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
