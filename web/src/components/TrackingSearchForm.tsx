"use client";

import Link from "next/link";
import { useActionState } from "react";

import { findShipment, type SearchState } from "@/actions/shipments";

const INITIAL: SearchState = {};

export function TrackingSearchForm() {
  const [state, formAction, pending] = useActionState(findShipment, INITIAL);

  return (
    <form action={formAction} className="stack-small" aria-label="Find a shipment">
      <div>
        <label htmlFor="search-tracking-number">Tracking number</label>
        <div className="search-row">
          <input
            id="search-tracking-number"
            name="tracking_number"
            type="text"
            required
            autoComplete="off"
            spellCheck={false}
            placeholder="e.g. SC4F7K2M9Q1X"
            defaultValue={state.trackingNumber ?? ""}
            aria-invalid={state.error ? true : undefined}
            aria-describedby="search-feedback"
          />
          <button type="submit" className="button" disabled={pending}>
            {pending ? "Searching…" : "Track"}
          </button>
        </div>
      </div>
      <div id="search-feedback" aria-live="polite">
        {state.error ? <p className="notice notice-error">{state.error}</p> : null}
        {state.notFound && state.trackingNumber ? (
          <p className="notice notice-info">
            <span className="mono">{state.trackingNumber}</span> is not being tracked yet.{" "}
            <Link href={`/?add=${encodeURIComponent(state.trackingNumber)}#add-shipment`}>
              Add it as a new shipment
            </Link>
            .
          </p>
        ) : null}
      </div>
    </form>
  );
}
