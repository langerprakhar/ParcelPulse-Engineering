import packageJson from "../../../../package.json";

export const dynamic = "force-dynamic";

/** Liveness: the web server is up. Does not touch the API. */
export function GET() {
  return Response.json({
    status: "ok",
    service: "parcelpulse-web",
    version: packageJson.version,
  });
}
