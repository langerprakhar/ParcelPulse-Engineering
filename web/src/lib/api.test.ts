// @vitest-environment node
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  ApiUnavailableError,
  createShipment,
  getShipment,
  getShipmentByTrackingNumber,
  isApiError,
  listEvents,
  listShipments,
  saveNotificationPreference,
} from "./api";

const fetchMock = vi.fn<typeof fetch>();

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
    ...init,
  });
}

/** A Response body can only be read once, so every call gets a fresh one. */
function respondWith(body: unknown, init: ResponseInit = {}): void {
  fetchMock.mockImplementation(async () => jsonResponse(body, init));
}

function lastRequest(): { url: string; init: RequestInit } {
  const [url, init] = fetchMock.mock.calls.at(-1)!;
  return { url: String(url), init: init ?? {} };
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  vi.stubEnv("API_BASE_URL", "http://api.test:8000/");
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("requests", () => {
  it("reads from the configured API without caching", async () => {
    respondWith({ id: "abc" });

    await getShipment("abc");

    const { url, init } = lastRequest();
    expect(url).toBe("http://api.test:8000/shipments/abc");
    expect(init.method).toBe("GET");
    expect(init.cache).toBe("no-store");
    expect(init.body).toBeUndefined();
  });

  it("builds list queries from the options that are set", async () => {
    respondWith({ items: [], total: 0, limit: 10, offset: 20 });

    await listShipments({ limit: 10, offset: 20, status: "DELIVERED" });
    expect(lastRequest().url).toBe(
      "http://api.test:8000/shipments?limit=10&offset=20&status=DELIVERED",
    );

    await listShipments();
    expect(lastRequest().url).toBe("http://api.test:8000/shipments");
  });

  it("requests the timeline in the order asked for", async () => {
    respondWith({ items: [], total: 0, limit: 100, offset: 0 });

    await listEvents("abc", { order: "desc", limit: 100 });

    const url = new URL(lastRequest().url);
    expect(url.pathname).toBe("/shipments/abc/events");
    expect(Object.fromEntries(url.searchParams)).toEqual({ order: "desc", limit: "100" });
  });

  it("escapes values placed in the path", async () => {
    respondWith({ id: "abc" });

    await getShipmentByTrackingNumber("SC 123/../x", "simcarrier");

    expect(lastRequest().url).toBe(
      "http://api.test:8000/shipments/by-tracking/SC%20123%2F..%2Fx?carrier=simcarrier",
    );
  });

  it("sends JSON bodies for writes", async () => {
    respondWith({ id: "abc" }, { status: 201 });

    await createShipment({ tracking_number: "SC4F7K2M9Q1X", carrier: "simcarrier" });

    const { url, init } = lastRequest();
    expect(url).toBe("http://api.test:8000/shipments");
    expect(init.method).toBe("POST");
    expect((init.headers as Record<string, string>)["Content-Type"]).toBe("application/json");
    expect(JSON.parse(init.body as string)).toEqual({
      tracking_number: "SC4F7K2M9Q1X",
      carrier: "simcarrier",
    });
  });

  it("replaces notification preferences with PUT", async () => {
    respondWith({ shipment_id: "abc" });

    await saveNotificationPreference("abc", {
      email: null,
      notify_out_for_delivery: true,
      notify_delivered: false,
      notify_delivery_exception: true,
    });

    const { url, init } = lastRequest();
    expect(url).toBe("http://api.test:8000/shipments/abc/notification-preferences");
    expect(init.method).toBe("PUT");
    expect(JSON.parse(init.body as string).email).toBeNull();
  });
});

describe("errors", () => {
  it("turns the API error envelope into an ApiError", async () => {
    respondWith(
      {
        error: {
          code: "shipment_already_exists",
          message: "Shipment SC4F7K2M9Q1X is already tracked",
          details: { shipment_id: "existing-id" },
        },
        correlation_id: "corr-1",
      },
      { status: 409 },
    );

    const error = await createShipment({
      tracking_number: "SC4F7K2M9Q1X",
      carrier: "simcarrier",
    }).catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(ApiError);
    expect(isApiError(error, "shipment_already_exists")).toBe(true);
    expect(isApiError(error, "shipment_not_found")).toBe(false);
    const apiError = error as ApiError;
    expect(apiError.status).toBe(409);
    expect(apiError.details).toEqual({ shipment_id: "existing-id" });
    expect(apiError.correlationId).toBe("corr-1");
  });

  it("copes with an error response that is not JSON", async () => {
    fetchMock.mockResolvedValue(
      new Response("<html>Bad gateway</html>", {
        status: 502,
        headers: { "X-Correlation-ID": "from-header" },
      }),
    );

    const error = (await getShipment("abc").catch((caught: unknown) => caught)) as ApiError;

    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(502);
    expect(error.code).toBe("http_error");
    expect(error.correlationId).toBe("from-header");
  });

  it("reports an unreachable API as ApiUnavailableError", async () => {
    fetchMock.mockRejectedValue(new TypeError("fetch failed"));

    const error = await getShipment("abc").catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(ApiUnavailableError);
    expect(isApiError(error)).toBe(false);
  });
});
