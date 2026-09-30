/** Reads a 1-based page number from a query string value; anything unusable becomes 1. */
export function parsePage(value: string | string[] | undefined): number {
  const text = Array.isArray(value) ? value[0] : value;
  const page = Number.parseInt(text ?? "", 10);
  return Number.isFinite(page) && page >= 1 ? page : 1;
}

export interface PageWindow {
  page: number;
  pageCount: number;
  /** 1-based positions of the first and last item shown; both 0 when there are none. */
  first: number;
  last: number;
  total: number;
  hasPrevious: boolean;
  hasNext: boolean;
}

export function pageWindow(total: number, page: number, pageSize: number): PageWindow {
  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  const first = total === 0 ? 0 : (page - 1) * pageSize + 1;
  return {
    page,
    pageCount,
    first: first > total ? 0 : first,
    last: first > total ? 0 : Math.min(total, page * pageSize),
    total,
    hasPrevious: page > 1,
    hasNext: page < pageCount,
  };
}
