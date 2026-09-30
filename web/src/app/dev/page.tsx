import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { CreateSimulatedShipmentForm, SimulatorControls } from "@/components/DevControls";
import { StatusBadge } from "@/components/StatusBadge";
import { getShipmentByTrackingNumber } from "@/lib/api";
import { devToolsEnabled, mailSinkUrl } from "@/lib/config";
import {
  listScenarios,
  listSimulatedShipments,
  type SimulatedShipmentSummary,
} from "@/lib/simulator";
import type { Shipment } from "@/lib/types";

export const metadata: Metadata = { title: "Developer tools" };

interface SimulatedRow {
  simulated: SimulatedShipmentSummary;
  /** The matching ParcelPulse shipment, when it is registered there. */
  shipment: Shipment | null;
}

async function loadSimulator(): Promise<{ scenarios: string[]; rows: SimulatedRow[] } | null> {
  try {
    const [scenarios, simulated] = await Promise.all([listScenarios(), listSimulatedShipments()]);
    const rows = await Promise.all(
      simulated.map(async (entry) => ({
        simulated: entry,
        shipment: await getShipmentByTrackingNumber(entry.tracking_number).catch(() => null),
      })),
    );
    return { scenarios: Object.keys(scenarios), rows: rows.reverse() };
  } catch {
    return null;
  }
}

export default async function DeveloperToolsPage() {
  // Not a feature of the product: the page does not exist unless switched on.
  if (!devToolsEnabled()) notFound();

  const simulator = await loadSimulator();

  return (
    <div className="stack">
      <div className="stack-small">
        <h1>Developer tools</h1>
        <p className="muted">
          Drive the carrier simulator to exercise ParcelPulse: send events in order, repeat them,
          delay them or swap them, and watch what the product does. Emails land in the{" "}
          <a href={mailSinkUrl()} target="_blank" rel="noreferrer">
            local mail sink
          </a>
          .
        </p>
      </div>

      {simulator === null ? (
        <p className="notice notice-error" role="alert">
          The carrier simulator is not reachable. Start the local stack from parcelpulse-infra.
        </p>
      ) : (
        <>
          <section className="card" aria-labelledby="create-heading">
            <h2 id="create-heading" className="card-title">
              New simulated shipment
            </h2>
            <CreateSimulatedShipmentForm scenarios={simulator.scenarios} />
          </section>

          <section className="stack" aria-labelledby="simulated-heading">
            <h2 id="simulated-heading">Simulated shipments</h2>
            {simulator.rows.length === 0 ? (
              <p className="card empty">None yet. Create one above.</p>
            ) : (
              simulator.rows.map(({ simulated, shipment }) => (
                <article key={simulated.tracking_number} className="card stack-small">
                  <div className="row-between">
                    <div className="row">
                      {shipment ? (
                        <Link href={`/shipments/${shipment.id}`} className="mono">
                          {simulated.tracking_number}
                        </Link>
                      ) : (
                        <span className="mono">{simulated.tracking_number}</span>
                      )}
                      {shipment ? (
                        <StatusBadge status={shipment.current_status} />
                      ) : (
                        <span className="tag">Not registered in ParcelPulse</span>
                      )}
                    </div>
                    <span className="small muted">
                      {simulated.scenario} · {simulated.sent} sent · {simulated.held} held ·{" "}
                      {simulated.planned} planned
                    </span>
                  </div>
                  <SimulatorControls trackingNumber={simulated.tracking_number} />
                </article>
              ))
            )}
          </section>
        </>
      )}
    </div>
  );
}
