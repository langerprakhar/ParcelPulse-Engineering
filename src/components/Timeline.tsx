import { LocalTime } from "@/components/LocalTime";
import { formatLocation, statusLabel } from "@/lib/format";
import type { TrackingEvent } from "@/lib/types";

/**
 * The shipment's history, in the order given (the page asks the API for newest
 * first, ordered by the carrier's event time).
 *
 * Every entry shows both when the event happened and when ParcelPulse received
 * it, and marks events that were delivered late.
 */
export function Timeline({
  events,
  currentEventId,
}: {
  events: TrackingEvent[];
  /** The event the shipment's current status comes from. */
  currentEventId?: string;
}) {
  if (events.length === 0) {
    return (
      <p className="empty">
        No tracking events yet. They appear here as soon as the carrier reports them.
      </p>
    );
  }

  return (
    <ol className="timeline">
      {events.map((event) => {
        const location = formatLocation(event.location);
        const isCurrent = event.id === currentEventId;
        return (
          <li
            key={event.id}
            className={isCurrent ? "timeline-item timeline-item-current" : "timeline-item"}
            aria-current={isCurrent ? "step" : undefined}
          >
            <span className="timeline-dot" aria-hidden="true" />
            <div className="timeline-head">
              <span className="timeline-title">{statusLabel(event.event_type)}</span>
              {event.arrived_out_of_order ? (
                <span
                  className="tag"
                  title="The carrier reported this after a later event had already arrived."
                >
                  Reported late
                </span>
              ) : null}
            </div>
            {event.description ? <div>{event.description}</div> : null}
            {location ? <div className="timeline-meta">{location}</div> : null}
            <div className="timeline-meta">
              <LocalTime iso={event.event_at} />
              {" · received "}
              <LocalTime iso={event.received_at} />
            </div>
          </li>
        );
      })}
    </ol>
  );
}
