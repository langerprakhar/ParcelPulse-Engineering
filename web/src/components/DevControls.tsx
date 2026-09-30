"use client";

import { useActionState } from "react";

import { createSimulated, simulate, type DevState } from "@/actions/dev";

const OPERATIONS = [
  { value: "advance", label: "Send next event", hint: "The next planned event, in order" },
  { value: "duplicate", label: "Resend last event", hint: "A carrier retry: same event again" },
  { value: "hold", label: "Hold next event", hint: "Skip it for now; release it later" },
  { value: "release-held", label: "Release held", hint: "Deliver held events late" },
  { value: "out-of-order", label: "Swap next two", hint: "Send the next two events reversed" },
  { value: "exception", label: "Delivery exception", hint: "Inject a failed delivery attempt" },
  { value: "lifecycle", label: "Finish journey", hint: "Send everything not yet sent" },
] as const;

function Feedback({ state }: { state: DevState }) {
  return (
    <div aria-live="polite">
      {state.error ? <p className="notice notice-error">{state.error}</p> : null}
      {state.message ? <p className="notice notice-success">{state.message}</p> : null}
      {state.lines && state.lines.length > 0 ? (
        <ul className="notice notice-info dev-lines">
          {state.lines.map((line, index) => (
            <li key={index} className="mono">
              {line}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

export function CreateSimulatedShipmentForm({ scenarios }: { scenarios: string[] }) {
  const [state, formAction, pending] = useActionState<DevState, FormData>(createSimulated, {});

  return (
    <form action={formAction} className="stack-small" aria-label="Create a simulated shipment">
      <div className="form-grid">
        <div>
          <label htmlFor="dev-scenario">Scenario</label>
          <select id="dev-scenario" name="scenario" defaultValue={scenarios[0] ?? "standard"}>
            {scenarios.map((scenario) => (
              <option key={scenario} value={scenario}>
                {scenario}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="dev-email">
            Notification email <span className="field-hint">(optional)</span>
          </label>
          <input
            id="dev-email"
            name="notification_email"
            type="email"
            defaultValue="dev@example.com"
          />
        </div>
      </div>
      <Feedback state={state} />
      <div>
        <button type="submit" className="button" disabled={pending}>
          {pending ? "Creating…" : "Create simulated shipment"}
        </button>
      </div>
    </form>
  );
}

export function SimulatorControls({ trackingNumber }: { trackingNumber: string }) {
  const [state, formAction, pending] = useActionState<DevState, FormData>(simulate, {});

  return (
    <form action={formAction} className="stack-small" aria-label={`Simulate ${trackingNumber}`}>
      <input type="hidden" name="tracking_number" value={trackingNumber} />
      <div className="row">
        {OPERATIONS.map((operation) => (
          <button
            key={operation.value}
            type="submit"
            name="operation"
            value={operation.value}
            title={operation.hint}
            className="button button-secondary button-small"
            disabled={pending}
          >
            {operation.label}
          </button>
        ))}
      </div>
      <Feedback state={state} />
    </form>
  );
}
