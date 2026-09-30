import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { createSimulated, simulate } from "@/actions/dev";

import { CreateSimulatedShipmentForm, SimulatorControls } from "./DevControls";

vi.mock("@/actions/dev", () => ({ createSimulated: vi.fn(), simulate: vi.fn() }));

beforeEach(() => {
  vi.mocked(createSimulated).mockReset();
  vi.mocked(simulate).mockReset();
});

describe("SimulatorControls", () => {
  it("submits the clicked operation for its shipment", async () => {
    vi.mocked(simulate).mockResolvedValue({ lines: ["IN_TRANSIT → PROCESSED"] });
    render(<SimulatorControls trackingNumber="SC4F7K2M9Q1X" />);

    await userEvent.click(screen.getByRole("button", { name: "Resend last event" }));

    const formData = vi.mocked(simulate).mock.calls[0][1];
    expect(Object.fromEntries(formData.entries())).toEqual({
      tracking_number: "SC4F7K2M9Q1X",
      operation: "duplicate",
    });
  });

  it("shows what the simulator sent and how ParcelPulse answered", async () => {
    vi.mocked(simulate).mockResolvedValue({
      lines: ["IN_TRANSIT → PROCESSED", "IN_TRANSIT (duplicate) → DUPLICATE"],
    });
    render(<SimulatorControls trackingNumber="SC4F7K2M9Q1X" />);

    await userEvent.click(screen.getByRole("button", { name: "Send next event" }));

    expect(await screen.findByText("IN_TRANSIT (duplicate) → DUPLICATE")).toBeInTheDocument();
  });

  it("shows why an operation was not possible", async () => {
    vi.mocked(simulate).mockResolvedValue({ error: "no held events to release" });
    render(<SimulatorControls trackingNumber="SC4F7K2M9Q1X" />);

    await userEvent.click(screen.getByRole("button", { name: "Release held" }));

    expect(await screen.findByText("no held events to release")).toBeInTheDocument();
  });

  it("offers every simulator behaviour", () => {
    render(<SimulatorControls trackingNumber="SC4F7K2M9Q1X" />);

    expect(screen.getAllByRole("button").map((button) => button.getAttribute("value"))).toEqual([
      "advance",
      "duplicate",
      "hold",
      "release-held",
      "out-of-order",
      "exception",
      "lifecycle",
    ]);
  });
});

describe("CreateSimulatedShipmentForm", () => {
  it("submits the chosen scenario and email", async () => {
    vi.mocked(createSimulated).mockResolvedValue({ message: "Created SC4F7K2M9Q1X." });
    render(<CreateSimulatedShipmentForm scenarios={["standard", "exception", "returned"]} />);

    await userEvent.selectOptions(screen.getByLabelText("Scenario"), "exception");
    await userEvent.click(screen.getByRole("button", { name: "Create simulated shipment" }));

    const formData = vi.mocked(createSimulated).mock.calls[0][1];
    expect(Object.fromEntries(formData.entries())).toEqual({
      scenario: "exception",
      notification_email: "dev@example.com",
    });
    expect(await screen.findByText("Created SC4F7K2M9Q1X.")).toBeInTheDocument();
  });
});
