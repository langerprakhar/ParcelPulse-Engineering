import { act, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { TrackingEvent } from "@/lib/types";

import { AutoRefresh } from "./AutoRefresh";
import { Timeline } from "./Timeline";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

function event(overrides: Partial<TrackingEvent>): TrackingEvent {
  return {
    id: "event-1",
    shipment_id: "shipment-1",
    provider: "simcarrier",
    provider_event_id: "evt_1",
    event_type: "IN_TRANSIT",
    event_at: "2026-09-29T12:00:00Z",
    received_at: "2026-09-29T12:00:30Z",
    location: null,
    description: null,
    estimated_delivery_at: null,
    arrived_out_of_order: false,
    changed_status: true,
    status_after: "IN_TRANSIT",
    ...overrides,
  };
}

// As the page receives them: newest first by carrier time.
const EVENTS: TrackingEvent[] = [
  event({
    id: "delivered",
    event_type: "DELIVERED",
    event_at: "2026-09-30T14:05:00Z",
    received_at: "2026-09-30T14:05:20Z",
    location: { city: "Bristol", region: "ENG", country: "GB" },
    description: "Delivered, handed to resident",
    status_after: "DELIVERED",
  }),
  event({
    id: "hub",
    event_type: "AT_DISTRIBUTION_CENTER",
    event_at: "2026-09-29T20:00:00Z",
    // Reported a day late, after the delivery itself.
    received_at: "2026-09-30T18:30:00Z",
    location: { facility: "Midlands Distribution Centre", city: "Coventry" },
    arrived_out_of_order: true,
    changed_status: false,
    status_after: "DELIVERED",
  }),
  event({ id: "transit", event_type: "IN_TRANSIT", description: "Departed origin facility" }),
];

describe("Timeline", () => {
  it("keeps the order it was given and labels each event", () => {
    render(<Timeline events={EVENTS} />);

    const items = screen.getAllByRole("listitem");
    expect(items.map((item) => within(item).getByText(/./, { selector: ".timeline-title" }).textContent)).toEqual([
      "Delivered",
      "At distribution centre",
      "In transit",
    ]);
  });

  it("shows both the carrier's event time and when it was received", () => {
    render(<Timeline events={EVENTS} />);

    const hub = screen.getAllByRole("listitem")[1];
    const [eventTime, receivedTime] = within(hub).getAllByRole("time");
    expect(eventTime).toHaveAttribute("datetime", "2026-09-29T20:00:00Z");
    expect(receivedTime).toHaveAttribute("datetime", "2026-09-30T18:30:00Z");
    expect(hub).toHaveTextContent("received");
  });

  it("marks only the events that were reported late", () => {
    render(<Timeline events={EVENTS} />);

    const [delivered, hub, transit] = screen.getAllByRole("listitem");
    expect(within(hub).getByText("Reported late")).toBeInTheDocument();
    expect(within(delivered).queryByText("Reported late")).not.toBeInTheDocument();
    expect(within(transit).queryByText("Reported late")).not.toBeInTheDocument();
  });

  it("shows description and location when the carrier provided them", () => {
    render(<Timeline events={EVENTS} />);

    const [delivered, hub, transit] = screen.getAllByRole("listitem");
    expect(within(delivered).getByText("Delivered, handed to resident")).toBeInTheDocument();
    expect(within(delivered).getByText("Bristol, ENG, GB")).toBeInTheDocument();
    expect(within(hub).getByText("Midlands Distribution Centre, Coventry")).toBeInTheDocument();
    expect(within(transit).getByText("Departed origin facility")).toBeInTheDocument();
  });

  it("highlights the event that the current status comes from", () => {
    render(<Timeline events={EVENTS} currentEventId="delivered" />);

    const [delivered, hub] = screen.getAllByRole("listitem");
    expect(delivered).toHaveAttribute("aria-current", "step");
    expect(hub).not.toHaveAttribute("aria-current");
  });

  it("explains an empty timeline", () => {
    render(<Timeline events={[]} />);

    expect(screen.getByText(/No tracking events yet/)).toBeInTheDocument();
    expect(screen.queryByRole("list")).not.toBeInTheDocument();
  });
});

describe("AutoRefresh", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    refresh.mockClear();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  function setVisibility(state: "visible" | "hidden") {
    Object.defineProperty(document, "visibilityState", { configurable: true, value: state });
  }

  it("refreshes the page data on the interval while the tab is visible", () => {
    setVisibility("visible");
    render(<AutoRefresh intervalMs={5_000} />);

    act(() => vi.advanceTimersByTime(4_999));
    expect(refresh).not.toHaveBeenCalled();

    act(() => vi.advanceTimersByTime(1));
    expect(refresh).toHaveBeenCalledTimes(1);

    act(() => vi.advanceTimersByTime(10_000));
    expect(refresh).toHaveBeenCalledTimes(3);
  });

  it("does not refresh while the tab is in the background", () => {
    setVisibility("hidden");
    render(<AutoRefresh intervalMs={5_000} />);

    act(() => vi.advanceTimersByTime(30_000));

    expect(refresh).not.toHaveBeenCalled();
    setVisibility("visible");
  });

  it("stops when it is removed from the page", () => {
    setVisibility("visible");
    const { unmount } = render(<AutoRefresh intervalMs={5_000} />);

    unmount();
    act(() => vi.advanceTimersByTime(30_000));

    expect(refresh).not.toHaveBeenCalled();
  });
});
