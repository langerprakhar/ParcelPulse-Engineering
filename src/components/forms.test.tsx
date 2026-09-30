import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { findShipment, registerShipment } from "@/actions/shipments";

import { AddShipmentForm } from "./AddShipmentForm";
import { TrackingSearchForm } from "./TrackingSearchForm";

// The real actions run on the server; here they are replaced to observe what the
// forms submit and how they render each returned state.
vi.mock("@/actions/shipments", () => ({
  findShipment: vi.fn(),
  registerShipment: vi.fn(),
}));

beforeEach(() => {
  vi.mocked(findShipment).mockReset();
  vi.mocked(registerShipment).mockReset();
});

function submitted(action: typeof findShipment | typeof registerShipment): Record<string, unknown> {
  const formData = vi.mocked(action).mock.calls.at(-1)![1];
  return Object.fromEntries(formData.entries());
}

describe("TrackingSearchForm", () => {
  it("submits the tracking number that was typed", async () => {
    vi.mocked(findShipment).mockResolvedValue({});
    render(<TrackingSearchForm />);

    await userEvent.type(screen.getByLabelText("Tracking number"), "SC4F7K2M9Q1X");
    await userEvent.click(screen.getByRole("button", { name: "Track" }));

    expect(submitted(findShipment)).toEqual({ tracking_number: "SC4F7K2M9Q1X" });
  });

  it("shows a validation error returned by the server", async () => {
    vi.mocked(findShipment).mockResolvedValue({
      trackingNumber: "BAD",
      error: "Enter a tracking number: 6 to 40 letters and digits.",
    });
    render(<TrackingSearchForm />);

    await userEvent.type(screen.getByLabelText("Tracking number"), "bad");
    await userEvent.click(screen.getByRole("button", { name: "Track" }));

    expect(await screen.findByText(/6 to 40 letters and digits/)).toBeInTheDocument();
    expect(screen.getByLabelText("Tracking number")).toHaveAttribute("aria-invalid", "true");
  });

  it("offers to add a shipment that is not tracked yet", async () => {
    vi.mocked(findShipment).mockResolvedValue({ trackingNumber: "SC0000000000", notFound: true });
    render(<TrackingSearchForm />);

    await userEvent.type(screen.getByLabelText("Tracking number"), "SC0000000000");
    await userEvent.click(screen.getByRole("button", { name: "Track" }));

    const link = await screen.findByRole("link", { name: "Add it as a new shipment" });
    expect(link).toHaveAttribute("href", "/?add=SC0000000000#add-shipment");
  });
});

describe("AddShipmentForm", () => {
  const carriers = [{ code: "simcarrier" }, { code: "othercarrier" }];

  it("submits tracking number, carrier and email", async () => {
    vi.mocked(registerShipment).mockResolvedValue({});
    render(<AddShipmentForm carriers={carriers} />);

    await userEvent.type(screen.getByLabelText("Tracking number"), "SC4F7K2M9Q1X");
    await userEvent.selectOptions(screen.getByLabelText("Carrier"), "othercarrier");
    await userEvent.type(screen.getByLabelText(/Email for notifications/), "me@example.com");
    await userEvent.click(screen.getByRole("button", { name: "Start tracking" }));

    expect(submitted(registerShipment)).toEqual({
      tracking_number: "SC4F7K2M9Q1X",
      carrier: "othercarrier",
      notification_email: "me@example.com",
    });
  });

  it("prefills the tracking number handed over from the search form", () => {
    render(<AddShipmentForm carriers={carriers} defaultTrackingNumber="SC0000000000" />);

    expect(screen.getByLabelText("Tracking number")).toHaveValue("SC0000000000");
  });

  it("shows field errors next to their fields and keeps the entered values", async () => {
    vi.mocked(registerShipment).mockResolvedValue({
      values: { tracking_number: "SC4F7K2M9Q1X", carrier: "simcarrier", notification_email: "nope" },
      fieldErrors: { notification_email: "Enter a valid email address, or leave it empty." },
    });
    render(<AddShipmentForm carriers={carriers} />);

    await userEvent.type(screen.getByLabelText("Tracking number"), "SC4F7K2M9Q1X");
    await userEvent.click(screen.getByRole("button", { name: "Start tracking" }));

    expect(await screen.findByText(/valid email address/)).toBeInTheDocument();
    const email = screen.getByLabelText(/Email for notifications/);
    expect(email).toHaveAttribute("aria-invalid", "true");
    expect(email).toHaveValue("nope");
    expect(screen.getByLabelText("Tracking number")).toHaveValue("SC4F7K2M9Q1X");
  });

  it("cannot be submitted when no carrier is available", () => {
    render(<AddShipmentForm carriers={[]} />);

    expect(screen.getByRole("button", { name: "Start tracking" })).toBeDisabled();
  });
});
