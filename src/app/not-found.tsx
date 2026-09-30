import Link from "next/link";

export default function NotFound() {
  return (
    <div className="card stack-small">
      <h1>Not found</h1>
      <p className="muted">There is nothing at this address.</p>
      <p>
        <Link href="/">Track a parcel</Link> or <Link href="/shipments">see all shipments</Link>.
      </p>
    </div>
  );
}
