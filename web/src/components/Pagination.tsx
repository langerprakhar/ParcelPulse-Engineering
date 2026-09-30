import Link from "next/link";

import type { PageWindow } from "@/lib/pagination";

/**
 * Previous/next links for a paged list. `hrefFor` builds the URL of a page so the
 * caller keeps control of any filters in the query string.
 */
export function Pagination({
  range,
  hrefFor,
  noun,
}: {
  range: PageWindow;
  hrefFor: (page: number) => string;
  noun: string;
}) {
  return (
    <nav className="pagination" aria-label="Pagination">
      <span>
        {range.last === 0
          ? `No ${noun} on this page`
          : `Showing ${range.first}–${range.last} of ${range.total} ${noun}`}
      </span>
      <span className="row">
        {range.hasPrevious ? (
          <Link
            className="button button-secondary button-small"
            href={hrefFor(Math.min(range.page - 1, range.pageCount))}
            rel="prev"
          >
            Previous
          </Link>
        ) : null}
        {range.hasNext ? (
          <Link
            className="button button-secondary button-small"
            href={hrefFor(range.page + 1)}
            rel="next"
          >
            Next
          </Link>
        ) : null}
      </span>
    </nav>
  );
}
