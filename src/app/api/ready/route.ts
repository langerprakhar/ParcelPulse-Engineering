import { apiBaseUrl } from "@/lib/config";

export const dynamic = "force-dynamic";

/**
 * Readiness: the web server can reach the API, and the API reports itself ready.
 * Returns 503 with the reason otherwise, without exposing internal addresses.
 */
export async function GET() {
  let api: "ok" | "not_ready" | "unreachable";
  try {
    const response = await fetch(`${apiBaseUrl()}/ready`, {
      cache: "no-store",
      signal: AbortSignal.timeout(3_000),
    });
    api = response.ok ? "ok" : "not_ready";
  } catch {
    api = "unreachable";
  }

  return Response.json(
    { status: api === "ok" ? "ready" : "not_ready", checks: { api } },
    { status: api === "ok" ? 200 : 503 },
  );
}
