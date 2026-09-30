"use client"; // Error boundaries must be Client Components

import { useEffect } from "react";

export default function ErrorPage({
  error,
  retry,
}: {
  error: Error & { digest?: string };
  retry: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="card stack-small" role="alert">
      <h1>Something went wrong</h1>
      <p className="muted">
        ParcelPulse could not load this page. The tracking service may be unavailable.
      </p>
      {error.digest ? <p className="small muted">Reference: {error.digest}</p> : null}
      <div>
        <button type="button" className="button" onClick={() => retry()}>
          Try again
        </button>
      </div>
    </div>
  );
}
