import type { Metadata } from "next";
import Link from "next/link";

import { Pagination } from "@/components/Pagination";
import { ShipmentTable } from "@/components/ShipmentTable";
import { listShipments } from "@/lib/api";
import { statusLabel } from "@/lib/format";
import { pageWindow, parsePage } from "@/lib/pagination";
import { SHIPMENT_STATUSES, type ShipmentStatus } from "@/lib/types";

export const metadata: Metadata = { title: "Shipments" };

const PAGE_SIZE = 20;

function parseStatus(value: string | string[] | undefined): ShipmentStatus | undefined {
  const text = Array.isArray(value) ? value[0] : value;
  return SHIPMENT_STATUSES.find((status) => status === text);
}

export default async function ShipmentsPage({ searchParams }: PageProps<"/shipments">) {
  const params = await searchParams;
  const status = parseStatus(params.status);
  const page = parsePage(params.page);

  const shipments = await listShipments({
    limit: PAGE_SIZE,
    offset: (page - 1) * PAGE_SIZE,
    status,
  });
  const range = pageWindow(shipments.total, page, PAGE_SIZE);

  const hrefFor = (target: number) => {
    const query = new URLSearchParams();
    if (status) query.set("status", status);
    if (target > 1) query.set("page", String(target));
    const text = query.toString();
    return text ? `/shipments?${text}` : "/shipments";
  };

  return (
    <div className="stack">
      <div className="row-between">
        <h1>Shipments</h1>
        <Link href="/#add-shipment" className="button">
          Add a shipment
        </Link>
      </div>

      <form method="get" action="/shipments" className="card row filter-row" aria-label="Filter shipments">
        <label htmlFor="status-filter">Status</label>
        <select id="status-filter" name="status" defaultValue={status ?? ""}>
          <option value="">All statuses</option>
          {SHIPMENT_STATUSES.map((option) => (
            <option key={option} value={option}>
              {statusLabel(option)}
            </option>
          ))}
        </select>
        <button type="submit" className="button button-secondary">
          Apply
        </button>
        {status ? <Link href="/shipments">Clear</Link> : null}
      </form>

      <section className="card card-flush" aria-label="Shipment list">
        {shipments.items.length > 0 ? (
          <ShipmentTable shipments={shipments.items} />
        ) : (
          <p className="empty">
            {status
              ? `No shipments are currently "${statusLabel(status)}".`
              : "No shipments yet. Add one to start tracking."}
          </p>
        )}
        <Pagination range={range} hrefFor={hrefFor} noun="shipments" />
      </section>
    </div>
  );
}
