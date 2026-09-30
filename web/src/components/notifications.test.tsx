import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { savePreferences } from "@/actions/notifications";
import type { Notification, NotificationPreference } from "@/lib/types";

import { NotificationHistory } from "./NotificationHistory";
import { NotificationPreferencesForm } from "./NotificationPreferencesForm";

vi.mock("@/actions/notifications", () => ({ savePreferences: vi.fn() }));

const SHIPMENT_ID = "11111111-2222-3333-4444-555555555555";

const PREFERENCE: NotificationPreference = {
  shipment_id: SHIPMENT_ID,
  email: "me@example.com",
  notify_out_for_delivery: true,
  notify_delivered: false,
  notify_delivery_exception: true,
  updated_at: "2026-09-30T10:00:00Z",
};

beforeEach(() => {
  vi.mocked(savePreferences).mockReset();
});

describe("NotificationPreferencesForm", () => {
  it("shows the saved preferences", () => {
    render(<NotificationPreferencesForm preference={PREFERENCE} />);

    expect(screen.getByLabelText("Email address")).toHaveValue("me@example.com");
    expect(screen.getByRole("checkbox", { name: /Out for delivery/ })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: /^Delivered/ })).not.toBeChecked();
    expect(screen.getByRole("checkbox", { name: /Delivery problems/ })).toBeChecked();
  });

  it("submits the edited preferences for this shipment", async () => {
    vi.mocked(savePreferences).mockResolvedValue({ saved: true });
    render(<NotificationPreferencesForm preference={PREFERENCE} />);

    const email = screen.getByLabelText("Email address");
    await userEvent.clear(email);
    await userEvent.type(email, "new@example.com");
    await userEvent.click(screen.getByRole("checkbox", { name: /^Delivered/ }));
    await userEvent.click(screen.getByRole("checkbox", { name: /Out for delivery/ }));
    await userEvent.click(screen.getByRole("button", { name: "Save preferences" }));

    const [shipmentId, , formData] = vi.mocked(savePreferences).mock.calls[0];
    expect(shipmentId).toBe(SHIPMENT_ID);
    expect(Object.fromEntries(formData.entries())).toEqual({
      email: "new@example.com",
      notify_delivered: "on",
      notify_delivery_exception: "on",
    });
    expect(await screen.findByText("Preferences saved.")).toBeInTheDocument();
  });

  it("shows an email error from the server", async () => {
    vi.mocked(savePreferences).mockResolvedValue({
      fieldErrors: { email: "Enter a valid email address, or leave it empty." },
    });
    render(<NotificationPreferencesForm preference={{ ...PREFERENCE, email: null }} />);

    await userEvent.click(screen.getByRole("button", { name: "Save preferences" }));

    expect(await screen.findByText(/valid email address/)).toBeInTheDocument();
    expect(screen.queryByText("Preferences saved.")).not.toBeInTheDocument();
  });
});

function notification(overrides: Partial<Notification>): Notification {
  return {
    id: "notification-1",
    shipment_id: SHIPMENT_ID,
    tracking_event_id: "event-1",
    type: "DELIVERED",
    channel: "EMAIL",
    destination: "me@example.com",
    status: "SENT",
    attempts: 1,
    created_at: "2026-09-30T14:05:20Z",
    sent_at: "2026-09-30T14:05:21Z",
    last_error: null,
    ...overrides,
  };
}

describe("NotificationHistory", () => {
  it("lists each notification with its delivery status", () => {
    render(
      <NotificationHistory
        notifications={[
          notification({ id: "sent" }),
          notification({
            id: "retrying",
            type: "OUT_FOR_DELIVERY",
            status: "RETRYING",
            attempts: 2,
            sent_at: null,
            last_error: "TransientDeliveryError: mail server unavailable",
          }),
        ]}
      />,
    );

    const [, sent, retrying] = screen.getAllByRole("row");
    expect(within(sent).getByText("Delivered")).toBeInTheDocument();
    expect(within(sent).getByText("Sent")).toHaveClass("badge-done");
    expect(within(sent).getByText("me@example.com")).toBeInTheDocument();

    expect(within(retrying).getByText("Out for delivery")).toBeInTheDocument();
    expect(within(retrying).getByText("Retrying")).toHaveClass("badge-active");
    expect(within(retrying).getByText("2")).toBeInTheDocument();
    expect(within(retrying).getByText(/mail server unavailable/)).toBeInTheDocument();
    expect(within(retrying).getByText("Not yet")).toBeInTheDocument();
  });

  it("explains an empty history", () => {
    render(<NotificationHistory notifications={[]} />);

    expect(screen.getByText(/Nothing has been sent/)).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});
