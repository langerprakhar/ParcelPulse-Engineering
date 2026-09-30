"use client";

import { useSyncExternalStore } from "react";

import { formatUtc } from "@/lib/format";

const LOCAL_FORMAT: Intl.DateTimeFormatOptions = {
  day: "2-digit",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  timeZoneName: "short",
};

const subscribeToNothing = () => () => {};

/**
 * Shows a timestamp in the viewer's own time zone.
 *
 * The server cannot know that time zone, so it (and the first client render)
 * shows UTC; once hydrated, the text switches to local time. The UTC value
 * stays available as the tooltip.
 */
export function LocalTime({ iso }: { iso: string }) {
  const hydrated = useSyncExternalStore(
    subscribeToNothing,
    () => true,
    () => false,
  );
  const utc = formatUtc(iso);
  const date = new Date(iso);
  const text =
    hydrated && !Number.isNaN(date.getTime())
      ? new Intl.DateTimeFormat(undefined, LOCAL_FORMAT).format(date)
      : utc;

  return (
    <time dateTime={iso} title={utc}>
      {text}
    </time>
  );
}
