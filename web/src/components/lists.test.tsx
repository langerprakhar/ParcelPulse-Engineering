import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { pageWindow } from "@/lib/pagination";
import type { Shipment } from "@/lib/types";

import { Pagination } from "./Pagination";
import { ShipmentTable } from "./ShipmentTable";
import { StatusBadge } from "./StatusBadge";

function shipment(overrides: Partial<Shipment> = {}): Shipment {
  return {
    id: "11111111-2222-3333-4444-555555555555",
    tracking_number: "SC4F7K2M9Q1X",
    carrier: "simcarrier",
    current_status: "IN_TRANSIT",
    estimated_delivery_at: "2026-10-02T18:00:00Z",
    last_event_at: "2026-09-30T14:05:00Z",
    created_at: "2026-09-29T09:00:00Z",
    updated_at: "2026-09-30T14:05:10Z",
    ...overrides,
  };
}

describe("StatusBadge", () => {
  it("shows wording rather than the raw status, with a tone class", () => {
    render(<StatusBadge status="OUT_FOR_DELIVERY" />);

    const badge = screen.getByText("Out for delivery");
    expect(badge).toHaveClass("badge", "badge-active");
  });

  it("falls back to the raw value for a status it does not know", () => {
    render(<StatusBadge status="HELD_AT_CUSTOMS" />);

    expect(screen.getByText("HELD_AT_CUSTOMS")).toHaveClass("badge");
  });
});

describe("ShipmentTable", () => {
  it("links each tracking number to its shipment and shows status and times", () => {
    render(<ShipmentTable shipments={[shipment()]} />);

    const row = screen.getAllByRole("row")[1];
    const link = within(row).getByRole("link", { name: "SC4F7K2M9Q1X" });
    expect(link).toHaveAttribute("href", "/shipments/11111111-2222-3333-4444-555555555555");
    expect(within(row).getByText("In transit")).toBeInTheDocument();
    expect(within(row).getByText("simcarrier")).toBeInTheDocument();

    const times = within(row).getAllByRole("time");
    expect(times.map((time) => time.getAttribute("datetime"))).toEqual([
      "2026-10-02T18:00:00Z",
      "2026-09-30T14:05:00Z",
    ]);
  });

  it("says so when the carrier gave no estimate and no event has arrived", () => {
    render(
      <ShipmentTable
        shipments={[
          shipment({ current_status: "CREATED", estimated_delivery_at: null, last_event_at: null }),
        ]}
      />,
    );

    expect(screen.getByText("Awaiting carrier")).toBeInTheDocument();
    expect(screen.getByText("Not provided")).toBeInTheDocument();
    expect(screen.getByText("No events yet")).toBeInTheDocument();
  });
});

describe("Pagination", () => {
  const hrefFor = (page: number) => `/shipments?status=DELIVERED&page=${page}`;

  it("describes the range and links to the neighbouring pages", () => {
    render(<Pagination range={pageWindow(53, 2, 20)} hrefFor={hrefFor} noun="shipments" />);

    expect(screen.getByText("Showing 21–40 of 53 shipments")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Previous" })).toHaveAttribute(
      "href",
      "/shipments?status=DELIVERED&page=1",
    );
    expect(screen.getByRole("link", { name: "Next" })).toHaveAttribute(
      "href",
      "/shipments?status=DELIVERED&page=3",
    );
  });

  it("omits links that would lead nowhere", () => {
    render(<Pagination range={pageWindow(12, 1, 20)} hrefFor={hrefFor} noun="shipments" />);

    expect(screen.getByText("Showing 1–12 of 12 shipments")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Previous" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Next" })).not.toBeInTheDocument();
  });

  it("leads back to the last real page from beyond the end", () => {
    render(<Pagination range={pageWindow(12, 7, 20)} hrefFor={hrefFor} noun="shipments" />);

    expect(screen.getByText("No shipments on this page")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Previous" })).toHaveAttribute(
      "href",
      "/shipments?status=DELIVERED&page=1",
    );
  });
});
