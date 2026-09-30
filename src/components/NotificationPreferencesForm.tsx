"use client";

import { useActionState } from "react";

import { savePreferences, type PreferenceState } from "@/actions/notifications";
import type { NotificationPreference } from "@/lib/types";

const OPTIONS = [
  {
    name: "notify_out_for_delivery",
    label: "Out for delivery",
    hint: "The parcel is on the vehicle and should arrive today.",
  },
  {
    name: "notify_delivered",
    label: "Delivered",
    hint: "The carrier has handed the parcel over.",
  },
  {
    name: "notify_delivery_exception",
    label: "Delivery problems",
    hint: "A delivery attempt failed or the carrier reported an exception.",
  },
] as const;

export function NotificationPreferencesForm({
  preference,
}: {
  preference: NotificationPreference;
}) {
  const [state, formAction, pending] = useActionState<PreferenceState, FormData>(
    savePreferences.bind(null, preference.shipment_id),
    {},
  );
  const emailError = state.fieldErrors?.email;

  return (
    <form action={formAction} className="stack-small" aria-label="Notification preferences">
      <div>
        <label htmlFor="preference-email">Email address</label>
        <input
          id="preference-email"
          name="email"
          type="email"
          autoComplete="email"
          defaultValue={preference.email ?? ""}
          aria-invalid={emailError ? true : undefined}
          aria-describedby="preference-email-hint"
        />
        <p id="preference-email-hint" className="small muted">
          Leave empty to switch notifications off for this shipment.
        </p>
        {emailError ? <p className="small notice notice-error">{emailError}</p> : null}
      </div>

      <fieldset className="stack-small plain-fieldset">
        <legend className="small muted">Send an email when the parcel is</legend>
        {OPTIONS.map((option) => (
          <label key={option.name} className="checkbox">
            <input type="checkbox" name={option.name} defaultChecked={preference[option.name]} />
            <span>
              {option.label}
              <span className="small muted"> - {option.hint}</span>
            </span>
          </label>
        ))}
      </fieldset>

      <div aria-live="polite">
        {state.error ? <p className="notice notice-error">{state.error}</p> : null}
        {state.saved ? <p className="notice notice-success">Preferences saved.</p> : null}
      </div>

      <div>
        <button type="submit" className="button" disabled={pending}>
          {pending ? "Saving…" : "Save preferences"}
        </button>
      </div>
    </form>
  );
}
