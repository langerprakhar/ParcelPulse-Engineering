"use client";

import { useActionState } from "react";

import { registerShipment, type RegisterState } from "@/actions/shipments";
import type { Carrier } from "@/lib/types";

export function AddShipmentForm({
  carriers,
  defaultTrackingNumber = "",
}: {
  carriers: Carrier[];
  defaultTrackingNumber?: string;
}) {
  const [state, formAction, pending] = useActionState<RegisterState, FormData>(
    registerShipment,
    {},
  );
  const values = state.values ?? {};
  const errors = state.fieldErrors ?? {};

  return (
    <form action={formAction} className="stack-small" aria-label="Add a shipment">
      <div className="form-grid">
        <div>
          <label htmlFor="add-tracking-number">Tracking number</label>
          <input
            id="add-tracking-number"
            name="tracking_number"
            type="text"
            required
            autoComplete="off"
            spellCheck={false}
            className="mono"
            defaultValue={values.tracking_number ?? defaultTrackingNumber}
            aria-invalid={errors.tracking_number ? true : undefined}
            aria-describedby={errors.tracking_number ? "add-tracking-number-error" : undefined}
          />
          {errors.tracking_number ? (
            <p id="add-tracking-number-error" className="small notice notice-error">
              {errors.tracking_number}
            </p>
          ) : null}
        </div>

        <div>
          <label htmlFor="add-carrier">Carrier</label>
          <select
            id="add-carrier"
            name="carrier"
            required
            defaultValue={values.carrier ?? carriers[0]?.code ?? ""}
            aria-invalid={errors.carrier ? true : undefined}
            aria-describedby={errors.carrier ? "add-carrier-error" : undefined}
          >
            {carriers.length === 0 ? <option value="">No carriers available</option> : null}
            {carriers.map((carrier) => (
              <option key={carrier.code} value={carrier.code}>
                {carrier.code}
              </option>
            ))}
          </select>
          {errors.carrier ? (
            <p id="add-carrier-error" className="small notice notice-error">
              {errors.carrier}
            </p>
          ) : null}
        </div>

        <div>
          <label htmlFor="add-email">
            Email for notifications <span className="field-hint">(optional)</span>
          </label>
          <input
            id="add-email"
            name="notification_email"
            type="email"
            autoComplete="email"
            defaultValue={values.notification_email ?? ""}
            aria-invalid={errors.notification_email ? true : undefined}
            aria-describedby={errors.notification_email ? "add-email-error" : undefined}
          />
          {errors.notification_email ? (
            <p id="add-email-error" className="small notice notice-error">
              {errors.notification_email}
            </p>
          ) : null}
        </div>
      </div>

      {state.error ? (
        <p className="notice notice-error" role="alert">
          {state.error}
        </p>
      ) : null}

      <div>
        <button type="submit" className="button" disabled={pending || carriers.length === 0}>
          {pending ? "Adding…" : "Start tracking"}
        </button>
      </div>
    </form>
  );
}
